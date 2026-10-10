"""Tipo de trabajo `productos`: catálogo y clasificación, encolado al terminar la `calidad`
(ver specs/f4-analisis.md#F4.2.T1 y `tipos_datos.py` para el patrón de conexión en el
subproceso: la única disponible acá es la de `eventos._engine()`).
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from predicts.db.modelos import Dataset, Producto
from predicts.productos.catalogo import actualizar_catalogo
from predicts.productos.clasificacion import clasificar_productos
from predicts.productos.equivalentes import generar_embeddings, generar_propuestas
from predicts.trabajos import eventos
from predicts.trabajos.registro import TrabajoEnCurso, tipo_trabajo


def _dataset_id(trabajo: TrabajoEnCurso) -> uuid.UUID:
    return uuid.UUID(trabajo.parametros["dataset_id"])


def _dataset(db: Session, trabajo: TrabajoEnCurso) -> Dataset:
    dataset = db.get(Dataset, _dataset_id(trabajo))
    if dataset is None or dataset.empresa_id != trabajo.empresa_id:
        raise ValueError(f"dataset {_dataset_id(trabajo)} no encontrado o de otra empresa")
    return dataset


@tipo_trabajo("productos")
def productos(trabajo: TrabajoEnCurso) -> None:
    """Actualiza el catálogo de productos del dataset y los clasifica (tipo y categoría)."""
    engine = eventos._engine()
    with Session(engine) as db:
        dataset = _dataset(db, trabajo)
        tocados = actualizar_catalogo(db, dataset)
        db.commit()
        ids = [p.id for p in tocados]

    eventos.emitir(trabajo.id, "catalogo", {"productos": len(ids)})

    with Session(engine) as db:
        productos_tocados = [db.get(Producto, i) for i in ids]
        clasificar_productos(db, trabajo.empresa_id, productos_tocados)
        db.commit()

    eventos.emitir(trabajo.id, "clasificacion", {"productos": len(ids)})

    with Session(engine) as db:
        embebidos = generar_embeddings(db, trabajo.empresa_id)
        db.commit()
        grupos = generar_propuestas(db, trabajo.empresa_id)
        db.commit()

    eventos.emitir(
        trabajo.id, "equivalentes", {"embeddings": len(embebidos), "grupos_propuestos": len(grupos)}
    )
