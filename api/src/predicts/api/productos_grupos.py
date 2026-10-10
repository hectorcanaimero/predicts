"""Rutas de grupos de productos equivalentes: listar propuestas, confirmar, rechazar y separar
un producto de su grupo (ver `predicts.productos.equivalentes` y specs/f4-analisis.md#F4.2.T2).

Aisladas por empresa (`predicts.tenancy`). El análisis (F4.3) solo usa los grupos
`estado="confirmado"`; un producto sin grupo es su propio grupo.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from predicts.auth.dependencias import Db, EmpresaActual
from predicts.db.modelos import GrupoProducto, Producto
from predicts.errores import ErrorApi
from predicts.tenancy import obtener_o_404

router = APIRouter(tags=["productos-grupos"])


class ProductoDeGrupoSalida(BaseModel):
    id: str
    nombre: str
    categoria: str | None


class GrupoSalida(BaseModel):
    id: str
    nombre: str
    estado: str
    similitud: float | None
    productos: list[ProductoDeGrupoSalida]


def _salida(grupo: GrupoProducto, productos: Sequence[Producto]) -> GrupoSalida:
    return GrupoSalida(
        id=str(grupo.id),
        nombre=grupo.nombre,
        estado=grupo.estado,
        similitud=grupo.similitud,
        productos=[
            ProductoDeGrupoSalida(id=str(p.id), nombre=p.nombre, categoria=p.categoria)
            for p in productos
        ],
    )


@router.get("/productos/grupos", summary="Listar grupos de productos equivalentes")
def listar_grupos(empresa: EmpresaActual, db: Db, estado: str = "propuesto") -> list[GrupoSalida]:
    grupos = db.scalars(
        select(GrupoProducto)
        .where(GrupoProducto.empresa_id == empresa.id, GrupoProducto.estado == estado)
        .order_by(GrupoProducto.creado_en)
    ).all()
    productos_por_grupo = {
        grupo.id: db.scalars(
            select(Producto)
            .where(Producto.empresa_id == empresa.id, Producto.grupo_id == grupo.id)
            .order_by(Producto.nombre)
        ).all()
        for grupo in grupos
    }
    return [_salida(grupo, productos_por_grupo[grupo.id]) for grupo in grupos]


@router.post("/productos/grupos/{grupo_id}/confirmar", summary="Confirmar un grupo propuesto")
def confirmar_grupo(grupo_id: uuid.UUID, empresa: EmpresaActual, db: Db) -> GrupoSalida:
    grupo = obtener_o_404(db, GrupoProducto, grupo_id, empresa.id)
    grupo.estado = "confirmado"
    db.commit()
    productos = db.scalars(
        select(Producto).where(Producto.empresa_id == empresa.id, Producto.grupo_id == grupo.id)
    ).all()
    return _salida(grupo, productos)


@router.post("/productos/grupos/{grupo_id}/rechazar", summary="Rechazar un grupo propuesto")
def rechazar_grupo(grupo_id: uuid.UUID, empresa: EmpresaActual, db: Db) -> GrupoSalida:
    grupo = obtener_o_404(db, GrupoProducto, grupo_id, empresa.id)
    grupo.estado = "rechazado"
    productos = db.scalars(
        select(Producto).where(Producto.empresa_id == empresa.id, Producto.grupo_id == grupo.id)
    ).all()
    for producto in productos:
        producto.grupo_id = None
    db.commit()
    return _salida(grupo, [])


@router.post("/productos/{producto_id}/separar", summary="Separar un producto de su grupo")
def separar_producto(
    producto_id: uuid.UUID, empresa: EmpresaActual, db: Db
) -> ProductoDeGrupoSalida:
    producto = obtener_o_404(db, Producto, producto_id, empresa.id)
    if producto.grupo_id is None:
        raise ErrorApi("producto_sin_grupo", 422)
    producto.grupo_id = None
    db.commit()
    return ProductoDeGrupoSalida(
        id=str(producto.id), nombre=producto.nombre, categoria=producto.categoria
    )
