"""Exportación a CSV de recordatorios, ofertas y riesgo (FR-19/FR-21, specs/f5-mensajes.md#F5.2.T1).

Junta el resultado de un análisis (`recompra`/`ofertas`/`riesgo`) con la decisión de `contactar`
(F4.3.T2) y el mensaje renderizado de F5.1, y lo escribe en CSV vía DuckDB `COPY` (streaming:
DuckDB lee y escribe en bloques, nunca carga el Parquet entero en memoria). UTF-8 con BOM para
que Excel lo abra bien, separador `,` o `;`, encabezados en el idioma del proyecto. Solo filas
con `contactar = sí` por defecto; `incluir_revisar=True` suma las dudosas (`revisar`).
"""

from __future__ import annotations

import re
import shutil
import unicodedata
from collections.abc import Mapping
from datetime import date
from pathlib import Path

import pyarrow as pa

from predicts.config import Settings
from predicts.datos.duckdb import conexion_duckdb

TIPOS = ("recordatorios", "ofertas", "riesgo")
IDIOMAS = ("es", "en", "pt-BR")
SEPARADORES = (",", ";")
BOM = b"\xef\xbb\xbf"

# Clave de `mensajes` para las filas de riesgo a nivel tienda (`producto_id` nulo).
GENERAL = "__general__"

# tipo de exportación → (archivo de resultados, tipo de plantilla de mensaje de F5.1).
FUENTES: dict[str, tuple[str, str]] = {
    "recordatorios": ("recompra.parquet", "recordatorio"),
    "ofertas": ("ofertas.parquet", "oferta"),
    "riesgo": ("riesgo.parquet", "reactivacion"),
}

# Por tipo, expresión SQL (sobre el alias `d`, la fila del archivo de resultados) para las
# columnas que no comparten el mismo origen: fechas y probabilidad solo existen en recordatorios
# (recompra.parquet); ofertas tiene un puntaje en vez de una probabilidad y un descuento en vez
# de días; riesgo tiene días desde la última compra pero ni fechas ni probabilidad.
_COLUMNAS: dict[str, dict[str, str]] = {
    "recordatorios": {
        "fecha_sugerida": "d.fecha_probable",
        "fecha_min": "d.fecha_min",
        "fecha_max": "d.fecha_max",
        "probabilidad": "d.p",
        "dias": "CAST(d.dias_desde_ultima AS VARCHAR)",
        "oferta": "''",
    },
    "ofertas": {
        "fecha_sugerida": "NULL",
        "fecha_min": "NULL",
        "fecha_max": "NULL",
        "probabilidad": "d.puntaje",
        "dias": "''",
        "oferta": "CASE WHEN d.descuento > 0 "
        "THEN CAST(round(100 * d.descuento) AS VARCHAR) ELSE '' END",
    },
    "riesgo": {
        "fecha_sugerida": "NULL",
        "fecha_min": "NULL",
        "fecha_max": "NULL",
        "probabilidad": "NULL",
        "dias": "CAST(d.dias_desde_ultima AS VARCHAR)",
        "oferta": "''",
    },
}

_CAMPOS = (
    "cliente_id", "producto_id", "producto_nombre", "fecha_sugerida", "fecha_min", "fecha_max",
    "probabilidad", "motivo", "mensaje", "contactar",
)  # fmt: skip

ENCABEZADOS: dict[str, dict[str, str]] = {
    "es": dict(
        zip(
            _CAMPOS,
            (
                "cliente_id", "producto_id", "producto", "fecha_sugerida", "fecha_mínima",
                "fecha_máxima", "probabilidad", "motivo", "mensaje", "contactar",
            ),
            strict=True,
        )
    ),  # fmt: skip
    "en": dict(
        zip(
            _CAMPOS,
            (
                "customer_id", "product_id", "product", "suggested_date", "min_date",
                "max_date", "probability", "reason", "message", "contact",
            ),
            strict=True,
        )
    ),  # fmt: skip
    "pt-BR": dict(
        zip(
            _CAMPOS,
            (
                "cliente_id", "produto_id", "produto", "data_sugerida", "data_minima",
                "data_maxima", "probabilidade", "motivo", "mensagem", "contatar",
            ),
            strict=True,
        )
    ),  # fmt: skip
}

_ETIQUETAS_CONTACTAR: dict[str, dict[str, str]] = {
    "es": {"contactar": "sí", "no_contactar": "no", "revisar": "revisar"},
    "en": {"contactar": "yes", "no_contactar": "no", "revisar": "review"},
    "pt-BR": {"contactar": "sim", "no_contactar": "não", "revisar": "revisar"},
}

_SLUG_INVALIDO = re.compile(r"[^a-zA-Z0-9]+")


def nombre_archivo(proyecto: str, tipo: str, hoy: date | None = None) -> str:
    """`<proyecto>_<tipo>_<fecha>.csv`, con el nombre del proyecto pasado a un slug ASCII."""
    slug = unicodedata.normalize("NFKD", proyecto).encode("ascii", "ignore").decode()
    slug = _SLUG_INVALIDO.sub("_", slug).strip("_") or "export"
    return f"{slug}_{tipo}_{(hoy or date.today()).isoformat()}.csv"


