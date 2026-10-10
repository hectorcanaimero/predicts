"""Esquema interno de compras (Parquet) y su validación.

Todo productor (ingesta de CSV, conectores futuros, scripts de datasets,
generador sintético) escribe exactamente este Parquet — ver
docs/arch/001-predicts.md#modelo-de-datos.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from predicts.config import Settings
from predicts.datos.duckdb import conexion_duckdb


@dataclass(frozen=True)
class ColumnaCompra:
    nombre: str
    tipo: str
    obligatoria: bool


COLUMNAS_COMPRA: tuple[ColumnaCompra, ...] = (
    ColumnaCompra("cliente_id", "VARCHAR", True),
    ColumnaCompra("fecha", "TIMESTAMP", True),
    ColumnaCompra("producto_id", "VARCHAR", True),
    ColumnaCompra("producto_id_tipo", "VARCHAR", True),
    ColumnaCompra("producto_nombre", "VARCHAR", False),
    ColumnaCompra("pedido_id", "VARCHAR", False),
    ColumnaCompra("categoria", "VARCHAR", False),
    ColumnaCompra("marca", "VARCHAR", False),
    ColumnaCompra("cantidad", "DOUBLE", False),
    ColumnaCompra("precio_unitario", "DOUBLE", False),
    ColumnaCompra("valor_total", "DOUBLE", False),
)

_PRODUCTO_ID_TIPOS_VALIDOS = ("sku", "ean")


def validar_parquet(path: str | Path, cfg: Settings | None = None) -> list[str]:
    """Valida un Parquet contra `COLUMNAS_COMPRA`.

    Devuelve la lista de errores encontrados (vacía si el Parquet es válido):
    columnas obligatorias faltantes, columnas con un tipo DuckDB distinto al
    esperado, nulos en columnas obligatorias y valores de `producto_id_tipo`
    fuera de `sku`/`ean`.
    """
    ruta = str(path)
    errores: list[str] = []
    con = conexion_duckdb(solo_lectura=True, cfg=cfg)
    try:
        columnas_parquet = {
            fila[0]: fila[1]
            for fila in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [ruta]).fetchall()
        }

        for columna in COLUMNAS_COMPRA:
            if columna.nombre not in columnas_parquet:
                if columna.obligatoria:
                    errores.append(f"falta la columna obligatoria '{columna.nombre}'")
                continue
            tipo_real = columnas_parquet[columna.nombre]
            if tipo_real != columna.tipo:
                errores.append(
                    f"columna '{columna.nombre}' tiene tipo {tipo_real}, "
                    f"se esperaba {columna.tipo}"
                )
            if columna.obligatoria:
                (n_nulos,) = con.execute(
                    f'SELECT count(*) FROM read_parquet(?) WHERE "{columna.nombre}" IS NULL',
                    [ruta],
                ).fetchone()
                if n_nulos:
                    errores.append(
                        f"columna obligatoria '{columna.nombre}' tiene {n_nulos} nulos"
                    )

        if "producto_id_tipo" in columnas_parquet:
            (n_invalidos,) = con.execute(
                "SELECT count(*) FROM read_parquet(?) "
                "WHERE producto_id_tipo NOT IN ('sku', 'ean')",
                [ruta],
            ).fetchone()
            if n_invalidos:
                errores.append(
                    f"'producto_id_tipo' tiene {n_invalidos} valores fuera de "
                    f"{'|'.join(_PRODUCTO_ID_TIPOS_VALIDOS)}"
                )
    finally:
        con.close()

    return errores
