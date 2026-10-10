"""SQL de solo lectura para el agente analista (FR-22): vistas fijas de un dataset y de su último
análisis, y `consultar(sql)` con las defensas en capas:

1. **Validación**: una sola sentencia (`duckdb.extract_statements`) de tipo `SELECT` (incluye
   `WITH`) y sin funciones de archivo, red o extensiones (`_PROHIBIDAS`; el chequeo es por
   palabra en todo el texto, aun dentro de literales: preferimos un falso positivo).
2. **Conexión**: tras crear las vistas, `enable_external_access=false` con `allowed_directories`
   = la carpeta del dataset (las vistas leen sus Parquet) y `lock_configuration=true`, así que
   nada de lo que pase la validación puede leer otros archivos, la red ni cambiar la config.
3. **Recursos**: `memory_limit` de 1 GB, tope de `MAX_FILAS` filas y `TIMEOUT_S` segundos
   (`con.interrupt()` desde un `Timer`).

DuckDB no admite `read_only` sobre `:memory:`: la conexión es de solo lectura porque solo se
ejecutan sentencias `SELECT` y los datos viven en Parquet fuera de la base.
"""

from __future__ import annotations

import re
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
from sqlalchemy import select
from sqlalchemy.orm import Session

from predicts.analisis import ciclos, ofertas, recompra, riesgo
from predicts.db.modelos import Analisis, Dataset, GrupoProducto, Producto

MAX_FILAS = 1000
TIMEOUT_S = 10.0
MEMORIA = "1GB"

_PROHIBIDAS = re.compile(
    r"\b(read_\w+|\w+_scan|parquet_\w+|sniff_csv|glob|query|query_table|getenv|httpfs|copy|"
    r"attach|detach|install|load|export|import|pragma)\b",
    re.IGNORECASE,
)

# Vista → (descripción, {columna: descripción}). Las columnas reales salen de `DESCRIBE`; acá
# solo sus descripciones para el LLM.
VISTAS: dict[str, tuple[str, dict[str, str]]] = {
    "compras": (
        "Cada línea de compra del dataset (todas las filas, sin filtrar por período).",
        {
            "cliente_id": "id del cliente",
            "fecha": "fecha y hora de la compra",
            "producto_id": "id del producto en el CSV (SKU o EAN)",
            "producto_id_tipo": "'sku' o 'ean'",
            "producto_nombre": "nombre del producto",
            "pedido_id": "id del pedido (puede ser NULL)",
            "categoria": "categoría según el CSV (puede ser NULL)",
            "marca": "marca (puede ser NULL)",
            "cantidad": "unidades compradas",
            "precio_unitario": "precio por unidad",
            "valor_total": "importe de la línea",
        },
    ),
    "productos": (
        "Catálogo de productos de la empresa con su clasificación.",
        {
            "producto_id": "id del producto en el CSV (une con compras.producto_id)",
            "producto_nombre": "nombre del producto",
            "categoria": "categoría asignada",
            "tipo": "'recompra' (consumible), 'durable' (no se recompra) o 'desconocido'",
            "grupo_producto_id": "'grupo:<id>' si el producto está en un grupo confirmado de "
            "equivalentes (así aparece en predicciones/ciclos/riesgo/ofertas); NULL si no",
            "grupo_nombre": "nombre del grupo confirmado (NULL si no hay)",
        },
    ),
    "predicciones": (
        "Predicción de recompra por cliente y producto del último análisis (horizonte del "
        "análisis). Los productos durables no están; los de un grupo aparecen como 'grupo:<id>'.",
        {
            "cliente_id": "id del cliente",
            "producto_id": "id del producto o 'grupo:<id>'",
            "producto_nombre": "nombre del producto o del grupo",
            "ciclo": "ciclo de recompra estimado del par, en días",
            "p": "probabilidad de recompra dentro del horizonte (0 a 1)",
            "fecha_probable": "fecha más probable de la próxima compra",
            "fecha_min": "inicio de la ventana probable",
            "fecha_max": "fin de la ventana probable",
            "n_compras": "días de compra del par",
            "dias_desde_ultima": "días desde la última compra a la fecha de referencia",
            "posible_abandono": "true si ya pasó mucho más que su ciclo",
            "motivo": "explicación legible",
        },
    ),
    "ciclos": (
        "Ciclo típico de recompra por producto del último análisis.",
        {
            "producto_id": "id del producto o 'grupo:<id>'",
            "producto_nombre": "nombre del producto o del grupo",
            "ciclo_mediano": "ciclo típico en días",
            "dispersion": "dispersión del ciclo (MAD, días)",
            "desvio_log": "desvío de los intervalos en escala logarítmica",
            "clientes_recurrentes": "clientes que lo compraron más de una vez",
        },
    ),
    "riesgo": (
        "Clientes en riesgo de abandono del último análisis, por producto o por tienda.",
        {
            "nivel": "'producto' (dejó de comprar un producto) o 'tienda' (dejó de comprar)",
            "cliente_id": "id del cliente",
            "producto_id": "id del producto (NULL en nivel 'tienda')",
            "producto_nombre": "nombre del producto (NULL en nivel 'tienda')",
            "n_compras": "días de compra",
            "ciclo": "ciclo habitual en días",
            "dispersion": "dispersión del ciclo en días",
            "dias_desde_ultima": "días desde la última compra",
            "atraso": "días más allá del ciclo esperado",
            "valor": "valor histórico comprado",
            "motivo": "explicación legible",
        },
    ),
    "ofertas": (
        "Ofertas personalizadas recomendadas por cliente del último análisis.",
        {
            "cliente_id": "id del cliente",
            "producto_id": "producto ofrecido",
            "producto_nombre": "nombre del producto ofrecido",
            "puntaje": "puntaje combinado (mayor = mejor oferta)",
            "p_recompra": "probabilidad de recompra si vino de la predicción",
            "lift": "lift de co-compra si vino de la co-compra",
            "por_producto": "producto ya comprado que dio el lift",
            "descuento": "descuento de la lista de ofertas (fracción)",
            "fuentes": "lista de fuentes: recompra, cocompra, oferta",
            "motivo": "explicación legible",
        },
    ),
}

