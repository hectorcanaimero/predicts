"""Servidor MCP (F7.1.T3): el agente analista (F7.1.T1) y los resultados de un análisis,
expuestos como herramientas MCP (SDK `mcp` 2.x), autenticadas con una API key de empresa
(F2.2.T2, igual que `auth.api_keys.empresa_por_api_key`).

Dos transportes, una sola forma de autenticar (ver `_empresa`):

- **stdio**: sin headers HTTP, así que la clave es fija para todo el proceso (la pasa
  `predicts mcp --api-key`, ver `comandos/mcp.py`); una empresa por proceso.
- **HTTP streamable**: cada request trae su propia clave en `Authorization: Bearer pk_...`
  (`ctx.headers`), así que el mismo servidor sirve a varias empresas a la vez.

Herramientas: `listar_proyectos`, `listar_datasets`, `recordatorios`, `ciclos_producto`,
`clientes_en_riesgo` (sobre los Parquet del último análisis `listo`, ver `agente/sql.py` y
`analisis/*.py` para las columnas) y `preguntar` (el grafo de `agente/grafo.py`).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path

import duckdb
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import select
from sqlalchemy.orm import Session

from predicts.agente.grafo import preguntar as preguntar_agente
from predicts.agente.sql import abrir_dataset
from predicts.analisis import ciclos, recompra, riesgo
from predicts.auth.api_keys import empresa_por_api_key
from predicts.db.modelos import Analisis, Dataset, Empresa, Proyecto
from predicts.db.sesion import SessionLocal
from predicts.errores import ErrorApi
from predicts.tenancy import de_empresa, obtener_o_404

NOMBRE_SERVIDOR = "predicts"


def _clave(ctx: Context, clave_fija: str | None) -> str | None:
    """`Authorization` de la request HTTP si la hay; si no (stdio), la clave fija del proceso."""
    if ctx.headers is not None:
        return ctx.headers.get("authorization")
    return f"Bearer {clave_fija}" if clave_fija else None


def _empresa(db: Session, ctx: Context, clave_fija: str | None) -> Empresa:
    try:
        return empresa_por_api_key(db, _clave(ctx, clave_fija))
    except ErrorApi as e:
        raise ToolError(e.codigo) from e


@contextmanager
def _sesion_empresa(
    db_factory: Callable[[], Session], ctx: Context, clave_fija: str | None
) -> Generator[tuple[Session, Empresa]]:
    db = db_factory()
    try:
        yield db, _empresa(db, ctx, clave_fija)
    finally:
        db.close()


def _analisis_de_empresa(db: Session, empresa: Empresa, analisis_id: uuid.UUID) -> Analisis:
    try:
        return obtener_o_404(db, Analisis, analisis_id, empresa.id)
    except ErrorApi as e:
        raise ToolError(e.codigo) from e


def _ruta_resultado(analisis: Analisis, nombre_archivo: str) -> str:
    ruta = Path(analisis.ruta_resultados or "") / nombre_archivo
    if not analisis.ruta_resultados or not ruta.exists():
        raise ToolError(f"El análisis no tiene resultados de '{nombre_archivo}'.")
    return str(ruta)


def _consultar_parquet(ruta: str, columnas: str, filtro: str, params: list) -> list[dict]:
    """`SELECT {columnas} FROM read_parquet(ruta) {filtro}`, con `?` en `filtro` por cada
    elemento de `params` (en orden). Devuelve filas JSON-serializables (fechas incluidas)."""
    con = duckdb.connect(":memory:")
    try:
        cursor = con.execute(f"SELECT {columnas} FROM read_parquet(?) {filtro}", [ruta, *params])
        nombres = [d[0] for d in cursor.description]
        filas = [dict(zip(nombres, f, strict=True)) for f in cursor.fetchall()]
    finally:
        con.close()
    return json.loads(json.dumps(filas, default=str))


def crear_servidor(
    db_factory: Callable[[], Session] = SessionLocal, clave: str | None = None
) -> MCPServer:
    """Servidor MCP con las herramientas de F7.1.T3. `clave`: API key fija para stdio (ignorada
    si la request HTTP trae su propio `Authorization`)."""
    servidor = MCPServer(NOMBRE_SERVIDOR)

    @servidor.tool()
    def listar_proyectos(ctx: Context) -> list[dict]:
        """Proyectos de la empresa autenticada."""
        with _sesion_empresa(db_factory, ctx, clave) as (db, empresa):
            consulta = de_empresa(select(Proyecto), empresa.id).order_by(Proyecto.creado_en)
            return [
                {
                    "id": str(p.id),
                    "nombre": p.nombre,
                    "idioma_mensajes": p.idioma_mensajes,
                    "tono": p.tono,
                }
                for p in db.scalars(consulta).all()
            ]

    @servidor.tool()
    def listar_datasets(ctx: Context) -> list[dict]:
        """Datasets de la empresa autenticada, de todos sus proyectos."""
        with _sesion_empresa(db_factory, ctx, clave) as (db, empresa):
            consulta = de_empresa(select(Dataset), empresa.id).order_by(Dataset.creado_en)
            return [
                {
                    "id": str(d.id),
                    "proyecto_id": str(d.proyecto_id),
                    "nombre_archivo": d.nombre_archivo,
                    "estado": d.estado,
                }
                for d in db.scalars(consulta).all()
            ]

    @servidor.tool()
    def recordatorios(
        analisis_id: uuid.UUID, ctx: Context, dias: int = 7, limite: int = 20
    ) -> list[dict]:
        """Próximos recordatorios de recompra del análisis: predicciones con `fecha_probable`
        entre hoy y `dias` días, ordenadas por probabilidad descendente."""
        with _sesion_empresa(db_factory, ctx, clave) as (db, empresa):
            analisis = _analisis_de_empresa(db, empresa, analisis_id)
            ruta = _ruta_resultado(analisis, recompra.NOMBRE)
        return _consultar_parquet(
            ruta,
            "cliente_id, producto_id, producto_nombre, ciclo, p, fecha_probable, fecha_min, "
            "fecha_max, n_compras, dias_desde_ultima, motivo",
            "WHERE fecha_probable BETWEEN current_date AND current_date + CAST(? AS INTEGER) "
            "ORDER BY p DESC, fecha_probable LIMIT ?",
            [dias, limite],
        )

    @servidor.tool()
    def ciclos_producto(analisis_id: uuid.UUID, producto: str, ctx: Context) -> list[dict]:
        """Ciclo típico (mediana, dispersión) de los productos o grupos del análisis cuyo id
        coincide exactamente con `producto` o cuyo nombre lo contiene (sin mayúsculas)."""
        with _sesion_empresa(db_factory, ctx, clave) as (db, empresa):
            analisis = _analisis_de_empresa(db, empresa, analisis_id)
            ruta = _ruta_resultado(analisis, ciclos.NOMBRE)
        return _consultar_parquet(
            ruta,
            "producto_id, producto_nombre, ciclo_mediano, dispersion, desvio_log, "
            "clientes_recurrentes",
            "WHERE producto_id = ? OR producto_nombre ILIKE ?",
            [producto, f"%{producto}%"],
        )

    @servidor.tool()
    def clientes_en_riesgo(analisis_id: uuid.UUID, ctx: Context, limite: int = 20) -> list[dict]:
        """Clientes en riesgo de abandono del análisis (nivel producto o tienda), por valor
        histórico descendente."""
        with _sesion_empresa(db_factory, ctx, clave) as (db, empresa):
            analisis = _analisis_de_empresa(db, empresa, analisis_id)
            ruta = _ruta_resultado(analisis, riesgo.NOMBRE)
        return _consultar_parquet(
            ruta,
            "nivel, cliente_id, producto_id, producto_nombre, n_compras, ciclo, dispersion, "
            "dias_desde_ultima, atraso, valor, motivo",
            "ORDER BY valor DESC NULLS LAST, n_compras DESC LIMIT ?",
            [limite],
        )

    @servidor.tool()
    def preguntar(dataset_id: uuid.UUID, pregunta: str, ctx: Context) -> dict:
        """Responde `pregunta` sobre el dataset con el agente analista (F7.1.T1): dataset y
        último análisis `listo`."""
        with _sesion_empresa(db_factory, ctx, clave) as (db, empresa):
            try:
                dataset = obtener_o_404(db, Dataset, dataset_id, empresa.id)
            except ErrorApi as e:
                raise ToolError(e.codigo) from e
            if not dataset.ruta_parquet or dataset.estado != "listo":
                raise ToolError("El dataset todavía no está listo.")
            conexion = abrir_dataset(db, dataset)
            try:
                respuesta = preguntar_agente(conexion, pregunta)
            finally:
                conexion.con.close()
            return respuesta.model_dump(mode="json")

    return servidor
