"""Datasets públicos mapeados al esquema interno de compras.

Ver `docs/notas/datasets.md` para origen, licencia, filtros y conteos medidos
de cada dataset.
"""

from __future__ import annotations

import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import httpx
import numpy as np
import openpyxl
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from predicts.config import Settings, settings
from predicts.datos.duckdb import conexion_duckdb

ESQUEMA_COMPRAS = pa.schema(
    [
        ("cliente_id", pa.string()),
        ("fecha", pa.timestamp("us")),
        ("producto_id", pa.string()),
        ("producto_id_tipo", pa.string()),
        ("producto_nombre", pa.string()),
        ("pedido_id", pa.string()),
        ("categoria", pa.string()),
        ("marca", pa.string()),
        ("cantidad", pa.float64()),
        ("precio_unitario", pa.float64()),
        ("valor_total", pa.float64()),
    ]
)


@dataclass(frozen=True)
class ConteosDataset:
    """Conteos medidos del Parquet resultante — van en `docs/notas/datasets.md` y el PR."""

    filas: int
    clientes: int
    productos: int
    fecha_min: datetime | None
    fecha_max: datetime | None


def _muestrear_clientes(tabla: pa.Table, muestra: int, semilla: int) -> pa.Table:
    """Filtra `tabla` a `muestra` clientes elegidos al azar con semilla fija."""
    clientes = pc.unique(tabla.column("cliente_id"))
    rng = np.random.default_rng(semilla)
    indices = rng.choice(len(clientes), size=min(muestra, len(clientes)), replace=False)
    elegidos = clientes.take(pa.array(indices))
    return tabla.filter(pc.is_in(tabla.column("cliente_id"), value_set=elegidos))


def _conteos(tabla: pa.Table) -> ConteosDataset:
    fechas = tabla.column("fecha")
    return ConteosDataset(
        filas=tabla.num_rows,
        clientes=pc.count_distinct(tabla.column("cliente_id")).as_py(),
        productos=pc.count_distinct(tabla.column("producto_id")).as_py(),
        fecha_min=pc.min(fechas).as_py() if tabla.num_rows else None,
        fecha_max=pc.max(fechas).as_py() if tabla.num_rows else None,
    )


def _escribir(tabla: pa.Table, salida: str | Path) -> ConteosDataset:
    ruta = Path(salida)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(tabla, ruta)
    return _conteos(tabla)


# --------------------------------------------------------------------------
# Online Retail II (UCI, CC BY 4.0) — archive.ics.uci.edu/dataset/502
# --------------------------------------------------------------------------

URL_ONLINE_RETAIL_II = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
_NOMBRE_ZIP_ONLINE_RETAIL = "online-retail-ii.zip"
_NOMBRE_XLSX_ONLINE_RETAIL = "online_retail_II.xlsx"
_COLUMNAS_ONLINE_RETAIL = (
    "Invoice",
    "StockCode",
    "Description",
    "Quantity",
    "InvoiceDate",
    "Price",
    "Customer ID",
)


def descargar_online_retail(cfg: Settings | None = None) -> Path:
    """Descarga el Excel de Online Retail II a `DATA_DIR/raw/` si no está ya ahí.

    Fuente oficial (CC BY 4.0): https://archive.ics.uci.edu/dataset/502/online+retail+ii
    """
    cfg = cfg or settings()
    raw_dir = Path(cfg.DATA_DIR) / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    ruta_xlsx = raw_dir / _NOMBRE_XLSX_ONLINE_RETAIL
    if ruta_xlsx.exists():
        return ruta_xlsx

    ruta_zip = raw_dir / _NOMBRE_ZIP_ONLINE_RETAIL
    if not ruta_zip.exists():
        with httpx.stream(
            "GET", URL_ONLINE_RETAIL_II, follow_redirects=True, timeout=180.0
        ) as resp:
            resp.raise_for_status()
            with ruta_zip.open("wb") as destino:
                for chunk in resp.iter_bytes():
                    destino.write(chunk)

    with zipfile.ZipFile(ruta_zip) as zf:
        nombre_interno = next(n for n in zf.namelist() if n.lower().endswith(".xlsx"))
        with zf.open(nombre_interno) as origen, ruta_xlsx.open("wb") as destino:
            destino.write(origen.read())

    return ruta_xlsx


