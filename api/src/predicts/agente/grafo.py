"""Agente analista (FR-22): grafo LangGraph `modelo ⇄ herramientas` con el LLM de 9router.

Herramientas: `consultar_sql` (ver `agente/sql.py`; el esquema de las vistas con la descripción
de cada columna va en el prompt de sistema) y `describir_dataset` (esquema + tamaños). Como mucho
`MAX_CONSULTAS` consultas por pregunta (las rechazadas cuentan): al llegar al tope el modelo se
invoca sin herramientas y tiene que responder con lo que tiene. La respuesta final la pide en
JSON `{respuesta, advertencias}` en el idioma del usuario; las consultas salen del estado del
grafo (no del LLM), así los números que se muestran son los que realmente devolvió DuckDB.
"""

from __future__ import annotations

import json
import operator
from collections.abc import Sequence
from typing import Annotated, Any, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field, ValidationError

from predicts.agente.sql import MAX_FILAS, Conexion, ConsultaRechazada, consultar
from predicts.ia import Contador, _extraer_json, _texto, llm_texto

MAX_CONSULTAS = 6
# Turnos del modelo: las consultas más algunos `describir_dataset` / respuestas sin consulta.
MAX_TURNOS = MAX_CONSULTAS + 3
FILAS_MUESTRA = 20
FILAS_AL_LLM = 50

