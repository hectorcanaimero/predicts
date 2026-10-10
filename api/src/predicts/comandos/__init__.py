"""Registro de comandos del CLI `predicts`.

Cada módulo de este paquete define sus comandos con el decorador `comando`;
`predicts.cli` descubre los módulos y los registra en la app Typer, así una
fase nueva agrega `predicts/comandos/<algo>.py` sin tocar `cli.py`.
"""

from collections.abc import Callable

_registro: list[Callable] = []


def comando(func: Callable) -> Callable:
    """Marca `func` como comando del CLI `predicts`."""
    _registro.append(func)
    return func


def comandos_registrados() -> list[Callable]:
    """Comandos marcados con `@comando` hasta el momento."""
    return list(_registro)
