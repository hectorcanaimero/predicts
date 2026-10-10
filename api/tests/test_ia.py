"""Tests de `predicts.ia` con clientes falsos (sin red): Jev, 9router, embeddings, el reintento
por JSON inválido, el contador y el registro en `decisiones_jev`."""

from __future__ import annotations

import threading
import uuid

import pytest
from langchain_core.messages import AIMessage
from pydantic import BaseModel
from typesafe_sdk import ChoiceAnswer, NoulAnswer, SystemOneResponse, Usage

from predicts.config import settings_para_tests
from predicts.db.modelos import DecisionJev, Empresa
from predicts.ia import (
    Contador,
    Decision,
    decidir_choice,
    decidir_lote,
    decidir_si_no,
    embeddings,
    generar,
    registrar_decision,
)


class ClienteJevFalso:
    """Devuelve una `SystemOneResponse` fija y guarda las llamadas para inspección."""

    def __init__(self, respuestas: dict[str, object], tokens: tuple[int, int] = (10, 2)) -> None:
        self._respuestas = respuestas
        self._tokens = tokens
        self.llamadas: list[tuple[object, object]] = []

    def system_one(self, state, questions):
        self.llamadas.append((state, questions))
        return SystemOneResponse(
            model="jev-test",
            usage=Usage(input_tokens=self._tokens[0], output_tokens=self._tokens[1]),
            answers=dict(self._respuestas),
        )


def test_decidir_choice() -> None:
    probabilidades = {"categoria_a": 0.91, "categoria_b": 0.09}
    respuesta = ChoiceAnswer(choice="categoria_a", confidence=0.91, probabilities=probabilidades)
    cliente = ClienteJevFalso({"respuesta": respuesta})
    contador = Contador()

    decision = decidir_choice(
        "¿Qué categoría es?", {"categoria_a": "...", "categoria_b": "..."}, {"nombre": "producto"},
        cliente=cliente, contador=contador,
    )

    assert decision == Decision(opcion="categoria_a", confianza=0.91, crudo=respuesta.model_dump())
    assert len(cliente.llamadas) == 1
    assert contador.resumen()["llamadas"] == {"jev": 1}
    assert contador.resumen()["tokens"]["jev"] == {"entrada": 10, "salida": 2}


@pytest.mark.parametrize(
    ("noul", "opcion_esperada", "confianza_esperada"),
    [(0.95, "si", 0.95), (0.1, "no", 0.9), (0.5, "si", 0.5)],
)
def test_decidir_si_no(noul: float, opcion_esperada: str, confianza_esperada: float) -> None:
    respuesta = NoulAnswer(noul=noul)
    cliente = ClienteJevFalso({"respuesta": respuesta})

    decision = decidir_si_no("¿Es recompra?", {"producto": "leche"}, cliente=cliente)

    assert decision.opcion == opcion_esperada
    assert decision.confianza == pytest.approx(confianza_esperada)


def test_decidir_lote_una_sola_llamada_con_varias_preguntas() -> None:
    probabilidades = {"recompra": 0.8, "durable": 0.2}
    respuesta_tipo = ChoiceAnswer(choice="recompra", confidence=0.8, probabilities=probabilidades)
    respuestas = {"tipo_producto": respuesta_tipo, "contactar": NoulAnswer(noul=0.2)}
    cliente = ClienteJevFalso(respuestas)

    # el cliente falso no mira las preguntas, solo cuántas veces se llama a system_one
    preguntas = {"tipo_producto": object(), "contactar": object()}
    decisiones = decidir_lote({"producto": "leche"}, preguntas, cliente=cliente)

    assert len(cliente.llamadas) == 1, "decidir_lote debe hacer una sola llamada"
    assert decisiones["tipo_producto"] == Decision(
        opcion="recompra", confianza=0.8, crudo=respuestas["tipo_producto"].model_dump()
    )
    assert decisiones["contactar"].opcion == "no"


class _Esquema(BaseModel):
    categoria: str
    confianza: float


def _mensaje_ia(texto: str) -> AIMessage:
    return AIMessage(
        content=texto,
        usage_metadata={"input_tokens": 20, "output_tokens": 5, "total_tokens": 25},
        response_metadata={"model_name": "router-test"},
    )


class LlmFalso:
    """Devuelve los mensajes de `respuestas` en orden, una por llamada a `invoke`."""

    def __init__(self, respuestas: list[str]) -> None:
        self._respuestas = [_mensaje_ia(r) for r in respuestas]
        self.llamadas = 0

    def invoke(self, mensajes):
        mensaje = self._respuestas[self.llamadas]
        self.llamadas += 1
        return mensaje


def test_generar_valida_json_al_primer_intento() -> None:
    llm = LlmFalso(['{"categoria": "lacteos", "confianza": 0.9}'])
    contador = Contador()

    resultado = generar("clasifica el producto", _Esquema, llm=llm, contador=contador)

    assert resultado == _Esquema(categoria="lacteos", confianza=0.9)
    assert llm.llamadas == 1
    assert contador.resumen()["llamadas"]["9router"] == 1


