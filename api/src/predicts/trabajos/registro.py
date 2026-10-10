"""Registro de tipos de trabajo.

Cada fase define los suyos en `predicts/trabajos/tipos_<algo>.py` con `@tipo_trabajo("nombre")`;
el worker llama a `descubrir()` para importarlos sin tocar este archivo.

La función de un tipo recibe un `TrabajoEnCurso` y corre en el subproceso del worker, así que
debe estar definida a nivel de módulo (se pasa por referencia al hijo con `spawn`).
"""

from __future__ import annotations

import importlib
import pkgutil
import uuid
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class TrabajoEnCurso:
    id: uuid.UUID
    empresa_id: uuid.UUID
    tipo: str
    parametros: dict


FuncionTrabajo = Callable[[TrabajoEnCurso], None]

_tipos: dict[str, FuncionTrabajo] = {}


def tipo_trabajo(nombre: str) -> Callable[[FuncionTrabajo], FuncionTrabajo]:
    def decorador(func: FuncionTrabajo) -> FuncionTrabajo:
        if _tipos.get(nombre, func) is not func:
            raise ValueError(f"tipo de trabajo duplicado: {nombre}")
        _tipos[nombre] = func
        return func

    return decorador


def obtener(nombre: str) -> FuncionTrabajo | None:
    return _tipos.get(nombre)


def descubrir() -> None:
    """Importa todos los módulos de `predicts.trabajos` para que registren sus tipos."""
    from predicts import trabajos

    for info in pkgutil.iter_modules(trabajos.__path__, f"{trabajos.__name__}."):
        importlib.import_module(info.name)
