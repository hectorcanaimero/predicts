"""Tipos de trabajo `ingesta` y `calidad` (ver specs/f4-analisis.md#F4.1.T2).

Corren en el subproceso del worker (`trabajos.worker`), que solo les pasa un
`TrabajoEnCurso`. La única conexión a Postgres disponible ahí es la que `eventos.configurar`
deja lista en `eventos._engine()` (la fija el worker al arrancar el hijo), así que estos
trabajos la reutilizan para leer y escribir el `Dataset`, en vez de `predicts.db.sesion`
(que apuntaría a `DATABASE_URL` del proceso, no a la conexión que el worker eligió).
"""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from predicts.datos.calidad import calcular
from predicts.datos.deteccion import Deteccion
from predicts.datos.ingesta import DatasetAIngerir
from predicts.datos.ingesta import ingerir as ejecutar_ingesta
from predicts.datos.mapeo import MapeoConfirmado
from predicts.db.modelos import Dataset
from predicts.trabajos import cola, eventos
from predicts.trabajos.registro import TrabajoEnCurso, tipo_trabajo

NOMBRE_PARQUET = "compras.parquet"


def _dataset_id(trabajo: TrabajoEnCurso) -> uuid.UUID:
    return uuid.UUID(trabajo.parametros["dataset_id"])


def _dataset(db: Session, trabajo: TrabajoEnCurso) -> Dataset:
    dataset = db.get(Dataset, _dataset_id(trabajo))
    if dataset is None or dataset.empresa_id != trabajo.empresa_id:
        raise ValueError(f"dataset {_dataset_id(trabajo)} no encontrado o de otra empresa")
    return dataset


@tipo_trabajo("ingesta")
def ingesta(trabajo: TrabajoEnCurso) -> None:
    """Ingiere el CSV del dataset con su mapeo confirmado y encola la `calidad` al terminar."""
    engine = eventos._engine()
    with Session(engine) as db:
        dataset = _dataset(db, trabajo)
        assert dataset.ruta_original and dataset.ruta_parquet  # los pone la API antes de encolar
        a_ingerir = DatasetAIngerir(
            ruta_csv=Path(dataset.ruta_original),
            deteccion=Deteccion.model_validate(dataset.deteccion),
            ruta_parquet=Path(dataset.ruta_parquet),
        )
        mapeo = MapeoConfirmado.model_validate(dataset.mapeo)

    def progreso(etapa: str, contadores: dict) -> None:
        eventos.emitir(trabajo.id, etapa, contadores)

    try:
        resumen = ejecutar_ingesta(a_ingerir, mapeo, progreso=progreso)
    except Exception:
        with Session(engine) as db:
            _dataset(db, trabajo).estado = "error"
            db.commit()
        raise

    with Session(engine) as db:
        dataset = _dataset(db, trabajo)
        dataset.resumen_ingesta = resumen.model_dump(mode="json")
        dataset.estado = "listo"
        cola.encolar(db, trabajo.empresa_id, "calidad", {"dataset_id": str(dataset.id)})


@tipo_trabajo("calidad")
def calidad(trabajo: TrabajoEnCurso) -> None:
    """Calcula el informe de calidad del Parquet ya ingerido, lo guarda en `datasets.calidad`
    y encola la clasificación de `productos` (F4.2.T1)."""
    engine = eventos._engine()
    with Session(engine) as db:
        dataset = _dataset(db, trabajo)
        assert dataset.ruta_parquet  # lo pone la ingesta antes de encolar la calidad
        ruta_parquet = dataset.ruta_parquet
        descartes = (dataset.resumen_ingesta or {}).get("descartadas", {})

    informe = calcular(ruta_parquet, descartes)
    eventos.emitir(trabajo.id, "calidad", {"filas": informe.filas})

    with Session(engine) as db:
        dataset = _dataset(db, trabajo)
        dataset.calidad = informe.model_dump(mode="json")
        cola.encolar(db, trabajo.empresa_id, "productos", {"dataset_id": str(dataset.id)})
