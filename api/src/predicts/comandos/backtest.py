"""Comando `predicts backtest`."""

from __future__ import annotations

from pathlib import Path

import typer

from predicts.comandos import comando
from predicts.datos.duckdb import conexion_duckdb
from predicts.modelo import ParamsModelo
from predicts.modelo.backtest import Estadistico
from predicts.modelo.backtest import backtest as medir


def _fmt(e: Estadistico) -> str:
    if e.media is None:
        return "-"
    return f"{e.media:.4f}" + (f" ± {e.desvio:.4f}" if e.desvio is not None else "")


@comando
def backtest(
    compras: Path = typer.Argument(..., help="Parquet de compras (esquema interno)."),  # noqa: B008
    semanas: int = typer.Option(8, "--semanas", help="Corte = última fecha − N semanas."),  # noqa: B008
    horizonte: int = typer.Option(14, "--horizonte", help="Días de la ventana a predecir."),  # noqa: B008
    k: int = typer.Option(  # noqa: B008
        None, "--k", help="Top-K para precisión/cobertura (por defecto: compradores reales)."
    ),
    repeticiones: int = typer.Option(1, "--repeticiones", help="Ventanas hacia atrás."),  # noqa: B008
    salida: Path = typer.Option(  # noqa: B008
        None, "--salida", help="JSON con las métricas completas (incluye calibración)."
    ),
) -> None:
    """Mide el modelo contra la línea base en ventanas pasadas e imprime la comparación."""
    try:
        r = medir(
            conexion_duckdb(),
            str(compras),
            ParamsModelo(),
            semanas,
            horizonte,
            k=k,
            repeticiones=repeticiones,
        )
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error

    typer.echo(
        f"modelo {r.version_modelo} · semanas={r.semanas} horizonte={r.horizonte} "
        f"ventanas={len(r.ventanas)} pares={r.n_pares} k={r.k or 'compradores reales'}"
    )
    filas = [("métrica", "modelo", "línea base")] + [
        (campo, _fmt(getattr(r.modelo, campo)), _fmt(getattr(r.linea_base, campo)))
        for campo in ("precision_at_k", "cobertura_at_k", "brier", "mae_dias")
    ]
    anchos = [max(len(f[i]) for f in filas) for i in range(3)]
    for f in filas:
        typer.echo("  ".join(c.ljust(a) for c, a in zip(f, anchos, strict=True)).rstrip())

    if salida is not None:
        salida.parent.mkdir(parents=True, exist_ok=True)
        salida.write_text(r.model_dump_json(indent=2))
        typer.echo(f"resultados: {salida}")
