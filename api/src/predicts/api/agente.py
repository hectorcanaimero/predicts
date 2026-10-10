"""Agente analista (FR-22): `POST /agente/preguntas` responde una pregunta sobre un dataset de la
empresa con `agente.grafo.preguntar` sobre las vistas de `agente.sql` (dataset + último análisis
listo). El costo de IA de cada pregunta se registra en el log y vuelve en `costo_ia`.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from pydantic import BaseModel, Field

from predicts.agente.grafo import Respuesta, preguntar
from predicts.agente.sql import abrir_dataset
from predicts.auth.dependencias import Db, EmpresaActual
from predicts.db.modelos import Dataset
from predicts.errores import ErrorApi
from predicts.ia import Contador, llm_texto
from predicts.tenancy import obtener_o_404

router = APIRouter(tags=["agente"])
logger = logging.getLogger(__name__)


class MensajeHistorial(BaseModel):
    rol: Literal["usuario", "agente"]
    contenido: str = Field(max_length=10_000)


class PreguntaEntrada(BaseModel):
    dataset_id: uuid.UUID
    pregunta: str = Field(min_length=1, max_length=2_000)
    historial: list[MensajeHistorial] = Field(default_factory=list, max_length=20)


class RespuestaSalida(Respuesta):
    costo_ia: dict


def obtener_llm() -> BaseChatModel:
    """Dependencia aparte para que los tests inyecten un LLM falso."""
    return llm_texto()


@router.post("/agente/preguntas", summary="Preguntar al agente analista sobre un dataset")
def preguntar_agente(
    entrada: PreguntaEntrada,
    empresa: EmpresaActual,
    db: Db,
    llm: Annotated[BaseChatModel, Depends(obtener_llm)],
) -> RespuestaSalida:
    dataset = obtener_o_404(db, Dataset, entrada.dataset_id, empresa.id)
    if not dataset.ruta_parquet or dataset.estado != "listo":
        raise ErrorApi("dataset_no_listo", 409, estado=dataset.estado)
    historial: list[BaseMessage] = [
        HumanMessage(m.contenido) if m.rol == "usuario" else AIMessage(m.contenido)
        for m in entrada.historial
    ]
    contador = Contador()
    conexion = abrir_dataset(db, dataset)
    try:
        respuesta = preguntar(conexion, entrada.pregunta, historial, llm, contador)
    finally:
        conexion.con.close()
        costo = contador.resumen()
        logger.info(
            "agente: empresa=%s dataset=%s consultas_llm=%s costo_usd=%.6f",
            empresa.id,
            dataset.id,
            costo["llamadas"].get("9router", 0),
            costo["costo_estimado_usd"],
        )
    return RespuestaSalida(**respuesta.model_dump(), costo_ia=costo)