def _filas_online_retail(ruta_xlsx: Path) -> Iterator[dict]:
    """Filas válidas de las dos hojas del Excel, mapeadas al esquema interno.

    Descarta filas sin `Customer ID`, cancelaciones (`Invoice` que empieza con
    `C`) y cantidades <= 0, tal como pide la tarea.
    """
    libro = openpyxl.load_workbook(ruta_xlsx, read_only=True, data_only=True)
    try:
        for hoja in libro.worksheets:
            filas = hoja.iter_rows(values_only=True)
            encabezado = next(filas, None)
            if encabezado is None:
                continue
            indice = {str(nombre).strip(): i for i, nombre in enumerate(encabezado) if nombre}
            if not all(columna in indice for columna in _COLUMNAS_ONLINE_RETAIL):
                continue

            for fila in filas:
                invoice = fila[indice["Invoice"]]
                cliente = fila[indice["Customer ID"]]
                cantidad = fila[indice["Quantity"]]
                if invoice is None or cliente is None or cantidad is None:
                    continue
                invoice_str = str(invoice).strip()
                if invoice_str.upper().startswith("C") or cantidad <= 0:
                    continue

                precio = fila[indice["Price"]]
                descripcion = fila[indice["Description"]]
                yield {
                    "cliente_id": str(int(cliente)) if isinstance(cliente, float) else str(cliente),
                    "fecha": fila[indice["InvoiceDate"]],
                    "producto_id": str(fila[indice["StockCode"]]),
                    "producto_id_tipo": "sku",
                    "producto_nombre": str(descripcion) if descripcion is not None else None,
                    "pedido_id": invoice_str,
                    "categoria": None,
                    "marca": None,
                    "cantidad": float(cantidad),
                    "precio_unitario": float(precio) if precio is not None else None,
                    "valor_total": float(cantidad) * float(precio) if precio is not None else None,
                }
    finally:
        libro.close()


def mapear_online_retail(
    ruta_xlsx: str | Path, *, muestra: int | None = None, semilla: int = 0
) -> pa.Table:
    """Mapea el Excel de Online Retail II al esquema interno de compras.

    Expuesta por separado de `preparar_online_retail` para poder probar el
    mapeo contra un Excel de fixture sin red.
    """
    filas = list(_filas_online_retail(Path(ruta_xlsx)))
    tabla = pa.Table.from_pylist(filas, schema=ESQUEMA_COMPRAS)
    if muestra is not None:
        tabla = _muestrear_clientes(tabla, muestra, semilla)
    return tabla


def preparar_online_retail(
    salida: str | Path,
    *,
    muestra: int | None = None,
    semilla: int = 0,
    cfg: Settings | None = None,
) -> ConteosDataset:
    """Descarga (si falta), mapea y escribe Online Retail II en `salida`."""
    ruta_xlsx = descargar_online_retail(cfg)
    tabla = mapear_online_retail(ruta_xlsx, muestra=muestra, semilla=semilla)
    return _escribir(tabla, salida)


# --------------------------------------------------------------------------
# Instacart Market Basket Analysis — sin espejo público confirmado sin login
# --------------------------------------------------------------------------

# Instacart no publica fechas reales de pedido, solo `order_number` y
# `days_since_prior_order`. La fecha es sintética: esta fecha base fija más la
# suma acumulada de `days_since_prior_order` por cliente — documentado en
# docs/notas/datasets.md, no son fechas reales.
FECHA_BASE_INSTACART = date(2023, 1, 1)

ARCHIVOS_INSTACART_REQUERIDOS = ("orders.csv", "products.csv", "aisles.csv", "departments.csv")
ARCHIVOS_INSTACART_PRODUCTOS = ("order_products__prior.csv", "order_products__train.csv")

MENSAJE_INSTACART_SIN_FUENTE = (
    "No encontramos un espejo público de Instacart Market Basket Analysis descargable sin "
    "login (se buscó en Hugging Face; no hay uno con licencia clara). El origen es la "
    "competencia de Kaggle https://www.kaggle.com/competitions/instacart-market-basket-analysis "
    "(requiere cuenta). Descargá ahí orders.csv, products.csv, aisles.csv, departments.csv y "
    "order_products__prior.csv (y/o order_products__train.csv), y pasá la carpeta con --desde."
)


def _literal_sql(ruta: Path) -> str:
    """Ruta como literal SQL — DuckDB no admite parámetros preparados en DDL."""
    return "'" + str(ruta).replace("'", "''") + "'"


def _validar_carpeta_instacart(carpeta: Path) -> list[str]:
    archivos_productos = [n for n in ARCHIVOS_INSTACART_PRODUCTOS if (carpeta / n).exists()]
    faltantes = [n for n in ARCHIVOS_INSTACART_REQUERIDOS if not (carpeta / n).exists()]
    if not archivos_productos:
        faltantes.append(" o ".join(ARCHIVOS_INSTACART_PRODUCTOS))
    return faltantes


