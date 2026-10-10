"""Tests de `datos/deteccion.py` con los fixtures de `tests/fixtures/csv/`."""

from __future__ import annotations

from pathlib import Path

import pytest

from predicts.config import settings_para_tests
from predicts.datos.deteccion import detectar
from predicts.errores import ErrorApi

FIXTURES = Path(__file__).parent / "fixtures" / "csv"


@pytest.fixture()
def cfg(tmp_path):
    return settings_para_tests(DATA_DIR=str(tmp_path))


def _columna(deteccion, nombre):
    return next(c for c in deteccion.columnas if c.nombre == nombre)


def test_utf8_basico(cfg) -> None:
    d = detectar(FIXTURES / "utf8.csv", cfg=cfg)

    assert d.codificacion == "utf-8"
    assert d.separador == ","
    assert d.encabezado is True
    assert [c.nombre for c in d.columnas] == [
        "cliente_id",
        "fecha",
        "producto_id",
        "producto_id_tipo",
        "producto_nombre",
        "cantidad",
        "precio_unitario",
    ]
    assert len(d.vista_previa) == 3
    assert d.vista_previa[0]["producto_nombre"] == "Café especial"


def test_fecha_aaaa_mm_dd_detectada_con_100_por_ciento(cfg) -> None:
    d = detectar(FIXTURES / "utf8.csv", cfg=cfg)

    fecha = _columna(d, "fecha")
    candidato = next(c for c in fecha.candidatos_fecha if c.formato == "aaaa-mm-dd")
    assert candidato.porcentaje == 1.0


def test_decimal_con_punto_detectado(cfg) -> None:
    d = detectar(FIXTURES / "utf8.csv", cfg=cfg)

    precio = _columna(d, "precio_unitario")
    assert precio.separador_decimal == "punto"


def test_latin1_con_acentos_decodifica_correctamente(cfg) -> None:
    d = detectar(FIXTURES / "latin1_acentos.csv", cfg=cfg)

    # cp1252 y latin-1 decodifican igual estos acentos (ninguno usa 0x80-0x9F); lo que
    # importa es que el contenido salga correcto, no la etiqueta exacta.
    assert d.codificacion in ("latin-1", "cp1252")
    nombre = _columna(d, "nombre")
    assert nombre.valores_muestra == ["José Pérez", "María González", "Álvaro Nuñez"]
    ciudad = _columna(d, "ciudad")
    assert ciudad.valores_muestra == ["São Paulo", "León", "Curitiba"]


def test_separador_punto_y_coma(cfg) -> None:
    d = detectar(FIXTURES / "separador_punto_y_coma.csv", cfg=cfg)

    assert d.separador == ";"
    assert [c.nombre for c in d.columnas] == ["cliente_id", "fecha", "producto_id", "cantidad"]


def test_decimales_con_coma(cfg) -> None:
    d = detectar(FIXTURES / "decimales_coma.csv", cfg=cfg)

    precio = _columna(d, "precio_unitario")
    assert precio.separador_decimal == "coma"
    assert precio.valores_muestra == ["10,50", "15,90", "5,20"]


def test_fechas_dd_mm_aaaa_mejor_candidato(cfg) -> None:
    d = detectar(FIXTURES / "fechas_dd_mm_aaaa.csv", cfg=cfg)

    fecha = _columna(d, "fecha")
    por_formato = {c.formato: c.porcentaje for c in fecha.candidatos_fecha}
    assert por_formato["dd/mm/aaaa"] == 1.0
    assert por_formato["aaaa-mm-dd"] == 0.0


def test_csv_sin_encabezado(cfg) -> None:
    d = detectar(FIXTURES / "sin_encabezado.csv", cfg=cfg)

    assert d.encabezado is False
    assert [c.nombre for c in d.columnas] == ["column0", "column1", "column2"]
    assert d.vista_previa[0]["column1"] == "manzana"


def test_archivo_vacio_no_rompe(cfg) -> None:
    d = detectar(FIXTURES / "vacio.csv", cfg=cfg)

    assert d.columnas == []
    assert d.vista_previa == []


def test_archivo_binario_disfrazado_corta_con_422(cfg) -> None:
    with pytest.raises(ErrorApi) as exc:
        detectar(FIXTURES / "binario_disfrazado.csv", cfg=cfg)

    assert exc.value.codigo == "codificacion_no_detectada"
    assert exc.value.status == 422


def test_porcentaje_nulos(cfg, tmp_path) -> None:
    ruta = tmp_path / "con_nulos.csv"
    ruta.write_text("a,b\n1,x\n2,\n3,y\n4,\n", encoding="utf-8")

    d = detectar(ruta, cfg=cfg)

    b = _columna(d, "b")
    assert b.porcentaje_nulos == 0.5
