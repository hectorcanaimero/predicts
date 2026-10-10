"""Ruta de exportación a CSV: `GET /analisis/{id}/exportar` (ver `predicts.exportar` y
specs/f5-mensajes.md#F5.2.T1).

Aislada por empresa (`predicts.tenancy`). Streaming al cliente HTTP en bloques desde un archivo
temporal (el que escribió `exportar.exportar_csv`, ya con `COPY` de DuckDB): nunca carga el CSV
entero en memoria.
"""

from __future__ import annotations

import shutil
import tempfile
import uuid
from collections.abc import Generator
from pathlib import Path

import duckdb
import pyarrow as pa
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from predicts.auth.dependencias import Db, EmpresaActual
from predicts.config import settings
from predicts.db.modelos import Analisis, Dataset, Producto, Proyecto
from predicts.errores import ErrorApi
from predicts.exportar import FUENTES, GENERAL, SEPARADORES, TIPOS, exportar_csv, nombre_archivo
from predicts.mensajes import plantillas
from predicts.tenancy import obtener_o_404
from predicts.trabajos.tipos_mensajes import combinaciones_de_analisis

router = APIRouter(tags=["exportar"])

_TIPO_ANALISIS = {"recordatorios": "recompra", "ofertas": "ofertas", "riesgo": "riesgo"}

# Igual cruce por nombre de producto normalizado que `trabajos/tipos_mensajes.py` /
# `analisis/orquestador.py`; no se importa de ahí para no acoplar los módulos entre sí.
_NORMALIZAR_NOMBRE = (
    "lower(strip_accents(regexp_replace(trim(d.producto_nombre), '\\s+', ' ', 'g')))"
)


def _mapa_mensajes(
    db: Session, analisis: Analisis, proyecto: Proyecto, tipo_mensaje: str, ruta_datos: Path
) -> dict[str, str]:
    """`producto_id` (o `GENERAL` para las filas de riesgo a nivel tienda) → texto de la
    plantilla F5.1 ya cacheada, sin renderizar (el reemplazo de marcadores es por fila)."""
    combos = [c for c in combinaciones_de_analisis(db, analisis) if c.tipo == tipo_mensaje]
    if not combos:
        return {}
    cacheadas = plantillas.obtener_cacheadas(
        db, analisis.empresa_id, proyecto.idioma_mensajes, proyecto.tono,
        [c.clave for c in combos],
    )  # fmt: skip
    texto_por_base = {c.base: cacheadas[c.clave].texto for c in combos if c.clave in cacheadas}
    if not texto_por_base:
        return {}
    if "general" in texto_por_base:
        texto_por_base[GENERAL] = texto_por_base.pop("general")
    categorias = {
        b.removeprefix("categoria:") for b in texto_por_base if b.startswith("categoria:")
    }
    if not categorias:
        return texto_por_base

    filas_categoria = db.execute(
        select(Producto.nombre_normalizado, Producto.categoria).where(
            Producto.empresa_id == analisis.empresa_id, Producto.categoria.in_(categorias)
        )
    ).all()
    con = duckdb.connect()
    try:
        con.register(
            "_categorias",
            pa.table(
                {
                    "nombre_normalizado": pa.array([f[0] for f in filas_categoria], pa.string()),
                    "categoria": pa.array([f[1] for f in filas_categoria], pa.string()),
                }
            ),
        )
        encontrados = con.execute(
            f"""
            SELECT DISTINCT d.producto_id, c.categoria
            FROM read_parquet($r) d
            JOIN _categorias c ON c.nombre_normalizado = {_NORMALIZAR_NOMBRE}
            WHERE d.producto_id IS NOT NULL
            """,
            {"r": str(ruta_datos)},
        ).fetchall()
    finally:
        con.close()
    for producto_id, categoria in encontrados:
        clave = f"categoria:{categoria}"
        if clave in texto_por_base:
            texto_por_base[producto_id] = texto_por_base[clave]
    return texto_por_base


def _generar(ruta: Path, carpeta_tmp: str) -> Generator[bytes]:
    try:
        with ruta.open("rb") as f:
            while trozo := f.read(1024 * 1024):
                yield trozo
    finally:
        shutil.rmtree(carpeta_tmp, ignore_errors=True)


@router.get("/analisis/{analisis_id}/exportar", summary="Exportar recordatorios, ofertas o riesgo")
def exportar_analisis(
    analisis_id: uuid.UUID,
    empresa: EmpresaActual,
    db: Db,
    tipo: str,
    separador: str = ",",
    incluir_revisar: bool = False,
) -> StreamingResponse:
    analisis = obtener_o_404(db, Analisis, analisis_id, empresa.id)
    if tipo not in TIPOS:
        raise ErrorApi("tipo_invalido", 422, tipo=tipo, validos=list(TIPOS))
    if separador not in SEPARADORES:
        raise ErrorApi("separador_invalido", 422, separador=separador)
    if _TIPO_ANALISIS[tipo] not in analisis.tipos or "contactar" not in analisis.tipos:
        raise ErrorApi("tipo_no_solicitado", 404, tipo=tipo)

    dataset = db.get(Dataset, analisis.dataset_id)
    if dataset is not None and dataset.estado == "archivado":
        raise ErrorApi("archivo_vencido", 410)
    if analisis.estado != "listo" or not analisis.ruta_resultados:
        raise ErrorApi("analisis_no_listo", 409, estado=analisis.estado)

    proyecto = db.get(Proyecto, dataset.proyecto_id) if dataset is not None else None
    if dataset is None or proyecto is None:
        raise ErrorApi("no_encontrado", 404)

    archivo, tipo_mensaje = FUENTES[tipo]
    resultados = Path(analisis.ruta_resultados)
    ruta_datos = resultados / archivo
    if not ruta_datos.exists() or not (resultados / "contactar.parquet").exists():
        raise ErrorApi("analisis_no_listo", 409, estado=analisis.estado)

    mensajes = _mapa_mensajes(db, analisis, proyecto, tipo_mensaje, ruta_datos)

    carpeta_tmp = tempfile.mkdtemp()
    try:
        destino = exportar_csv(
            resultados,
            tipo,
            proyecto.idioma_mensajes,
            proyecto.nombre,
            Path(carpeta_tmp) / "export.csv",
            separador=separador,
            incluir_revisar=incluir_revisar,
            mensajes=mensajes,
            cfg=settings(),
        )
    except Exception:
        shutil.rmtree(carpeta_tmp, ignore_errors=True)
        raise

    nombre = nombre_archivo(proyecto.nombre, tipo)
    return StreamingResponse(
        _generar(destino, carpeta_tmp),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
