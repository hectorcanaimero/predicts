"""Rutas de análisis: lanzar (tipos + parámetros → trabajo), estado/resumen/métricas, resultados
paginados desde el Parquet (DuckDB, sin cargar todo en memoria) y borrado.

Aisladas por empresa (`predicts.tenancy`). El trabajo real corre en `analisis.orquestador`
(F4.3.T1/T2); esta ruta solo valida la entrada, encola y sirve lo que el trabajo ya escribió.
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Query
from pydantic import BaseModel, ValidationError
from sqlalchemy import select

from predicts.analisis.orquestador import TIPOS, ParametrosAnalisis
from predicts.auth.dependencias import Db, EmpresaActual
from predicts.config import settings
from predicts.datos.duckdb import conexion_duckdb
from predicts.db.modelos import Analisis, Dataset
from predicts.errores import ErrorApi
from predicts.tenancy import obtener_o_404
from predicts.trabajos import cola

router = APIRouter(tags=["analisis"])

# tipo → (archivo, columnas válidas para `orden`, orden por defecto, empate determinista).
# Mismas columnas que documentan `analisis/recompra.py`, `ciclos.py`, `riesgo.py`, `ofertas.py`.
_RESULTADOS: dict[str, tuple[str, tuple[str, ...], str, tuple[str, ...]]] = {
    "recompra": (
        "recompra.parquet",
        (
            "cliente_id", "producto_id", "producto_nombre", "ciclo", "p", "fecha_probable",
            "fecha_min", "fecha_max", "n_compras", "dias_desde_ultima", "posible_abandono",
            "motivo",
        ),
        "-p",
        ("cliente_id", "producto_id"),
    ),  # fmt: skip
    "ciclos": (
        "ciclos.parquet",
        ("producto_id", "producto_nombre", "ciclo_mediano", "dispersion", "desvio_log",
         "clientes_recurrentes"),  # fmt: skip
        "-clientes_recurrentes",
        ("producto_id",),
    ),
    "riesgo": (
        "riesgo.parquet",
        ("nivel", "cliente_id", "producto_id", "producto_nombre", "n_compras", "ciclo",
         "dispersion", "dias_desde_ultima", "atraso", "valor", "motivo"),  # fmt: skip
        "-valor",
        ("cliente_id", "producto_id"),
    ),
    "ofertas": (
        "ofertas.parquet",
        ("cliente_id", "producto_id", "producto_nombre", "puntaje", "p_recompra", "lift",
         "por_producto", "descuento", "fuentes", "motivo"),  # fmt: skip
        "-puntaje",
        ("cliente_id", "producto_id"),
    ),
}


class AnalisisEntrada(BaseModel):
    tipos: list[str]
    parametros: dict | None = None


class AnalisisSalida(BaseModel):
    id: str
    dataset_id: str
    tipos: list[str]
    parametros: dict | None
    estado: str
    trabajo_id: str | None
    version_modelo: str | None
    metricas: dict | None
    resumen: dict | None
    costo_ia: dict | None


def _salida(analisis: Analisis) -> AnalisisSalida:
    return AnalisisSalida(
        id=str(analisis.id),
        dataset_id=str(analisis.dataset_id),
        tipos=list(analisis.tipos),
        parametros=analisis.parametros,
        estado=analisis.estado,
        trabajo_id=str(analisis.trabajo_id) if analisis.trabajo_id else None,
        version_modelo=analisis.version_modelo,
        metricas=analisis.metricas,
        resumen=analisis.resumen,
        costo_ia=analisis.costo_ia,
    )


@router.post(
    "/datasets/{dataset_id}/analisis", status_code=202, summary="Lanzar un análisis"
)
def lanzar_analisis(
    dataset_id: uuid.UUID, entrada: AnalisisEntrada, empresa: EmpresaActual, db: Db
) -> AnalisisSalida:
    dataset = obtener_o_404(db, Dataset, dataset_id, empresa.id)
    if dataset.estado != "listo":
        raise ErrorApi("dataset_no_listo", 409, estado=dataset.estado)

    invalidos = sorted(set(entrada.tipos) - set(TIPOS))
    if invalidos or not entrada.tipos:
        raise ErrorApi("tipos_invalidos", 422, tipos=invalidos or "ninguno")
    try:
        ParametrosAnalisis.model_validate(entrada.parametros or {})
    except ValidationError as e:
        raise ErrorApi("parametros_invalidos", 422, detalle=e.errors()) from e

    analisis = Analisis(
        empresa_id=empresa.id,
        dataset_id=dataset.id,
        tipos=entrada.tipos,
        parametros=entrada.parametros,
        estado="en_cola",
    )
    db.add(analisis)
    db.flush()
    trabajo = cola.encolar(db, empresa.id, "analisis", {"analisis_id": str(analisis.id)})
    analisis.trabajo_id = trabajo.id
    db.commit()
    return _salida(analisis)


@router.get("/datasets/{dataset_id}/analisis", summary="Listar los análisis de un dataset")
def listar_analisis(
    dataset_id: uuid.UUID, empresa: EmpresaActual, db: Db
) -> list[AnalisisSalida]:
    dataset = obtener_o_404(db, Dataset, dataset_id, empresa.id)
    analisis = db.scalars(
        select(Analisis)
        .where(Analisis.dataset_id == dataset.id, Analisis.empresa_id == empresa.id)
        .order_by(Analisis.creado_en.desc())
    ).all()
    return [_salida(a) for a in analisis]


@router.get("/analisis/{analisis_id}", summary="Estado, resumen y métricas de un análisis")
def obtener_analisis(analisis_id: uuid.UUID, empresa: EmpresaActual, db: Db) -> AnalisisSalida:
    analisis = obtener_o_404(db, Analisis, analisis_id, empresa.id)
    return _salida(analisis)


def _orden_sql(tipo: str, columnas: tuple[str, ...], defecto: str, orden: str | None) -> str:
    campo_pedido = orden if orden is not None else defecto
    descendente = campo_pedido.startswith("-")
    campo = campo_pedido[1:] if descendente else campo_pedido
    if campo not in columnas:
        raise ErrorApi("orden_invalido", 422, tipo=tipo, campo=campo)
    _, _, _, empate = _RESULTADOS[tipo]
    partes = [f'"{campo}" {"DESC" if descendente else "ASC"} NULLS LAST']
    partes += [f'"{c}" NULLS LAST' for c in empate if c != campo]
    return ", ".join(partes)


@router.get("/analisis/{analisis_id}/resultados", summary="Resultados paginados de un análisis")
def resultados_analisis(
    analisis_id: uuid.UUID,
    empresa: EmpresaActual,
    db: Db,
    tipo: str,
    pagina: int = Query(1, ge=1),
    tam_pagina: int = Query(50, ge=1, le=500),
    orden: str | None = None,
) -> dict:
    analisis = obtener_o_404(db, Analisis, analisis_id, empresa.id)
    if tipo not in _RESULTADOS:
        raise ErrorApi("tipo_invalido", 422, tipo=tipo, validos=sorted(_RESULTADOS))
    if tipo not in analisis.tipos:
        raise ErrorApi("tipo_no_solicitado", 404, tipo=tipo)
    dataset = db.get(Dataset, analisis.dataset_id)
    if dataset is not None and dataset.estado == "archivado":
        raise ErrorApi("archivo_vencido", 410)
    if analisis.estado != "listo" or not analisis.ruta_resultados:
        raise ErrorApi("analisis_no_listo", 409, estado=analisis.estado)

    archivo, columnas, defecto, _ = _RESULTADOS[tipo]
    orden_sql = _orden_sql(tipo, columnas, defecto, orden)
    ruta = str(Path(analisis.ruta_resultados) / archivo).replace("'", "''")

    con = conexion_duckdb(cfg=settings())
    try:
        (total,) = con.execute(f"SELECT count(*) FROM read_parquet('{ruta}')").fetchone()
        cursor = con.execute(
            f"SELECT * FROM read_parquet('{ruta}') ORDER BY {orden_sql} LIMIT ? OFFSET ?",
            [tam_pagina, (pagina - 1) * tam_pagina],
        )
        nombres = [c[0] for c in cursor.description]
        filas = [dict(zip(nombres, f, strict=True)) for f in cursor.fetchall()]
    finally:
        con.close()
    return {"pagina": pagina, "tam_pagina": tam_pagina, "total": total, "resultados": filas}


@router.delete("/analisis/{analisis_id}", status_code=204, summary="Borrar un análisis")
def borrar_analisis(analisis_id: uuid.UUID, empresa: EmpresaActual, db: Db) -> None:
    analisis = obtener_o_404(db, Analisis, analisis_id, empresa.id)
    if analisis.estado == "corriendo":
        raise ErrorApi("analisis_corriendo", 409)
    if analisis.ruta_resultados:
        shutil.rmtree(Path(analisis.ruta_resultados).parent, ignore_errors=True)
    db.delete(analisis)
    db.commit()
