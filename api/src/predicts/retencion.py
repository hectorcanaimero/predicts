"""Retención de archivos (ver specs/f8-3d-demo-despliegue.md#F8.3.T2).

Pasados `RETENCION_DIAS` desde `Dataset.subido_en`, se borra la carpeta de crudos del dataset
(`original.csv`, `compras.parquet` y los `resultados/` de cada análisis bajo ella) y se marca el
dataset como `archivado`. El resumen, las métricas y las plantillas quedan en Postgres y no se
tocan: la API los sigue sirviendo, solo los datos detallados (que viven en esos Parquet) dejan de
estar disponibles.

También limpia `DATA_DIR/tmp` (temporales de DuckDB, ver `datos/duckdb.py`) de restos de más de un
día: archivos que un trabajo interrumpido pudo dejar sin barrer.
"""

from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from predicts.config import Settings
from predicts.db.modelos import Dataset

_TMP_MAX_DIAS = 1


@dataclass(frozen=True)
class ResultadoLimpieza:
    datasets_archivados: list[uuid.UUID] = field(default_factory=list)
    tmp_borrados: list[Path] = field(default_factory=list)


def _carpeta_dataset(cfg: Settings, dataset: Dataset) -> Path:
    return Path(cfg.DATA_DIR) / str(dataset.empresa_id) / str(dataset.id)


def _vencidos(
    db: Session, cfg: Settings, ahora: datetime, empresa_id: uuid.UUID | None
) -> list[Dataset]:
    corte = ahora - timedelta(days=cfg.RETENCION_DIAS)
    condiciones = [Dataset.estado != "archivado", Dataset.subido_en < corte]
    if empresa_id is not None:
        condiciones.append(Dataset.empresa_id == empresa_id)
    return list(db.scalars(select(Dataset).where(*condiciones)))


def _limpiar_tmp(cfg: Settings, ahora: datetime, dry_run: bool) -> list[Path]:
    tmp_dir = Path(cfg.DATA_DIR) / "tmp"
    if not tmp_dir.is_dir():
        return []
    corte = ahora - timedelta(days=_TMP_MAX_DIAS)
    borrados = []
    for entrada in sorted(tmp_dir.iterdir()):
        mtime = datetime.fromtimestamp(entrada.stat().st_mtime, tz=UTC)
        if mtime >= corte:
            continue
        borrados.append(entrada)
        if dry_run:
            continue
        if entrada.is_dir():
            shutil.rmtree(entrada, ignore_errors=True)
        else:
            entrada.unlink(missing_ok=True)
    return borrados


def limpiar(
    db: Session,
    cfg: Settings,
    *,
    empresa_id: uuid.UUID | None = None,
    ahora: datetime | None = None,
    dry_run: bool = False,
) -> ResultadoLimpieza:
    """Archiva los datasets vencidos (de `empresa_id`, o de todas si es `None`) y limpia
    `DATA_DIR/tmp`. Con `dry_run`, no borra nada ni escribe en la base: solo informa qué haría."""
    ahora = ahora or datetime.now(UTC)

    archivados: list[uuid.UUID] = []
    for dataset in _vencidos(db, cfg, ahora, empresa_id):
        archivados.append(dataset.id)
        if dry_run:
            continue
        shutil.rmtree(_carpeta_dataset(cfg, dataset), ignore_errors=True)
        dataset.estado = "archivado"
        dataset.archivado_en = ahora
        dataset.ruta_original = None
        dataset.ruta_parquet = None
    if not dry_run:
        db.commit()

    tmp_borrados = _limpiar_tmp(cfg, ahora, dry_run)
    return ResultadoLimpieza(datasets_archivados=archivados, tmp_borrados=tmp_borrados)