HERRAMIENTAS = [
    {
        "type": "function",
        "function": {
            "name": "consultar_sql",
            "description": (
                "Ejecuta UNA consulta SQL de DuckDB de solo lectura (SELECT o WITH) sobre las "
                f"vistas descritas en el prompt. Devuelve hasta {MAX_FILAS} filas en JSON."
            ),
            "parameters": {
                "type": "object",
                "properties": {"sql": {"type": "string", "description": "La consulta SQL."}},
                "required": ["sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "describir_dataset",
            "description": "Describe las vistas disponibles: columnas, filas y rango de fechas.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

SISTEMA = """Eres un analista de datos de compras de una tienda. Respondes preguntas sobre el \
dataset usando SOLO los datos que obtienes con la herramienta `consultar_sql` (DuckDB, solo \
lectura, una sentencia SELECT/WITH por llamada, como mucho {max_consultas} consultas).

Vistas disponibles:

{esquema}

Reglas:
- No inventes números: cada cifra de tu respuesta tiene que salir de una consulta.
- Si los datos no alcanzan para responder, dilo claramente y explica qué faltaría.
- Responde en el mismo idioma en que escribe el usuario.
- Cuando termines, responde SOLO con un JSON compacto:
  {{"respuesta": "<texto para el usuario>", "advertencias": ["<limitaciones o supuestos>"]}}"""


class Consulta(BaseModel):
    sql: str
    filas_muestra: list[dict[str, Any]]
    n_filas: int


class Respuesta(BaseModel):
    respuesta: str
    consultas: list[Consulta] = Field(default_factory=list)
    advertencias: list[str] = Field(default_factory=list)


class _Final(BaseModel):
    respuesta: str
    advertencias: list[str] = Field(default_factory=list)


class Estado(TypedDict):
    mensajes: Annotated[list[BaseMessage], add_messages]
    consultas: Annotated[list[Consulta], operator.add]
    advertencias: Annotated[list[str], operator.add]
    intentos: int
    turnos: int
    final: bool


def describir(conexion: Conexion) -> str:
    """Esquema de las vistas + filas por vista y rango de fechas de `compras`."""
    con = conexion.con
    filas = {v: con.execute(f"SELECT count(*) FROM {v}").fetchone()[0] for v in conexion.vistas}
    desde, hasta, clientes, productos = con.execute(
        "SELECT CAST(min(fecha) AS DATE), CAST(max(fecha) AS DATE), count(DISTINCT cliente_id), "
        "count(DISTINCT producto_id) FROM compras"
    ).fetchone()
    analisis = f"análisis {conexion.analisis_id}" if conexion.analisis_id else "sin análisis"
    return (
        f"{conexion.esquema}\n\nFilas por vista: {json.dumps(filas)}\n"
        f"compras: del {desde} al {hasta}, {clientes} clientes, {productos} productos.\n"
        f"Resultados: {analisis}."
    )


def _final(texto: str) -> _Final:
    try:
        return _Final.model_validate_json(_extraer_json(texto))
    except ValidationError:
        return _Final(respuesta=texto.strip())


def preguntar(
    conexion: Conexion,
    pregunta: str,
    historial: Sequence[BaseMessage] = (),
    llm: BaseChatModel | None = None,
    contador: Contador | None = None,
) -> Respuesta:
    """Responde `pregunta` sobre las vistas de `conexion` (ver el docstring del módulo).

    `historial`: mensajes previos de la conversación (`HumanMessage`/`AIMessage`).
    """
    llm = llm or llm_texto()
    contador = contador or Contador()
    con_herramientas = llm.bind_tools(HERRAMIENTAS)

    def modelo(estado: Estado) -> dict:
        final = estado["intentos"] >= MAX_CONSULTAS or estado["turnos"] >= MAX_TURNOS
        mensaje = (llm if final else con_herramientas).invoke(estado["mensajes"])
        contador.registrar_llm(mensaje)
        return {"mensajes": [mensaje], "turnos": estado["turnos"] + 1, "final": final}

    def siguiente(estado: Estado) -> str:
        ultimo = estado["mensajes"][-1]
        llama = isinstance(ultimo, AIMessage) and ultimo.tool_calls
        return "herramientas" if llama and not estado["final"] else END

    def herramientas(estado: Estado) -> dict:
        intentos = estado["intentos"]
        salida: dict[str, list] = {"mensajes": [], "consultas": [], "advertencias": []}
        for llamada in estado["mensajes"][-1].tool_calls:
            if llamada["name"] == "describir_dataset":
                contenido = describir(conexion)
            elif llamada["name"] != "consultar_sql":
                contenido = f"Herramienta desconocida: {llamada['name']}"
            elif intentos >= MAX_CONSULTAS:
                contenido = (
                    f"Límite de {MAX_CONSULTAS} consultas alcanzado: responde con lo que ya tienes."
                )
            else:
                intentos += 1
                sql = str(llamada["args"].get("sql", ""))
                try:
                    r = consultar(conexion, sql)
                except ConsultaRechazada as e:
                    contenido = f"Consulta rechazada: {e}"
                else:
                    salida["consultas"].append(
                        Consulta(sql=sql, filas_muestra=r.filas[:FILAS_MUESTRA], n_filas=r.n_filas)
                    )
                    if r.truncado:
                        salida["advertencias"].append(
                            f"Una consulta devolvió más de {MAX_FILAS} filas; "
                            f"solo se usaron las primeras {MAX_FILAS}."
                        )
                    contenido = json.dumps(
                        {
                            "columnas": r.columnas,
                            "filas": r.filas[:FILAS_AL_LLM],
                            "n_filas": r.n_filas,
                            "truncado": r.truncado,
                        },
                        default=str,
                        ensure_ascii=False,
                    )
            salida["mensajes"].append(ToolMessage(contenido, tool_call_id=llamada["id"]))
        if intentos >= MAX_CONSULTAS > estado["intentos"]:
            salida["advertencias"].append(
                f"Se alcanzó el máximo de {MAX_CONSULTAS} consultas por pregunta."
            )
        return {**salida, "intentos": intentos}

    grafo = StateGraph(Estado)
    grafo.add_node("modelo", modelo)
    grafo.add_node("herramientas", herramientas)
    grafo.add_edge(START, "modelo")
    grafo.add_conditional_edges("modelo", siguiente, ["herramientas", END])
    grafo.add_edge("herramientas", "modelo")

    sistema = SystemMessage(SISTEMA.format(max_consultas=MAX_CONSULTAS, esquema=conexion.esquema))
    estado = grafo.compile().invoke(
        {
            "mensajes": [sistema, *historial, HumanMessage(pregunta)],
            "consultas": [],
            "advertencias": [],
            "intentos": 0,
            "turnos": 0,
            "final": False,
        },
        {"recursion_limit": 2 * MAX_TURNOS + 4},
    )
    final = _final(_texto(estado["mensajes"][-1]))
    return Respuesta(
        respuesta=final.respuesta,
        consultas=estado["consultas"],
        advertencias=[*estado["advertencias"], *final.advertencias],
    )