def preparar_instacart(
    salida: str | Path,
    *,
    carpeta: str | Path | None,
    muestra: int | None = None,
    semilla: int = 0,
    cfg: Settings | None = None,
) -> ConteosDataset:
    """Construye el Parquet de Instacart a partir de los CSV originales en `carpeta`.

    No hay descarga automática: ver `MENSAJE_INSTACART_SIN_FUENTE`. Las fechas
    son sintéticas (`FECHA_BASE_INSTACART` + acumulado de
    `days_since_prior_order`), no fechas reales de pedido.
    """
    if carpeta is None:
        raise ValueError(MENSAJE_INSTACART_SIN_FUENTE)

    ruta_carpeta = Path(carpeta)
    faltantes = _validar_carpeta_instacart(ruta_carpeta)
    if faltantes:
        raise ValueError(
            f"Faltan archivos de Instacart en {ruta_carpeta}: {', '.join(faltantes)}. "
            + MENSAJE_INSTACART_SIN_FUENTE
        )

    archivos_productos = [n for n in ARCHIVOS_INSTACART_PRODUCTOS if (ruta_carpeta / n).exists()]

    def _vista(nombre: str, archivo: str) -> str:
        return (
            f"CREATE VIEW {nombre} AS SELECT * FROM "
            f"read_csv_auto({_literal_sql(ruta_carpeta / archivo)})"
        )

    con = conexion_duckdb(cfg=cfg)
    try:
        con.execute(_vista("orders", "orders.csv"))
        con.execute(
            "CREATE VIEW order_products AS "
            + " UNION ALL ".join(
                f"SELECT order_id, product_id FROM "
                f"read_csv_auto({_literal_sql(ruta_carpeta / n)})"
                for n in archivos_productos
            )
        )
        con.execute(_vista("products", "products.csv"))
        con.execute(_vista("aisles", "aisles.csv"))
        con.execute(_vista("departments", "departments.csv"))

        if muestra is not None:
            filas_ids = con.execute("SELECT DISTINCT user_id FROM orders").fetchall()
            ids_totales = [fila[0] for fila in filas_ids]
            rng = np.random.default_rng(semilla)
            tamano = min(muestra, len(ids_totales))
            elegidos = rng.choice(ids_totales, size=tamano, replace=False)
            con.execute("CREATE TABLE usuarios_muestra (user_id BIGINT)")
            con.executemany(
                "INSERT INTO usuarios_muestra VALUES (?)", [(int(u),) for u in elegidos]
            )
            con.execute(
                "CREATE VIEW orders_filtradas AS "
                "SELECT o.* FROM orders o JOIN usuarios_muestra u USING (user_id)"
            )
        else:
            con.execute("CREATE VIEW orders_filtradas AS SELECT * FROM orders")

        con.execute(
            f"""
            CREATE VIEW ordenes_con_fecha AS
            SELECT
                order_id,
                user_id,
                CAST(
                    DATE '{FECHA_BASE_INSTACART.isoformat()}' + INTERVAL (
                        SUM(COALESCE(days_since_prior_order, 0)) OVER (
                            PARTITION BY user_id ORDER BY order_number
                            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                        )
                    ) DAY AS TIMESTAMP
                ) AS fecha
            FROM orders_filtradas
            """
        )

        con.execute(
            """
            CREATE VIEW compras_instacart AS
            SELECT
                CAST(o.user_id AS VARCHAR) AS cliente_id,
                o.fecha AS fecha,
                CAST(op.product_id AS VARCHAR) AS producto_id,
                'sku' AS producto_id_tipo,
                p.product_name AS producto_nombre,
                CAST(o.order_id AS VARCHAR) AS pedido_id,
                d.department || ' / ' || a.aisle AS categoria,
                CAST(NULL AS VARCHAR) AS marca,
                1.0 AS cantidad,
                CAST(NULL AS DOUBLE) AS precio_unitario,
                CAST(NULL AS DOUBLE) AS valor_total
            FROM ordenes_con_fecha o
            JOIN order_products op USING (order_id)
            JOIN products p ON p.product_id = op.product_id
            JOIN aisles a ON a.aisle_id = p.aisle_id
            JOIN departments d ON d.department_id = p.department_id
            """
        )
        tabla = (
            con.execute("SELECT * FROM compras_instacart").to_arrow_table().cast(ESQUEMA_COMPRAS)
        )
    finally:
        con.close()

    return _escribir(tabla, salida)
