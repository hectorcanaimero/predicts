"""Render de una plantilla por fila de resultado: siempre en código, nunca con el LLM.

Marcadores soportados: `{producto}`, `{dias}`, `{oferta}`, `{nombre_tienda}`. `render` reemplaza
los que vengan en `valores` y falla si queda alguno sin reemplazar (clave faltante en `valores`
o marcador que el LLM no debió usar).
"""

from __future__ import annotations

import re
from collections.abc import Mapping

MARCADORES_PERMITIDOS = frozenset({"producto", "dias", "oferta", "nombre_tienda"})
_MARCADOR = re.compile(r"\{(\w*)\}")


def render(texto: str, valores: Mapping[str, str]) -> str:
    """Completa `texto` con `valores` (clave → valor); lanza `ValueError` si queda algún
    `{marcador}` sin reemplazar."""
    resultado = texto
    for clave, valor in valores.items():
        resultado = resultado.replace(f"{{{clave}}}", str(valor))
    sobrantes = set(_MARCADOR.findall(resultado))
    if sobrantes:
        raise ValueError(f"marcadores sin reemplazar: {sorted(sobrantes)}")
    return resultado