def _render_sql(texto: str, producto: str, dias: str, oferta: str, tienda: str) -> str:
    """Mismo reemplazo que `mensajes.render.render` (los 4 marcadores de
    `MARCADORES_PERMITIDOS`), pero como SQL vectorizado: con un millón de filas, un `REPLACE`
    en DuckDB es muchísimo más rápido que una función Python por fila."""
    return (
        f"REPLACE(REPLACE(REPLACE(REPLACE({texto}, "
        f"'{{producto}}', {producto}), "
        f"'{{dias}}', {dias}), "
        f"'{{oferta}}', {oferta}), "
        f"'{{nombre_tienda}}', {tienda})"
    )


def exportar_csv(
    resultados: Path,
    tipo: str,
    idioma: str,
    nombre_tienda: str,
    destino: Path,
    *,
    separador: str = ",",
    incluir_revisar: bool = False,
    mensajes: Mapping[str, str] | None = None,
    cfg: Settings | None = None,
) -> Path:
    """Escribe en `destino` el CSV (UTF-8 con BOM) de `tipo`, leyendo en streaming desde los
    Parquet de `resultados` (DuckDB `COPY`, memoria acotada).

    `mensajes`: texto de la plantilla F5.1 (sin renderizar) por `producto_id`, o `GENERAL` para
    las filas de riesgo a nivel tienda (`producto_id` nulo); el reemplazo de marcadores se hace
    por fila porque `{dias}` y `{producto}` varían según la fila, no según la plantilla.
    """
    if tipo not in FUENTES:
        raise ValueError(f"tipo inválido: {tipo}")
    if idioma not in ENCABEZADOS:
        raise ValueError(f"idioma inválido: {idioma}")
    if separador not in SEPARADORES:
        raise ValueError(f"separador inválido: {separador}")

    archivo, _ = FUENTES[tipo]
    ruta_datos = resultados / archivo
    ruta_contactar = resultados / "contactar.parquet"
    if not ruta_datos.exists() or not ruta_contactar.exists():
        raise FileNotFoundError(f"faltan resultados para exportar {tipo!r} en {resultados}")

    col = _COLUMNAS[tipo]
    enc = ENCABEZADOS[idioma]
    etq = _ETIQUETAS_CONTACTAR[idioma]
    decisiones = "'contactar', 'revisar'" if incluir_revisar else "'contactar'"

    mensajes = mensajes or {}
    tabla_mensajes = pa.table(
        {
            "clave": pa.array(list(mensajes.keys()), pa.string()),
            "texto": pa.array(list(mensajes.values()), pa.string()),
        }
    )

    mensaje_sql = _render_sql(
        "coalesce(m.texto, '')", "coalesce(d.producto_nombre, '')", col["dias"], col["oferta"],
        "$tienda",
    )  # fmt: skip

    sin_bom = destino.with_suffix(destino.suffix + ".sinbom")
    con = conexion_duckdb(cfg=cfg)
    try:
        con.register("_mensajes_export", tabla_mensajes)
        ruta_datos_sql = str(ruta_datos).replace("'", "''")
        ruta_contactar_sql = str(ruta_contactar).replace("'", "''")
        destino_sql = str(sin_bom).replace("'", "''")
        con.execute(
            f"""
            COPY (
                SELECT
                    d.cliente_id AS "{enc["cliente_id"]}",
                    d.producto_id AS "{enc["producto_id"]}",
                    d.producto_nombre AS "{enc["producto_nombre"]}",
                    {col["fecha_sugerida"]} AS "{enc["fecha_sugerida"]}",
                    {col["fecha_min"]} AS "{enc["fecha_min"]}",
                    {col["fecha_max"]} AS "{enc["fecha_max"]}",
                    {col["probabilidad"]} AS "{enc["probabilidad"]}",
                    d.motivo AS "{enc["motivo"]}",
                    {mensaje_sql} AS "{enc["mensaje"]}",
                    CASE c.decision
                        WHEN 'contactar' THEN '{etq["contactar"]}'
                        WHEN 'no_contactar' THEN '{etq["no_contactar"]}'
                        WHEN 'revisar' THEN '{etq["revisar"]}'
                    END AS "{enc["contactar"]}"
                FROM read_parquet('{ruta_datos_sql}') d
                JOIN read_parquet('{ruta_contactar_sql}') c USING (cliente_id)
                LEFT JOIN _mensajes_export m ON m.clave = coalesce(d.producto_id, '{GENERAL}')
                WHERE c.decision IN ({decisiones})
                ORDER BY d.cliente_id, d.producto_id
            ) TO '{destino_sql}' (HEADER, DELIMITER '{separador}')
            """,
            {"tienda": nombre_tienda},
        )
    finally:
        con.close()

    with destino.open("wb") as salida, sin_bom.open("rb") as entrada:
        salida.write(BOM)
        shutil.copyfileobj(entrada, salida)
    sin_bom.unlink()
    return destino
