"""Tests de `predicts.modelo.ciclos`: intervalos, ciclo contraído y exclusiones."""

from __future__ import annotations

import statistics
from datetime import date, datetime
from pathlib import Path

import duckdb
import pyarrow as pa
import pytest

from predicts.datos.sintetico import generar
from predicts.modelo import ParamsModelo, ajustar, intervalos

FIXTURE = Path(__file__).parent / "fixtures" / "sintetico_compras.parquet"
FIXTURE_VERDAD = Path(__file__).parent / "fixtures" / "sintetico_compras.verdad.parquet"


def _con_compras(filas: list[tuple[str, str, str]]) -> duckdb.DuckDBPyConnection:
    """Conexión con una tabla `compras` mínima (cliente, producto, fecha ISO)."""
    con = duckdb.connect()
    tabla = pa.table(
        {
            "cliente_id": [f[0] for f in filas],
            "producto_id": [f[1] for f in filas],
            "fecha": [datetime.fromisoformat(f[2]) for f in filas],
        }
    )
    con.register("compras", tabla)
    return con


def _errores(con: duckdb.DuckDBPyConnection, n_min: int, n_max: int) -> tuple[float, float]:
    """Error relativo absoluto medio (contraído, solo par) contra `ciclo_real`."""
    return con.execute(
        """
        SELECT avg(abs(p.ciclo / v.ciclo_real - 1)),
               avg(abs(p.med_cliente / v.ciclo_real - 1))
        FROM ajuste_pares p JOIN verdad v USING (cliente_id, producto_id)
        WHERE p.n_intervalos BETWEEN ? AND ?
        """,
        [n_min, n_max],
    ).fetchone()


def test_mismo_dia_es_una_sola_compra() -> None:
    con = _con_compras(
        [
            ("c1", "p1", "2024-01-01T09:00"),
            ("c1", "p1", "2024-01-01T18:00"),
            ("c1", "p1", "2024-01-11T10:00"),
            ("c1", "p1", "2024-01-31T10:00"),
        ]
    )
    vista = intervalos(con, "compras")
    filas = con.execute(f"SELECT dia, intervalo, n_compra FROM {vista} ORDER BY dia").fetchall()
    assert filas == [
        (date(2024, 1, 1), None, 1),
        (date(2024, 1, 11), 10, 2),
        (date(2024, 1, 31), 20, 3),
    ]


def test_formulas_a_mano() -> None:
    # c1: intervalos 10, 20 → med 15, mad 5, n 2
    # c2: intervalos 30, 30, 30 → med 30, mad 0, n 3
    # producto: med de medianas = 22.5; residuos de pares con ≥3 intervalos: c2 → 0
    con = _con_compras(
        [
            ("c1", "p1", "2024-01-01"),
            ("c1", "p1", "2024-01-11"),
            ("c1", "p1", "2024-01-31"),
            ("c2", "p1", "2024-01-01"),
            ("c2", "p1", "2024-01-31"),
            ("c2", "p1", "2024-03-01"),
            ("c2", "p1", "2024-03-31"),
        ]
    )
    ajuste = ajustar(con, "compras", ParamsModelo(k=2))
    pares = {
        r[0]: r[1:]
        for r in con.execute(
            f"SELECT cliente_id, n_intervalos, med_cliente, mad_cliente, med_producto, ciclo "
            f"FROM {ajuste.pares}"
        ).fetchall()
    }
    assert pares["c1"][:4] == (2, 15.0, 5.0, 22.5)
    assert pares["c1"][4] == pytest.approx((2 * 15 + 2 * 22.5) / 4)
    assert pares["c2"][4] == pytest.approx((3 * 30 + 2 * 22.5) / 5)
    producto = con.execute(
        f"SELECT med_producto, clientes_recurrentes, desvio_log FROM {ajuste.productos}"
    ).fetchone()
    assert producto == (22.5, 2, 0.0)


def test_pares_con_poca_historia_quedan_excluidos_con_motivo() -> None:
    con = _con_compras(
        [
            ("c1", "p1", "2024-01-01"),
            ("c1", "p1", "2024-01-11"),
            ("c1", "p1", "2024-01-21"),
            ("c2", "p1", "2024-01-01"),
            ("c2", "p1", "2024-01-15"),
            ("c3", "durable", "2024-01-01"),
        ]
    )
    ajuste = ajustar(con, "compras", ParamsModelo(min_compras=3))
    assert con.execute(f"SELECT cliente_id FROM {ajuste.pares}").fetchall() == [("c1",)]
    excluidos = con.execute(
        f"SELECT cliente_id, producto_id, n_compras, motivo FROM {ajuste.excluidos} "
        "ORDER BY cliente_id"
    ).fetchall()
    assert excluidos == [
        ("c2", "p1", 2, "historia_insuficiente"),
        ("c3", "durable", 1, "historia_insuficiente"),
    ]


def test_ciclo_dentro_del_15_por_ciento_en_el_sintetico() -> None:
    con = duckdb.connect()
    con.execute(f"CREATE VIEW verdad AS SELECT * FROM read_parquet('{FIXTURE_VERDAD}')")
    ajuste = ajustar(con, str(FIXTURE), ParamsModelo())
    evaluados, dentro = con.execute(
        f"""
        SELECT count(*), count(*) FILTER (abs(p.ciclo / v.ciclo_real - 1) <= 0.15)
        FROM {ajuste.pares} p JOIN verdad v USING (cliente_id, producto_id)
        WHERE p.n_compras >= 4
        """
    ).fetchone()
    assert evaluados >= 50
    assert dentro / evaluados >= 0.8


def test_contraccion_mejora_pares_con_pocos_intervalos() -> None:
    # Ventana corta (≈3,5 meses, ciclos de 10–45 días): muchos pares con 2–3 intervalos.
    resultado = generar(
        n_clientes=300,
        productos=8,
        semilla=7,
        fecha_inicio=date(2024, 1, 1),
        fecha_fin=date(2024, 4, 15),
        prob_abandono=0.0,
    )
    con = duckdb.connect()
    con.register("compras", resultado.compras)
    con.register("verdad", resultado.verdad)
    ajustar(con, "compras", ParamsModelo(k=2))
    n = con.execute("SELECT count(*) FROM ajuste_pares WHERE n_intervalos IN (2, 3)").fetchone()[0]
    assert n >= 100
    contraido, solo_par = _errores(con, 2, 3)
    assert contraido < solo_par


def test_desvio_log_por_producto_aproxima_el_ruido_del_generador() -> None:
    # Los productos de recompra del generador tienen desvío log en [0.15, 0.3].
    resultado = generar(n_clientes=80, productos=6, semilla=3)
    con = duckdb.connect()
    con.register("compras", resultado.compras)
    ajuste = ajustar(con, "compras", ParamsModelo())
    desvios = [r[0] for r in con.execute(f"SELECT desvio_log FROM {ajuste.productos}").fetchall()]
    assert desvios
    assert 0.1 <= statistics.median(desvios) <= 0.35


def test_params_invalidos() -> None:
    with pytest.raises(ValueError):
        ParamsModelo(k=-1)
    with pytest.raises(ValueError):
        ParamsModelo(min_compras=1)
