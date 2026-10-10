"""Tests de `predicts.datos.esquema`: `COLUMNAS_COMPRA` y `validar_parquet`."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from predicts.config import settings_para_tests
from predicts.datos.esquema import COLUMNAS_COMPRA, validar_parquet

_CFG = settings_para_tests()

_FILAS_VALIDAS = {
    "cliente_id": ["cliente-1", "cliente-2"],
    "fecha": [datetime(2024, 1, 1), datetime(2024, 1, 15)],
    "producto_id": ["producto-1", "producto-2"],
    "producto_id_tipo": ["sku", "ean"],
    "producto_nombre": ["Producto 1", "Producto 2"],
    "pedido_id": ["pedido-1", "pedido-2"],
    "categoria": ["limpieza", "alimentos"],
    "marca": ["marca-a", "marca-b"],
    "cantidad": [1.0, 2.0],
    "precio_unitario": [10.0, 5.0],
    "valor_total": [10.0, 10.0],
}

_TIPOS = {
    "cliente_id": pa.string(),
    "fecha": pa.timestamp("us"),
    "producto_id": pa.string(),
    "producto_id_tipo": pa.string(),
    "producto_nombre": pa.string(),
    "pedido_id": pa.string(),
    "categoria": pa.string(),
    "marca": pa.string(),
    "cantidad": pa.float64(),
    "precio_unitario": pa.float64(),
    "valor_total": pa.float64(),
}


def _escribir(tmp_path: Path, nombre: str, columnas: dict, tipos: dict | None = None) -> Path:
    tipos = tipos or _TIPOS
    tabla = pa.table({k: pa.array(v, type=tipos[k]) for k, v in columnas.items()})
    ruta = tmp_path / nombre
    pq.write_table(tabla, ruta)
    return ruta


def test_columnas_compra_tiene_las_columnas_de_la_arquitectura() -> None:
    nombres = [c.nombre for c in COLUMNAS_COMPRA]
    assert nombres == [
        "cliente_id",
        "fecha",
        "producto_id",
        "producto_id_tipo",
        "producto_nombre",
        "pedido_id",
        "categoria",
        "marca",
        "cantidad",
        "precio_unitario",
        "valor_total",
    ]
    obligatorias = {c.nombre for c in COLUMNAS_COMPRA if c.obligatoria}
    assert obligatorias == {"cliente_id", "fecha", "producto_id", "producto_id_tipo"}


def test_parquet_valido_no_tiene_errores(tmp_path: Path) -> None:
    ruta = _escribir(tmp_path, "valido.parquet", _FILAS_VALIDAS)
    assert validar_parquet(ruta, cfg=_CFG) == []


def test_detecta_columna_obligatoria_faltante(tmp_path: Path) -> None:
    columnas = {k: v for k, v in _FILAS_VALIDAS.items() if k != "producto_id_tipo"}
    ruta = _escribir(tmp_path, "sin_tipo.parquet", columnas)
    errores = validar_parquet(ruta, cfg=_CFG)
    assert any("producto_id_tipo" in e and "falta" in e for e in errores)


def test_detecta_tipo_incorrecto(tmp_path: Path) -> None:
    columnas = dict(_FILAS_VALIDAS)
    columnas["cantidad"] = ["uno", "dos"]
    tipos = dict(_TIPOS)
    tipos["cantidad"] = pa.string()
    ruta = _escribir(tmp_path, "tipo_malo.parquet", columnas, tipos)
    errores = validar_parquet(ruta, cfg=_CFG)
    assert any("cantidad" in e and "tipo" in e for e in errores)


def test_detecta_nulos_en_columna_obligatoria(tmp_path: Path) -> None:
    columnas = dict(_FILAS_VALIDAS)
    columnas["fecha"] = [datetime(2024, 1, 1), None]
    ruta = _escribir(tmp_path, "con_nulos.parquet", columnas)
    errores = validar_parquet(ruta, cfg=_CFG)
    assert any("fecha" in e and "nulos" in e for e in errores)


def test_detecta_producto_id_tipo_invalido(tmp_path: Path) -> None:
    columnas = dict(_FILAS_VALIDAS)
    columnas["producto_id_tipo"] = ["sku", "otro"]
    ruta = _escribir(tmp_path, "tipo_producto_malo.parquet", columnas)
    errores = validar_parquet(ruta, cfg=_CFG)
    assert any("producto_id_tipo" in e and "sku|ean" in e for e in errores)


def test_parquet_sin_columnas_obligatorias_reporta_todas(tmp_path: Path) -> None:
    columnas = {"producto_nombre": ["solo esta columna"]}
    tipos = {"producto_nombre": pa.string()}
    ruta = _escribir(tmp_path, "casi_vacio.parquet", columnas, tipos)
    errores = validar_parquet(ruta, cfg=_CFG)
    for obligatoria in ("cliente_id", "fecha", "producto_id", "producto_id_tipo"):
        assert any(obligatoria in e for e in errores)
