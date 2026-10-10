"""Tipo de trabajo `analisis`: corre los análisis pedidos sobre el Parquet de un dataset.

El trabajo recibe `{"analisis_id": ...}`; la fila `analisis` (la crea la API) trae los `tipos`
y los `parametros` (FR-15, ver `ParametrosAnalisis`). Pasos:

1. **Compras del análisis** (tabla DuckDB `compras`): el Parquet filtrado por período, sin los
   productos que el catálogo marcó `durable` y con los productos de un grupo `confirmado`
   fundidos en uno (`producto_id = 'grupo:<id>'`, nombre del grupo). Un producto sin grupo es su
   propio grupo y conserva el `producto_id` del CSV. El cruce con `productos` es por nombre
   normalizado, con la misma expresión que `productos/catalogo.py`.
2. `modelo.ajustar` una vez; `ciclos` y `recompra` leen de ese ajuste (`fecha_ref` = última
   fecha de las compras del análisis).
   `riesgo`, `ofertas` y `contactar` (F4.3.T2) también leen de ese ajuste y de la predicción;
   `contactar` usa el riesgo aunque no se haya pedido (lo calcula igual) y es el único que llama
   a Jev (solo para los casos límite, ver `contactar.py`).
3. Backtest de recompra al final (pisa las tablas del ajuste) → `analisis.metricas`.
4. `analisis.resumen` (NFR-4): totales, top productos por análisis, costo de IA, versión del
   modelo y parámetros efectivos.

Eventos: `leyendo` (filas/clientes/productos), `ciclos`, `prediccion`, `riesgo`, `ofertas`,
`contactar`, `backtest`.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pyarrow as pa
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from typesafe_sdk import TypeSafeClient

from predicts.analisis import ciclos, contactar, ofertas, recompra, riesgo
from predicts.config import Settings, settings
from predicts.datos.duckdb import conexion_duckdb
from predicts.db.modelos import Analisis, Dataset, GrupoProducto, Producto
from predicts.ia import Contador
from predicts.modelo import VERSION_MODELO, ParamsModelo, ajustar
from predicts.modelo.backtest import backtest
from predicts.modelo.prediccion import predecir
from predicts.trabajos import eventos
from predicts.trabajos.registro import TrabajoEnCurso, tipo_trabajo

TIPOS = ("recompra", "ciclos", "riesgo", "ofertas", "contactar", "mensajes")
UMBRAL_DEFECTO = 0.5

# Igual que en productos/catalogo.py: así el cruce con `productos.nombre_normalizado` coincide.
_NORMALIZAR = "lower(strip_accents(regexp_replace(trim(producto_nombre), '\\s+', ' ', 'g')))"

Emitir = Callable[[str, dict], None]


class ParametrosAnalisis(BaseModel):
    """FR-15. Los que faltan toman el default de la configuración (`completar`)."""

    desde: date | None = None
    hasta: date | None = None
    min_compras: int | None = Field(default=None, ge=2)
    horizonte: int | None = Field(default=None, ge=1)
    umbral: float = Field(default=UMBRAL_DEFECTO, ge=0, le=1)
    semanas_backtest: int | None = Field(default=None, ge=1)
    factor_riesgo: float = Field(default=riesgo.FACTOR_DEFECTO, ge=0)
    max_ofertas: int = Field(default=ofertas.MAX_OFERTAS_DEFECTO, ge=1, le=50)

    @model_validator(mode="after")
    def _periodo(self) -> ParametrosAnalisis:
        if self.desde and self.hasta and self.desde > self.hasta:
            raise ValueError("desde debe ser <= hasta")
        return self

    def completar(self, cfg: Settings) -> ParametrosAnalisis:
        return self.model_copy(
            update={
                "min_compras": self.min_compras or cfg.MIN_COMPRAS,
                "horizonte": self.horizonte or cfg.HORIZONTE_DIAS,
                "semanas_backtest": self.semanas_backtest or cfg.VENTANA_VALIDACION_SEMANAS,
            }
        )


def _catalogo(db: Session, empresa_id: uuid.UUID) -> pa.Table:
    """nombre_normalizado → durable y grupo confirmado (si hay) de los productos de la empresa."""
    filas = db.execute(
        select(Producto.nombre_normalizado, Producto.tipo, GrupoProducto.id, GrupoProducto.nombre)
        .outerjoin(
            GrupoProducto,
            (GrupoProducto.id == Producto.grupo_id) & (GrupoProducto.estado == "confirmado"),
        )
        .where(Producto.empresa_id == empresa_id)
    ).all()
    return pa.table(
        {
            "nombre_normalizado": pa.array([f[0] for f in filas], pa.string()),
            "durable": pa.array([f[1] == "durable" for f in filas], pa.bool_()),
            "grupo_id": pa.array([str(f[2]) if f[2] else None for f in filas], pa.string()),
            "grupo_nombre": pa.array([f[3] for f in filas], pa.string()),
        }
    )


def ejecutar(
    db: Session,
    analisis: Analisis,
    emitir: Emitir,
    cfg: Settings | None = None,
    cliente_jev: TypeSafeClient | None = None,
    llm: Any | None = None,
) -> None:
    """Corre los análisis de `analisis` y guarda resultados, métricas y resumen (sin commit).

    `cliente_jev` y `llm`: solo para tests; por defecto `ia.cliente_jev()` / `ia.llm_texto()`
    (el segundo solo lo usa el paso `mensajes`, si se pidió).
    """
    cfg = cfg or settings()
    desconocidos = set(analisis.tipos) - set(TIPOS)
    if desconocidos or not analisis.tipos:
        raise ValueError(f"tipos de análisis inválidos: {sorted(desconocidos) or 'ninguno'}")
    params = ParametrosAnalisis.model_validate(analisis.parametros or {}).completar(cfg)
    dataset = db.get(Dataset, analisis.dataset_id)
    if dataset is None or dataset.empresa_id != analisis.empresa_id or not dataset.ruta_parquet:
        raise ValueError(f"dataset {analisis.dataset_id} no encontrado o sin ingerir")

    resultados = Path(dataset.ruta_parquet).parent / "analisis" / str(analisis.id) / "resultados"
    resultados.mkdir(parents=True, exist_ok=True)
    contador = Contador()

    con = conexion_duckdb(cfg=cfg)
    try:
        con.register("_catalogo", _catalogo(db, analisis.empresa_id))
        con.execute(
            f"""
            CREATE TABLE compras AS
            SELECT c.cliente_id, c.fecha,
                   coalesce('grupo:' || k.grupo_id, c.producto_id) AS producto_id,
                   c.producto_id AS producto_id_origen,
                   coalesce(k.grupo_nombre, c.producto_nombre) AS producto_nombre,
                   c.cantidad, c.precio_unitario, c.valor_total,
                   k.durable IS TRUE AS durable, k.grupo_id IS NOT NULL AS agrupado
            FROM read_parquet($ruta) c
            LEFT JOIN _catalogo k ON k.nombre_normalizado = {_NORMALIZAR}
            WHERE ($desde IS NULL OR CAST(c.fecha AS DATE) >= $desde)
              AND ($hasta IS NULL OR CAST(c.fecha AS DATE) <= $hasta)
            """,
            {"ruta": dataset.ruta_parquet, "desde": params.desde, "hasta": params.hasta},
        )
        con.unregister("_catalogo")
        (durables, agrupados) = con.execute(
            "SELECT count(DISTINCT producto_id) FILTER (WHERE durable), "
            "count(DISTINCT producto_id) FILTER (WHERE agrupado) FROM compras"
        ).fetchone()
        con.execute("DELETE FROM compras WHERE durable")
        filas, clientes, productos, fecha_ref = con.execute(
            "SELECT count(*), count(DISTINCT cliente_id), count(DISTINCT producto_id), "
            "CAST(max(fecha) AS DATE) FROM compras"
        ).fetchone()
        if fecha_ref is None:
            raise ValueError("no quedan compras en el período elegido")
        totales = {
            "filas": filas,
            "clientes": clientes,
            "productos": productos,
            "productos_durables_excluidos": durables,
            "grupos_aplicados": agrupados,
        }
        emitir("leyendo", {"filas": filas, "clientes": clientes, "productos": productos})
        con.execute(
            "CREATE TABLE nombres AS SELECT producto_id, any_value(producto_nombre) "
            "AS producto_nombre FROM compras GROUP BY producto_id"
        )

        modelo = ParamsModelo(min_compras=params.min_compras)
        ajuste = ajustar(con, "compras", modelo)
        resumen: dict = {
            "version_modelo": VERSION_MODELO,
            "parametros": params.model_dump(mode="json"),
            "fecha_ref": fecha_ref.isoformat(),
            "tipos": list(analisis.tipos),
            "totales": totales,
        }
        if "ciclos" in analisis.tipos:
            resumen["ciclos"] = ciclos.calcular(ajuste, "nombres", resultados)
            emitir("ciclos", {"productos": resumen["ciclos"]["productos"]})
        metricas = None
        if "recompra" in analisis.tipos:
            resumen["recompra"] = r = recompra.calcular(
                ajuste, "nombres", fecha_ref, params.horizonte, params.umbral, resultados
            )
            emitir(
                "prediccion", {"pares": r["pares_evaluados"], "recordatorios": r["recordatorios"]}
            )
        if {"riesgo", "contactar"} & set(analisis.tipos):
            resumen["riesgo"] = r = riesgo.calcular(
                ajuste, "compras", "nombres", fecha_ref, params.factor_riesgo, resultados
            )
            emitir("riesgo", {"pares": r["pares"], "clientes": r["clientes"]})
        if {"ofertas", "contactar"} & set(analisis.tipos):
            # Idempotente: recompra ya la creó si se pidió; acá hace falta aunque no.
            vista = predecir(ajuste, fecha_ref, params.horizonte)
        if "ofertas" in analisis.tipos:
            resumen["ofertas"] = r = ofertas.calcular(
                ajuste,
                "compras",
                "nombres",
                vista,
                params.umbral,
                params.horizonte,
                Path(dataset.ruta_parquet).parent / ofertas.LISTA,
                params.max_ofertas,
                resultados,
            )
            emitir("ofertas", {"ofertas": r["ofertas"], "clientes": r["clientes"]})
        if "contactar" in analisis.tipos:
            resumen["contactar"] = r = contactar.decidir(
                ajuste,
                vista,
                "nombres",
                riesgo.TABLA,
                params.umbral,
                params.horizonte,
                fecha_ref,
                resultados,
                db=db,
                empresa_id=analisis.empresa_id,
                analisis_id=analisis.id,
                cfg=cfg,
                cliente=cliente_jev,
                contador=contador,
            )
            emitir("contactar", {"clientes": r["clientes"], "por_jev": r["por_jev"]})
        if "recompra" in analisis.tipos:
            metricas = backtest(con, "compras", modelo, params.semanas_backtest, params.horizonte)
            emitir("backtest", {"pares": metricas.n_pares})
    finally:
        con.close()

    if "mensajes" in analisis.tipos:
        from predicts.trabajos import tipos_mensajes  # import diferido: evita ciclo de imports

        resumen["mensajes"] = tipos_mensajes.generar_para_analisis(
            db,
            analisis,
            dataset,
            resultados=resultados,
            llm=llm,
            cliente_jev=cliente_jev,
            contador=contador,
        )
        emitir("mensajes", {"combinaciones": resumen["mensajes"]["combinaciones"]})

    resumen["costo_ia"] = analisis.costo_ia = contador.resumen()
    analisis.version_modelo = VERSION_MODELO
    analisis.ruta_resultados = str(resultados)
    analisis.metricas = metricas.model_dump(mode="json") if metricas else None
    analisis.resumen = resumen


@tipo_trabajo("analisis")
def analisis(trabajo: TrabajoEnCurso) -> None:
    analisis_id = uuid.UUID(trabajo.parametros["analisis_id"])
    with Session(eventos._engine()) as db:
        fila = db.get(Analisis, analisis_id)
        if fila is None or fila.empresa_id != trabajo.empresa_id:
            raise ValueError(f"análisis {analisis_id} no encontrado o de otra empresa")
        fila.estado = "corriendo"
        db.commit()
        try:
            ejecutar(db, fila, lambda etapa, c: eventos.emitir(trabajo.id, etapa, c))
        except Exception:
            db.rollback()
            fila.estado = "error"
            db.commit()
            raise
        fila.estado = "listo"
        db.commit()
