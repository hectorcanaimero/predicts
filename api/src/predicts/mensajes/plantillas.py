"""Genera plantillas de mensaje con el LLM (`ia.generar`), en lotes de hasta `TAMANO_LOTE`
combinaciones por llamada, y las cachea en `plantillas_mensaje`.

Una `Combinacion` es (clave base del producto/grupo/categoría, tipo, etiqueta legible); su
`clave` (`base::tipo`) es la clave de caché (junto con empresa, idioma y tono) y la clave que el
LLM usa en la respuesta. `generar_plantillas` solo le pide al LLM las combinaciones que no están
en caché (o, con `forzar=True`, las que no estén `editada`); una plantilla `editada` nunca se
regenera.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from predicts.db.modelos import PlantillaMensaje as PlantillaMensajeFila
from predicts.ia import Contador, generar
from predicts.mensajes.render import _MARCADOR, MARCADORES_PERMITIDOS

TAMANO_LOTE = 20

TIPOS = ("recordatorio", "oferta", "reactivacion")


@dataclass(frozen=True)
class Combinacion:
    """`base`: `producto:<id>` | `grupo:<id>` | `categoria:<nombre>` | `general`."""

    base: str
    tipo: str
    etiqueta: str

    @property
    def clave(self) -> str:
        return f"{self.base}::{self.tipo}"


class Texto(BaseModel):
    """Lo que el LLM debe devolver por combinación: ≤ 300 caracteres, solo marcadores permitidos."""

    texto: str

    @model_validator(mode="after")
    def _validar(self) -> Texto:
        if not self.texto.strip() or len(self.texto) > 300:
            raise ValueError("texto vacío o de más de 300 caracteres")
        desconocidos = set(_MARCADOR.findall(self.texto)) - MARCADORES_PERMITIDOS
        if desconocidos:
            raise ValueError(f"marcadores no permitidos: {sorted(desconocidos)}")
        return self


class _Lote(BaseModel):
    plantillas: dict[str, Texto]


_TEXTOS: dict[str, dict] = {
    "es": {
        "intro": (
            "Escribís los mensajes cortos que una tienda le manda a sus clientes. Cada mensaje "
            "debe sonar natural en español, tener como máximo 300 caracteres y usar el tono "
            "pedido."
        ),
        "reglas": (
            "Reglas: no inventes descuentos ni montos que no te dieron; no uses urgencia falsa "
            '("solo hoy", "últimas horas") si no viene en los datos; no menciones datos '
            "personales del cliente (nombre, email, teléfono, dirección)."
        ),
        "marcadores": (
            "Podés usar estos marcadores tal cual, sin inventar otros, y solo si el mensaje los "
            "necesita: {producto} (nombre del producto o categoría), {dias} (un plazo en días), "
            "{oferta} (un descuento, ya viene como porcentaje) y {nombre_tienda} (el nombre de "
            "la tienda)."
        ),
        "tono": {
            "cercano": 'Tono cercano, como un mensaje a un conocido: "¡Hola! Vimos que ya es '
            'hora de reponer {producto} 😊"',
            "neutro": 'Tono neutro, cordial sin ser informal: "Han pasado {dias} días desde tu '
            'última compra de {producto}."',
            "formal": 'Tono formal: "Le informamos que, según su historial, podría necesitar '
            'reponer {producto} en los próximos {dias} días."',
        },
        "tipos": {
            "recordatorio": "recordarle que probablemente le toca volver a comprar el producto",
            "oferta": "avisarle de una oferta en un producto que le puede interesar",
            "reactivacion": "invitarlo a volver a comprar, sin culpa ni desesperación",
        },
        "pide": "Generá un mensaje para cada una de estas combinaciones (la clave entre comillas "
        "es la que tenés que usar en la respuesta):",
        "regenera": "Esta plantilla se rechazó en la revisión anterior por: {motivo}. Corregila "
        "teniendo en cuenta ese motivo.",
    },
    "en": {
        "intro": (
            "You write the short messages a store sends its customers. Each message must sound "
            "natural in English, be at most 300 characters, and match the requested tone."
        ),
        "reglas": (
            "Rules: don't invent discounts or amounts you weren't given; don't use false "
            'urgency ("today only", "last hours") unless it came in the data; don\'t mention '
            "personal data about the customer (name, email, phone, address)."
        ),
        "marcadores": (
            "You may use these placeholders as-is, never invent others, and only if the message "
            "needs them: {producto} (product or category name), {dias} (a number of days), "
            "{oferta} (a discount, already given as a percentage) and {nombre_tienda} (the "
            "store's name)."
        ),
        "tono": {
            "cercano": "Friendly tone, like a message to an acquaintance: \"Hey! Looks like it's "
            'time to restock {producto} 😊"',
            "neutro": "Neutral, polite but not informal: \"It's been {dias} days since your "
            'last purchase of {producto}."',
            "formal": 'Formal tone: "We would like to inform you that, based on your history, '
            'you may need to restock {producto} within the next {dias} days."',
        },
        "tipos": {
            "recordatorio": "remind them they likely need to repurchase the product",
            "oferta": "let them know about an offer on a product they may like",
            "reactivacion": "invite them back, without guilt or desperation",
        },
        "pide": "Generate one message for each of these combinations (the quoted key is the one "
        "you must use in the response):",
        "regenera": "This template was rejected in the previous review because: {motivo}. Fix "
        "it taking that reason into account.",
    },
    "pt-BR": {
        "intro": (
            "Você escreve as mensagens curtas que uma loja manda para os clientes. Cada mensagem "
            "deve parecer natural em português do Brasil, ter no máximo 300 caracteres e usar o "
            "tom pedido."
        ),
        "reglas": (
            "Regras: não invente descontos ou valores que não te deram; não use urgência falsa "
            '("só hoje", "últimas horas") se não vier nos dados; não mencione dados pessoais do '
            "cliente (nome, e-mail, telefone, endereço)."
        ),
        "marcadores": (
            "Você pode usar estes marcadores assim como estão, sem inventar outros, e só se a "
            "mensagem precisar deles: {producto} (nome do produto ou categoria), {dias} (um "
            "prazo em dias), {oferta} (um desconto, já em porcentagem) e {nombre_tienda} (o nome "
            "da loja)."
        ),
        "tono": {
            "cercano": 'Tom próximo, como mensagem para um conhecido: "Oi! Vimos que já é hora '
            'de repor {producto} 😊"',
            "neutro": 'Tom neutro, cordial sem ser informal: "Já faz {dias} dias desde sua '
            'última compra de {producto}."',
            "formal": 'Tom formal: "Informamos que, de acordo com seu histórico, pode ser '
            'necessário repor {producto} nos próximos {dias} dias."',
        },
        "tipos": {
            "recordatorio": "lembrar que provavelmente é hora de comprar o produto de novo",
            "oferta": "avisar sobre uma oferta em um produto que pode interessar",
            "reactivacion": "convidar para voltar a comprar, sem culpa nem desespero",
        },
        "pide": "Gere uma mensagem para cada uma destas combinações (a chave entre aspas é a que "
        "você deve usar na resposta):",
        "regenera": "Esta plantilla foi rejeitada na revisão anterior por: {motivo}. Corrija "
        "levando em conta esse motivo.",
    },
}


def _prompt(
    combos: Sequence[Combinacion], idioma: str, tono: str, motivos: Mapping[str, str]
) -> str:
    t = _TEXTOS[idioma]
    partes = [t["intro"], t["reglas"], t["marcadores"], t["tono"][tono], "", t["pide"]]
    for combo in combos:
        linea = f'- "{combo.clave}": {t["tipos"][combo.tipo]}. {combo.etiqueta}.'
        if motivo := motivos.get(combo.clave):
            linea += " " + t["regenera"].format(motivo=motivo)
        partes.append(linea)
    return "\n".join(partes)


def generar_lote(
    combos: Sequence[Combinacion],
    idioma: str,
    tono: str,
    llm: ChatOpenAI | None = None,
    contador: Contador | None = None,
    motivos: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Una sola llamada a `ia.generar` para hasta `TAMANO_LOTE` combinaciones; devuelve
    `clave → texto`. `motivos`: por qué se rechazó la versión anterior, si se está regenerando."""
    if not combos:
        return {}
    if len(combos) > TAMANO_LOTE:
        raise ValueError(f"máximo {TAMANO_LOTE} combinaciones por llamada, llegaron {len(combos)}")
    prompt = _prompt(combos, idioma, tono, motivos or {})
    lote = generar(prompt, _Lote, llm=llm, contador=contador)
    faltantes = {c.clave for c in combos} - lote.plantillas.keys()
    if faltantes:
        raise ValueError(f"el modelo no devolvió plantillas para: {sorted(faltantes)}")
    return {combo.clave: lote.plantillas[combo.clave].texto for combo in combos}


