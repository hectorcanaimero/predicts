"""Clientes de IA: Jev (decisiones, `TypeSafeClient`) y 9router (texto y embeddings, `ChatOpenAI`
y HTTP), con contador de costo (NFR-3). Ver docs/arch/001-predicts.md#jev.

Patrones de referencia: `/mnt/storage/project/apolicies/src/apolicies/llm.py` (`estruturar`) y
`juez_jev.py` (`system_one`). Gotchas de 9router:
`/mnt/storage/project/agndaZAP/docs/notas/2026-09-23-9router-gotchas.md` (`/v1/embeddings` solo
acepta ids directos, no combos).
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

import httpx
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session
from typesafe_sdk import (
    Choice,
    ChoiceAnswer,
    Noul,
    NoulAnswer,
    Question,
    SystemOneResponse,
    TypeSafeClient,
)

from predicts.config import Settings, settings
from predicts.db.modelos import DecisionJev


class Decision(BaseModel):
    """Resultado de una decisión de Jev: opción elegida, confianza (0 a 1) y la respuesta cruda."""

    opcion: str
    confianza: float
    crudo: dict[str, Any]


def cliente_jev(configuracion: Settings | None = None) -> TypeSafeClient:
    cfg = configuracion or settings()
    return TypeSafeClient(api_key=cfg.TYPESAFE_API_KEY, model=cfg.TYPESAFE_MODEL)


def llm_texto(configuracion: Settings | None = None) -> ChatOpenAI:
    cfg = configuracion or settings()
    return ChatOpenAI(
        base_url=cfg.ROUTER_BASE_URL,
        api_key=cfg.ROUTER_API_KEY,
        model=cfg.ROUTER_MODEL,
        timeout=120,
        # Único nivel de reintento (conexión, 429, 5xx); `generar` solo reintenta JSON inválido.
        max_retries=2,
        streaming=False,
    )


# Precios estimados en USD por 1000 tokens, por proveedor. Placeholder: ajustar con los precios
# reales de 9router (dependen del modelo detrás del combo en ROUTER_MODEL) y de Jev cuando el
# plan de TypeSafe los publique.
PRECIOS_USD_POR_1K_TOKENS: dict[str, dict[str, float]] = {
    "jev": {"entrada": 0.0, "salida": 0.0},
    "9router": {"entrada": 0.0005, "salida": 0.0015},
    "embeddings": {"entrada": 0.0001, "salida": 0.0},
}


class Contador:
    """Contador thread-safe de llamadas, tokens de entrada/salida y costo estimado por proveedor."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._llamadas: dict[str, int] = {}
        self._tokens: dict[str, dict[str, int]] = {}

    def _registrar(self, proveedor: str, entrada: int, salida: int) -> None:
        with self._lock:
            self._llamadas[proveedor] = self._llamadas.get(proveedor, 0) + 1
            tokens = self._tokens.setdefault(proveedor, {"entrada": 0, "salida": 0})
            tokens["entrada"] += entrada
            tokens["salida"] += salida

    def registrar_jev(self, respuesta: SystemOneResponse) -> None:
        uso = respuesta.usage
        self._registrar("jev", uso.input_tokens or 0, uso.output_tokens or 0)

    def registrar_llm(self, mensaje: AIMessage) -> None:
        uso = mensaje.usage_metadata or {}
        self._registrar("9router", uso.get("input_tokens", 0), uso.get("output_tokens", 0))

    def registrar_embeddings(self, tokens_entrada: int) -> None:
        self._registrar("embeddings", tokens_entrada, 0)

    def _costo_estimado(self) -> float:
        total = 0.0
        for proveedor, tokens in self._tokens.items():
            precios = PRECIOS_USD_POR_1K_TOKENS.get(proveedor, {"entrada": 0.0, "salida": 0.0})
            total += tokens["entrada"] / 1000 * precios["entrada"]
            total += tokens["salida"] / 1000 * precios["salida"]
        return total

    def costo_estimado(self) -> float:
        with self._lock:
            return self._costo_estimado()

    def resumen(self) -> dict[str, Any]:
        with self._lock:
            return {
                "llamadas": dict(self._llamadas),
                "tokens": {proveedor: dict(t) for proveedor, t in self._tokens.items()},
                "costo_estimado_usd": self._costo_estimado(),
            }


def _decision_desde_choice(respuesta: ChoiceAnswer) -> Decision:
    return Decision(
        opcion=respuesta.choice, confianza=respuesta.confidence, crudo=respuesta.model_dump()
    )


def _decision_desde_noul(respuesta: NoulAnswer) -> Decision:
    opcion = "si" if respuesta.noul >= 0.5 else "no"
    confianza = respuesta.noul if opcion == "si" else 1 - respuesta.noul
    return Decision(opcion=opcion, confianza=confianza, crudo=respuesta.model_dump())


def decidir_choice(
    pregunta: str,
    opciones: Mapping[str, str],
    contexto: dict,
    cliente: TypeSafeClient | None = None,
    contador: Contador | None = None,
) -> Decision:
    cliente = cliente or cliente_jev()
    pregunta_choice = Choice(instructions=pregunta, criteria=opciones)
    respuesta = cliente.system_one(contexto, {"respuesta": pregunta_choice})
    if contador is not None:
        contador.registrar_jev(respuesta)
    return _decision_desde_choice(respuesta.choices["respuesta"])


def decidir_si_no(
    pregunta: str,
    contexto: dict,
    cliente: TypeSafeClient | None = None,
    contador: Contador | None = None,
) -> Decision:
    cliente = cliente or cliente_jev()
    respuesta = cliente.system_one(contexto, {"respuesta": Noul(instructions=pregunta)})
    if contador is not None:
        contador.registrar_jev(respuesta)
    return _decision_desde_noul(respuesta.nouls["respuesta"])