def test_generar_reintenta_tras_json_invalido() -> None:
    llm = LlmFalso(["esto no es json", '{"categoria": "lacteos", "confianza": 0.9}'])

    resultado = generar("clasifica el producto", _Esquema, llm=llm, intentos=3)

    assert resultado.categoria == "lacteos"
    assert llm.llamadas == 2


def test_generar_falla_tras_agotar_los_intentos() -> None:
    llm = LlmFalso(["no json", "sigue sin ser json"])

    with pytest.raises(ValueError, match="Salida inválida"):
        generar("clasifica el producto", _Esquema, llm=llm, intentos=2)

    assert llm.llamadas == 2


def test_generar_extrae_json_de_bloque_markdown() -> None:
    llm = LlmFalso(['Aquí está:\n```json\n{"categoria": "lacteos", "confianza": 0.5}\n```'])

    resultado = generar("clasifica", _Esquema, llm=llm)

    assert resultado.categoria == "lacteos"


class ClienteEmbeddingsFalso:
    def __init__(self, dimension: int = 3) -> None:
        self._dimension = dimension
        self.llamadas: list[dict] = []

    def post(self, url, headers=None, json=None):
        self.llamadas.append({"url": url, "headers": headers, "json": json})
        entradas = json["input"]
        return _RespuestaEmbeddingsFalsa(
            {
                "data": [{"embedding": [float(i)] * self._dimension} for i in range(len(entradas))],
                "usage": {"prompt_tokens": sum(len(t) for t in entradas)},
            }
        )


class _RespuestaEmbeddingsFalsa:
    def __init__(self, cuerpo: dict) -> None:
        self._cuerpo = cuerpo

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._cuerpo


def test_embeddings_en_lotes() -> None:
    cliente = ClienteEmbeddingsFalso(dimension=2)
    contador = Contador()

    vectores = embeddings(
        ["a", "bb", "ccc"],
        configuracion=settings_para_tests(),
        cliente=cliente,
        contador=contador,
        tamano_lote=2,
    )

    assert len(vectores) == 3
    assert len(cliente.llamadas) == 2, "3 textos con lote de 2 deben hacer 2 llamadas"
    assert cliente.llamadas[0]["json"]["input"] == ["a", "bb"]
    assert cliente.llamadas[1]["json"]["input"] == ["ccc"]
    assert contador.resumen()["llamadas"]["embeddings"] == 2


def test_embeddings_url_termina_en_v1_embeddings() -> None:
    cliente = ClienteEmbeddingsFalso()
    embeddings(["a"], configuracion=settings_para_tests(), cliente=cliente)
    assert cliente.llamadas[0]["url"].endswith("/v1/embeddings")


def test_contador_resumen_y_costo_estimado() -> None:
    contador = Contador()
    uso = Usage(input_tokens=100, output_tokens=10)
    contador.registrar_jev(SystemOneResponse(model="jev", usage=uso, answers={}))
    contador.registrar_llm(_mensaje_ia("hola"))
    contador.registrar_embeddings(50)

    resumen = contador.resumen()
    assert resumen["llamadas"] == {"jev": 1, "9router": 1, "embeddings": 1}
    assert resumen["tokens"]["9router"] == {"entrada": 20, "salida": 5}
    assert resumen["costo_estimado_usd"] == pytest.approx(contador.costo_estimado())
    assert contador.costo_estimado() > 0


def test_contador_es_thread_safe() -> None:
    contador = Contador()

    def registrar() -> None:
        for _ in range(100):
            contador.registrar_llm(_mensaje_ia("x"))

    hilos = [threading.Thread(target=registrar) for _ in range(8)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    resumen = contador.resumen()
    assert resumen["llamadas"]["9router"] == 800
    assert resumen["tokens"]["9router"]["entrada"] == 800 * 20


@pytest.mark.db
def test_registrar_decision_guarda_en_decisiones_jev(db) -> None:
    empresa = Empresa(nombre="Acme")
    db.add(empresa)
    db.flush()

    referencia = uuid.uuid4()
    crudo = {"choice": "recompra", "confidence": 0.82}
    decision = Decision(opcion="recompra", confianza=0.82, crudo=crudo)

    fila = registrar_decision(
        db, empresa.id, "tipo_producto", referencia, {"nombre": "leche"}, decision
    )
    db.commit()

    guardada = db.get(DecisionJev, fila.id)
    assert guardada is not None
    assert guardada.empresa_id == empresa.id
    assert guardada.tipo == "tipo_producto"
    assert guardada.referencia == referencia
    assert guardada.opcion == "recompra"
    assert guardada.confianza == pytest.approx(0.82)
    assert guardada.entrada_resumida == {"nombre": "leche"}
