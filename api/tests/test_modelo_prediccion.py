"""Tests de `predicts.modelo.prediccion` y `predicts.modelo.linea_base`.

Los valores esperados se calculan con `statistics.NormalDist` (independiente
de SciPy) sobre la log-normal: `F(x) = Φ((ln x − ln ciclo) / σ)`, y el factor
de actividad `w = (1−ε)·S(t) / ((1−ε)·S(t) + ε)`.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import NormalDist

import duckdb
import pyarrow as pa
import pytest

from predicts.modelo import Ajuste, ParamsModelo, ajustar
from predicts.modelo.linea_base import linea_base
from predicts.modelo.prediccion import PREVIA_ABANDONO, predecir

FIXTURE = Path(__file__).parent / "fixtures" / "sintetico_compras.parquet"
N = NormalDist()
ULTIMA = date(2024, 1, 1)


def _ajuste(pares: list[tuple[float, float]]) -> Ajuste:
    """Ajuste a mano: un par por (ciclo, desvio_log), todos con última compra `ULTIMA`."""
    con = duckdb.connect()
    con.register(
        "_p",
        pa.table(
            {
                "cliente_id": [f"c{i}" for i in range(len(pares))],
                "producto_id": ["p"] * len(pares),
                "ciclo": [c for c, _ in pares],
                "desvio_log": [s for _, s in pares],
                "n_compras": [3] * len(pares),
                "ultima_compra": [ULTIMA] * len(pares),
            }
        ),
    )
    con.execute("CREATE TABLE ajuste_pares AS SELECT * FROM _p")
    return Ajuste(con=con, params=ParamsModelo())


def _predecir(ciclo: float, sigma: float, t: int, h: int) -> tuple:
    ajuste = _ajuste([(ciclo, sigma)])
    vista = predecir(ajuste, ULTIMA + timedelta(days=t), h)
    return ajuste.con.execute(
        f"SELECT p, fecha_probable, fecha_min, fecha_max, posible_abandono FROM {vista}"
    ).fetchone()


def _sf(x: float, ciclo: float, sigma: float) -> float:
    # erfc, no 1 − cdf: en la cola 1 − cdf se cancela a 0.
    return 0.5 * math.erfc((math.log(x) - math.log(ciclo)) / sigma / math.sqrt(2))


def _w(s_t: float) -> float:
    e = PREVIA_ABANDONO
    return (1 - e) * s_t / ((1 - e) * s_t + e)


def _dia(x: float) -> date:
    return ULTIMA + timedelta(days=round(x))


def test_t_cero_es_la_distribucion_sin_condicionar() -> None:
    # t = 0, H = ciclo → P = w(1) · F(30) = (1 − ε) · Φ(0); cuantiles de la log-normal.
    p, probable, minimo, maximo, abandono = _predecir(30, 0.5, t=0, h=30)
    assert p == pytest.approx((1 - PREVIA_ABANDONO) * 0.5)
    assert probable == _dia(30)
    assert minimo == _dia(30 * math.exp(0.5 * N.inv_cdf(0.25)))  # ≈ 21.4
    assert maximo == _dia(30 * math.exp(0.5 * N.inv_cdf(0.75)))  # ≈ 42.0
    assert not abandono


def test_condicional_a_no_haber_comprado() -> None:
    # t = 30 = ciclo, H = 30: P = (S(30) − S(60)) / S(30) = 2·Φ(ln 2 / 0.5) − 1.
    p, probable, minimo, maximo, _ = _predecir(30, 0.5, t=30, h=30)
    assert p == pytest.approx(_w(0.5) * (2 * N.cdf(math.log(2) / 0.5) - 1))  # ≈ 0.826
    # Mediana condicional: S(x) = 0.5·S(30) = 0.25 → z = Φ⁻¹(0.75).
    assert probable == _dia(30 * math.exp(0.5 * N.inv_cdf(0.75)))
    # Cuartiles condicionales: S(x) = 0.375 y 0.125.
    assert minimo == _dia(30 * math.exp(0.5 * N.inv_cdf(0.625)))
    assert maximo == _dia(30 * math.exp(0.5 * N.inv_cdf(0.875)))


def test_t_mucho_mayor_que_el_ciclo() -> None:
    # t = 100 · ciclo: S(t) ≈ 1e-53, todavía representable → comparar con la fórmula directa.
    ciclo, sigma, t, h = 10, 0.3, 1000, 14
    p, probable, _, _, abandono = _predecir(ciclo, sigma, t, h)
    s_t, s_th = _sf(t, ciclo, sigma), _sf(t + h, ciclo, sigma)
    assert 0 < s_t < 1e-50
    p_cond = (s_t - s_th) / s_t
    assert p_cond > 0.5  # la log-normal sola diría "compra ya"
    assert p == pytest.approx(_w(s_t) * p_cond, rel=1e-6)
    assert p < 1e-40
    assert abandono
    assert probable >= ULTIMA + timedelta(days=t)


def test_s_t_subdesborda_sin_dividir_por_cero() -> None:
    # z ≈ 92: S(t) = 0 en coma flotante; la fórmula ingenua daría 0/0.
    p, probable, minimo, maximo, abandono = _predecir(10, 0.1, t=100_000, h=30)
    assert _sf(100_000, 10, 0.1) == 0.0
    assert 0 <= p < 0.01
    assert abandono
    assert minimo <= probable <= maximo


def test_horizonte_grande() -> None:
    p, *_ = _predecir(30, 0.5, t=10, h=100_000)
    s_t = _sf(10, 30, 0.5)
    assert p == pytest.approx(_w(s_t) * (s_t - _sf(100_010, 30, 0.5)) / s_t)
    assert p == pytest.approx(_w(s_t), abs=1e-12)


def test_desvio_cero_no_rompe() -> None:
    p_dentro, *_ = _predecir(30, 0.0, t=20, h=14)
    p_fuera, *_ = _predecir(30, 0.0, t=0, h=14)
    assert p_dentro == pytest.approx(1 - PREVIA_ABANDONO)
    assert p_fuera == pytest.approx(0.0)


def test_horizonte_negativo() -> None:
    with pytest.raises(ValueError):
        predecir(_ajuste([(30, 0.5)]), ULTIMA, -1)


def _corte_y_verdad(con: duckdb.DuckDBPyConnection, h: int) -> date:
    """Divide el sintético en `compras_ajuste` (≤ corte) y `verdad` (compra en (corte, corte+H])."""
    con.execute(f"CREATE VIEW todas AS SELECT * FROM read_parquet('{FIXTURE}')")
    fecha_max = con.execute("SELECT CAST(max(fecha) AS DATE) FROM todas").fetchone()[0]
    corte = fecha_max - timedelta(days=60)
    con.execute(
        f"CREATE VIEW compras_ajuste AS SELECT * FROM todas WHERE CAST(fecha AS DATE) <= '{corte}'"
    )
    con.execute(
        """
        CREATE TABLE verdad AS
        SELECT DISTINCT cliente_id, producto_id FROM todas
        WHERE CAST(fecha AS DATE) > $c AND CAST(fecha AS DATE) <= $c + $h
        """,
        {"c": corte, "h": h},
    )
    return corte


def _medias(con: duckdb.DuckDBPyConnection, vista: str) -> tuple[float, float]:
    return con.execute(
        f"""
        SELECT avg(p) FILTER (WHERE v.cliente_id IS NOT NULL),
               avg(p) FILTER (WHERE v.cliente_id IS NULL)
        FROM {vista} x LEFT JOIN verdad v USING (cliente_id, producto_id)
        """
    ).fetchone()


def test_sintetico_compradores_tienen_mas_probabilidad() -> None:
    con = duckdb.connect()
    h = 30
    corte = _corte_y_verdad(con, h)
    vista = predecir(ajustar(con, "compras_ajuste", ParamsModelo()), corte, h)

    n, fuera, rango_mal = con.execute(
        f"""
        SELECT count(*),
               count(*) FILTER (WHERE p < 0 OR p > 1 OR p IS NULL),
               count(*) FILTER (WHERE NOT (fecha_min <= fecha_probable
                                           AND fecha_probable <= fecha_max))
        FROM {vista}
        """
    ).fetchone()
    assert n > 0
    assert fuera == 0
    assert rango_mal == 0

    compran, no_compran = _medias(con, vista)
    assert compran > no_compran


def test_linea_base_a_mano() -> None:
    con = duckdb.connect()
    filas = [
        ("c1", "2024-01-01"), ("c1", "2024-01-11"), ("c1", "2024-01-31"),  # prom 15 → 02-15
        ("c2", "2024-01-01"), ("c2", "2024-01-05"),  # prom 4 → 01-09 (antes de fecha_ref)
        ("c3", "2024-01-01"),  # sin intervalos: fuera
        ("c4", "2024-01-01"), ("c4", "2024-02-01"),  # prom 31 → 03-03 (después de ref + H)
    ]  # fmt: skip
    con.register(
        "compras",
        pa.table(
            {
                "cliente_id": [c for c, _ in filas],
                "producto_id": ["p"] * len(filas),
                "fecha": [datetime.fromisoformat(f) for _, f in filas],
            }
        ),
    )
    vista = linea_base(con, "compras", date(2024, 2, 1), 14)
    assert con.execute(
        f"SELECT cliente_id, ciclo, p, fecha_probable, fecha_min, fecha_max, n_compras "
        f"FROM {vista} ORDER BY cliente_id"
    ).fetchall() == [
        ("c1", 15.0, 1.0, date(2024, 2, 15), date(2024, 2, 15), date(2024, 2, 15), 3),
        ("c2", 4.0, 0.0, date(2024, 1, 9), date(2024, 1, 9), date(2024, 1, 9), 2),
        ("c4", 31.0, 0.0, date(2024, 3, 3), date(2024, 3, 3), date(2024, 3, 3), 2),
    ]


def test_linea_base_sintetico() -> None:
    con = duckdb.connect()
    h = 30
    corte = _corte_y_verdad(con, h)
    vista = linea_base(con, "compras_ajuste", corte, h)
    assert (
        con.execute(f"SELECT count(*) FILTER (WHERE p NOT IN (0, 1)) FROM {vista}").fetchone()[0]
        == 0
    )
    compran, no_compran = _medias(con, vista)
    assert compran > no_compran
