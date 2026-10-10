"""Ofertas personalizadas (FR-14).

**Matriz ítem–ítem de co-compra** (`matriz_lift`, tabla `ofertas_lift`): dos productos se
co-compran cuando el mismo cliente compró los dos (en cualquier momento del período). Con `N`
clientes, `n_a` clientes de A, `n_b` de B y `n_ab` de ambos:
`lift(A, B) = n_ab · N / (n_a · n_b)` (cuánto más probable es comprar B sabiendo que compró A).
Solo entran pares con soporte `n_ab ≥ max(CO_COMPRADORES_MIN, soporte_min · N)`: un lift alto con
un solo cliente en común es ruido.

**Candidatos por cliente**, de tres fuentes:

1. `recompra`: pares con `p ≥ umbral` en el horizonte (la predicción de recompra).
2. `cocompra`: productos que el cliente todavía no compra con `lift ≥ LIFT_MIN` respecto de
   alguno que sí compra (se queda el de mayor lift).
3. `oferta` (solo si se subió la lista): productos de la lista que el cliente ya compró.

**Puntaje combinado:** `puntaje = max(p, 1 − 1/lift, BASE_OFERTA_HISTORIAL) · (1 + descuento)`,
tomando de cada término solo las fuentes presentes (0 si no) y `descuento` (fracción, 0 si el
producto no está en la lista). `1 − 1/lift` lleva el lift a (0, 1) para compararlo con `p`
(lift 2 → 0,5; lift 5 → 0,8). Se guardan las `max_ofertas` de mayor puntaje por cliente.

La lista de ofertas (`POST /datasets/{id}/ofertas`) se guarda junto al Parquet del dataset como
`LISTA` (producto_id del CSV, descuento como fracción); un producto de un grupo confirmado hereda
el mayor descuento de sus variantes.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from predicts.modelo import Ajuste

NOMBRE = "ofertas.parquet"
LISTA = "ofertas_lista.parquet"
TABLA_LIFT = "ofertas_lift"

SOPORTE_MIN = 0.01
CO_COMPRADORES_MIN = 2
LIFT_MIN = 1.2
BASE_OFERTA_HISTORIAL = 0.25
MAX_OFERTAS_DEFECTO = 5


def matriz_lift(
    con: duckdb.DuckDBPyConnection, compras: str, soporte_min: float = SOPORTE_MIN
) -> str:
    """Crea `ofertas_lift` (producto_a, producto_b, n_ab, n_a, n_b, lift); ver el docstring.

    ponytail: autojoin por cliente, O(Σ productos_por_cliente²); con catálogos de decenas de
    miles de productos por cliente, cortar a los K productos más comprados por cliente.
    """
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE _cp AS SELECT DISTINCT cliente_id, producto_id FROM {compras};
        CREATE OR REPLACE TABLE {TABLA_LIFT} AS
        WITH total AS (SELECT count(DISTINCT cliente_id) AS n FROM _cp),
        por_producto AS (SELECT producto_id, count(*) AS n FROM _cp GROUP BY 1),
        pares AS (
            SELECT a.producto_id AS producto_a, b.producto_id AS producto_b, count(*) AS n_ab
            FROM _cp a JOIN _cp b ON a.cliente_id = b.cliente_id AND a.producto_id <> b.producto_id
            GROUP BY 1, 2
        )
        SELECT p.producto_a, p.producto_b, p.n_ab, a.n AS n_a, b.n AS n_b,
               p.n_ab * t.n / (a.n * b.n) AS lift
        FROM pares p CROSS JOIN total t
        JOIN por_producto a ON a.producto_id = p.producto_a
        JOIN por_producto b ON b.producto_id = p.producto_b
        WHERE p.n_ab >= greatest($co_min, $soporte * t.n)
        """,
        {"co_min": CO_COMPRADORES_MIN, "soporte": soporte_min},
    )
    return TABLA_LIFT


