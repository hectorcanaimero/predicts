"""Intervalos entre compras y ciclo de recompra por par (cliente, producto).

Todo el cálculo es SQL de DuckDB: nada pasa por un bucle Python por par, así
el ajuste escala a millones de filas dentro de `DUCKDB_MEMORY_LIMIT`.

Fórmulas (y su porqué):

- **Días de compra distintos.** Varias líneas del mismo par el mismo día
  (dos pedidos, dos renglones) son una sola compra: si no, aparecerían
  intervalos de 0 días que hunden la mediana y no son recompras.
- **Intervalo** = días entre compras consecutivas del par. `n` = número de
  intervalos del par (= compras − 1).
- **Mediana y MAD del par** (`med_cliente`, `mad_cliente`): mediana y
  desviación absoluta mediana de sus intervalos. Robustas a un intervalo
  atípico (vacaciones, compra extra), que con la media arrastraría el ciclo.
- **Mediana del producto** (`med_producto`): mediana de las medianas de los
  pares con al menos un intervalo. Un voto por cliente: con los intervalos
  agrupados, los clientes de ciclo corto aportarían más intervalos y
  sesgarían el ciclo del producto hacia abajo.
- **Clientes recurrentes** del producto: pares con al menos un intervalo
  (dos días de compra distintos).
- **Ciclo contraído**: `ciclo = (n·med_cliente + k·med_producto) / (n + k)`.
  Promedio ponderado tipo bayesiano: el producto actúa como `k` intervalos
  "previos". Con pocos intervalos la mediana del par es ruidosa y el ciclo
  se acerca al del producto; con muchos, manda el par.
- **Dispersión del par**: la misma contracción sobre los MAD,
  `(n·mad_cliente + k·mad_producto) / (n + k)`, en días.
- **MAD del producto** (`mad_producto`) y **desvío log** (`desvio_log`):
  dispersión *dentro* de cada par, agrupada entre clientes. Por cada
  intervalo se toma el residuo respecto de la mediana de su par
  (`intervalo − med_cliente` en días, `ln(intervalo) − ln(med_cliente)` en
  log); `mad_producto = mediana(|residuo|)` y
  `desvio_log = 1.4826 · mediana(|residuo log|)`. Restar la mediana del par
  quita la diferencia de ciclo *entre* clientes (que ya captura `ciclo`) y
  deja la variación de un intervalo a otro, que es lo que necesita la
  log-normal de la predicción. 1.4826 convierte un MAD en desvío estándar
  bajo normalidad (estimador robusto: un intervalo atípico no lo infla como
  inflaría un desvío estándar). Agrupar entre clientes lo hace estable, cosa
  que un desvío por par con 3 intervalos no es. Solo entran pares con al
  menos `min_intervalos_desvio` intervalos; si un producto no tiene ninguno,
  se usa el valor agrupado de todos los productos y, si tampoco hay, los
  defaults de `ParamsModelo`.
- **Exclusiones**: pares con menos de `min_compras` días de compra quedan
  fuera del ajuste con motivo `historia_insuficiente` (y su conteo); pares
  cuyo producto no tiene ningún intervalo (durables) con `sin_recompra`.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb

VISTA_INTERVALOS = "intervalos"
TABLA_PARES = "ajuste_pares"
TABLA_PRODUCTOS = "ajuste_productos"
TABLA_EXCLUIDOS = "ajuste_excluidos"

# MAD → desvío estándar bajo normalidad (1 / Φ⁻¹(3/4)).
_MAD_A_DESVIO = 1.4826


@dataclass(frozen=True)
class ParamsModelo:
    """`k`: peso del producto en la contracción, en "intervalos equivalentes".
    `min_compras`: días de compra mínimos para ajustar un par (`MIN_COMPRAS`).
    `min_intervalos_desvio`: intervalos mínimos de un par para aportar a la
    dispersión del producto (con menos, el residuo respecto de su propia
    mediana es casi cero y la subestima).
    `desvio_log_defecto` / `mad_defecto`: últimos recursos sin datos.
    """

    k: float = 2.0
    min_compras: int = 3
    min_intervalos_desvio: int = 3
    desvio_log_defecto: float = 0.5
    mad_defecto: float = 0.0

    def __post_init__(self) -> None:
        if self.k < 0:
            raise ValueError("k debe ser >= 0")
        if self.min_compras < 2:
            raise ValueError("min_compras debe ser >= 2 (un ciclo necesita un intervalo)")
        if self.min_intervalos_desvio < 2:
            raise ValueError("min_intervalos_desvio debe ser >= 2")


@dataclass(frozen=True)
class Ajuste:
    """Resultado de `ajustar`: tablas DuckDB en `con`.

    - `pares`: cliente_id, producto_id, n_compras, n_intervalos, primera_compra,
      ultima_compra, med_cliente, mad_cliente, med_producto, ciclo, dispersion,
      desvio_log.
    - `productos`: producto_id, med_producto, mad_producto, desvio_log,
      clientes_recurrentes.
    - `excluidos`: cliente_id, producto_id, n_compras, motivo.
    """

    con: duckdb.DuckDBPyConnection
    params: ParamsModelo
    pares: str = TABLA_PARES
    productos: str = TABLA_PRODUCTOS
    excluidos: str = TABLA_EXCLUIDOS


def _fuente(compras: str) -> str:
    """`compras` es una tabla/vista de `con` o la ruta de un Parquet del esquema interno."""
    if compras.endswith(".parquet"):
        return "read_parquet('{}')".format(compras.replace("'", "''"))
    return compras


def intervalos(con: duckdb.DuckDBPyConnection, compras: str) -> str:
    """Crea la vista de días de compra distintos por par con el intervalo
    desde la compra anterior (NULL en la primera). Devuelve su nombre.

    Columnas: cliente_id, producto_id, dia, intervalo (días), n_compra (1..n).
    """
    con.execute(
        f"""
        CREATE OR REPLACE VIEW {VISTA_INTERVALOS} AS
        WITH dias AS (
            SELECT DISTINCT cliente_id, producto_id, CAST(fecha AS DATE) AS dia
            FROM {_fuente(compras)}
        )
        SELECT cliente_id, producto_id, dia,
               date_diff('day', lag(dia) OVER w, dia) AS intervalo,
               row_number() OVER w AS n_compra
        FROM dias
        WINDOW w AS (PARTITION BY cliente_id, producto_id ORDER BY dia)
        """
    )
    return VISTA_INTERVALOS


def ajustar(con: duckdb.DuckDBPyConnection, compras: str, params: ParamsModelo) -> Ajuste:
    """Ajusta ciclo, dispersión y desvío log por par y por producto (fórmulas
    en el docstring del módulo). Reemplaza las tablas de un ajuste anterior en `con`.
    """
    vista = intervalos(con, compras)
    # Se materializa una vez: la vista se lee tres veces abajo.
    con.execute(f"CREATE OR REPLACE TEMP TABLE _intervalos AS SELECT * FROM {vista}")
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE _pares AS
        SELECT cliente_id, producto_id,
               count(*) AS n_compras,
               count(intervalo) AS n_intervalos,
               min(dia) AS primera_compra,
               max(dia) AS ultima_compra,
               median(intervalo) AS med_cliente,
               mad(intervalo) AS mad_cliente
        FROM _intervalos
        GROUP BY cliente_id, producto_id
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE _residuos AS
        SELECT i.producto_id,
               abs(i.intervalo - p.med_cliente) AS res_dias,
               abs(ln(i.intervalo) - ln(p.med_cliente)) AS res_log
        FROM _intervalos i
        JOIN _pares p USING (cliente_id, producto_id)
        WHERE i.intervalo IS NOT NULL AND p.n_intervalos >= ?
        """,
        [params.min_intervalos_desvio],
    )
    con.execute(
        f"""
        CREATE OR REPLACE TABLE {TABLA_PRODUCTOS} AS
        WITH global AS (
            SELECT median(res_dias) AS mad, {_MAD_A_DESVIO} * median(res_log) AS desvio
            FROM _residuos
        ),
        disp AS (
            SELECT producto_id, median(res_dias) AS mad,
                   {_MAD_A_DESVIO} * median(res_log) AS desvio
            FROM _residuos GROUP BY producto_id
        ),
        centro AS (
            SELECT producto_id, median(med_cliente) AS med_producto,
                   count(*) AS clientes_recurrentes
            FROM _pares WHERE n_intervalos >= 1 GROUP BY producto_id
        )
        SELECT c.producto_id, c.med_producto,
               coalesce(d.mad, g.mad, $mad) AS mad_producto,
               coalesce(d.desvio, g.desvio, $desvio) AS desvio_log,
               c.clientes_recurrentes
        FROM centro c CROSS JOIN global g LEFT JOIN disp d USING (producto_id)
        """,
        {"mad": params.mad_defecto, "desvio": params.desvio_log_defecto},
    )
    con.execute(
        f"""
        CREATE OR REPLACE TABLE {TABLA_EXCLUIDOS} AS
        SELECT p.cliente_id, p.producto_id, p.n_compras,
               CASE WHEN p.n_compras < $min THEN 'historia_insuficiente'
                    ELSE 'sin_recompra' END AS motivo
        FROM _pares p LEFT JOIN {TABLA_PRODUCTOS} pr USING (producto_id)
        WHERE p.n_compras < $min OR pr.med_producto IS NULL
        """,
        {"min": params.min_compras},
    )
    con.execute(
        f"""
        CREATE OR REPLACE TABLE {TABLA_PARES} AS
        SELECT p.cliente_id, p.producto_id, p.n_compras, p.n_intervalos,
               p.primera_compra, p.ultima_compra,
               p.med_cliente, p.mad_cliente, pr.med_producto,
               (p.n_intervalos * p.med_cliente + $k * pr.med_producto)
                   / (p.n_intervalos + $k) AS ciclo,
               (p.n_intervalos * p.mad_cliente + $k * pr.mad_producto)
                   / (p.n_intervalos + $k) AS dispersion,
               pr.desvio_log
        FROM _pares p JOIN {TABLA_PRODUCTOS} pr USING (producto_id)
        WHERE p.n_compras >= $min
        """,
        {"k": params.k, "min": params.min_compras},
    )
    con.execute("DROP TABLE _intervalos; DROP TABLE _pares; DROP TABLE _residuos")
    return Ajuste(con=con, params=params)
