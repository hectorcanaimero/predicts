"""Tests sin red de `predicts.datos.datasets_publicos`: mapeo con fixtures chicas."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from predicts.config import settings_para_tests
from predicts.datos.datasets_publicos import (
    MENSAJE_INSTACART_SIN_FUENTE,
    mapear_online_retail,
    preparar_instacart,
)
from predicts.datos.esquema import validar_parquet

_CFG = settings_para_tests()
_FIXTURES = Path(__file__).parent / "fixtures" / "publicos"
_XLSX_ONLINE_RETAIL = _FIXTURES / "online_retail_ii_fixture.xlsx"
_CARPETA_INSTACART = _FIXTURES / "instacart"


def test_mapear_online_retail_descarta_cancelaciones_sin_cliente_y_cantidad_negativa() -> None:
    tabla = mapear_online_retail(_XLSX_ONLINE_RETAIL)
    filas = tabla.to_pylist()

    # 5 filas por hoja - 1 cancelación ('C...') - 1 sin Customer ID - 1 cantidad <= 0 = 2 por
    # la primera hoja, + las 2 válidas de la segunda hoja.
    assert len(filas) == 4
    assert all(fila["cliente_id"] in {"13085", "17850"} for fila in filas)
    assert all(not fila["pedido_id"].upper().startswith("C") for fila in filas)
    assert all(fila["cantidad"] > 0 for fila in filas)
    assert all(fila["producto_id_tipo"] == "sku" for fila in filas)

    fila = next(f for f in filas if f["pedido_id"] == "489434" and f["producto_id"] == "85048")
    assert fila["cliente_id"] == "13085"
    assert fila["fecha"] == datetime(2009, 12, 1, 7, 45)
    assert fila["producto_nombre"] == "15C NOVELTY BAGS"
    assert fila["cantidad"] == 12.0
    assert fila["precio_unitario"] == 1.95
    assert fila["valor_total"] == pytest.approx(12 * 1.95)


def test_mapear_online_retail_pasa_validar_parquet(tmp_path: Path) -> None:
    tabla = mapear_online_retail(_XLSX_ONLINE_RETAIL)
    ruta = tmp_path / "compras.parquet"
    import pyarrow.parquet as pq

    pq.write_table(tabla, ruta)
    assert validar_parquet(ruta, cfg=_CFG) == []


def test_mapear_online_retail_con_muestra_filtra_clientes() -> None:
    tabla = mapear_online_retail(_XLSX_ONLINE_RETAIL, muestra=1, semilla=0)
    clientes = set(tabla.column("cliente_id").to_pylist())
    assert len(clientes) == 1
    assert clientes <= {"13085", "17850"}


def test_preparar_instacart_sin_carpeta_explica_donde_conseguirlo() -> None:
    with pytest.raises(ValueError, match="Kaggle"):
        preparar_instacart("salida.parquet", carpeta=None)


def test_preparar_instacart_sin_carpeta_usa_el_mensaje_documentado() -> None:
    with pytest.raises(ValueError) as excinfo:
        preparar_instacart("salida.parquet", carpeta=None)
    assert str(excinfo.value) == MENSAJE_INSTACART_SIN_FUENTE


def test_preparar_instacart_con_carpeta_incompleta_lista_los_archivos_faltantes(
    tmp_path: Path,
) -> None:
    carpeta_incompleta = tmp_path / "instacart"
    carpeta_incompleta.mkdir()
    (carpeta_incompleta / "orders.csv").write_text("order_id,user_id\n")

    with pytest.raises(ValueError, match="products.csv"):
        preparar_instacart("salida.parquet", carpeta=carpeta_incompleta)


def test_preparar_instacart_construye_fechas_sinteticas_acumuladas(tmp_path: Path) -> None:
    ruta = tmp_path / "compras.parquet"
    conteos = preparar_instacart(ruta, carpeta=_CARPETA_INSTACART, cfg=_CFG)

    assert conteos.filas == 7
    assert conteos.clientes == 2
    assert conteos.productos == 4
    assert conteos.fecha_min == datetime(2023, 1, 1)
    assert conteos.fecha_max == datetime(2023, 1, 18)
    assert validar_parquet(ruta, cfg=_CFG) == []

    import pyarrow.parquet as pq

    filas = pq.read_table(ruta).to_pylist()
    fechas_cliente_1 = sorted({f["fecha"] for f in filas if f["cliente_id"] == "1"})
    # order_number 1, 2, 3 con days_since_prior_order None(=0), 7, 10 -> día 0, 7, 17.
    assert fechas_cliente_1 == [
        datetime(2023, 1, 1),
        datetime(2023, 1, 8),
        datetime(2023, 1, 18),
    ]
    assert all(f["producto_id_tipo"] == "sku" for f in filas)
    assert all(f["categoria"] for f in filas)


def test_preparar_instacart_con_muestra_filtra_clientes(tmp_path: Path) -> None:
    ruta = tmp_path / "compras.parquet"
    conteos = preparar_instacart(ruta, carpeta=_CARPETA_INSTACART, muestra=1, semilla=0, cfg=_CFG)
    assert conteos.clientes == 1
