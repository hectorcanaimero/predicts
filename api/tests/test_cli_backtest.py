"""Tests del comando `predicts backtest` con el fixture sintético."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from predicts.cli import app
from predicts.config import settings_para_tests
from predicts.modelo.backtest import MetricasBacktest

FIXTURE = Path(__file__).parent / "fixtures" / "sintetico_compras.parquet"
runner = CliRunner()


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch) -> None:
    cfg = settings_para_tests(DATA_DIR=str(tmp_path / "data"))
    monkeypatch.setattr("predicts.datos.duckdb.settings", lambda: cfg)


def test_imprime_tabla_y_escribe_json(tmp_path) -> None:
    salida = tmp_path / "r" / "resultados.json"
    args = ["backtest", str(FIXTURE), "--semanas", "8", "--horizonte", "14"]
    resultado = runner.invoke(app, [*args, "--repeticiones", "2", "--salida", str(salida)])
    assert resultado.exit_code == 0, resultado.output
    for texto in ("modelo", "línea base", "precision_at_k", "brier", "±", "ventanas=2"):
        assert texto in resultado.output

    r = MetricasBacktest.model_validate_json(salida.read_text())
    assert (r.semanas, r.horizonte, len(r.ventanas)) == (8, 14, 2)
    assert r.n_pares > 0
    assert f"{r.modelo.brier.media:.4f}" in resultado.output


def test_k_explicito() -> None:
    resultado = runner.invoke(app, ["backtest", str(FIXTURE), "--horizonte", "7", "--k", "5"])
    assert resultado.exit_code == 0, resultado.output
    assert "k=5" in resultado.output


def test_parametro_invalido_sale_con_error() -> None:
    resultado = runner.invoke(app, ["backtest", str(FIXTURE), "--semanas", "0"])
    assert resultado.exit_code == 1
