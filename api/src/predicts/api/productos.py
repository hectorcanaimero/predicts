"""Rutas de productos: listar los que necesitan revisión y corregir recompra/durable o
categoría (ver `predicts.productos.clasificacion` y specs/f4-analisis.md#F4.2.T1).

Aisladas por empresa (`predicts.tenancy`). Las correcciones de la persona se registran en
`decisiones_jev.corregida_a` cuando hay una decisión de Jev para ese producto.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from predicts.auth.dependencias import Db, EmpresaActual, UsuarioActual
from predicts.db.modelos import Dataset, DecisionJev, Producto
from predicts.errores import ErrorApi
from predicts.tenancy import obtener_o_404

router = APIRouter(tags=["productos"])


class ProductoSalida(BaseModel):
    id: str
    nombre: str
    categoria: str | None
    categoria_origen: str | None
    tipo: str
    tipo_origen: str | None
    confianza: float | None
    estado_revision: str
    estadisticas: dict | None


def _salida(producto: Producto) -> ProductoSalida:
    return ProductoSalida(
        id=str(producto.id),
        nombre=producto.nombre,
        categoria=producto.categoria,
        categoria_origen=producto.categoria_origen,
        tipo=producto.tipo,
        tipo_origen=producto.tipo_origen,
        confianza=producto.confianza,
        estado_revision=producto.estado_revision,
        estadisticas=producto.estadisticas,
    )


@router.get("/datasets/{dataset_id}/productos", summary="Listar los productos de la empresa")
def listar_productos(
    dataset_id: uuid.UUID, empresa: EmpresaActual, db: Db, estado: str | None = None
) -> list[ProductoSalida]:
    """El catálogo de productos es por empresa (no por dataset); `dataset_id` solo sirve para
    aislar la ruta y confirmar que el dataset existe y es de la empresa."""
    obtener_o_404(db, Dataset, dataset_id, empresa.id)
    consulta = select(Producto).where(Producto.empresa_id == empresa.id)
    if estado is not None:
        consulta = consulta.where(Producto.estado_revision == estado)
    productos = db.scalars(consulta.order_by(Producto.nombre)).all()
    return [_salida(p) for p in productos]


class CorregirProductoEntrada(BaseModel):
    tipo: str | None = None
    categoria: str | None = None


def _corregir_decision(
    db: Session, empresa_id: uuid.UUID, usuario_id: uuid.UUID, tipo_decision: str,
    referencia: uuid.UUID, opcion_nueva: str,
) -> None:
    decision = db.scalar(
        select(DecisionJev)
        .where(
            DecisionJev.empresa_id == empresa_id,
            DecisionJev.tipo == tipo_decision,
            DecisionJev.referencia == referencia,
        )
        .order_by(DecisionJev.creado_en.desc())
    )
    if decision is not None and decision.opcion != opcion_nueva and decision.corregida_a is None:
        decision.corregida_a = opcion_nueva
        decision.corregida_por = usuario_id
        decision.corregida_en = datetime.now(UTC)


@router.patch(
    "/productos/{producto_id}", summary="Corregir el tipo o la categoría de un producto"
)
def corregir_producto(
    producto_id: uuid.UUID,
    entrada: CorregirProductoEntrada,
    usuario: UsuarioActual,
    empresa: EmpresaActual,
    db: Db,
) -> ProductoSalida:
    producto = obtener_o_404(db, Producto, producto_id, empresa.id)
    if entrada.tipo is None and entrada.categoria is None:
        raise ErrorApi("nada_que_corregir", 422)

    if entrada.tipo is not None:
        if entrada.tipo not in ("recompra", "durable"):
            raise ErrorApi("tipo_invalido", 422, tipo=entrada.tipo)
        _corregir_decision(db, empresa.id, usuario.id, "tipo_producto", producto.id, entrada.tipo)
        producto.tipo = entrada.tipo
        producto.tipo_origen = "persona"
        producto.confianza = None

    if entrada.categoria is not None:
        _corregir_decision(db, empresa.id, usuario.id, "categoria", producto.id, entrada.categoria)
        producto.categoria = entrada.categoria
        producto.categoria_origen = "persona"

    producto.estado_revision = "ok"
    db.commit()
    return _salida(producto)
