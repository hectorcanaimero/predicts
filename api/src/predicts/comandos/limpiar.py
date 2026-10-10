"""Comando `predicts limpiar`: aplica la retención de archivos a mano (ver `predicts.retencion`),
sin esperar a que el worker la encole."""

from __future__ import annotations

import typer

from predicts.comandos import comando
from predicts.config import settings
from predicts.db.sesion import SessionLocal
from predicts.retencion import limpiar as ejecutar_limpieza


@comando
def limpiar(
    dry_run: bool = typer.Option(  # noqa: B008
        False, "--dry-run", help="Solo informa qué archivaría/borraría, sin tocar nada."
    ),
) -> None:
    """Archiva los datasets con más de `RETENCION_DIAS` desde la subida y limpia `DATA_DIR/tmp`."""
    db = SessionLocal()
    try:
        resultado = ejecutar_limpieza(db, settings(), dry_run=dry_run)
    finally:
        db.close()

    verbo_datasets = "a archivar" if dry_run else "archivados"
    typer.echo(f"datasets {verbo_datasets}: {len(resultado.datasets_archivados)}")
    for dataset_id in resultado.datasets_archivados:
        typer.echo(f"  {dataset_id}")

    verbo_tmp = "a borrar" if dry_run else "borrados"
    typer.echo(f"tmp {verbo_tmp}: {len(resultado.tmp_borrados)}")
    for ruta in resultado.tmp_borrados:
        typer.echo(f"  {ruta}")
