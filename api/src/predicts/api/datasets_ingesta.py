"""Rutas para arrancar la ingesta de un dataset ya mapeado y leer su informe de calidad.

Aisladas por empresa (`predicts.tenancy`). Estados del dataset: `subido → mapeado →
ingiriendo → listo | error` (`trabajos/tipos_datos.py` hace las transiciones de `ingiriendo`
en adelante; la de `calidad` no cambia el estado del dataset, solo llena `datasets.calidad`).
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from predicts.auth.dependencias import Db, EmpresaActual
from predicts.config import settings
from predicts.db.modelos import Dataset
from predicts.errores import ErrorApi
from predicts.tenancy import obtener_o_404
from predicts.trabajos import cola
from predicts.trabajos.tipos_datos import NOMBRE_PARQUET

router = APIRouter(tags=["ingesta"])


class IngestaSalida(BaseModel):
    trabajo_id: str
    estado: str


def _carpeta_dataset(empresa_id: uuid.UUID, dataset_id: uuid.UUID) -> Path:
    return Path(settings().DATA_DIR) / str(empresa_id) / str(dataset_id)


@router.post(
    "/datasets/{dataset_id}/ingesta", status_code=202, summary="Iniciar la ingesta de un dataset"
)
def iniciar_ingesta(dataset_id: uuid.UUID, empresa: EmpresaActual, db: Db) -> IngestaSalida:
    dataset = obtener_o_404(db, Dataset, dataset_id, empresa.id)
    if dataset.estado != "mapeado":
        raise ErrorApi("mapeo_no_confirmado", 409, estado=dataset.estado)

    dataset.ruta_parquet = str(_carpeta_dataset(empresa.id, dataset.id) / NOMBRE_PARQUET)
    dataset.estado = "ingiriendo"
    trabajo = cola.encolar(db, empresa.id, "ingesta", {"dataset_id": str(dataset.id)})
    return IngestaSalida(trabajo_id=str(trabajo.id), estado=dataset.estado)


@router.get("/datasets/{dataset_id}/calidad", summary="Informe de calidad de un dataset")
def obtener_calidad(dataset_id: uuid.UUID, empresa: EmpresaActual, db: Db) -> dict:
    dataset = obtener_o_404(db, Dataset, dataset_id, empresa.id)
    if dataset.calidad is None:
        raise ErrorApi("calidad_no_disponible", 404, estado=dataset.estado)
    return dataset.calidad
