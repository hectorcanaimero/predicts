"""Rutas del universo de clientes (F8.2.T1, specs/f8-3d-demo-despliegue.md#F8.2.T1): la muestra
estratificada y el historial resumido de un cliente, calculados con DuckDB directo sobre el
Parquet del dataset del análisis (ver `analisis.universo`). Aisladas por empresa."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from predicts.analisis import universo
from predicts.analisis.orquestador import ParametrosAnalisis
from predicts.auth.dependencias import Db, EmpresaActual
from predicts.config import settings
from predicts.datos.duckdb import conexion_duckdb
from predicts.db.modelos import Analisis, Dataset
from predicts.errores import ErrorApi
from predicts.tenancy import obtener_o_404

router = APIRouter(tags=["universo"])


class ClienteUniverso(BaseModel):
    cliente_id: str
    frecuencia: float
    valor: float
    recencia: int
    estado: universo.Estado
    grupo: int


class ProductoHistorial(BaseModel):
    producto_id: str
    producto_nombre: str | None
    n_compras: int
    cantidad_total: float | None
    valor_total: float | None
    ultima_compra: date
    ciclo: float | None
    proxima_compra: date | None


class HistorialCliente(BaseModel):
    cliente_id: str
    productos: list[ProductoHistorial]


def _analisis_y_ruta(
    db: Session, analisis_id: uuid.UUID, empresa_id: uuid.UUID
) -> tuple[Analisis, str]:
    analisis = obtener_o_404(db, Analisis, analisis_id, empresa_id)
    dataset = db.get(Dataset, analisis.dataset_id)
    if dataset is None or not dataset.ruta_parquet:
        raise ErrorApi("dataset_no_listo", 409)
    return analisis, dataset.ruta_parquet


@router.get("/analisis/{analisis_id}/universo", summary="Universo de clientes")
def universo_clientes(
    analisis_id: uuid.UUID,
    empresa: EmpresaActual,
    db: Db,
    max: int = Query(5000, ge=1, le=50_000),
    k: int = Query(universo.K_DEFECTO, ge=1, le=20),
) -> list[ClienteUniverso]:
    analisis, ruta_parquet = _analisis_y_ruta(db, analisis_id, empresa.id)
    params = ParametrosAnalisis.model_validate(analisis.parametros or {})
    con = conexion_duckdb(cfg=settings())
    try:
        filas = universo.calcular_universo(
            con,
            ruta_parquet,
            desde=params.desde,
            hasta=params.hasta,
            k=k,
            max_muestra=max,
            factor_riesgo=params.factor_riesgo,
        )
    finally:
        con.close()
    return [ClienteUniverso(**f) for f in filas]


@router.get(
    "/analisis/{analisis_id}/universo/{cliente_id}", summary="Historial resumido de un cliente"
)
def historial_de_cliente(
    analisis_id: uuid.UUID, cliente_id: str, empresa: EmpresaActual, db: Db
) -> HistorialCliente:
    analisis, ruta_parquet = _analisis_y_ruta(db, analisis_id, empresa.id)
    params = ParametrosAnalisis.model_validate(analisis.parametros or {})
    con = conexion_duckdb(cfg=settings())
    try:
        historial = universo.historial_cliente(
            con, ruta_parquet, cliente_id, desde=params.desde, hasta=params.hasta
        )
    finally:
        con.close()
    if not historial["productos"]:
        raise ErrorApi("no_encontrado", 404)
    return HistorialCliente(**historial)
