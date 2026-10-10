#!/usr/bin/env python3
"""Genera los fixtures sintéticos chicos de `api/tests/fixtures/` con semilla fija.

Uso: `uv run --project api python ../scripts/generar_fixtures.py` (o
`api/.venv/bin/python scripts/generar_fixtures.py` desde la raíz del repo).
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "api" / "src"))

from predicts.datos.sintetico import escribir, generar  # noqa: E402

SALIDA = RAIZ / "api" / "tests" / "fixtures" / "sintetico_compras.parquet"


def main() -> None:
    resultado = generar(
        n_clientes=35,
        productos=6,
        semilla=20261009,
        fecha_inicio=date(2022, 1, 1),
        fecha_fin=date(2023, 7, 1),
    )
    ruta_verdad = escribir(resultado, SALIDA)
    print(f"compras: {SALIDA} ({resultado.compras.num_rows} filas)")
    print(f"verdad: {ruta_verdad} ({resultado.verdad.num_rows} pares)")


if __name__ == "__main__":
    main()
