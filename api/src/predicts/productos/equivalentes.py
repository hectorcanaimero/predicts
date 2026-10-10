"""Productos equivalentes vía embeddings en pgvector (ver specs/f4-analisis.md#F4.2.T2):

- `generar_embeddings`: embeddings del `nombre_normalizado` (`ia.embeddings`, lotes de 100) solo
  para productos sin embedding.
- `generar_propuestas`: busca vecinos por coseno (índice HNSW de `productos.embedding`, ver la
  migración inicial) dentro de la misma empresa y propone un `GrupoProducto` (`estado=
  "propuesto"`) cuando la similitud ≥ `UMBRAL_EQUIVALENTES` **y** coincide la marca o la
  categoría, si existen. Las propuestas no se aplican solas: `api/productos_grupos.py` las
  confirma, rechaza o separa.

El análisis (F4.3) usa los grupos `confirmado`; un producto sin grupo (`grupo_id is None`) es su
propio grupo.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from predicts.config import Settings, settings
from predicts.db.modelos import GrupoProducto, Producto
from predicts.ia import Contador
from predicts.ia import embeddings as _embeddings_ia

TAMANO_LOTE_EMBEDDINGS = 100

# Similitud coseno mínima (1 - distancia) para proponer que dos productos son equivalentes.
UMBRAL_EQUIVALENTES = 0.85

FuncionEmbeddings = Callable[[Sequence[str]], list[list[float]]]


def generar_embeddings(
    db: Session,
    empresa_id: uuid.UUID,
    *,
    calcular: FuncionEmbeddings | None = None,
    cfg: Settings | None = None,
    contador: Contador | None = None,
) -> list[Producto]:
    """Calcula el embedding de `nombre_normalizado` para los productos de `empresa_id` que aún
    no lo tienen, en lotes de `TAMANO_LOTE_EMBEDDINGS`. `calcular` permite inyectar una función
    determinista en los tests en vez de llamar a `ia.embeddings`."""
    productos = db.scalars(
        select(Producto).where(
            Producto.empresa_id == empresa_id, Producto.embedding.is_(None)
        )
    ).all()
    if not productos:
        return []

    if calcular is None:
        cfg = cfg or settings()

        def calcular(textos: Sequence[str]) -> list[list[float]]:
            return _embeddings_ia(
                textos, configuracion=cfg, contador=contador, tamano_lote=TAMANO_LOTE_EMBEDDINGS
            )

    vectores = calcular([p.nombre_normalizado for p in productos])
    for producto, vector in zip(productos, vectores, strict=True):
        producto.embedding = vector

    db.flush()
    return list(productos)


def _coincide(a: str | None, b: str | None) -> bool | None:
    """`True`/`False` si ambos existen; `None` si falta alguno (nada que comparar)."""
    if a is None or b is None:
        return None
    return a == b


def _condicion_marca_o_categoria(p1: Producto, p2: Producto) -> bool:
    """Coincide marca o coincide categoría, cada una solo si existe en ambos productos. Si
    ninguna de las dos existe, no hay señal que aplicar y manda solo la similitud."""
    marca1 = (p1.estadisticas or {}).get("marca")
    marca2 = (p2.estadisticas or {}).get("marca")
    coincide_marca = _coincide(marca1, marca2)
    coincide_categoria = _coincide(p1.categoria, p2.categoria)
    if coincide_marca is None and coincide_categoria is None:
        return True
    return bool(coincide_marca) or bool(coincide_categoria)


def _raiz(padre: dict[uuid.UUID, uuid.UUID], x: uuid.UUID) -> uuid.UUID:
    while padre[x] != x:
        padre[x] = padre[padre[x]]
        x = padre[x]
    return x


def _unir(padre: dict[uuid.UUID, uuid.UUID], a: uuid.UUID, b: uuid.UUID) -> None:
    ra, rb = _raiz(padre, a), _raiz(padre, b)
    if ra != rb:
        padre[rb] = ra


def generar_propuestas(
    db: Session,
    empresa_id: uuid.UUID,
    *,
    umbral: float = UMBRAL_EQUIVALENTES,
) -> list[GrupoProducto]:
    """Propone grupos de productos equivalentes dentro de `empresa_id`: para cada producto con
    embedding y sin grupo, busca vecinos por coseno (≥ `umbral`) que además coincidan en marca o
    categoría (si existen), y une todos los que se tocan en un mismo `GrupoProducto` nuevo
    (`estado="propuesto"`). No toca productos que ya están en un grupo (propuesto, confirmado o
    rechazado): hay que `separar`los primero.
    """
    productos = db.scalars(
        select(Producto).where(
            Producto.empresa_id == empresa_id,
            Producto.embedding.is_not(None),
            Producto.grupo_id.is_(None),
        )
    ).all()
    if len(productos) < 2:
        return []

    por_id = {p.id: p for p in productos}
    padre = {p.id: p.id for p in productos}
    # ponytail: similitud por par, no por grupo; si el grupo final tiene más de un par se guarda
    # la más baja (la más conservadora). Upgrade: recalcular sobre el centroide si hace falta.
    similitudes: dict[frozenset[uuid.UUID], float] = {}

    for producto in productos:
        distancia = Producto.embedding.cosine_distance(producto.embedding)
        vecinos = db.execute(
            select(Producto.id, distancia.label("distancia")).where(
                Producto.empresa_id == empresa_id,
                Producto.id != producto.id,
                Producto.embedding.is_not(None),
                Producto.grupo_id.is_(None),
                distancia <= 1 - umbral,
            )
        ).all()
        for vecino_id, dist in vecinos:
            vecino = por_id.get(vecino_id)
            if vecino is None or not _condicion_marca_o_categoria(producto, vecino):
                continue
            _unir(padre, producto.id, vecino_id)
            similitudes[frozenset((producto.id, vecino_id))] = 1 - dist

    componentes: dict[uuid.UUID, list[uuid.UUID]] = {}
    for pid in padre:
        componentes.setdefault(_raiz(padre, pid), []).append(pid)

    grupos_creados: list[GrupoProducto] = []
    for miembros in componentes.values():
        if len(miembros) < 2:
            continue
        pares = [
            sim for par, sim in similitudes.items() if par <= frozenset(miembros)
        ]
        grupo = GrupoProducto(
            empresa_id=empresa_id,
            nombre=por_id[miembros[0]].nombre,
            estado="propuesto",
            similitud=min(pares) if pares else None,
        )
        db.add(grupo)
        db.flush()
        for pid in miembros:
            por_id[pid].grupo_id = grupo.id
        grupos_creados.append(grupo)

    return grupos_creados