# Vista de resultados → archivo del análisis.
_RESULTADOS = {
    "predicciones": recompra.NOMBRE,
    "ciclos": ciclos.NOMBRE,
    "riesgo": riesgo.NOMBRE,
    "ofertas": ofertas.NOMBRE,
}


class ConsultaRechazada(ValueError):
    """La sentencia no pasó la validación o falló al ejecutarse (el mensaje va al LLM)."""


@dataclass
class Resultado:
    columnas: list[str]
    filas: list[dict[str, Any]]
    n_filas: int
    truncado: bool


@dataclass
class Conexion:
    con: duckdb.DuckDBPyConnection
    vistas: list[str]
    analisis_id: uuid.UUID | None = None
    esquema: str = field(default="")


def _literal(ruta: Path) -> str:
    return "'" + str(ruta).replace("'", "''") + "'"


def abrir(
    ruta_parquet: str | Path,
    ruta_resultados: str | Path | None = None,
    productos: pa.Table | None = None,
    analisis_id: uuid.UUID | None = None,
) -> Conexion:
    """Conexión con las vistas del dataset (`compras`, `productos`) y, si hay `ruta_resultados`,
    las del análisis cuyos archivos existen. `productos`: ver `catalogo`."""
    ruta_parquet = Path(ruta_parquet).resolve()
    con = duckdb.connect(":memory:")
    try:
        con.execute(f"SET memory_limit = '{MEMORIA}'")
        con.execute(f"CREATE VIEW compras AS SELECT * FROM read_parquet({_literal(ruta_parquet)})")
        vistas = ["compras"]
        if productos is not None:
            con.register("_productos", productos)
            con.execute("CREATE TABLE productos AS SELECT * FROM _productos")
            con.unregister("_productos")
            vistas.append("productos")
        permitidos = [str(ruta_parquet.parent)]
        if ruta_resultados is not None:
            carpeta = Path(ruta_resultados).resolve()
            for vista, archivo in _RESULTADOS.items():
                if (carpeta / archivo).exists():
                    con.execute(
                        f"CREATE VIEW {vista} AS "
                        f"SELECT * FROM read_parquet({_literal(carpeta / archivo)})"
                    )
                    vistas.append(vista)
            permitidos.append(str(carpeta))
        con.execute("SET allowed_directories = $1", [permitidos])
        con.execute("SET enable_external_access = false")
        con.execute("SET lock_configuration = true")
        conexion = Conexion(con, vistas, analisis_id)
        conexion.esquema = esquema(conexion)
        return conexion
    except Exception:
        con.close()
        raise


