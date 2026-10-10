"""Catálogo de productos: upsert en `productos` (por empresa y nombre normalizado) con las
estadísticas del dataset que alimentan la regla previa de `clasificacion.py` (ver
specs/f4-analisis.md#F4.2.T1).

Todo con una consulta DuckDB sobre el Parquet ya ingerido (mismo patrón que `datos/calidad.py`).
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from predicts.config import Settings, settings
from predicts.datos.duckdb import conexion_duckdb
from predicts.db.modelos import Dataset, Producto

_SQL_ESTADISTICAS = """
    WITH base AS (
        SELECT
            cliente_id,
            producto_id AS producto_id_origen,
            lower(strip_accents(regexp_replace(trim(producto_nombre), '\\s+', ' ', 'g')))
                AS nombre_normalizado,
            regexp_replace(trim(producto_nombre), '\\s+', ' ', 'g') AS nombre,
            categoria,
            precio_unitario,
            date_trunc('day', fecha) AS dia
        FROM read_parquet(?)
        WHERE producto_nombre IS NOT NULL AND trim(producto_nombre) != ''
    ),
    por_producto AS (
        SELECT
            nombre_normalizado,
            any_value(nombre) AS nombre,
            any_value(producto_id_origen) AS producto_id_origen,
            mode(categoria) AS categoria,
            count(DISTINCT cliente_id) AS clientes,
            avg(precio_unitario) AS precio_medio
        FROM base
        GROUP BY nombre_normalizado
    ),
    dias AS (
        SELECT DISTINCT nombre_normalizado, cliente_id, dia FROM base
    ),
    recompra AS (
        SELECT nombre_normalizado, count(*) FILTER (WHERE dias_distintos >= 2) AS clientes_recompra
        FROM (
            SELECT nombre_normalizado, cliente_id, count(*) AS dias_distintos
            FROM dias
            GROUP BY nombre_normalizado, cliente_id
        )
        GROUP BY nombre_normalizado
    ),
    gaps AS (
        SELECT
            nombre_normalizado,
            date_diff(
                'day', lag(dia) OVER (PARTITION BY nombre_normalizado, cliente_id ORDER BY dia), dia
            ) AS gap
        FROM dias
    ),
    medianas AS (
        SELECT nombre_normalizado, median(gap) AS mediana_intervalo_dias
        FROM gaps
        WHERE gap IS NOT NULL
        GROUP BY nombre_normalizado
    )
    SELECT
        p.nombre_normalizado, p.nombre, p.producto_id_origen, p.categoria, p.clientes,
        coalesce(r.clientes_recompra, 0) AS clientes_recompra, m.mediana_intervalo_dias,
        p.precio_medio
    FROM por_producto p
    LEFT JOIN recompra r USING (nombre_normalizado)
    LEFT JOIN medianas m USING (nombre_normalizado)
"""


def _calcular_estadisticas(ruta_parquet: str | Path, cfg: Settings) -> list[dict]:
    con = conexion_duckdb(solo_lectura=True, cfg=cfg)
    try:
        filas = con.execute(_SQL_ESTADISTICAS, [str(ruta_parquet)]).fetchall()
    finally:
        con.close()
    columnas = (
        "nombre_normalizado", "nombre", "producto_id_origen", "categoria", "clientes",
        "clientes_recompra", "mediana_intervalo_dias", "precio_medio",
    )
    return [dict(zip(columnas, fila, strict=True)) for fila in filas]


def actualizar_catalogo(
    db: Session, dataset: Dataset, cfg: Settings | None = None
) -> list[Producto]:
    """Upsert en `productos` de `dataset.empresa_id`, por `nombre_normalizado`, con las
    estadísticas calculadas del Parquet ya ingerido: clientes, clientes que recompraron,
    mediana del intervalo entre compras (en días) y precio medio. La categoría del CSV, si la
    trae, siempre se usa (pisa cualquier categoría anterior de Jev o de la persona).

    Devuelve los `Producto` nuevos o actualizados (para que `clasificacion.py` los reciba sin
    tener que volver a consultar toda la tabla).
    """
    cfg = cfg or settings()
    assert dataset.ruta_parquet
    filas = _calcular_estadisticas(dataset.ruta_parquet, cfg)

    existentes = {
        p.nombre_normalizado: p
        for p in db.scalars(select(Producto).where(Producto.empresa_id == dataset.empresa_id))
    }

    tocados: list[Producto] = []
    for fila in filas:
        producto = existentes.get(fila["nombre_normalizado"])
        estadisticas = {
            "clientes": fila["clientes"],
            "clientes_recompra": fila["clientes_recompra"],
            "mediana_intervalo_dias": fila["mediana_intervalo_dias"],
            "precio_medio": fila["precio_medio"],
        }
        if producto is None:
            producto = Producto(
                empresa_id=dataset.empresa_id,
                nombre_normalizado=fila["nombre_normalizado"],
                nombre=fila["nombre"],
                producto_id_origen=fila["producto_id_origen"],
                estadisticas=estadisticas,
            )
            db.add(producto)
        else:
            producto.nombre = fila["nombre"]
            producto.producto_id_origen = fila["producto_id_origen"]
            producto.estadisticas = estadisticas

        if fila["categoria"] is not None:
            producto.categoria = fila["categoria"]
            producto.categoria_origen = "csv"

        tocados.append(producto)

    db.flush()
    return tocados
