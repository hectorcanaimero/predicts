"""Comando `predicts sintetico`."""

from __future__ import annotations

from pathlib import Path

import typer

from predicts.comandos import comando
from predicts.datos.sintetico import escribir, generar


@comando
def sintetico(
    clientes: int = typer.Option(..., "--clientes", help="Número de clientes a generar."),  # noqa: B008
    salida: Path = typer.Option(..., "--salida", help="Parquet de compras a escribir."),  # noqa: B008
    productos: int = typer.Option(10, "--productos", help="Productos del catálogo."),  # noqa: B008
    semilla: int = typer.Option(0, "--semilla", help="Semilla del generador aleatorio."),  # noqa: B008
) -> None:
    """Genera un Parquet sintético de compras con ciclo y abandono conocidos por par."""
    resultado = generar(clientes, productos, semilla)
    ruta_verdad = escribir(resultado, salida)
    typer.echo(f"compras: {salida} ({resultado.compras.num_rows} filas)")
    typer.echo(f"verdad: {ruta_verdad} ({resultado.verdad.num_rows} pares)")