def decidir_lote(
    contexto: dict,
    preguntas: Mapping[str, Question],
    cliente: TypeSafeClient | None = None,
    contador: Contador | None = None,
) -> dict[str, Decision]:
    """Una sola llamada a `system_one` con varias preguntas (`Choice` o `Noul`), por nombre."""
    cliente = cliente or cliente_jev()
    respuesta = cliente.system_one(contexto, preguntas)
    if contador is not None:
        contador.registrar_jev(respuesta)

    decisiones: dict[str, Decision] = {}
    for nombre in preguntas:
        contestada = respuesta.answers[nombre]
        if isinstance(contestada, ChoiceAnswer):
            decisiones[nombre] = _decision_desde_choice(contestada)
        elif isinstance(contestada, NoulAnswer):
            decisiones[nombre] = _decision_desde_noul(contestada)
        else:
            raise ValueError(f"Tipo de respuesta no soportado para '{nombre}': {contestada}")
    return decisiones


def registrar_decision(
    db: Session,
    empresa_id: uuid.UUID,
    tipo: str,
    referencia: uuid.UUID,
    entrada_resumida: dict | None,
    decision: Decision,
) -> DecisionJev:
    """Persiste una `Decision` de Jev en `decisiones_jev`. `referencia` es el id del objeto
    decidido (p. ej. el producto o la columna del dataset), según `tipo`."""
    fila = DecisionJev(
        empresa_id=empresa_id,
        tipo=tipo,
        referencia=referencia,
        entrada_resumida=entrada_resumida,
        opcion=decision.opcion,
        confianza=decision.confianza,
    )
    db.add(fila)
    db.flush()
    return fila


# Salida estructurada sin tool_choice forzado (ver D9 en apolicies): el combo detrás de 9router
# puede no soportar tool_choice forzado de forma confiable, así que el esquema va en el prompt y
# la respuesta es JSON en texto.
INSTRUCCION_JSON = """Responde SOLO con un objeto JSON válido (compacto, sin indentación) que siga
este JSON Schema. No escribas nada fuera del JSON.

{esquema}"""

_BLOQUE_JSON = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _texto(mensaje: AIMessage) -> str:
    if isinstance(mensaje.content, str):
        return mensaje.content
    return "".join(
        parte if isinstance(parte, str) else parte.get("text", "")
        for parte in mensaje.content
        if isinstance(parte, str) or parte.get("type") == "text"
    )


def _extraer_json(texto: str) -> str:
    """JSON de la respuesta: bloque ```json``` si lo hay, si no del primer `{` al último `}`."""
    if bloque := _BLOQUE_JSON.search(texto):
        return bloque.group(1).strip()
    inicio, fin = texto.find("{"), texto.rfind("}")
    return texto[inicio : fin + 1] if inicio != -1 else texto


def generar[T: BaseModel](
    prompt: str,
    esquema: type[T],
    llm: ChatOpenAI | None = None,
    contador: Contador | None = None,
    intentos: int = 3,
) -> T:
    """Genera `esquema` a partir de `prompt` vía 9router, con hasta `intentos - 1` reintentos
    cuando la salida no valida contra el esquema."""
    llm = llm or llm_texto()
    esquema_json = json.dumps(
        esquema.model_json_schema(), ensure_ascii=False, separators=(",", ":")
    )
    mensajes: list[BaseMessage] = [
        SystemMessage(INSTRUCCION_JSON.format(esquema=esquema_json)),
        HumanMessage(prompt),
    ]
    error_str = ""
    for intento in range(1, intentos + 1):
        respuesta = llm.invoke(mensajes)
        if contador is not None:
            contador.registrar_llm(respuesta)
        texto = _texto(respuesta)
        try:
            return esquema.model_validate_json(_extraer_json(texto))
        except ValidationError as error:
            error_str = str(error)
        if intento < intentos:
            mensajes += [
                AIMessage(texto),
                HumanMessage(
                    f"La respuesta anterior no pasó la validación: {error_str}\n"
                    f"Responde de nuevo solo con el JSON de {esquema.__name__}, con datos válidos."
                ),
            ]
    raise ValueError(f"Salida inválida del modelo para {esquema.__name__}: {error_str}")


def _url_embeddings(router_base_url: str) -> str:
    base = router_base_url.rstrip("/")
    if not base.endswith("/v1"):
        base += "/v1"
    return f"{base}/embeddings"


def embeddings(
    textos: Sequence[str],
    configuracion: Settings | None = None,
    cliente: httpx.Client | None = None,
    contador: Contador | None = None,
    tamano_lote: int = 100,
) -> list[list[float]]:
    """Embeddings de `textos` contra `/v1/embeddings` de 9router, en lotes de `tamano_lote`."""
    cfg = configuracion or settings()
    url = _url_embeddings(cfg.ROUTER_BASE_URL)
    propio = cliente is None
    cliente = cliente or httpx.Client(timeout=120)
    try:
        vectores: list[list[float]] = []
        textos_lista = list(textos)
        for inicio in range(0, len(textos_lista), tamano_lote):
            lote = textos_lista[inicio : inicio + tamano_lote]
            respuesta = cliente.post(
                url,
                headers={"Authorization": f"Bearer {cfg.ROUTER_API_KEY}"},
                json={"model": cfg.ROUTER_EMBEDDINGS_MODEL, "input": lote},
            )
            respuesta.raise_for_status()
            cuerpo = respuesta.json()
            vectores.extend(dato["embedding"] for dato in cuerpo["data"])
            if contador is not None:
                contador.registrar_embeddings(cuerpo.get("usage", {}).get("prompt_tokens", 0))
        return vectores
    finally:
        if propio:
            cliente.close()
