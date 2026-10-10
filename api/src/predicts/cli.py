"""CLI `predicts`: descubre los comandos de `predicts.comandos` y los registra."""

import importlib
import pkgutil

import typer

from predicts import comandos

app = typer.Typer(name="predicts", help="CLI de predicts.")


@app.callback()
def _callback() -> None:
    """Punto de entrada del CLI `predicts` (fuerza modo multi-comando aunque haya uno solo)."""


def _descubrir_comandos() -> None:
    for info in pkgutil.iter_modules(comandos.__path__, f"{comandos.__name__}."):
        importlib.import_module(info.name)
    for func in comandos.comandos_registrados():
        app.command()(func)


_descubrir_comandos()


if __name__ == "__main__":
    app()
