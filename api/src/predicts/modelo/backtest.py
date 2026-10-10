"""Backtesting del modelo contra la línea base.

Cómo se mide (y su porqué):

- **Corte.** `corte = fecha_max − semanas` (fecha_max = última compra del
  archivo). Se ajusta solo con compras ≤ corte y se predice con
  `fecha_ref = corte`: el modelo no ve nada del futuro que se le pide.
- **Verdad.** Un par "compra" si tiene alguna compra en `(corte, corte + H]`;
  su fecha real es la primera de esa ventana.
- **Población.** Los pares que el modelo ajusta (`prediccion`). La línea base
  se evalúa sobre los mismos pares: comparar sobre poblaciones distintas
  mezclaría el método con quién entra. Los pares nuevos (sin historia al
  corte) no se pueden predecir y no cuentan.
- **Top-K.** Pares ordenados por `p`; `precision_at_k` = aciertos / K,
  `cobertura_at_k` = aciertos / compradores reales. K por defecto = número de
  compradores reales. Los empates en el borde del top-K (la línea base es
  todo 0/1) se resuelven por valor esperado: el grupo empatado aporta
  `lugares_libres · compradores_del_grupo / tamaño_del_grupo`. Romperlos por
  id premiaría o castigaría según el orden alfabético.
- **Brier** = media de `(p − compró)²`: penaliza la confianza mal puesta,
  que es lo que una probabilidad 0/1 hace siempre que se equivoca.
- **Calibración** en 10 tramos fijos de `p` ([0, 0.1), …, [0.9, 1]): `p`
  medio predicho vs. fracción que compró. Tramos fijos y no deciles por
  cuantil porque la línea base solo tiene dos valores de `p`.
- **mae_dias** = media de `|fecha_probable − fecha real|` en los pares que
  compraron.
- **Repeticiones.** La ventana `r` (0..R−1) usa `corte − r·H`: ventanas de
  verdad consecutivas que no se solapan. Se reporta media y desvío (muestral,
  None con una sola ventana) por métrica; la calibración agrupa todas.
"""

from __future__ import annotations

from datetime import date, timedelta

import duckdb
import numpy as np
from pydantic import BaseModel

from predicts.modelo import VERSION_MODELO
from predicts.modelo.ciclos import ParamsModelo, _fuente, ajustar
from predicts.modelo.linea_base import linea_base
from predicts.modelo.prediccion import predecir

_TRAMOS = 10


class Tramo(BaseModel):
    desde: float
    hasta: float
    n: int
    predicho: float | None
    observado: float | None


class MetricasMetodo(BaseModel):
    precision_at_k: float | None
    cobertura_at_k: float | None
    brier: float | None
    calibracion: list[Tramo]
    mae_dias: float | None


class Ventana(BaseModel):
    corte: date
    n_pares: int
    k: int
    modelo: MetricasMetodo
    linea_base: MetricasMetodo


class Estadistico(BaseModel):
    media: float | None
    desvio: float | None


class Resumen(BaseModel):
    precision_at_k: Estadistico
    cobertura_at_k: Estadistico
    brier: Estadistico
    mae_dias: Estadistico
    calibracion: list[Tramo]


class MetricasBacktest(BaseModel):
    """`modelo` / `linea_base`: media ± desvío entre ventanas y calibración
    agrupada. `n_pares`: pares evaluados sumando ventanas. `k`: el pedido
    (None = compradores reales de cada ventana; el usado está en `ventanas`).
    """

    version_modelo: str
    semanas: int
    horizonte: int
    n_pares: int
    k: int | None
    modelo: Resumen
    linea_base: Resumen
    ventanas: list[Ventana]


def calibracion(p: np.ndarray, y: np.ndarray) -> list[Tramo]:
    tramo = np.minimum((p * _TRAMOS).astype(int), _TRAMOS - 1)
    salida = []
    for i in range(_TRAMOS):
        m = tramo == i
        n = int(m.sum())
        salida.append(
            Tramo(
                desde=i / _TRAMOS,
                hasta=(i + 1) / _TRAMOS,
                n=n,
                predicho=float(p[m].mean()) if n else None,
                observado=float(y[m].mean()) if n else None,
            )
        )
    return salida


