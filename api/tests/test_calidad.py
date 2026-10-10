"""Tests de `datos/calidad.py` sobre Parquets construidos a mano con el esquema de
`datos/esquema.py` (mismo esquema que escribe `ingesta.py`, FR-6/FR-7)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from predicts.config import settings_para_tests
from predicts.datos.calidad import calcular
from predicts.datos.esquema import COLUMNAS_COMPRA

_TIPO_PYARROW = {"VARCHAR": pa.string(), "TIMESTAMP": pa.timestamp("us"), "DOUBLE": pa.float64()}
_ESQUEMA = pa.schema([(c.nombre, _TIPO_PYARROW[c.tipo]) for c in COLUMNAS_COMPRA])


@pytest.fixture()
def cfg(tmp_path):
    return settings_para_tests(DATA_DIR=str(tmp_path), MIN_COMPRAS=3)


def _escribir(tmp_path: Path, filas: list[dict]) -> Path:
    columnas = {c.nombre: [f.get(c.nombre) for f in filas] for c in COLUMNAS_COMPRA}
    tabla = pa.Table.from_pydict(columnas, schema=_ESQUEMA)
    ruta = tmp_path / "compras.parquet"
    pq.write_table(tabla, ruta)
    return ruta


def _fila(cliente: str, producto: str, fecha: str, **extra: object) -> dict:
    return {
        "cliente_id": cliente, "fecha": datetime.fromisoformat(fecha), "producto_id": producto,
        "producto_id_tipo": "sku", **extra,
    }


def test_conteos_basicos_y_sin_duplicados(tmp_path, cfg) -> None:
    filas = [
        _fila("c1", "p1", "2024-01-01"),
        _fila("c1", "p2", "2024-01-05"),
        _fila("c2", "p1", "2024-02-01"),
    ]
    ruta = _escribir(tmp_path, filas)

    informe = calcular(ruta, cfg=cfg)

    assert informe.filas == 3
    assert informe.clientes == 2
    assert informe.productos == 2
    assert informe.fecha_min == datetime(2024, 1, 1)
    assert informe.fecha_max == datetime(2024, 2, 1)
    assert informe.duplicados_exactos == 0
    assert informe.descartadas == {}


def test_duplicados_exactos_contados_como_filas_de_mas(tmp_path, cfg) -> None:
    fila = _fila("c1", "p1", "2024-01-01")
    ruta = _escribir(tmp_path, [fila, dict(fila), dict(fila)])

    informe = calcular(ruta, cfg=cfg)

    assert informe.filas == 3
    assert informe.duplicados_exactos == 2


def test_distribucion_compras_por_cliente(tmp_path, cfg) -> None:
    filas = [
        _fila("c1", "p1", "2024-01-01"), _fila("c1", "p2", "2024-01-02"),
        _fila("c1", "p3", "2024-01-03"),
        _fila("c2", "p1", "2024-01-01"),
    ]
    ruta = _escribir(tmp_path, filas)

    informe = calcular(ruta, cfg=cfg)

    d = informe.distribucion_compras_cliente
    assert d.minimo == 1
    assert d.maximo == 3
    assert d.promedio == pytest.approx(2.0)
    assert d.mediana == pytest.approx(2.0)


def test_pares_con_historia_suficiente_y_porcentaje(tmp_path, cfg) -> None:
    # c1-p1: 3 días distintos (alcanza MIN_COMPRAS=3); c2-p2: 2 días (no alcanza).
    filas = [
        _fila("c1", "p1", "2024-01-01"), _fila("c1", "p1", "2024-01-10"),
        _fila("c1", "p1", "2024-01-20"),
        _fila("c2", "p2", "2024-01-01"), _fila("c2", "p2", "2024-01-10"),
    ]
    ruta = _escribir(tmp_path, filas)

    informe = calcular(ruta, cfg=cfg)

    assert informe.pares.total_pares == 2
    assert informe.pares.con_historia_suficiente == 1
    assert informe.pares.porcentaje == pytest.approx(0.5)


def test_viabilidad_alcanza_para_los_tres_analisis(tmp_path, cfg) -> None:
    filas = [
        _fila("c1", "p1", "2024-01-01"), _fila("c1", "p1", "2024-01-10"),
        _fila("c1", "p1", "2024-01-20"),
        _fila("c1", "p2", "2024-01-01"),  # mismo cliente, segundo producto -> habilita ofertas
    ]
    ruta = _escribir(tmp_path, filas)

    informe = calcular(ruta, cfg=cfg)

    assert informe.viabilidad["recompra"].viable is True
    assert informe.viabilidad["riesgo"].viable is True
    assert informe.viabilidad["ofertas"].viable is True
    assert all(v.motivo is None for v in informe.viabilidad.values())


def test_viabilidad_no_alcanza_con_un_solo_par_y_una_sola_compra(tmp_path, cfg) -> None:
    ruta = _escribir(tmp_path, [_fila("c1", "p1", "2024-01-01")])

    informe = calcular(ruta, cfg=cfg)

    assert informe.viabilidad["recompra"].viable is False
    assert informe.viabilidad["recompra"].motivo
    assert informe.viabilidad["riesgo"].viable is False
    assert informe.viabilidad["ofertas"].viable is False
    assert informe.viabilidad["ofertas"].motivo


def test_descartes_de_la_ingesta_se_incluyen_en_el_informe(tmp_path, cfg) -> None:
    ruta = _escribir(tmp_path, [_fila("c1", "p1", "2024-01-01")])

    informe = calcular(ruta, descartes_ingesta={"cliente_vacio": 2, "fecha_invalida": 1}, cfg=cfg)

    assert informe.descartadas == {"cliente_vacio": 2, "fecha_invalida": 1}


def test_parquet_vacio_no_rompe_y_no_es_viable(tmp_path, cfg) -> None:
    ruta = _escribir(tmp_path, [])

    informe = calcular(ruta, cfg=cfg)

    assert informe.filas == 0
    assert informe.clientes == 0
    assert informe.fecha_min is None
    assert informe.fecha_max is None
    assert informe.distribucion_compras_cliente.minimo == 0
    assert informe.pares.total_pares == 0
    assert informe.pares.porcentaje == 0.0
    assert informe.viabilidad["recompra"].viable is False
