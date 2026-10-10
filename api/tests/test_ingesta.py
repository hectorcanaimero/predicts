"""Tests de `datos/ingesta.py` con los fixtures de `tests/fixtures/csv/` (F3.1) y mapeos
construidos a mano (equivalentes a los que confirma `datos/mapeo.py`, F3.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

import predicts.datos.ingesta as ingesta_mod
from predicts.config import settings_para_tests
from predicts.datos.deteccion import detectar
from predicts.datos.duckdb import conexion_duckdb
from predicts.datos.esquema import validar_parquet
from predicts.datos.ingesta import (
    MOTIVO_CLIENTE_VACIO,
    MOTIVO_FECHA_INVALIDA,
    MOTIVO_PRODUCTO_VACIO,
    DatasetAIngerir,
    ingerir,
)
from predicts.datos.mapeo import MapeoColumna, MapeoConfirmado

FIXTURES = Path(__file__).parent / "fixtures" / "csv"


@pytest.fixture()
def cfg(tmp_path):
    return settings_para_tests(DATA_DIR=str(tmp_path))


def _mapeo(columnas: dict[str, str], producto_id_tipo: str, formato_fecha: str) -> MapeoConfirmado:
    return MapeoConfirmado(
        columnas=[MapeoColumna(columna=col, campo=campo) for campo, col in columnas.items()],
        producto_id_tipo=producto_id_tipo,
        formato_fecha=formato_fecha,
    )


def _leer_parquet(ruta: Path, cfg) -> list[dict]:
    con = conexion_duckdb(solo_lectura=True, cfg=cfg)
    try:
        cursor = con.execute(f"SELECT * FROM read_parquet('{ruta}') ORDER BY cliente_id")
        nombres = [d[0] for d in cursor.description]
        return [dict(zip(nombres, fila, strict=True)) for fila in cursor.fetchall()]
    finally:
        con.close()


def test_utf8_todas_las_filas_validas(tmp_path, cfg) -> None:
    deteccion = detectar(FIXTURES / "utf8.csv", cfg=cfg)
    mapeo = _mapeo(
        {
            "cliente_id": "cliente_id", "fecha": "fecha", "producto_id": "producto_id",
            "producto_nombre": "producto_nombre", "cantidad": "cantidad",
            "precio_unitario": "precio_unitario",
        },
        producto_id_tipo="sku", formato_fecha="aaaa-mm-dd",
    )
    dataset = DatasetAIngerir(
        ruta_csv=FIXTURES / "utf8.csv", deteccion=deteccion,
        ruta_parquet=tmp_path / "compras.parquet",
    )

    resumen = ingerir(dataset, mapeo, cfg=cfg)

    assert resumen.filas_leidas == 3
    assert resumen.filas_validas == 3
    assert resumen.descartadas == {}
    assert validar_parquet(resumen.ruta_parquet, cfg=cfg) == []

    filas = _leer_parquet(Path(resumen.ruta_parquet), cfg)
    assert [f["cliente_id"] for f in filas] == ["1", "2", "3"]
    assert filas[0]["producto_id_tipo"] == "sku"
    assert filas[0]["producto_nombre"] == "Café especial"
    assert filas[0]["precio_unitario"] == pytest.approx(10.50)


def test_separador_punto_y_coma_y_fecha_dd_mm_aaaa(tmp_path, cfg) -> None:
    deteccion = detectar(FIXTURES / "separador_punto_y_coma.csv", cfg=cfg)
    assert deteccion.separador == ";"
    mapeo = _mapeo(
        {"cliente_id": "cliente_id", "fecha": "fecha", "producto_id": "producto_id"},
        producto_id_tipo="sku", formato_fecha="dd/mm/aaaa",
    )
    dataset = DatasetAIngerir(
        ruta_csv=FIXTURES / "separador_punto_y_coma.csv", deteccion=deteccion,
        ruta_parquet=tmp_path / "compras.parquet",
    )

    resumen = ingerir(dataset, mapeo, cfg=cfg)

    assert resumen.filas_leidas == 2
    assert resumen.filas_validas == 2
    assert resumen.descartadas == {}
    filas = _leer_parquet(Path(resumen.ruta_parquet), cfg)
    assert filas[0]["fecha"].isoformat() == "2024-01-05T00:00:00"


def test_decimales_con_coma_se_castean_a_double(tmp_path, cfg) -> None:
    deteccion_fixture = detectar(FIXTURES / "decimales_coma.csv", cfg=cfg)
    precio = next(c for c in deteccion_fixture.columnas if c.nombre == "precio_unitario")
    assert precio.separador_decimal == "coma"

    csv = tmp_path / "numeros.csv"
    csv.write_text(
        "cliente_id;fecha;producto_id;precio_unitario;valor_total\n"
        "1;2024-01-05;SKU001;10,50;21,00\n"
    )
    deteccion = detectar(csv, cfg=cfg)
    mapeo = _mapeo(
        {
            "cliente_id": "cliente_id", "fecha": "fecha", "producto_id": "producto_id",
            "precio_unitario": "precio_unitario", "valor_total": "valor_total",
        },
        producto_id_tipo="sku", formato_fecha="aaaa-mm-dd",
    )
    dataset = DatasetAIngerir(
        ruta_csv=csv, deteccion=deteccion, ruta_parquet=tmp_path / "compras.parquet"
    )

    resumen = ingerir(dataset, mapeo, cfg=cfg)

    filas = _leer_parquet(Path(resumen.ruta_parquet), cfg)
    assert filas[0]["precio_unitario"] == pytest.approx(10.50)
    assert filas[0]["valor_total"] == pytest.approx(21.00)


def test_descartes_por_motivo(tmp_path, cfg) -> None:
    csv = tmp_path / "con_errores.csv"
    csv.write_text(
        "cliente_id,fecha,producto_id,marca\n"
        "1,2024-01-05,SKU001,Marca  Buena\n"
        " ,2024-01-06,SKU002,Marca X\n"
        "3,fecha-invalida,SKU003,Marca Y\n"
        "4,2024-01-07, ,Marca Z\n"
    )
    deteccion = detectar(csv, cfg=cfg)
    mapeo = _mapeo(
        {
            "cliente_id": "cliente_id", "fecha": "fecha", "producto_id": "producto_id",
            "marca": "marca",
        },
        producto_id_tipo="sku", formato_fecha="aaaa-mm-dd",
    )
    dataset = DatasetAIngerir(
        ruta_csv=csv, deteccion=deteccion, ruta_parquet=tmp_path / "compras.parquet"
    )

    resumen = ingerir(dataset, mapeo, cfg=cfg)

    assert resumen.filas_leidas == 4
    assert resumen.filas_validas == 1
    assert resumen.descartadas == {
        MOTIVO_CLIENTE_VACIO: 1, MOTIVO_FECHA_INVALIDA: 1, MOTIVO_PRODUCTO_VACIO: 1,
    }
    filas = _leer_parquet(Path(resumen.ruta_parquet), cfg)
    assert len(filas) == 1
    assert filas[0]["marca"] == "Marca Buena"


def test_cliente_id_numerico_no_pierde_ceros_a_la_izquierda(tmp_path, cfg) -> None:
    csv = tmp_path / "ids.csv"
    csv.write_text("cliente_id,fecha,producto_id\n007,2024-01-05,SKU001\n")
    deteccion = detectar(csv, cfg=cfg)
    mapeo = _mapeo(
        {"cliente_id": "cliente_id", "fecha": "fecha", "producto_id": "producto_id"},
        producto_id_tipo="sku", formato_fecha="aaaa-mm-dd",
    )
    dataset = DatasetAIngerir(
        ruta_csv=csv, deteccion=deteccion, ruta_parquet=tmp_path / "compras.parquet"
    )

    resumen = ingerir(dataset, mapeo, cfg=cfg)

    filas = _leer_parquet(Path(resumen.ruta_parquet), cfg)
    assert filas[0]["cliente_id"] == "007"


def test_progreso_se_llama_por_cada_umbral_de_filas(tmp_path, cfg, monkeypatch) -> None:
    monkeypatch.setattr(ingesta_mod, "_FILAS_PROGRESO", 2)
    monkeypatch.setattr(ingesta_mod, "_TAMANO_LOTE", 1)

    csv = tmp_path / "varias.csv"
    filas_csv = "\n".join(f"{i},2024-01-0{i},SKU00{i}" for i in range(1, 6))
    csv.write_text("cliente_id,fecha,producto_id\n" + filas_csv + "\n")
    deteccion = detectar(csv, cfg=cfg)
    mapeo = _mapeo(
        {"cliente_id": "cliente_id", "fecha": "fecha", "producto_id": "producto_id"},
        producto_id_tipo="sku", formato_fecha="aaaa-mm-dd",
    )
    dataset = DatasetAIngerir(
        ruta_csv=csv, deteccion=deteccion, ruta_parquet=tmp_path / "compras.parquet"
    )

    llamadas: list[dict] = []
    ingerir(dataset, mapeo, progreso=lambda etapa, contadores: llamadas.append(contadores), cfg=cfg)

    # Con 5 filas, lotes de 1 y umbral 2: avisos a las 2, 4 y 5 filas leídas (el último, final).
    assert [c["leidas"] for c in llamadas] == [2, 4, 5]
