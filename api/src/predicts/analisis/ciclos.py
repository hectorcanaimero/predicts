"""Ciclo típico por producto (FR-12): mediana, dispersión y clientes recurrentes.

Sale directo de la tabla `productos` del ajuste del modelo (ver `modelo/ciclos.py`): no se
recalcula nada, así los ciclos coinciden con los que usa la predicción de recompra.
"""

from __future__ import annotations

from pathlib import Path

from predicts.modelo import Ajuste

NOMBRE = "ciclos.parquet"


def calcular(ajuste: Ajuste, nombres: str, resultados: Path) -> dict:
    """Escribe `resultados/ciclos.parquet` y devuelve los totales para el resumen.

    Columnas: producto_id, producto_nombre, ciclo_mediano (días), dispersion (MAD en días),
    desvio_log, clientes_recurrentes. `nombres`: tabla (producto_id, producto_nombre) de `con`.
    """
    con = ajuste.con
    con.execute(
        f"""
        CREATE OR REPLACE TABLE res_ciclos AS
        SELECT p.producto_id, n.producto_nombre, p.med_producto AS ciclo_mediano,
               p.mad_producto AS dispersion, p.desvio_log, p.clientes_recurrentes
        FROM {ajuste.productos} p LEFT JOIN {nombres} n USING (producto_id)
        ORDER BY p.clientes_recurrentes DESC, p.producto_id
        """
    )
    ruta = str(resultados / NOMBRE).replace("'", "''")
    con.execute(f"COPY res_ciclos TO '{ruta}' (FORMAT parquet)")
    top = con.execute(
        "SELECT producto_id, producto_nombre, ciclo_mediano, clientes_recurrentes "
        "FROM res_ciclos LIMIT 10"
    ).fetchall()
    return {
        "productos": con.execute("SELECT count(*) FROM res_ciclos").fetchone()[0],
        "top_productos": [
            {"producto_id": p, "producto_nombre": n, "ciclo_mediano": c, "clientes_recurrentes": r}
            for p, n, c, r in top
        ],
    }
