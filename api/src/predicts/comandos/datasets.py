"""Comando `predicts preparar-dataset`."""

from __future__ import annotations

import enum
from pathlib import Path

import typer

from predicts.comandos import comando
from predicts.datos.datasets_publicos import preparar_instacart, preparar_online_retail


class _Dataset(enum.StrEnum):
    ONLINE_RETAIL = "online-retail"
    INSTACART = "instacart"


@comando
def preparar_dataset(
    dataset: _Dataset = typer.Argument(..., help="Dataset a preparar."),  # noqa: B008
    salida: Path = typer.Option(..., "--salida", help="Parquet de compras a escribir."),  # noqa: B008
    muestra: int = typer.Option(  # noqa: B008
        None, "--muestra", help="Tomar solo N clientes al azar (con --semilla)."
    ),
    semilla: int = typer.Option(0, "--semilla", help="Semilla para --muestra."),  # noqa: B008
    desde: Path = typer.Option(  # noqa: B008
        None, "--desde", help="Carpeta con los CSV originales de Instacart."
    ),
) -> None:
    """Descarga/mapea un dataset público al esquema interno y lo escribe en `--salida`."""
    if dataset is _Dataset.ONLINE_RETAIL:
        conteos = preparar_online_retail(salida, muestra=muestra, semilla=semilla)
    else:
        try:
            conteos = preparar_instacart(salida, carpeta=desde, muestra=muestra, semilla=semilla)
        except ValueError as error:
            typer.echo(str(error), err=True)
            raise typer.Exit(code=1) from error

    typer.echo(f"compras: {salida} ({conteos.filas} filas)")
    typer.echo(f"clientes: {conteos.clientes}, productos: {conteos.productos}")
    typer.echo(f"fechas: {conteos.fecha_min} .. {conteos.fecha_max}")
