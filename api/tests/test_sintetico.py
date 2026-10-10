"""Tests de `predicts.datos.sintetico`: esquema, ciclo real por par y abandono."""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date
from pathlib import Path

import pytest

from predicts.config import settings_para_tests
from predicts.datos.esquema import validar_parquet
from predicts.datos.sintetico import escribir, generar

_CFG = settings_para_tests()

# Semilla fija: el generador es determinístico, así que estos números no cambian entre corridas.
_PARAMS = dict(
    n_clientes=30,
    productos=5,
    semilla=42,
    fecha_inicio=date(2022, 1, 1),
    fecha_fin=date(2024, 1, 1),
)


@pytest.fixture(scope="module")
def resultado():
    return generar(**_PARAMS)


def _intervalos_por_par(compras: list[dict]) -> dict[tuple[str, str], list[int]]:
    fechas_por_par: dict[tuple[str, str], list] = defaultdict(list)
    for fila in compras:
        fechas_por_par[(fila["cliente_id"], fila["producto_id"])].append(fila["fecha"])
    return {
        par: [(f[i + 1] - f[i]).days for i in range(len(f) - 1)]
        for par, f in ((p, sorted(fs)) for p, fs in fechas_por_par.items())
    }


def test_compras_cumplen_el_esquema_interno(resultado, tmp_path: Path) -> None:
    ruta = tmp_path / "compras.parquet"
    escribir(resultado, ruta)
    assert validar_parquet(ruta, cfg=_CFG) == []


def test_escribir_genera_tambien_la_verdad(resultado, tmp_path: Path) -> None:
    ruta = tmp_path / "compras.parquet"
    ruta_verdad = escribir(resultado, ruta)
    assert ruta_verdad.name == "compras.verdad.parquet"
    assert ruta_verdad.exists()


def test_mediana_de_intervalos_por_par_coincide_con_el_ciclo_real(resultado) -> None:
    compras = resultado.compras.to_pylist()
    verdad = {(v["cliente_id"], v["producto_id"]): v for v in resultado.verdad.to_pylist()}
    intervalos_por_par = _intervalos_por_par(compras)

    razones = []
    pares_evaluados = 0
    pares_dentro_de_tolerancia = 0
    for par, intervalos in intervalos_por_par.items():
        ciclo_real = verdad[par]["ciclo_real"]
        if ciclo_real is None or len(intervalos) < 4:
            continue
        pares_evaluados += 1
        mediana = statistics.median(intervalos)
        razon = mediana / ciclo_real
        razones.append(razon)
        if abs(razon - 1) <= 0.10:
            pares_dentro_de_tolerancia += 1

    assert pares_evaluados >= 30, "muy pocos pares con historia suficiente para medir"
    # La mediana de una log-normal con media log(ciclo_real) es exactamente
    # ciclo_real sin importar el desvío, así que la razón agregada (robusta al
    # ruido de cada par individual) debe quedar muy cerca de 1.
    assert abs(statistics.median(razones) - 1) <= 0.10
    # Y una mayoría clara de los pares individuales también debe caer en la
    # tolerancia (algunos pares con pocos intervalos quedan fuera por ruido).
    assert pares_dentro_de_tolerancia / pares_evaluados >= 0.7


def test_productos_durables_tienen_una_sola_compra_por_cliente(resultado) -> None:
    compras = resultado.compras.to_pylist()
    conteos = defaultdict(int)
    for fila in compras:
        conteos[(fila["cliente_id"], fila["producto_id"])] += 1

    durables = [v for v in resultado.verdad.to_pylist() if v["ciclo_real"] is None]
    assert durables, "la fixture de este test debería generar al menos un par durable"
    for v in durables:
        assert v["abandono_en"] is None
        assert conteos[(v["cliente_id"], v["producto_id"])] == 1


def test_pares_abandonados_no_compran_despues_de_abandono_en(resultado) -> None:
    compras = resultado.compras.to_pylist()
    fechas_por_par: dict[tuple[str, str], list] = defaultdict(list)
    for fila in compras:
        fechas_por_par[(fila["cliente_id"], fila["producto_id"])].append(fila["fecha"])

    abandonados = [v for v in resultado.verdad.to_pylist() if v["abandono_en"] is not None]
    assert abandonados, "la fixture de este test debería generar al menos un par abandonado"
    for v in abandonados:
        par = (v["cliente_id"], v["producto_id"])
        assert all(f <= v["abandono_en"] for f in fechas_por_par[par])


def test_generar_valida_los_argumentos() -> None:
    with pytest.raises(ValueError):
        generar(n_clientes=0, productos=1, semilla=0)
    with pytest.raises(ValueError):
        generar(n_clientes=1, productos=0, semilla=0)
    with pytest.raises(ValueError):
        generar(
            n_clientes=1,
            productos=1,
            semilla=0,
            fecha_inicio=date(2024, 1, 1),
            fecha_fin=date(2023, 1, 1),
        )