def calcular(
    ajuste: Ajuste,
    compras: str,
    nombres: str,
    prediccion: str,
    umbral: float,
    horizonte: int,
    lista: Path | None,
    max_ofertas: int,
    resultados: Path,
) -> dict:
    """Escribe `resultados/ofertas.parquet`. `prediccion`: vista de `modelo.predecir`; `compras`
    debe tener `producto_id_origen` (el id del CSV) para cruzar con la lista.

    Columnas: cliente_id, producto_id, producto_nombre, puntaje, p_recompra, lift, por_producto
    (el producto ya comprado que dio el lift), descuento, fuentes (lista), motivo.
    """
    con = ajuste.con
    matriz_lift(con, compras)
    con.execute("CREATE OR REPLACE TEMP TABLE _lista (producto_id VARCHAR, descuento DOUBLE)")
    if lista is not None and lista.exists():
        con.execute(
            f"""
            INSERT INTO _lista
            SELECT m.producto_id, max(l.descuento)
            FROM read_parquet($lista) l
            JOIN (SELECT DISTINCT producto_id_origen, producto_id FROM {compras}) m
                ON m.producto_id_origen = l.producto_id
            GROUP BY 1
            """,
            {"lista": str(lista)},
        )
    con.execute(
        f"""
        CREATE OR REPLACE TABLE res_ofertas AS
        WITH candidatos AS (
            SELECT cliente_id, producto_id, p AS p_recompra, 'recompra' AS fuente
            FROM {prediccion} WHERE p >= $umbral
            UNION ALL BY NAME
            SELECT c.cliente_id, l.producto_b AS producto_id, max(l.lift) AS lift,
                   arg_max(l.producto_a, l.lift) AS por_producto, 'cocompra' AS fuente
            FROM _cp c JOIN {TABLA_LIFT} l ON l.producto_a = c.producto_id
            ANTI JOIN _cp x ON x.cliente_id = c.cliente_id AND x.producto_id = l.producto_b
            WHERE l.lift >= $lift_min
            GROUP BY c.cliente_id, l.producto_b
            UNION ALL BY NAME
            SELECT c.cliente_id, c.producto_id, 'oferta' AS fuente
            FROM _cp c SEMI JOIN _lista o USING (producto_id)
        ),
        juntos AS (
            SELECT cliente_id, producto_id, max(p_recompra) AS p_recompra, max(lift) AS lift,
                   any_value(por_producto) AS por_producto, list(fuente ORDER BY fuente) AS fuentes
            FROM candidatos GROUP BY ALL
        ),
        puntuados AS (
            SELECT j.*, coalesce(o.descuento, 0) AS descuento,
                   greatest(coalesce(j.p_recompra, 0), coalesce(1 - 1 / j.lift, 0),
                            CASE WHEN list_contains(j.fuentes, 'oferta')
                                 THEN $base_oferta ELSE 0 END)
                       * (1 + coalesce(o.descuento, 0)) AS puntaje
            FROM juntos j LEFT JOIN _lista o USING (producto_id)
        )
        SELECT u.cliente_id, u.producto_id, n.producto_nombre, u.puntaje, u.p_recompra, u.lift,
               u.por_producto, u.descuento, u.fuentes,
               concat_ws(' ',
                   CASE WHEN u.p_recompra IS NOT NULL
                        THEN printf('Le toca recomprar: %d %% de probabilidad en %d días.',
                                    CAST(round(100 * u.p_recompra) AS INTEGER), $h) END,
                   CASE WHEN u.lift IS NOT NULL
                        THEN printf('Quienes compran «%s» lo compran %.1f veces más que el resto.',
                                    m.producto_nombre, u.lift) END,
                   CASE WHEN u.descuento > 0
                        THEN printf('Está en oferta con %d %% de descuento.',
                                    CAST(round(100 * u.descuento) AS INTEGER)) END
               ) AS motivo
        FROM puntuados u
        LEFT JOIN {nombres} n USING (producto_id)
        LEFT JOIN {nombres} m ON m.producto_id = u.por_producto
        QUALIFY row_number() OVER (
            PARTITION BY u.cliente_id ORDER BY u.puntaje DESC, u.producto_id) <= $max
        ORDER BY u.cliente_id, u.puntaje DESC, u.producto_id
        """,
        {
            "umbral": umbral,
            "lift_min": LIFT_MIN,
            "base_oferta": BASE_OFERTA_HISTORIAL,
            "h": horizonte,
            "max": max_ofertas,
        },
    )
    ruta = str(resultados / NOMBRE).replace("'", "''")
    con.execute(f"COPY res_ofertas TO '{ruta}' (FORMAT parquet)")
    ofertas, clientes, en_lista = con.execute(
        "SELECT count(*), count(DISTINCT cliente_id), count(*) FILTER (WHERE descuento > 0) "
        "FROM res_ofertas"
    ).fetchone()
    por_fuente = dict(
        con.execute(
            "SELECT f, count(*) FROM (SELECT unnest(fuentes) AS f FROM res_ofertas) GROUP BY 1"
        ).fetchall()
    )
    return {
        "ofertas": ofertas,
        "clientes": clientes,
        "con_descuento": en_lista,
        "por_fuente": por_fuente,
        "pares_lift": con.execute(f"SELECT count(*) FROM {TABLA_LIFT}").fetchone()[0],
        "lista_productos": con.execute("SELECT count(*) FROM _lista").fetchone()[0],
    }
