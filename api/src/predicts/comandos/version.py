"""Comando `predicts version`."""

from predicts import __version__
from predicts.comandos import comando


@comando
def version() -> None:
    """Imprime la versión instalada de predicts."""
    print(__version__)
