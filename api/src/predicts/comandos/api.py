"""Comandos `predicts api` (uvicorn) y `predicts openapi` (escribe el OpenAPI sin
levantar el servidor; lo usa el frontend para generar sus tipos)."""

from __future__ import annotations

import json
from pathlib import Path

import typer
import uvicorn

from predicts.app import crear_app
from predicts.comandos import comando


@comando
def api(
    host: str = typer.Option("0.0.0.0", "--host", help="Host de escucha."),  # noqa: B008
    port: int = typer.Option(8000, "--port", help="Puerto de escucha."),  # noqa: B008
    reload: bool = typer.Option(False, "--reload", help="Recarga en caliente (dev)."),  # noqa: B008
) -> None:
    """Levanta la API con uvicorn."""
    uvicorn.run("predicts.app:crear_app", host=host, port=port, reload=reload, factory=True)


@comando
def openapi(
    salida: Path = typer.Option(  # noqa: B008
        ..., "--salida", help="Archivo donde escribir el esquema OpenAPI (JSON)."
    ),
) -> None:
    """Escribe el esquema OpenAPI de la API sin levantar el servidor."""
    esquema = crear_app().openapi()
    salida.write_text(json.dumps(esquema, indent=2, ensure_ascii=False), encoding="utf-8")
    typer.echo(f"openapi: {salida}")
