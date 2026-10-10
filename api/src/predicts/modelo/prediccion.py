"""Probabilidad de compra en el horizonte por par (cliente, producto).

Fórmulas (y su porqué):

- **Distribución del intervalo** `X` del par: log-normal con `μ = ln(ciclo)`
  y `σ = desvio_log` del producto (ver `ciclos.py`). `ciclo` es entonces la
  mediana de `X`: la misma escala robusta con la que se estimó.
- **Probabilidad en el horizonte**: con `t` = días desde la última compra a
  `fecha_ref` y `S = 1 − F`,
  `P = (F(t+H) − F(t)) / (1 − F(t)) = 1 − S(t+H) / S(t)`, condicional a no
  haber comprado todavía. Se calcula en logaritmos,
  `P = −expm1(log S(t+H) − log S(t))`, con `log S` = `log_ndtr(−z)`: así no
  se divide por cero ni se pierde precisión cuando `S(t)` es diminuto
  (cliente muy atrasado).
- **Abandono**: la log-normal sola tiene cola fina y su tasa de compra
  sigue alta muy lejos del ciclo ("está atrasado, compra ya"), justo al
  revés de lo que pasa con un cliente que se fue. Se mezcla con una
  probabilidad previa `ε = PREVIA_ABANDONO` de que el par se haya
  abandonado: la probabilidad posterior de que siga activo es
  `w = (1−ε)·S(t) / ((1−ε)·S(t) + ε) = expit(log S(t) + ln((1−ε)/ε))` y
  `P = w · P_condicional`. Con `S(t) ≫ ε` cambia `P` en menos de `ε`; con
  `S(t) ≪ ε` la lleva a 0. `posible_abandono` = `w < 0.5` (es más probable
  que se haya ido a que siga).
- **Fecha probable y rango**: cuantiles de `X` condicionados a `X > t`.
  El cuantil `q` cumple `S(x) = (1 − q)·S(t)`; en log,
  `z_q = −ndtri_exp(ln(1 − q) + log S(t))`, `x_q = exp(μ + σ·z_q)`.
  Mediana (q = 0.5) → `fecha_probable`; q = 0.25 / 0.75 → `fecha_min` /
  `fecha_max`. Todas quedan en o después de `fecha_ref`.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pyarrow as pa
from scipy.special import expit, log_ndtr, ndtri_exp

from predicts.modelo.ciclos import Ajuste

VISTA_PREDICCION = "prediccion"
TABLA_PREDICCION = "prediccion_pares"

PREVIA_ABANDONO = 0.01
# σ = 0 (intervalos idénticos) haría la log-normal degenerada; con este piso
# la predicción es prácticamente determinista sin dividir por cero.
_DESVIO_MIN = 1e-3
# Tope de días para no desbordar fechas con σ absurdos.
_DIAS_MAX = 36_500.0


def predecir(ajuste: Ajuste, fecha_ref: date, horizonte: int) -> str:
    """Crea la vista `prediccion` (fórmulas en el docstring del módulo).

    Columnas: cliente_id, producto_id, ciclo, p, fecha_probable, fecha_min,
    fecha_max, n_compras, dias_desde_ultima, posible_abandono.
    """
    if horizonte < 0:
        raise ValueError("horizonte debe ser >= 0")
    con = ajuste.con
    pares = con.execute(
        f"""
        SELECT cliente_id, producto_id, ciclo, n_compras, ultima_compra,
               greatest(date_diff('day', ultima_compra, CAST(? AS DATE)), 0) AS dias_desde_ultima,
               desvio_log
        FROM {ajuste.pares}
        """,
        [fecha_ref],
    ).arrow()
    if isinstance(pares, pa.RecordBatchReader):  # DuckDB >= 1.4 devuelve un lector
        pares = pares.read_all()

    mu = np.log(pares["ciclo"].to_numpy())
    sigma = np.maximum(pares["desvio_log"].to_numpy(), _DESVIO_MIN)
    t = pares["dias_desde_ultima"].to_numpy().astype(float)

    with np.errstate(divide="ignore"):  # ln(0) = −inf → S(0) = 1, correcto
        log_s_t = log_ndtr(-(np.log(t) - mu) / sigma)
        log_s_th = log_ndtr(-(np.log(t + horizonte) - mu) / sigma)
    # S(t+H) ≤ S(t); el mínimo evita P < 0 por redondeo y el nan_to_num el
    # caso −inf − (−inf) (ambos sobrevivientes nulos en coma flotante).
    p_cond = np.nan_to_num(-np.expm1(np.minimum(log_s_th - log_s_t, 0.0)), nan=0.0)
    activo = expit(log_s_t + np.log((1 - PREVIA_ABANDONO) / PREVIA_ABANDONO))
    p = activo * p_cond

    def cuantil(q: float) -> np.ndarray:
        z = -ndtri_exp(np.log1p(-q) + log_s_t)
        return np.minimum(np.exp(mu + sigma * z), _DIAS_MAX)

    tabla = pares.select(["cliente_id", "producto_id", "ciclo", "n_compras", "ultima_compra"])
    tabla = tabla.append_column("p", pa.array(p))
    tabla = tabla.append_column("x_mediana", pa.array(cuantil(0.5)))
    tabla = tabla.append_column("x_min", pa.array(cuantil(0.25)))
    tabla = tabla.append_column("x_max", pa.array(cuantil(0.75)))
    tabla = tabla.append_column("dias_desde_ultima", pares["dias_desde_ultima"])
    tabla = tabla.append_column("posible_abandono", pa.array(activo < 0.5))

    con.register("_prediccion_arrow", tabla)
    con.execute(f"CREATE OR REPLACE TABLE {TABLA_PREDICCION} AS SELECT * FROM _prediccion_arrow")
    con.unregister("_prediccion_arrow")
    con.execute(
        f"""
        CREATE OR REPLACE VIEW {VISTA_PREDICCION} AS
        SELECT cliente_id, producto_id, ciclo, p,
               ultima_compra + CAST(round(x_mediana) AS INTEGER) AS fecha_probable,
               ultima_compra + CAST(round(x_min) AS INTEGER) AS fecha_min,
               ultima_compra + CAST(round(x_max) AS INTEGER) AS fecha_max,
               n_compras, dias_desde_ultima, posible_abandono
        FROM {TABLA_PREDICCION}
        """
    )
    return VISTA_PREDICCION
