"""Router `/demo`: crea un proyecto "Demo" con una muestra de Online Retail II (UCI, CC BY 4.0)
y encola su análisis completo, para que una persona nueva vea resultados sin subir nada.

La muestra se prepara una sola vez en `DATA_DIR/demo/compras.parquet` (ver
`predicts.datos.datasets_publicos.preparar_online_retail`, F1.1.T2 — misma función que usa
`predicts preparar-dataset online-retail --muestra`) y se copia a la carpeta del dataset, igual
que la ingesta real (`api/datasets_ingesta.py`). Como el Parquet ya está en el esquema interno
de compras, el mapeo es la identidad: no hay detección ni confirmación manual.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from predicts.analisis.orquestador import TIPOS
from predicts.auth.dependencias import Db, EmpresaActual
from predicts.config import settings
from predicts.datos.datasets_publicos import preparar_online_retail
from predicts.datos.mapeo import CAMPOS_ESQUEMA, MapeoColumna, MapeoConfirmado
from predicts.db.modelos import Analisis, Dataset, Proyecto
from predicts.trabajos import cola

router = APIRouter(tags=["demo"])

NOMBRE_PROYECTO_DEMO = "Demo"
ATRIBUCION_DEMO = (
    "Muestra de Online Retail II (Chen, 2019), UCI Machine Learning Repository, "
    "licencia CC BY 4.0 — https://archive.ics.uci.edu/dataset/502/online+retail+ii"
)
# Online Retail II tiene catálogos muy variados incluso con pocos clientes (medido: 200
# clientes → 3180 productos distintos → 920 combinaciones de `mensajes`, ≈13 min de punta a
# punta por los ~99 llamados secuenciales a router/Jev que generan y revisan las plantillas;
# 50 clientes mantiene variedad y acorta esa cola). Ver el PR de F8.3.T1 para la medición.
MUESTRA_CLIENTES_DEMO = 50
SEMILLA_DEMO = 0

_MAPEO_DEMO = MapeoConfirmado(
    columnas=[MapeoColumna(columna=campo, campo=campo) for campo in CAMPOS_ESQUEMA],
    producto_id_tipo="sku",
    formato_fecha="aaaa-mm-dd",
)


class DemoSalida(BaseModel):
    proyecto_id: str
    dataset_id: str
    analisis_id: str


def _muestra_cacheada() -> Path:
    ruta = Path(settings().DATA_DIR) / "demo" / "compras.parquet"
    if not ruta.exists():
        preparar_online_retail(ruta, muestra=MUESTRA_CLIENTES_DEMO, semilla=SEMILLA_DEMO)
    return ruta


@router.post("/demo", status_code=201, summary="Crear el proyecto de demostración")
def crear_demo(empresa: EmpresaActual, db: Db) -> DemoSalida:
    muestra = _muestra_cacheada()

    proyecto = Proyecto(
        empresa_id=empresa.id,
        nombre=NOMBRE_PROYECTO_DEMO,
        idioma_mensajes="pt-BR",
        tono="neutro",
        descripcion=ATRIBUCION_DEMO,
    )
    db.add(proyecto)
    db.flush()

    dataset = Dataset(
        empresa_id=empresa.id,
        proyecto_id=proyecto.id,
        nombre_archivo="online_retail_ii_demo.parquet",
        tamano_bytes=muestra.stat().st_size,
        sha256=hashlib.sha256(muestra.read_bytes()).hexdigest(),
        estado="listo",
        mapeo=_MAPEO_DEMO.model_dump(),
    )
    db.add(dataset)
    db.flush()

    carpeta = Path(settings().DATA_DIR) / str(empresa.id) / str(dataset.id)
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta_parquet = carpeta / "compras.parquet"
    shutil.copy(muestra, ruta_parquet)
    dataset.ruta_parquet = str(ruta_parquet)

    analisis = Analisis(
        empresa_id=empresa.id,
        dataset_id=dataset.id,
        tipos=list(TIPOS),
        parametros=None,
        estado="en_cola",
    )
    db.add(analisis)
    db.flush()
    trabajo = cola.encolar(db, empresa.id, "analisis", {"analisis_id": str(analisis.id)})
    analisis.trabajo_id = trabajo.id
    db.commit()

    return DemoSalida(
        proyecto_id=str(proyecto.id), dataset_id=str(dataset.id), analisis_id=str(analisis.id)
    )