@dataclass(frozen=True)
class ResultadoGeneracion:
    filas: dict[str, PlantillaMensajeFila]
    nuevas: list[PlantillaMensajeFila]


def obtener_cacheadas(
    db: Session, empresa_id: uuid.UUID, idioma: str, tono: str, claves: Sequence[str]
) -> dict[str, PlantillaMensajeFila]:
    if not claves:
        return {}
    filas = db.scalars(
        select(PlantillaMensajeFila).where(
            PlantillaMensajeFila.empresa_id == empresa_id,
            PlantillaMensajeFila.idioma == idioma,
            PlantillaMensajeFila.tono == tono,
            PlantillaMensajeFila.clave.in_(claves),
        )
    ).all()
    return {f.clave: f for f in filas}


def generar_plantillas(
    db: Session,
    empresa_id: uuid.UUID,
    combos: Sequence[Combinacion],
    idioma: str,
    tono: str,
    *,
    llm: ChatOpenAI | None = None,
    contador: Contador | None = None,
    forzar: bool = False,
) -> ResultadoGeneracion:
    """Genera (o reusa de caché) una `PlantillaMensaje` por combinación de `combos`.

    Sin caché → se genera. Con `forzar=True`, además se regeneran las que no estén `editada`
    (una plantilla `editada` nunca se toca). Las nuevas/regeneradas quedan en `estado="ok"`,
    sin revisar todavía: eso lo hace `mensajes.revision`.
    """
    cacheadas = obtener_cacheadas(db, empresa_id, idioma, tono, [c.clave for c in combos])
    pendientes = [
        c
        for c in combos
        if c.clave not in cacheadas or (forzar and cacheadas[c.clave].estado != "editada")
    ]
    nuevas: list[PlantillaMensajeFila] = []
    for inicio in range(0, len(pendientes), TAMANO_LOTE):
        lote = pendientes[inicio : inicio + TAMANO_LOTE]
        textos = generar_lote(lote, idioma, tono, llm=llm, contador=contador)
        for combo in lote:
            fila = cacheadas.get(combo.clave)
            if fila is None:
                fila = PlantillaMensajeFila(
                    empresa_id=empresa_id, clave=combo.clave, idioma=idioma, tono=tono
                )
                db.add(fila)
            fila.tipo = combo.tipo
            fila.texto = textos[combo.clave]
            fila.estado = "ok"
            fila.motivo_revision = None
            cacheadas[combo.clave] = fila
            nuevas.append(fila)
    db.flush()
    filas = {c.clave: cacheadas[c.clave] for c in combos}
    return ResultadoGeneracion(filas=filas, nuevas=nuevas)
