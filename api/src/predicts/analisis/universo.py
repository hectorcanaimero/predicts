"""Universo de clientes (F8.2.T1, specs/f8-3d-demo-despliegue.md#F8.2.T1): muestra estratificada
por estado con frecuencia/valor/recencia y un grupo de k-means simple, agregados con DuckDB
directo sobre el Parquet del dataset (una fila por cliente llega a Python, no las compras).

Estado por cliente, a partir del ciclo (mediana) y la dispersión (MAD) de sus intervalos de
compra en toda la tienda, igual que el nivel "tienda" de `riesgo.calcular`:

- `activo`: sin suficiente historial (menos de dos días de compra) o dentro de su ritmo normal.
- `en_recompra`: se acerca a la fecha esperada de su próxima compra (recencia ≥ 80 % del ciclo).
- `en_riesgo`: ya pasó su ciclo más `factor_riesgo` veces la dispersión sin comprar.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

import numpy as np
from duckdb import DuckDBPyConnection

from predicts.analisis.riesgo import FACTOR_DEFECTO

Estado = Literal["activo", "en_recompra", "en_riesgo"]
K_DEFECTO = 4

_SQL_UNIVERSO = """
WITH base AS (
    SELECT cliente_id, CAST(fecha AS DATE) AS dia, valor_total
    FROM read_parquet($ruta)
    WHERE ($desde IS NULL OR CAST(fecha AS DATE) >= $desde)
      AND ($hasta IS NULL OR CAST(fecha AS DATE) <= $hasta)
),
referencia AS (SELECT max(dia) AS ref FROM base),
precio AS (SELECT count(valor_total) > 0 AS hay FROM base),
dias AS (SELECT DISTINCT cliente_id, dia FROM base),
intervalos AS (
    SELECT cliente_id, dia, date_diff('day', lag(dia) OVER w, dia) AS intervalo
    FROM dias WINDOW w AS (PARTITION BY cliente_id ORDER BY dia)
),
ciclo_cliente AS (
    SELECT cliente_id, median(intervalo) AS ciclo, mad(intervalo) AS dispersion
    FROM intervalos WHERE intervalo IS NOT NULL GROUP BY cliente_id
),
agregado AS (
    SELECT b.cliente_id, count(*) AS n_compras, min(b.dia) AS primera, max(b.dia) AS ultima,
           sum(b.valor_total) AS suma_valor, c.ciclo, c.dispersion
    FROM base b LEFT JOIN ciclo_cliente c USING (cliente_id)
    GROUP BY b.cliente_id, c.ciclo, c.dispersion
)
SELECT a.cliente_id,
       a.n_compras / greatest(date_diff('day', a.primera, a.ultima) / 30.0, 1.0) AS frecuencia,
       CASE WHEN (SELECT hay FROM precio) THEN coalesce(a.suma_valor, 0) ELSE a.n_compras END
           AS valor,
       date_diff('day', a.ultima, (SELECT ref FROM referencia)) AS recencia,
       CASE
           WHEN a.ciclo IS NULL THEN 'activo'
           WHEN date_diff('day', a.ultima, (SELECT ref FROM referencia))
                > a.ciclo + $factor * a.dispersion THEN 'en_riesgo'
           WHEN date_diff('day', a.ultima, (SELECT ref FROM referencia)) >= a.ciclo * 0.8
                THEN 'en_recompra'
           ELSE 'activo'
       END AS estado
FROM agregado a
ORDER BY a.cliente_id
"""

_SQL_HISTORIAL = """
WITH base AS (
    SELECT CAST(fecha AS DATE) AS dia, producto_id, producto_nombre, cantidad, valor_total
    FROM read_parquet($ruta)
    WHERE cliente_id = $cliente
      AND ($desde IS NULL OR CAST(fecha AS DATE) >= $desde)
      AND ($hasta IS NULL OR CAST(fecha AS DATE) <= $hasta)
),
dias AS (SELECT DISTINCT producto_id, dia FROM base),
intervalos AS (
    SELECT producto_id, dia, date_diff('day', lag(dia) OVER w, dia) AS intervalo
    FROM dias WINDOW w AS (PARTITION BY producto_id ORDER BY dia)
),
ciclo_producto AS (
    SELECT producto_id, median(intervalo) AS ciclo
    FROM intervalos WHERE intervalo IS NOT NULL GROUP BY producto_id
)
SELECT b.producto_id, any_value(b.producto_nombre) AS producto_nombre, count(*) AS n_compras,
       sum(b.cantidad) AS cantidad_total, sum(b.valor_total) AS valor_total,
       max(b.dia) AS ultima_compra, c.ciclo