def metricas(p: np.ndarray, y: np.ndarray, error_dias: np.ndarray, k: int) -> MetricasMetodo:
    """Métricas de un método. `y` booleano; `error_dias` |fecha_probable −
    fecha real| (NaN si no compró)."""
    n, positivos = len(p), int(y.sum())
    k = min(k, n)
    precision = cobertura = None
    if k > 0:
        umbral = np.sort(p)[::-1][k - 1]
        arriba, empate = p > umbral, p == umbral
        aciertos = y[arriba].sum() + (k - arriba.sum()) * y[empate].sum() / empate.sum()
        precision = float(aciertos / k)
        cobertura = float(aciertos / positivos) if positivos else None
    return MetricasMetodo(
        precision_at_k=precision,
        cobertura_at_k=cobertura,
        brier=float(np.mean((p - y) ** 2)) if n else None,
        calibracion=calibracion(p, y),
        mae_dias=float(np.mean(error_dias[y])) if positivos else None,
    )


def _estadistico(valores: list[float | None]) -> Estadistico:
    v = [x for x in valores if x is not None]
    return Estadistico(
        media=float(np.mean(v)) if v else None,
        desvio=float(np.std(v, ddof=1)) if len(v) > 1 else None,
    )


def _resumen(ventanas: list[MetricasMetodo], p: np.ndarray, y: np.ndarray) -> Resumen:
    return Resumen(
        **{
            campo: _estadistico([getattr(v, campo) for v in ventanas])
            for campo in ("precision_at_k", "cobertura_at_k", "brier", "mae_dias")
        },
        calibracion=calibracion(p, y),
    )


def backtest(
    con: duckdb.DuckDBPyConnection,
    compras: str,
    params: ParamsModelo,
    semanas: int,
    horizonte: int,
    *,
    k: int | None = None,
    repeticiones: int = 1,
) -> MetricasBacktest:
    """Mide modelo y línea base en `repeticiones` cortes hacia atrás (ver el
    docstring del módulo). `compras`: tabla/vista de `con` o ruta Parquet.
    Deja en `con` las vistas `prediccion` / `linea_base` del último corte evaluado.
    """
    if semanas < 1 or horizonte < 1 or repeticiones < 1:
        raise ValueError("semanas, horizonte y repeticiones deben ser >= 1")
    if k is not None and k < 1:
        raise ValueError("k debe ser >= 1")
    fuente = _fuente(compras)
    fecha_max = con.execute(f"SELECT CAST(max(fecha) AS DATE) FROM {fuente}").fetchone()[0]
    if fecha_max is None:
        raise ValueError("no hay compras")

    ventanas: list[Ventana] = []
    todos: dict[str, list[np.ndarray]] = {"pm": [], "pb": [], "y": []}
    for r in range(repeticiones):
        corte = fecha_max - timedelta(weeks=semanas) - timedelta(days=r * horizonte)
        con.execute(
            f"CREATE OR REPLACE VIEW _bt_compras AS "
            f"SELECT * FROM {fuente} WHERE CAST(fecha AS DATE) <= DATE '{corte.isoformat()}'"
        )
        pred = predecir(ajustar(con, "_bt_compras", params), corte, horizonte)
        base = linea_base(con, "_bt_compras", corte, horizonte)
        filas = con.execute(
            f"""
            WITH verdad AS (
                SELECT cliente_id, producto_id, min(CAST(fecha AS DATE)) AS real
                FROM {fuente}
                WHERE CAST(fecha AS DATE) > $c AND CAST(fecha AS DATE) <= $c + $h
                GROUP BY ALL
            )
            SELECT m.p, coalesce(b.p, 0.0),
                   v.real IS NOT NULL,
                   abs(date_diff('day', m.fecha_probable, v.real)),
                   abs(date_diff('day', b.fecha_probable, v.real))
            FROM {pred} m
            LEFT JOIN {base} b USING (cliente_id, producto_id)
            LEFT JOIN verdad v USING (cliente_id, producto_id)
            """,
            {"c": corte, "h": horizonte},
        ).fetchall()
        # None (sin compra real) → NaN.
        pm, pb, y, em, eb = np.array(filas, dtype=float).reshape(-1, 5).T
        y = y.astype(bool)
        k_ventana = k if k is not None else int(y.sum())
        ventanas.append(
            Ventana(
                corte=corte,
                n_pares=len(y),
                k=k_ventana,
                modelo=metricas(pm, y, em, k_ventana),
                linea_base=metricas(pb, y, eb, k_ventana),
            )
        )
        todos["pm"].append(pm)
        todos["pb"].append(pb)
        todos["y"].append(y)

    y_total = np.concatenate(todos["y"])
    return MetricasBacktest(
        version_modelo=VERSION_MODELO,
        semanas=semanas,
        horizonte=horizonte,
        n_pares=len(y_total),
        k=k,
        modelo=_resumen([v.modelo for v in ventanas], np.concatenate(todos["pm"]), y_total),
        linea_base=_resumen([v.linea_base for v in ventanas], np.concatenate(todos["pb"]), y_total),
        ventanas=ventanas,
    )
