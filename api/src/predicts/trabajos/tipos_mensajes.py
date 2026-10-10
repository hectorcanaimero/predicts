"""Tipo de trabajo `mensajes`: regenera a pedido las plantillas de un análisis ya terminado
(`POST /analisis/{id}/plantillas/regenerar`).

`generar_para_analisis` es el paso opcional que `analisis.orquestador` llama al final de un
análisis que pidió el tipo `mensajes` (con `forzar=False`: solo genera lo que falta en caché).
El trabajo `mensajes` llama a lo mismo con `forzar=True`: regenera también lo que ya estaba
cacheado, salvo lo `editada`.

`_combinaciones` arma la lista de (producto o grupo, o categoría si tiene pocos clientes) × tipo
a partir de los resultados ya escritos del análisis (`recompra.parquet` → `recordatorio`,
`ofertas.parquet` → `oferta`, `riesgo.parquet` → `reactivacion`, más una combinación `general`
si hay riesgo a nivel tienda). "Pocos clientes" se mide ahí mismo: cuántos clientes distintos
tiene ese producto en el archivo de resultados correspondiente.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import duckdb
import pyarrow as pa
from langchain_openai import ChatOpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session
from typesafe_sdk import TypeSafeClient

from predicts.analisis import ofertas, recompra, riesgo
from predicts.db.modelos import Analisis, Dataset, Producto, Proyecto
from predicts.ia import Contador
from predicts.mensajes import plantillas, revision
from predicts.mensajes.plantillas import Combinacion
from predicts.trabajos import eventos
from predicts.trabajos.registro import TrabajoEnCurso, tipo_trabajo

MIN_CLIENTES_PRODUCTO = 5

# Debe coincidir con `predicts.analisis.orquestador._NORMALIZAR` (mismo cruce por nombre de
# producto); no se importa de ahí para no crear un ciclo de imports entre los dos módulos.
_NORMALIZAR = "lower(strip_accents(regexp_replace(trim(producto_nombre), '\\s+', ' ', 'g')))"

_FUENTES = {
    "recordatorio": recompra.NOMBRE,
    "oferta": ofertas.NOMBRE,
    "reactivacion": riesgo.NOMBRE,
}


def _categorias_empresa(db: Session, empresa_id: uuid.UUID) -> list[tuple[str, str]]:
    filas = db.execute(
        select(Producto.nombre_normalizado, Producto.categoria).where(
            Producto.empresa_id == empresa_id, Producto.categoria.is_not(None)
        )
    ).all()
    return [(f[0], f[1]) for f in filas if f[1] is not None]


def _combinaciones(resultados: Path, categorias: list[tuple[str, str]]) -> list[Combinacion]:
    con = duckdb.connect()
    try:
        con.register(
            "_categorias",
            pa.table(
                {
                    "nombre_normalizado": pa.array([c[0] for c in categorias], pa.string()),
                    "categoria": pa.array([c[1] for c in categorias], pa.string()),
                }
            ),
        )
        combos: dict[str, Combinacion] = {}
        for tipo, nombre_archivo in _FUENTES.items():
            ruta = resultados / nombre_archivo
            if not ruta.exists():
                continue
            filtro = "WHERE producto_id IS NOT NULL" if tipo == "reactivacion" else ""
            filas = con.execute(
                f"""
                WITH base AS (
                    SELECT producto_id, any_value(producto_nombre) AS producto_nombre,
                           count(DISTINCT cliente_id) AS n_clientes
                    FROM read_parquet($r) {filtro} GROUP BY producto_id
                )
                SELECT b.producto_id, b.producto_nombre, b.n_clientes, c.categoria
                FROM base b LEFT JOIN _categorias c ON c.nombre_normalizado = {_NORMALIZAR}
                """,
                {"r": str(ruta)},
            ).fetchall()
            for producto_id, nombre, n_clientes, categoria in filas:
                if n_clientes < MIN_CLIENTES_PRODUCTO and categoria:
                    base, etiqueta = f"categoria:{categoria}", categoria
                else:
                    base, etiqueta = producto_id, nombre
                combo = Combinacion(base, tipo, etiqueta)
                combos.setdefault(combo.clave, combo)
            if tipo == "reactivacion":
                fila_general = con.execute(
                    "SELECT count(*) > 0 FROM read_parquet($r) WHERE producto_id IS NULL",
                    {"r": str(ruta)},
                ).fetchone()
                if fila_general and fila_general[0]:
                    general = Combinacion("general", "reactivacion", "general")
                    combos.setdefault(general.clave, general)
        return list(combos.values())
    finally:
        con.close()


def combinaciones_de_analisis(db: Session, analisis: Analisis) -> list[Combinacion]:
    if not analisis.ruta_resultados:
        return []
    categorias = _categorias_empresa(db, analisis.empresa_id)
    return _combinaciones(Path(analisis.ruta_resultados), categorias)


def generar_para_analisis(
    db: Session,
    analisis: Analisis,
    dataset: Dataset,
    *,
    resultados: Path | None = None,
    llm: ChatOpenAI | None = None,
    cliente_jev: TypeSafeClient | None = None,
    contador: Contador | None = None,
    forzar: bool = False,
) -> dict:
    """Genera (o regenera, con `forzar=True`) las plantillas de `analisis` y las revisa con Jev.

    `resultados`: carpeta de resultados del análisis; por defecto `analisis.ruta_resultados`
    (todavía no está si se llama desde el propio orquestador, que la pasa explícita).
    Devuelve totales para `analisis.resumen["mensajes"]`.
    """
    proyecto = db.get(Proyecto, dataset.proyecto_id)
    if proyecto is None:
        raise ValueError(f"dataset {dataset.id} sin proyecto")
    idioma, tono = proyecto.idioma_mensajes, proyecto.tono
    if resultados is None and analisis.ruta_resultados:
        resultados = Path(analisis.ruta_resultados)
    if resultados is None:
        raise ValueError(f"análisis {analisis.id} todavía sin resultados")
    categorias = _categorias_empresa(db, analisis.empresa_id)
    combos = _combinaciones(resultados, categorias)
    resultado = plantillas.generar_plantillas(
        db, analisis.empresa_id, combos, idioma, tono, llm=llm, contador=contador, forzar=forzar
    )
    revision.revisar_y_regenerar(
        db,
        analisis.empresa_id,
        combos,
        resultado,
        idioma,
        tono,
        llm=llm,
        cliente=cliente_jev,
        contador=contador,
    )
    por_estado: dict[str, int] = {}
    for fila in resultado.nuevas:
        por_estado[fila.estado] = por_estado.get(fila.estado, 0) + 1
    return {
        "combinaciones": len(combos),
        "nuevas": len(resultado.nuevas),
        "cacheadas": len(combos) - len(resultado.nuevas),
        "por_estado": por_estado,
    }


@tipo_trabajo("mensajes")
def mensajes(trabajo: TrabajoEnCurso) -> None:
    analisis_id = uuid.UUID(trabajo.parametros["analisis_id"])
    with Session(eventos._engine()) as db:
        analisis = db.get(Analisis, analisis_id)
        if analisis is None or analisis.empresa_id != trabajo.empresa_id:
            raise ValueError(f"análisis {analisis_id} no encontrado o de otra empresa")
        dataset = db.get(Dataset, analisis.dataset_id)
        if dataset is None or dataset.empresa_id != trabajo.empresa_id:
            raise ValueError(f"dataset de {analisis_id} no encontrado")
        resumen = generar_para_analisis(db, analisis, dataset, forzar=True)
        analisis.resumen = {**(analisis.resumen or {}), "mensajes": resumen}
        db.commit()
