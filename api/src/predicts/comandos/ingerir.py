"""Comando `predicts ingerir`: ingesta + calidad sin pasar por la base de datos, para
pruebas y medición de rendimiento (tiempo y memoria pico con un CSV grande, ver F3.3.T1)."""

from __future__ import annotations

from pathlib import Path

import typer

from predicts.comandos import comando
from predicts.datos.calidad import calcular
from predicts.datos.deteccion import detectar
from predicts.datos.ingesta import DatasetAIngerir
from predicts.datos.ingesta import ingerir as ejecutar_ingesta
from predicts.datos.mapeo import MapeoConfirmado


@comando
def ingerir(
    csv: Path = typer.Argument(..., help="CSV a ingerir."),  # noqa: B008
    mapeo: Path = typer.Option(..., "--mapeo", help="Mapeo confirmado (JSON)."),  # noqa: B008
    salida: Path = typer.Option(..., "--salida", help="Carpeta de salida."),  # noqa: B008
) -> None:
    """Detecta `csv`, lo ingiere con `--mapeo` y escribe `compras.parquet` más los informes
    de ingesta y calidad en `--salida`."""
    deteccion = detectar(csv)
    mapeo_confirmado = MapeoConfirmado.model_validate_json(mapeo.read_text())
    dataset = DatasetAIngerir(
        ruta_csv=csv, deteccion=deteccion, ruta_parquet=salida / "compras.parquet"
    )

    resumen = ejecutar_ingesta(
        dataset, mapeo_confirmado,
        progreso=lambda etapa, contadores: typer.echo(f"{etapa}: {contadores}"),
    )
    informe = calcular(resumen.ruta_parquet, descartes_ingesta=resumen.descartadas)

    salida.mkdir(parents=True, exist_ok=True)
    (salida / "resumen_ingesta.json").write_text(resumen.model_dump_json(indent=2))
    (salida / "informe_calidad.json").write_text(informe.model_dump_json(indent=2))

    typer.echo(
        f"compras: {resumen.ruta_parquet} ({resumen.filas_validas}/{resumen.filas_leidas} filas)"
    )
    typer.echo(f"descartadas: {resumen.descartadas}")
    typer.echo(f"clientes: {informe.clientes}, productos: {informe.productos}")
