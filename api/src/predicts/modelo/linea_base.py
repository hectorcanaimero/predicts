"""Línea base ingenua contra la que se mide el modelo.

Próxima compra = última compra + promedio de intervalos del par (redondeado
a días). "Compra en el horizonte" si cae en `(fecha_ref, fecha_ref + H]`;
la probabilidad es 1 o 0. Solo pares con al menos un intervalo. Sin
contracción, sin dispersión: es lo que haría una planilla.
"""

from __future__ import annotations

from datetime import date

import duckdb

from predicts.modelo.ciclos import intervalos

VISTA_LINEA_BASE = "linea_base"


def linea_base(
    con: duckdb.DuckDBPyConnection, compras: str, fecha_ref: date, horizonte: int
) -> str:
    """Crea la vista `linea_base` con las mismas columnas que `prediccion`
    (cliente_id, producto_id, ciclo, p, fecha_probable, fecha_min, fecha_max,
    n_compras); `fecha_min = fecha_max = fecha_probable`.
    """
    if horizonte < 0:
        raise ValueError("horizonte debe ser >= 0")
    vista = intervalos(con, compras)
    # Tabla, no vista: la vista `intervalos` se reemplaza en cada llamada.
    con.execute(
        f"""
        CREATE OR REPLACE TABLE _linea_base AS
        SELECT cliente_id, producto_id, avg(intervalo) AS ciclo, count(*) AS n_compras,
               max(dia) + CAST(round(avg(intervalo)) AS INTEGER) AS fecha_probable
        FROM {vista}
        GROUP BY cliente_id, producto_id
        HAVING count(intervalo) >= 1
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE VIEW {VISTA_LINEA_BASE} AS
        SELECT cliente_id, producto_id, ciclo,
               CASE WHEN fecha_probable > DATE '{fecha_ref.isoformat()}'
                     AND fecha_probable <= DATE '{fecha_ref.isoformat()}' + {int(horizonte)}
                    THEN 1.0 ELSE 0.0 END AS p,
               fecha_probable, fecha_probable AS fecha_min, fecha_probable AS fecha_max,
               n_compras
        FROM _linea_base
        """
    )
    return VISTA_LINEA_BASE
