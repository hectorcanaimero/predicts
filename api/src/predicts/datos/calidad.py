"""Informe de calidad de `compras.parquet` (FR-6) y viabilidad por análisis (FR-7).

Todo con consultas DuckDB sobre el Parquet ya escrito por `ingesta.py`; los descartes por
motivo no viven en el Parquet (son filas que nunca se escribieron), así que `calcular` los
recibe como parámetro, tal como los devuelve `ResumenIngesta.descartadas`.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from predicts.config import Settings, settings
from predicts.datos.duckdb import conexion_duckdb


class DistribucionComprasCliente(BaseModel):
    minimo: int
    maximo: int
    promedio: float
    mediana: float


class ParesConHistoria(BaseModel):
    total_pares: int
    con_historia_suficiente: int
    porcentaje: float


class Viabilidad(BaseModel):
    viable: bool
    motivo: str | None = None


class InformeCalidad(BaseModel):
    filas: int
    clientes: int
    productos: int
    fecha_min: datetime | None
    fecha_max: datetime | None
    duplicados_exactos: int
    descartadas: dict[str, int]
    distribucion_compras_cliente: DistribucionComprasCliente
    pares: ParesConHistoria
    viabilidad: dict[str, Viabilidad]


def _viabilidad(condicion: bool, motivo: str) -> Viabilidad:
    return Viabilidad(viable=condicion, motivo=None if condicion else motivo)


def calcular(
    ruta_parquet: str | Path,
    descartes_ingesta: dict[str, int] | None = None,
    cfg: Settings | None = None,
) -> InformeCalidad:
    """Calcula el `InformeCalidad` de `ruta_parquet`.

    `descartes_ingesta` es el `ResumenIngesta.descartadas` de la ingesta que produjo este
    Parquet (vacío si no se tiene, p. ej. un Parquet de otro origen).
    """
    ruta = str(ruta_parquet)
    cfg = cfg or settings()

    con = conexion_duckdb(solo_lectura=True, cfg=cfg)
    try:
        filas, clientes, productos, fecha_min, fecha_max = con.execute(
            "SELECT count(*), count(DISTINCT cliente_id), count(DISTINCT producto_id), "
            "min(fecha), max(fecha) FROM read_parquet(?)",
            [ruta],
        ).fetchone()

        (duplicados,) = con.execute(
            "SELECT coalesce(sum(cnt - 1), 0) FROM "
            "(SELECT *, count(*) AS cnt FROM read_parquet(?) GROUP BY ALL) WHERE cnt > 1",
            [ruta],
        ).fetchone()

        minimo, maximo, promedio, mediana = con.execute(
            "SELECT coalesce(min(n), 0), coalesce(max(n), 0), coalesce(avg(n), 0.0), "
            "coalesce(median(n), 0.0) FROM "
            "(SELECT count(*) AS n FROM read_parquet(?) GROUP BY cliente_id)",
            [ruta],
        ).fetchone()

        total_pares, con_historia = con.execute(
            "SELECT count(*), count(*) FILTER (WHERE dias >= ?) FROM "
            "(SELECT count(DISTINCT date_trunc('day', fecha)) AS dias FROM read_parquet(?) "
            "GROUP BY cliente_id, producto_id)",
            [cfg.MIN_COMPRAS, ruta],
        ).fetchone()

        (clientes_multi_producto,) = con.execute(
            "SELECT count(*) FILTER (WHERE n >= 2) FROM "
            "(SELECT count(DISTINCT producto_id) AS n FROM read_parquet(?) GROUP BY cliente_id)",
            [ruta],
        ).fetchone()
    finally:
        con.close()

    porcentaje_pares = con_historia / total_pares if total_pares else 0.0
    motivo_sin_historia = (
        f"ningún par cliente-producto tiene al menos {cfg.MIN_COMPRAS} días de compra "
        "distintos"
    )

    viabilidad = {
        "recompra": _viabilidad(con_historia >= 1, motivo_sin_historia),
        "riesgo": _viabilidad(con_historia >= 1, motivo_sin_historia),
        "ofertas": _viabilidad(
            clientes_multi_producto >= 1,
            "ningún cliente compró más de un producto distinto, no hay co-compra para "
            "calcular ofertas",
        ),
    }

    return InformeCalidad(
        filas=filas,
        clientes=clientes,
        productos=productos,
        fecha_min=fecha_min,
        fecha_max=fecha_max,
        duplicados_exactos=int(duplicados),
        descartadas=dict(descartes_ingesta or {}),
        distribucion_compras_cliente=DistribucionComprasCliente(
            minimo=int(minimo), maximo=int(maximo), promedio=float(promedio),
            mediana=float(mediana),
        ),
        pares=ParesConHistoria(
            total_pares=total_pares, con_historia_suficiente=con_historia,
            porcentaje=porcentaje_pares,
        ),
        viabilidad=viabilidad,
    )