FROM base b LEFT JOIN ciclo_producto c USING (producto_id)
GROUP BY b.producto_id, c.ciclo
ORDER BY ultima_compra DESC, producto_id
"""


def _normalizar(matriz: np.ndarray) -> np.ndarray:
    desvio = matriz.std(axis=0)
    desvio[desvio == 0] = 1.0
    return (matriz - matriz.mean(axis=0)) / desvio


def _kmeans(matriz: np.ndarray, k: int, semilla: int, iteraciones: int = 50) -> np.ndarray:
    """k-means simple (inicialización aleatoria, no k-means++): alcanza para agrupar la muestra
    del universo, no para clustering de precisión."""
    rng = np.random.default_rng(semilla)
    n = matriz.shape[0]
    k = min(k, n)
    centroides = matriz[rng.choice(n, size=k, replace=False)].copy()
    etiquetas = np.full(n, -1)
    for _ in range(iteraciones):
        distancias = np.linalg.norm(matriz[:, None, :] - centroides[None, :, :], axis=2)
        nuevas = distancias.argmin(axis=1)
        if np.array_equal(nuevas, etiquetas):
            break
        etiquetas = nuevas
        for i in range(k):
            miembros = matriz[etiquetas == i]
            if len(miembros):
                centroides[i] = miembros.mean(axis=0)
    return etiquetas


def _muestra_estratificada(filas: list[dict], max_muestra: int, semilla: int) -> list[dict]:
    """Cuota proporcional al tamaño de cada estado (reparto por resto mayor, acotado por el
    tamaño del grupo); dentro de cada estado, elige al azar con `semilla`."""
    if len(filas) <= max_muestra:
        return filas
    rng = np.random.default_rng(semilla)
    grupos: dict[str, list[dict]] = {}
    for f in filas:
        grupos.setdefault(f["estado"], []).append(f)
    proporciones = {e: max_muestra * len(g) / len(filas) for e, g in grupos.items()}
    cuotas = {e: min(int(p), len(grupos[e])) for e, p in proporciones.items()}
    restante = max_muestra - sum(cuotas.values())
    for e in sorted(proporciones, key=lambda e: proporciones[e] - cuotas[e], reverse=True):
        if restante <= 0:
            break
        if cuotas[e] < len(grupos[e]):
            cuotas[e] += 1
            restante -= 1
    while restante > 0:
        candidatos = [e for e in grupos if cuotas[e] < len(grupos[e])]
        if not candidatos:
            break
        for e in candidatos:
            if restante <= 0:
                break
            cuotas[e] += 1
            restante -= 1
    muestra: list[dict] = []
    for e, g in grupos.items():
        idx = rng.choice(len(g), size=cuotas[e], replace=False)
        muestra += [g[i] for i in idx]
    return muestra


def calcular_universo(
    con: DuckDBPyConnection,
    ruta_parquet: str,
    desde: date | None = None,
    hasta: date | None = None,
    k: int = K_DEFECTO,
    max_muestra: int = 5000,
    factor_riesgo: float = FACTOR_DEFECTO,
    semilla: int = 0,
) -> list[dict]:
    """Muestra estratificada por estado de hasta `max_muestra` clientes, con un `grupo`
    (k-means sobre frecuencia/valor/recencia normalizados) calculado sobre la muestra."""
    params = {"ruta": ruta_parquet, "desde": desde, "hasta": hasta, "factor": factor_riesgo}
    filas = con.execute(_SQL_UNIVERSO, params).fetchall()
    columnas = ["cliente_id", "frecuencia", "valor", "recencia", "estado"]
    universo = [dict(zip(columnas, f, strict=True)) for f in filas]
    muestra = _muestra_estratificada(universo, max_muestra, semilla)
    if muestra:
        matriz = _normalizar(
            np.array([[f["frecuencia"], f["valor"], f["recencia"]] for f in muestra])
        )
        grupos = _kmeans(matriz, k, semilla)
        for f, g in zip(muestra, grupos, strict=True):
            f["grupo"] = int(g)
    return muestra


def historial_cliente(
    con: DuckDBPyConnection,
    ruta_parquet: str,
    cliente_id: str,
    desde: date | None = None,
    hasta: date | None = None,
) -> dict:
    """Historial resumido de un cliente: por producto, compras, ciclo (mediana de intervalos)
    y próxima compra esperada (última + ciclo), ordenado por la compra más reciente."""
    filas = con.execute(
        _SQL_HISTORIAL,
        {"ruta": ruta_parquet, "cliente": cliente_id, "desde": desde, "hasta": hasta},
    ).fetchall()
    columnas = [
        "producto_id", "producto_nombre", "n_compras", "cantidad_total", "valor_total",
        "ultima_compra", "ciclo",
    ]  # fmt: skip
    productos = []
    for f in filas:
        d = dict(zip(columnas, f, strict=True))
        d["proxima_compra"] = (
            d["ultima_compra"] + timedelta(days=round(d["ciclo"])) if d["ciclo"] else None
        )
        productos.append(d)
    return {"cliente_id": cliente_id, "productos": productos}
