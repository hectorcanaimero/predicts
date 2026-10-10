"""Tests de `predicts.modelo.backtest`."""

from __future__ import annotations

import dataclasses
import json
from datetime import date, datetime, timedelta

import duckdb
import numpy as np
import pyarrow as pa
import pytest

from predicts.datos import sintetico
from predicts.modelo import ParamsModelo
from predicts.modelo.backtest import MetricasBacktest, backtest, metricas
from predicts.modelo.prediccion import PREVIA_ABANDONO

E = PREVIA_ABANDONO
CORTE = date(2024, 3, 1)


def _cinco_pares() -> duckdb.DuckDBPyConnection:
    """5 pares con 4 compras cada 10 días exactos (σ al piso: p ≈ 1 − ε o ≈ 0), H = 7,
    semanas = 1 → corte = 03-01, ventana (03-01, 03-08].

    | par | última | t  | debería | p modelo | base | compra real     |
    | a   | 02-25  | 5  | 03-06   | 1 − ε    | 1    | 03-06 (err 0)   |
    | b   | 02-29  | 1  | 03-10   | 0        | 0    | 03-08 (err 2)   |
    | c   | 02-22  | 8  | 03-03   | 1 − ε    | 1    | no              |
    | d   | 02-26  | 4  | 03-07   | 1 − ε    | 1    | 03-07 (err 0)   |
    | e   | 02-15  | 15 | 02-25   | ≈ 0 (abandono) | 0 | no            |
    """
    ultimas = {"a": "02-25", "b": "02-29", "c": "02-22", "d": "02-26", "e": "02-15"}
    reales = {"a": "03-06", "b": "03-08", "d": "03-07"}
    filas = []
    for c, u in ultimas.items():
        ultima = date.fromisoformat(f"2024-{u}")
        filas += [(c, ultima - timedelta(days=10 * i)) for i in range(4)]
    filas += [(c, date.fromisoformat(f"2024-{r}")) for c, r in reales.items()]
    con = duckdb.connect()
    con.register(
        "compras",
        pa.table(
            {
                "cliente_id": [c for c, _ in filas],
                "producto_id": ["p"] * len(filas),
                "fecha": [datetime.combine(d, datetime.min.time()) for _, d in filas],
            }
        ),
    )
    return con


def test_cinco_pares_a_mano() -> None:
    r = backtest(_cinco_pares(), "compras", ParamsModelo(), semanas=1, horizonte=7)
    (v,) = r.ventanas
    assert v.corte == CORTE
    assert (v.n_pares, v.k) == (5, 3)  # compran a, b, d

    # Top-3 del modelo = {a, c, d} → 2 aciertos de 3 compradores.
    m = v.modelo
    assert m.precision_at_k == pytest.approx(2 / 3)
    assert m.cobertura_at_k == pytest.approx(2 / 3)
    # Brier: a ε², b 1, c (1−ε)², d ε², e 0.
    assert m.brier == pytest.approx((2 * E**2 + 1 + (1 - E) ** 2) / 5, abs=1e-6)
    assert m.mae_dias == pytest.approx(2 / 3)  # (0 + 2 + 0) / 3
    assert m.calibracion[0].n == 2 and m.calibracion[0].observado == 0.5  # b, e
    assert m.calibracion[9].n == 3 and m.calibracion[9].observado == pytest.approx(2 / 3)
    assert m.calibracion[9].predicho == pytest.approx(1 - E, abs=1e-6)

    b = v.linea_base
    assert b.precision_at_k == pytest.approx(2 / 3)
    assert b.brier == pytest.approx(2 / 5)  # b y c errados por completo
    assert b.mae_dias == pytest.approx(2 / 3)
    assert b.calibracion[9].n == 3 and b.calibracion[9].predicho == 1.0

    assert r.modelo.brier.media == m.brier and r.modelo.brier.desvio is None
    assert r.n_pares == 5
    assert MetricasBacktest.model_validate_json(r.model_dump_json()) == r
    json.loads(r.model_dump_json())  # JSON válido (sin NaN)


def test_metricas_empates_por_valor_esperado() -> None:
    # p = [1, 1, 0, 0, 0], compran el 1.º, 3.º y 4.º; K = 3: el 1 empatado
    # entra entero (1 acierto) y queda 1 lugar entre 3 ceros con 2 compradores → 2/3.
    p = np.array([1.0, 1.0, 0.0, 0.0, 0.0])
    y = np.array([True, False, True, True, False])
    err = np.array([1.0, np.nan, 3.0, 5.0, np.nan])
    m = metricas(p, y, err, k=3)
    assert m.precision_at_k == pytest.approx((1 + 2 / 3) / 3)
    assert m.cobertura_at_k == pytest.approx((1 + 2 / 3) / 3)
    assert m.brier == pytest.approx(3 / 5)
    assert m.mae_dias == pytest.approx(3.0)
    # K mayor que la población: se recorta a n.
    assert metricas(p, y, err, k=50).precision_at_k == pytest.approx(3 / 5)


def _sintetico(tmp_path, monkeypatch, sin_ruido: bool) -> str:
    if sin_ruido:
        original = sintetico._catalogo
        monkeypatch.setattr(
            sintetico,
            "_catalogo",
            lambda *a: [dataclasses.replace(p, desvio_log=0.0) for p in original(*a)],
        )
    resultado = sintetico.generar(
        150,
        8,
        semilla=7,
        fecha_inicio=date(2023, 1, 1),
        fecha_fin=date(2024, 6, 30),
        frac_durable=0.0,
        **({"sigma_cliente": 0.0, "prob_abandono": 0.0} if sin_ruido else {}),
    )
    ruta = tmp_path / "compras.parquet"
    sintetico.escribir(resultado, ruta)
    return str(ruta)


def test_sin_ruido_ambos_precisos(tmp_path, monkeypatch) -> None:
    ruta = _sintetico(tmp_path, monkeypatch, sin_ruido=True)
    r = backtest(duckdb.connect(), ruta, ParamsModelo(), semanas=4, horizonte=14)
    assert r.n_pares > 500
    assert r.modelo.precision_at_k.media >= 0.9
    assert r.linea_base.precision_at_k.media >= 0.9


def test_con_ruido_modelo_supera_linea_base_en_brier(tmp_path, monkeypatch) -> None:
    ruta = _sintetico(tmp_path, monkeypatch, sin_ruido=False)
    r = backtest(duckdb.connect(), ruta, ParamsModelo(), semanas=8, horizonte=14, repeticiones=3)
    assert len(r.ventanas) == 3
    cortes = [v.corte for v in r.ventanas]
    assert cortes[0] - cortes[1] == cortes[1] - cortes[2] == timedelta(days=14)
    for v in r.ventanas:
        assert v.modelo.brier < v.linea_base.brier
    assert r.modelo.brier.desvio is not None
    assert r.n_pares == sum(v.n_pares for v in r.ventanas)


def test_parametros_invalidos() -> None:
    with pytest.raises(ValueError):
        backtest(_cinco_pares(), "compras", ParamsModelo(), semanas=0, horizonte=7)
    with pytest.raises(ValueError):
        backtest(_cinco_pares(), "compras", ParamsModelo(), semanas=1, horizonte=7, k=0)
