"""Riesgo de abandono (FR-13), en dos niveles:

- **Producto:** pares del ajuste (ya tienen `n_compras ≥ MIN_COMPRAS`: compras regulares previas)
  con `t > ciclo + factor·dispersión`, donde `t` = días desde la última compra a `fecha_ref` y
  `ciclo`/`dispersion` son los del par en el ajuste (ciclo contraído y MAD contraído, en días).
- **Tienda:** clientes cuya actividad total cayó por debajo de su ritmo: la misma regla sobre los
  días de compra del cliente en toda la tienda (cualquier producto), con `ciclo` = mediana y
  `dispersion` = MAD de sus intervalos, y al menos `min_compras` días de compra.

Orden: valor histórico (suma de `valor_total` del par o del cliente) si hay precio; si no, número
de compras. `factor` es `ParametrosAnalisis.factor_riesgo` (default `FACTOR_DEFECTO`).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from predicts.modelo import Ajuste

NOMBRE = "riesgo.parquet"
TABLA = "res_riesgo"
FACTOR_DEFECTO = 2.0


def calcular(
    ajuste: Ajuste,
    compras: str,
    nombres: str,
    fecha_ref: date,
    factor: float,
    resultados: Path,
) -> dict:
    """Escribe `resultados/riesgo.parquet` (y deja la tabla `res_riesgo` en la conexión).

    Columnas: nivel (`producto`|`tienda`), cliente_id, producto_id (NULL en `tienda`),
    producto_nombre, n_compras, ciclo, dispersion, dias_desde_ultima, atraso (días más allá del
    ciclo), valor, motivo.
    """
    con = ajuste.con
    con.execute(
        f"""
        CREATE OR REPLACE TABLE {TABLA} AS
        WITH valor_par AS (
            SELECT cliente_id, producto_id, sum(valor_total) AS valor
            FROM {compras} GROUP BY ALL
        ),
        dias AS (SELECT DISTINCT cliente_id, CAST(fecha AS DATE) AS dia FROM {compras}),
        intervalos AS (
            SELECT cliente_id, dia, date_diff('day', lag(dia) OVER w, dia) AS intervalo
            FROM dias WINDOW w AS (PARTITION BY cliente_id ORDER BY dia)
        ),
        tienda AS (
            SELECT i.cliente_id, count(*) AS n_compras, median(intervalo) AS ciclo,
                   mad(intervalo) AS dispersion, max(dia) AS ultima_compra, v.valor
            FROM intervalos i
            LEFT JOIN (SELECT cliente_id, sum(valor_total) AS valor FROM {compras} GROUP BY 1) v
                USING (cliente_id)
            GROUP BY i.cliente_id, v.valor
            HAVING count(*) >= $min
        ),
        todos AS (
            SELECT 'producto' AS nivel, p.cliente_id, p.producto_id, n.producto_nombre,
                   p.n_compras, p.ciclo, p.dispersion, p.ultima_compra, v.valor
            FROM {ajuste.pares} p
            LEFT JOIN {nombres} n USING (producto_id)
            LEFT JOIN valor_par v USING (cliente_id, producto_id)
            UNION ALL
            SELECT 'tienda', cliente_id, NULL, NULL, n_compras, ciclo, dispersion,
                   ultima_compra, valor
            FROM tienda
        ),
        con_t AS (
            SELECT *, date_diff('day', ultima_compra, $ref) AS dias_desde_ultima FROM todos
        )
        SELECT nivel, cliente_id, producto_id, producto_nombre, n_compras, ciclo, dispersion,
               dias_desde_ultima, dias_desde_ultima - ciclo AS atraso, valor,
               CASE WHEN nivel = 'producto'
                    THEN printf('Compraba «%s» cada ~%d días (%d compras); la última fue hace '
                                || '%d días, %d más de lo habitual.',
                                producto_nombre, CAST(round(ciclo) AS INTEGER), n_compras,
                                dias_desde_ultima,
                                CAST(round(dias_desde_ultima - ciclo) AS INTEGER))
                    ELSE printf('Compraba en la tienda cada ~%d días (%d días de compra); '
                                || 'no compra nada desde hace %d días, %d más de lo habitual.',
                                CAST(round(ciclo) AS INTEGER), n_compras, dias_desde_ultima,
                                CAST(round(dias_desde_ultima - ciclo) AS INTEGER))
               END AS motivo
        FROM con_t
        WHERE dias_desde_ultima > ciclo + $factor * dispersion
        ORDER BY valor DESC NULLS LAST, n_compras DESC, atraso DESC, cliente_id, producto_id
        """,
        {"ref": fecha_ref, "factor": factor, "min": ajuste.params.min_compras},
    )
    ruta = str(resultados / NOMBRE).replace("'", "''")
    con.execute(f"COPY {TABLA} TO '{ruta}' (FORMAT parquet)")
    pares, clientes_tienda, clientes, valor = con.execute(
        f"SELECT count(*) FILTER (WHERE nivel = 'producto'), "
        f"count(*) FILTER (WHERE nivel = 'tienda'), count(DISTINCT cliente_id), sum(valor) "
        f"FILTER (WHERE nivel = 'tienda') FROM {TABLA}"
    ).fetchone()
    return {
        "factor": factor,
        "pares": pares,
        "clientes_tienda": clientes_tienda,
        "clientes": clientes,
        "valor_en_riesgo_tienda": valor,
    }
