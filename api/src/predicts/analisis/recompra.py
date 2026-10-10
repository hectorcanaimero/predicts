"""Recompra (FR-11) y su backtest sobre el mismo dataset (FR-16).

- **Predicción:** `modelo.predecir` sobre el ajuste con `fecha_ref` = última fecha del dataset
  (lo decide el orquestador). Se guardan los pares con `p ≥ umbral`, ordenados por `p`, con las
  columnas de *Interfaces → Modelo* más el nombre del producto y un motivo legible.
- **Backtest:** `modelo.backtest` con el mismo horizonte (modelo y línea base lado a lado); lo
  corre el orquestador al final porque reemplaza las tablas del ajuste en la conexión.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from predicts.modelo import Ajuste
from predicts.modelo.prediccion import predecir

NOMBRE = "recompra.parquet"


def calcular(
    ajuste: Ajuste, nombres: str, fecha_ref: date, horizonte: int, umbral: float, resultados: Path
) -> dict:
    """Escribe `resultados/recompra.parquet` y devuelve los totales para el resumen.

    Columnas: cliente_id, producto_id, producto_nombre, ciclo, p, fecha_probable, fecha_min,
    fecha_max, n_compras, dias_desde_ultima, posible_abandono, motivo.
    """
    con = ajuste.con
    vista = predecir(ajuste, fecha_ref, horizonte)
    con.execute(
        f"""
        CREATE OR REPLACE TABLE res_recompra AS
        SELECT v.cliente_id, v.producto_id, n.producto_nombre, v.ciclo, v.p,
               v.fecha_probable, v.fecha_min, v.fecha_max, v.n_compras, v.dias_desde_ultima,
               v.posible_abandono,
               printf('Compra cada ~%d días (%d compras); la última fue hace %d días: '
                      || '%d %% de probabilidad de volver a comprar en %d días, '
                      || 'probablemente el %s.',
                      CAST(round(v.ciclo) AS INTEGER), v.n_compras, v.dias_desde_ultima,
                      CAST(round(100 * v.p) AS INTEGER), $h,
                      strftime(v.fecha_probable, '%d/%m/%Y')) AS motivo
        FROM {vista} v LEFT JOIN {nombres} n USING (producto_id)
        WHERE v.p >= $umbral
        ORDER BY v.p DESC, v.cliente_id, v.producto_id
        """,
        {"h": horizonte, "umbral": umbral},
    )
    ruta = str(resultados / NOMBRE).replace("'", "''")
    con.execute(f"COPY res_recompra TO '{ruta}' (FORMAT parquet)")

    (evaluados,) = con.execute(f"SELECT count(*) FROM {vista}").fetchone()
    excluidos = dict(
        con.execute(f"SELECT motivo, count(*) FROM {ajuste.excluidos} GROUP BY motivo").fetchall()
    )
    top = con.execute(
        """
        SELECT producto_id, any_value(producto_nombre), count(*) AS pares
        FROM res_recompra GROUP BY producto_id ORDER BY pares DESC, producto_id LIMIT 10
        """
    ).fetchall()
    recordatorios, clientes = con.execute(
        "SELECT count(*), count(DISTINCT cliente_id) FROM res_recompra"
    ).fetchone()
    return {
        "pares_evaluados": evaluados,
        "recordatorios": recordatorios,
        "clientes": clientes,
        "excluidos": excluidos,
        "top_productos": [{"producto_id": p, "producto_nombre": n, "pares": c} for p, n, c in top],
    }
