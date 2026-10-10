"""Ingesta de un CSV ya detectado/mapeado a `compras.parquet`, con DuckDB.

Lee todo como texto (`all_varchar`) y castea cada campo explícitamente — así una fila con un
valor raro en una columna no hace que DuckDB adivine mal el tipo de toda la columna y la
pierda. Las filas inválidas (fecha que no parsea, cliente o producto vacío) se descartan y se
cuentan por motivo, en un solo recorrido del CSV: se transmite en lotes (`to_arrow_reader`) y
cada lote se separa en válido/descartado antes de escribir el Parquet, nunca se materializa el
CSV completo en memoria.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from pydantic import BaseModel

from predicts.config import Settings, settings
from predicts.datos.deteccion import CANDIDATOS_FECHA, ColumnaDeteccion, Deteccion
from predicts.datos.duckdb import conexion_duckdb
from predicts.datos.esquema import validar_parquet
from predicts.datos.mapeo import IGNORAR, MapeoConfirmado

_FORMATOS_FECHA: dict[str, str] = dict(CANDIDATOS_FECHA)
_TAMANO_LOTE = 100_000
_FILAS_PROGRESO = 1_000_000
_COLUMNA_MOTIVO = "_motivo_descarte"

MOTIVO_CLIENTE_VACIO = "cliente_vacio"
MOTIVO_PRODUCTO_VACIO = "producto_vacio"
MOTIVO_FECHA_INVALIDA = "fecha_invalida"


@dataclass(frozen=True)
class DatasetAIngerir:
    """Lo que `ingerir` necesita de un dataset: el CSV original, la `Deteccion` (codificación,
    separador, separador decimal por columna) hecha sobre él, y dónde escribir el Parquet."""

    ruta_csv: Path
    deteccion: Deteccion
    ruta_parquet: Path


class ResumenIngesta(BaseModel):
    filas_leidas: int
    filas_validas: int
    descartadas: dict[str, int]
    ruta_parquet: str


Progreso = Callable[[str, dict[str, int]], None]


def _ident(columna: str) -> str:
    return '"' + columna.replace('"', '""') + '"'


def _columna_texto(campo_a_columna: dict[str, str], campo: str, colapsar_espacios: bool) -> str:
    columna = campo_a_columna.get(campo)
    if columna is None:
        return "CAST(NULL AS VARCHAR)"
    expr = f"TRIM({_ident(columna)})"
    if colapsar_espacios:
        expr = f"regexp_replace({expr}, '\\s+', ' ', 'g')"
    return expr


def _columna_numero(
    campo_a_columna: dict[str, str], columnas_deteccion: dict[str, ColumnaDeteccion], campo: str
) -> str:
    columna = campo_a_columna.get(campo)
    if columna is None:
        return "CAST(NULL AS DOUBLE)"
    expr = f"TRIM({_ident(columna)})"
    deteccion_columna = columnas_deteccion.get(columna)
    if deteccion_columna is not None and deteccion_columna.separador_decimal == "coma":
        expr = f"REPLACE({expr}, ',', '.')"
    return f"TRY_CAST({expr} AS DOUBLE)"


def _construir_consulta(
    ruta_csv: Path, deteccion: Deteccion, mapeo: MapeoConfirmado
) -> tuple[str, list[object]]:
    campo_a_columna = {c.campo: c.columna for c in mapeo.columnas if c.campo != IGNORAR}
    columnas_deteccion = {c.nombre: c for c in deteccion.columnas}
    codificacion = "utf-8" if deteccion.codificacion == "utf-8-sig" else deteccion.codificacion

    sql = f"""
        WITH crudo AS (
            SELECT * FROM read_csv(?, encoding=?, delim=?, header=?, all_varchar=true)
        ), preparado AS (
            SELECT
                TRIM({_ident(campo_a_columna["cliente_id"])}) AS cliente_id,
                try_strptime(TRIM({_ident(campo_a_columna["fecha"])}), ?) AS fecha,
                TRIM({_ident(campo_a_columna["producto_id"])}) AS producto_id,
                CAST(? AS VARCHAR) AS producto_id_tipo,
                {_columna_texto(campo_a_columna, "producto_nombre", True)} AS producto_nombre,
                {_columna_texto(campo_a_columna, "pedido_id", False)} AS pedido_id,
                {_columna_texto(campo_a_columna, "categoria", False)} AS categoria,
                {_columna_texto(campo_a_columna, "marca", True)} AS marca,
                {_columna_numero(campo_a_columna, columnas_deteccion, "cantidad")} AS cantidad,
                {_columna_numero(campo_a_columna, columnas_deteccion, "precio_unitario")}
                    AS precio_unitario,
                {_columna_numero(campo_a_columna, columnas_deteccion, "valor_total")}
                    AS valor_total
            FROM crudo
        )
        SELECT *,
            CASE
                WHEN cliente_id IS NULL OR cliente_id = '' THEN ?
                WHEN producto_id IS NULL OR producto_id = '' THEN ?
                WHEN fecha IS NULL THEN ?
                ELSE NULL
            END AS {_COLUMNA_MOTIVO}
        FROM preparado
    """
    params: list[object] = [
        str(ruta_csv), codificacion, deteccion.separador, deteccion.encabezado,
        _FORMATOS_FECHA[mapeo.formato_fecha], mapeo.producto_id_tipo,
        MOTIVO_CLIENTE_VACIO, MOTIVO_PRODUCTO_VACIO, MOTIVO_FECHA_INVALIDA,
    ]
    return sql, params


def ingerir(
    dataset: DatasetAIngerir,
    mapeo: MapeoConfirmado,
    progreso: Progreso | None = None,
    cfg: Settings | None = None,
) -> ResumenIngesta:
    """Ingiere `dataset.ruta_csv` según `mapeo` y escribe `dataset.ruta_parquet`.

    Descarta y cuenta por motivo las filas con fecha que no parsea, o cliente o producto
    vacío (tras normalizar). Llama `progreso(etapa, contadores)` cada ~1 M de filas leídas.
    """
    cfg = cfg or settings()
    sql, params = _construir_consulta(dataset.ruta_csv, dataset.deteccion, mapeo)

    ruta_parquet = Path(dataset.ruta_parquet)
    ruta_parquet.parent.mkdir(parents=True, exist_ok=True)

    filas_leidas = 0
    filas_validas = 0
    descartadas: dict[str, int] = {}
    ultimo_aviso = 0

    con = conexion_duckdb(cfg=cfg)
    try:
        reader = con.execute(sql, params).to_arrow_reader(_TAMANO_LOTE)
        columnas_salida = [c for c in reader.schema.names if c != _COLUMNA_MOTIVO]
        esquema_salida = pa.schema([reader.schema.field(n) for n in columnas_salida])
        escritor = pq.ParquetWriter(ruta_parquet, esquema_salida)
        try:
            for lote in reader:
                filas_leidas += lote.num_rows
                motivo_col = lote.column(_COLUMNA_MOTIVO)
                conteos = pc.value_counts(motivo_col)
                for valor, cantidad in zip(
                    conteos.field("values"), conteos.field("counts"), strict=True
                ):
                    motivo = valor.as_py()
                    if motivo is not None:
                        descartadas[motivo] = descartadas.get(motivo, 0) + cantidad.as_py()

                lote_valido = lote.filter(pc.is_null(motivo_col)).select(columnas_salida)
                filas_validas += lote_valido.num_rows
                if lote_valido.num_rows:
                    escritor.write_batch(lote_valido)

                if progreso is not None and filas_leidas - ultimo_aviso >= _FILAS_PROGRESO:
                    ultimo_aviso = filas_leidas
                    progreso(
                        "leyendo",
                        {"leidas": filas_leidas, "validas": filas_validas, **descartadas},
                    )
        finally:
            escritor.close()
    finally:
        con.close()

    if progreso is not None:
        progreso("leyendo", {"leidas": filas_leidas, "validas": filas_validas, **descartadas})

    errores = validar_parquet(ruta_parquet, cfg=cfg)
    if errores:
        raise ValueError(f"Parquet de ingesta inválido: {'; '.join(errores)}")

    return ResumenIngesta(
        filas_leidas=filas_leidas, filas_validas=filas_validas, descartadas=descartadas,
        ruta_parquet=str(ruta_parquet),
    )
