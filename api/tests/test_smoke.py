"""Test de humo: el paquete importa y el CLI corre."""

from typer.testing import CliRunner

import predicts
from predicts.cli import app

runner = CliRunner()


def test_importa_el_paquete() -> None:
    assert predicts.__version__


def test_cli_version() -> None:
    resultado = runner.invoke(app, ["version"])
    assert resultado.exit_code == 0
    assert predicts.__version__ in resultado.stdout
