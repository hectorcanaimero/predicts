"""Router `/proyectos`: `GET/POST /proyectos`, `GET/PATCH/DELETE /proyectos/{id}`.

Aislados por empresa (ver `predicts.tenancy` y `docs/notas/tenancy.md`). Borrar un proyecto
borra en cascada sus datasets y análisis vía `ON DELETE CASCADE` (modelos.py); la retención de
los archivos en disco de esos datasets la hace `retencion.py` (F8.3.T2).
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from predicts.auth.dependencias import Db, EmpresaActual
from predicts.db.modelos import Proyecto
from predicts.tenancy import de_empresa, obtener_o_404

router = APIRouter(prefix="/proyectos", tags=["proyectos"])

Idioma = Literal["pt-BR", "es", "en"]
Tono = Literal["cercano", "neutro", "formal"]


class ProyectoEntrada(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)
    idioma_mensajes: Idioma = "pt-BR"
    tono: Tono = "neutro"
    descripcion: str | None = Field(default=None, max_length=5000)


class ProyectoActualizar(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=200)
    idioma_mensajes: Idioma | None = None
    tono: Tono | None = None
    descripcion: str | None = Field(default=None, max_length=5000)


class ProyectoSalida(BaseModel):
    id: str
    nombre: str
    idioma_mensajes: Idioma
    tono: Tono
    descripcion: str | None


def _salida(proyecto: Proyecto) -> ProyectoSalida:
    return ProyectoSalida(
        id=str(proyecto.id),
        nombre=proyecto.nombre,
        idioma_mensajes=proyecto.idioma_mensajes,  # type: ignore[arg-type]
        tono=proyecto.tono,  # type: ignore[arg-type]
        descripcion=proyecto.descripcion,
    )


@router.get("", summary="Listar proyectos de la empresa actual")
def listar(empresa: EmpresaActual, db: Db) -> list[ProyectoSalida]:
    consulta = de_empresa(select(Proyecto), empresa.id).order_by(Proyecto.creado_en)
    return [_salida(p) for p in db.scalars(consulta).all()]


@router.post("", status_code=201, summary="Crear un proyecto")
def crear(datos: ProyectoEntrada, empresa: EmpresaActual, db: Db) -> ProyectoSalida:
    proyecto = Proyecto(empresa_id=empresa.id, **datos.model_dump())
    db.add(proyecto)
    db.commit()
    return _salida(proyecto)


@router.get("/{proyecto_id}", summary="Obtener un proyecto")
def obtener(proyecto_id: uuid.UUID, empresa: EmpresaActual, db: Db) -> ProyectoSalida:
    proyecto = obtener_o_404(db, Proyecto, proyecto_id, empresa.id)
    return _salida(proyecto)


@router.patch("/{proyecto_id}", summary="Editar un proyecto")
def actualizar(
    proyecto_id: uuid.UUID, datos: ProyectoActualizar, empresa: EmpresaActual, db: Db
) -> ProyectoSalida:
    proyecto = obtener_o_404(db, Proyecto, proyecto_id, empresa.id)
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(proyecto, campo, valor)
    db.commit()
    return _salida(proyecto)


@router.delete("/{proyecto_id}", status_code=204, summary="Borrar un proyecto")
def borrar(proyecto_id: uuid.UUID, empresa: EmpresaActual, db: Db) -> None:
    proyecto = obtener_o_404(db, Proyecto, proyecto_id, empresa.id)
    db.delete(proyecto)
    db.commit()
