"""Rutas de datasets: subida (multipart), listado por proyecto, detalle y borrado.

Aislados por empresa (ver `predicts.tenancy` y `docs/notas/tenancy.md`). `POST
/proyectos/{id}/datasets` guarda el CSV por streaming (`datos/subida.py`) y corre la
detección de formato (`datos/deteccion.py`); si cualquiera de las dos falla, se descarta
la fila de `datasets` a medio crear y los archivos ya escritos.
"""

from __future__ import annotations

import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel
from sqlalchemy import select

from predicts.auth.dependencias import Db, EmpresaActual
from predicts.config import settings
from predicts.datos.deteccion import detectar
from predicts.datos.subida import guardar_csv
from predicts.db.modelos import Dataset, Proyecto
from predicts.tenancy import de_empresa, obtener_o_404

router = APIRouter(tags=["datasets"])


class DatasetSalida(BaseModel):
    id: str
    proyecto_id: str
    nombre_archivo: str
    tamano_bytes: int
    sha256: str
    estado: str
    deteccion: dict | None


def _salida(dataset: Dataset) -> DatasetSalida:
    return DatasetSalida(
        id=str(dataset.id),
        proyecto_id=str(dataset.proyecto_id),
        nombre_archivo=dataset.nombre_archivo,
        tamano_bytes=dataset.tamano_bytes,
        sha256=dataset.sha256,
        estado=dataset.estado,
        deteccion=dataset.deteccion,
    )


def _carpeta_dataset(empresa_id: uuid.UUID, dataset_id: uuid.UUID) -> Path:
    return Path(settings().DATA_DIR) / str(empresa_id) / str(dataset_id)


@router.post(
    "/proyectos/{proyecto_id}/datasets", status_code=201, summary="Subir un CSV al proyecto"
)
def subir(
    proyecto_id: uuid.UUID,
    empresa: EmpresaActual,
    db: Db,
    archivo: UploadFile = File(...),  # noqa: B008
) -> DatasetSalida:
    proyecto = obtener_o_404(db, Proyecto, proyecto_id, empresa.id)
    cfg = settings()

    dataset = Dataset(
        empresa_id=empresa.id,
        proyecto_id=proyecto.id,
        nombre_archivo=archivo.filename or "dataset.csv",
        tamano_bytes=0,
        sha256="",
        estado="subido",
    )
    db.add(dataset)
    db.flush()

    destino = _carpeta_dataset(empresa.id, dataset.id) / "original.csv"
    try:
        guardado = guardar_csv(archivo.file, destino, cfg.MAX_CSV_MB)
        deteccion = detectar(guardado.ruta, cfg=cfg)
    except Exception:
        db.rollback()
        shutil.rmtree(destino.parent, ignore_errors=True)
        raise

    dataset.tamano_bytes = guardado.tamano_bytes
    dataset.sha256 = guardado.sha256
    dataset.ruta_original = str(guardado.ruta)
    dataset.deteccion = deteccion.model_dump()
    dataset.subido_en = datetime.now(UTC)
    db.commit()
    return _salida(dataset)


@router.get("/proyectos/{proyecto_id}/datasets", summary="Listar datasets de un proyecto")
def listar(proyecto_id: uuid.UUID, empresa: EmpresaActual, db: Db) -> list[DatasetSalida]:
    obtener_o_404(db, Proyecto, proyecto_id, empresa.id)
    consulta = (
        de_empresa(select(Dataset), empresa.id)
        .where(Dataset.proyecto_id == proyecto_id)
        .order_by(Dataset.creado_en)
    )
    return [_salida(d) for d in db.scalars(consulta).all()]


@router.get("/datasets/{dataset_id}", summary="Obtener un dataset")
def obtener(dataset_id: uuid.UUID, empresa: EmpresaActual, db: Db) -> DatasetSalida:
    dataset = obtener_o_404(db, Dataset, dataset_id, empresa.id)
    return _salida(dataset)


@router.delete("/datasets/{dataset_id}", status_code=204, summary="Borrar un dataset")
def borrar(dataset_id: uuid.UUID, empresa: EmpresaActual, db: Db) -> None:
    dataset = obtener_o_404(db, Dataset, dataset_id, empresa.id)
    shutil.rmtree(_carpeta_dataset(empresa.id, dataset.id), ignore_errors=True)
    db.delete(dataset)
    db.commit()