def esquema(conexion: Conexion) -> str:
    """Texto para el LLM: cada vista disponible con sus columnas, tipos y descripciones."""
    partes = []
    for vista in conexion.vistas:
        descripcion, columnas = VISTAS[vista]
        lineas = [f"{vista}: {descripcion}"]
        for nombre, tipo, *_ in conexion.con.execute(f"DESCRIBE {vista}").fetchall():
            lineas.append(f"  - {nombre} ({tipo}): {columnas.get(nombre, '')}".rstrip(": "))
        partes.append("\n".join(lineas))
    faltan = [v for v in VISTAS if v not in conexion.vistas]
    if faltan:
        partes.append(f"No disponibles (sin análisis que las genere): {', '.join(faltan)}")
    return "\n\n".join(partes)


def validar(sql: str) -> None:
    """`ConsultaRechazada` si `sql` no es una única sentencia SELECT/WITH sin funciones
    prohibidas."""
    try:
        sentencias = duckdb.extract_statements(sql)
    except duckdb.Error as e:
        raise ConsultaRechazada(f"SQL inválido: {e}") from e
    if len(sentencias) != 1:
        raise ConsultaRechazada("Se permite exactamente una sentencia por consulta.")
    if sentencias[0].type != duckdb.StatementType.SELECT:
        raise ConsultaRechazada("Solo se permiten consultas SELECT o WITH.")
    if prohibida := _PROHIBIDAS.search(sql):
        raise ConsultaRechazada(f"Uso no permitido: {prohibida.group(0)}.")


def consultar(
    conexion: Conexion, sql: str, max_filas: int = MAX_FILAS, timeout_s: float = TIMEOUT_S
) -> Resultado:
    """Valida y ejecuta `sql`; devuelve hasta `max_filas` filas (`truncado` si había más)."""
    validar(sql)
    con = conexion.con
    temporizador = threading.Timer(timeout_s, con.interrupt)
    temporizador.start()
    try:
        cursor = con.execute(sql)
        columnas = [d[0] for d in cursor.description]
        filas = cursor.fetchmany(max_filas + 1)
    except duckdb.InterruptException as e:
        raise ConsultaRechazada(f"La consulta superó el tiempo máximo de {timeout_s:g} s.") from e
    except duckdb.Error as e:
        raise ConsultaRechazada(f"Error al ejecutar: {e}") from e
    finally:
        temporizador.cancel()
    truncado = len(filas) > max_filas
    filas = filas[:max_filas]
    return Resultado(
        columnas=columnas,
        filas=[dict(zip(columnas, f, strict=True)) for f in filas],
        n_filas=len(filas),
        truncado=truncado,
    )


def catalogo(db: Session, empresa_id: uuid.UUID) -> pa.Table:
    """Tabla `productos` (ver `VISTAS`) con el catálogo de la empresa."""
    filas = db.execute(
        select(
            Producto.producto_id_origen,
            Producto.nombre,
            Producto.categoria,
            Producto.tipo,
            GrupoProducto.id,
            GrupoProducto.nombre,
        )
        .outerjoin(
            GrupoProducto,
            (GrupoProducto.id == Producto.grupo_id) & (GrupoProducto.estado == "confirmado"),
        )
        .where(Producto.empresa_id == empresa_id)
    ).all()
    return pa.table(
        {
            "producto_id": pa.array([f[0] for f in filas], pa.string()),
            "producto_nombre": pa.array([f[1] for f in filas], pa.string()),
            "categoria": pa.array([f[2] for f in filas], pa.string()),
            "tipo": pa.array([f[3] for f in filas], pa.string()),
            "grupo_producto_id": pa.array(
                [f"grupo:{f[4]}" if f[4] else None for f in filas], pa.string()
            ),
            "grupo_nombre": pa.array([f[5] for f in filas], pa.string()),
        }
    )


def abrir_dataset(db: Session, dataset: Dataset) -> Conexion:
    """`abrir` con el Parquet del dataset, el catálogo de su empresa y su último análisis
    `listo` (si hay). El llamador ya verificó que `dataset` es de la empresa."""
    if not dataset.ruta_parquet:
        raise ValueError(f"dataset {dataset.id} sin ingerir")
    analisis = db.scalars(
        select(Analisis)
        .where(
            Analisis.dataset_id == dataset.id,
            Analisis.empresa_id == dataset.empresa_id,
            Analisis.estado == "listo",
        )
        .order_by(Analisis.creado_en.desc())
        .limit(1)
    ).first()
    return abrir(
        dataset.ruta_parquet,
        analisis.ruta_resultados if analisis else None,
        catalogo(db, dataset.empresa_id),
        analisis.id if analisis else None,
    )
