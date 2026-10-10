"""Comando `predicts medir-mapeo`: corre `datos.mapeo.sugerir` con Jev real sobre el set de
CSVs desordenados (`api/tests/fixtures/desordenados/`, ver `scripts/generar_desordenados.py`) y
reporta acierto por columna y por campo, acierto del prellenado y costo. Ver
specs/f3-entrada-datos.md#F3.2.T2 y docs/notas/mapeo.md para la medición real."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import typer
from sqlalchemy.orm import Session
from typesafe_sdk import TypeSafeClient

from predicts.comandos import comando
from predicts.config import Settings, settings
from predicts.datos.deteccion import detectar
from predicts.datos.mapeo import IGNORAR, sugerir
from predicts.db.modelos import Empresa
from predicts.db.sesion import SessionLocal
from predicts.ia import Contador

FIXTURES_POR_DEFECTO = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "desordenados"


@dataclass(frozen=True)
class ResultadoColumna:
    archivo: str
    columna: str
    campo_esperado: str
    campo_sugerido: str
    confianza: float
    estado: str

    @property
    def acierto(self) -> bool:
        return self.campo_sugerido == self.campo_esperado


@dataclass(frozen=True)
class ResultadoProductoIdTipo:
    archivo: str
    tipo_esperado: str
    tipo_sugerido: str

    @property
    def acierto(self) -> bool:
        return self.tipo_sugerido == self.tipo_esperado


@dataclass
class Medicion:
    columnas: list[ResultadoColumna] = field(default_factory=list)
    producto_id_tipo: list[ResultadoProductoIdTipo] = field(default_factory=list)
    costo: dict = field(default_factory=dict)

    @property
    def acierto_total(self) -> float:
        return _tasa(c.acierto for c in self.columnas)

    def acierto_por_campo(self) -> dict[str, float]:
        por_campo: dict[str, list[bool]] = {}
        for columna in self.columnas:
            por_campo.setdefault(columna.campo_esperado, []).append(columna.acierto)
        return {campo: _tasa(aciertos) for campo, aciertos in por_campo.items()}

    def acierto_prellenado(self) -> float:
        return _tasa(c.acierto for c in self.columnas if c.estado == "prellenado")

    def porcentaje_prellenado(self) -> float:
        return _tasa(c.estado == "prellenado" for c in self.columnas)

    def acierto_producto_id_tipo(self) -> float:
        return _tasa(p.acierto for p in self.producto_id_tipo)

    def errores(self) -> list[ResultadoColumna]:
        return [c for c in self.columnas if not c.acierto]


def _tasa(valores: Iterable[bool]) -> float:
    valores = list(valores)
    return sum(valores) / len(valores) if valores else 0.0


def medir(
    carpeta_fixtures: Path,
    db: Session,
    empresa_id: uuid.UUID,
    cliente: TypeSafeClient | None = None,
    cfg: Settings | None = None,
) -> Medicion:
    """Corre `sugerir()` sobre cada `<nombre>.csv` de `carpeta_fixtures` que tenga su
    `<nombre>.esperado.json`, y compara contra la verdad. Una sola `Contador` para todo el set,
    así `medicion.costo` es el costo total de la corrida."""
    cfg = cfg or settings()
    contador = Contador()
    medicion = Medicion(costo={})

    for ruta_csv in sorted(carpeta_fixtures.glob("*.csv")):
        ruta_esperado = ruta_csv.parent / f"{ruta_csv.stem}.esperado.json"
        esperado = json.loads(ruta_esperado.read_text(encoding="utf-8"))

        deteccion = detectar(ruta_csv, cfg=cfg)
        sugerencias = sugerir(
            deteccion, db, empresa_id, uuid.uuid4(), cliente=cliente, contador=contador, cfg=cfg
        )

        for sugerencia in sugerencias.columnas:
            campo_esperado = esperado["columnas"].get(sugerencia.columna, IGNORAR)
            medicion.columnas.append(
                ResultadoColumna(
                    archivo=ruta_csv.name,
                    columna=sugerencia.columna,
                    campo_esperado=campo_esperado,
                    campo_sugerido=sugerencia.campo,
                    confianza=sugerencia.confianza,
                    estado=sugerencia.estado,
                )
            )

        tipo_esperado = esperado.get("producto_id_tipo")
        if tipo_esperado is not None and sugerencias.producto_id_tipo is not None:
            medicion.producto_id_tipo.append(
                ResultadoProductoIdTipo(
                    archivo=ruta_csv.name,
                    tipo_esperado=tipo_esperado,
                    tipo_sugerido=sugerencias.producto_id_tipo.tipo,
                )
            )

    medicion.costo = contador.resumen()
    return medicion


@comando
def medir_mapeo(
    fixtures: Path = typer.Option(  # noqa: B008
        FIXTURES_POR_DEFECTO, "--fixtures", help="Carpeta con los <nombre>.csv/.esperado.json."
    ),
) -> None:
    """Corre `sugerir()` con Jev real sobre `--fixtures` e imprime el acierto y el costo."""
    cfg = settings()
    db = SessionLocal()
    try:
        empresa = Empresa(nombre="medir-mapeo")
        db.add(empresa)
        db.flush()
        medicion = medir(fixtures, db, empresa.id, cfg=cfg)
    finally:
        db.rollback()
        db.close()

    archivos = len({c.archivo for c in medicion.columnas})
    typer.echo(f"archivos: {archivos}, columnas evaluadas: {len(medicion.columnas)}")
    typer.echo(f"acierto total: {medicion.acierto_total:.1%}")
    typer.echo(
        f"prellenado: {medicion.porcentaje_prellenado():.1%} del total, "
        f"con acierto {medicion.acierto_prellenado():.1%}"
    )
    typer.echo("acierto por campo:")
    for campo, tasa in sorted(medicion.acierto_por_campo().items()):
        typer.echo(f"  {campo}: {tasa:.1%}")
    if medicion.producto_id_tipo:
        typer.echo(f"acierto producto_id_tipo: {medicion.acierto_producto_id_tipo():.1%}")
    typer.echo(f"costo: {medicion.costo}")

    errores = medicion.errores()
    if errores:
        typer.echo(f"errores ({len(errores)}):")
        for error in errores:
            typer.echo(
                f"  {error.archivo}: '{error.columna}' -> esperado={error.campo_esperado} "
                f"sugerido={error.campo_sugerido} (confianza={error.confianza:.2f})"
            )
