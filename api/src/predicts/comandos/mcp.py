"""Comando `predicts mcp` (F7.1.T3): levanta el servidor MCP de `agente/mcp.py` por stdio o por
HTTP streamable (ver `docs/notas/mcp.md` para cómo conectarlo desde Claude Desktop/Code)."""

from __future__ import annotations

import typer

from predicts.agente.mcp import crear_servidor
from predicts.comandos import comando


@comando
def mcp(
    transporte: str = typer.Option(
        "stdio", "--transporte", help="'stdio' (una empresa por proceso) o 'http' (multiempresa)."
    ),
    api_key: str | None = typer.Option(
        None,
        "--api-key",
        envvar="PREDICTS_API_KEY",
        help="Clave de empresa para 'stdio' (sin esto, el servidor rechaza toda llamada).",
    ),
    host: str = typer.Option("0.0.0.0", "--host", help="Host de escucha (solo 'http')."),  # noqa: B008
    port: int = typer.Option(8300, "--port", help="Puerto de escucha (solo 'http')."),  # noqa: B008
) -> None:
    """Levanta el servidor MCP: `listar_proyectos`, `listar_datasets`, `recordatorios`,
    `ciclos_producto`, `clientes_en_riesgo` y `preguntar`."""
    servidor = crear_servidor(clave=api_key)
    if transporte == "stdio":
        servidor.run(transport="stdio")
    elif transporte == "http":
        servidor.run(transport="streamable-http", host=host, port=port)
    else:
        raise typer.BadParameter("usa 'stdio' o 'http'", param_hint="--transporte")
