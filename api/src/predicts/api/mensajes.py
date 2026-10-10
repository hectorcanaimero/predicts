"""Rutas de plantillas de mensaje: listar las de un análisis, editarlas a mano y pedir que se
regeneren (ver `predicts.mensajes` y `predicts.trabajos.tipos_mensajes`).

Aisladas por empresa (`predicts.tenancy`). Editar una plantilla la marca `editada`: no se vuelve
a generar ni a revisar, ni acá ni en un análisis futuro.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from predicts.auth.dependencias import Db, EmpresaActual
from predicts.db.modelos import Analisis, Dataset, PlantillaMensaje, Proyecto
from predicts.errores import ErrorApi
from predicts.mensajes import plantillas
from predicts.mensajes.plantillas import Texto
from predicts.tenancy import obtener_o_404
from predicts.trabajos import cola
from predicts.trabajos.tipos_mensajes import combinaciones_de_analisis

router = APIRouter(tags=["mensajes"])


class PlantillaSalida(BaseModel):
    id: str
    clave: str
    tipo: str
    idioma: str
    tono: str
    texto: str
    estado: str
    motivo_revision: str | None


def _salida(fila: PlantillaMensaje) -> PlantillaSalida:
    return PlantillaSalida(
        id=str(fila.id),
        clave=fila.clave,
        tipo=fila.tipo,
        idioma=fila.idioma,
        tono=fila.tono,
        texto=fila.texto,
        estado=fila.estado,
        motivo_revision=fila.motivo_revision,
    )


def _dataset_y_proyecto(db: Session, analisis: Analisis) -> tuple[Dataset, Proyecto]:
    dataset = db.get(Dataset, analisis.dataset_id)
    if dataset is None:
        raise ErrorApi("no_encontrado", 404)
    proyecto = db.get(Proyecto, dataset.proyecto_id)
    if proyecto is None:
        raise ErrorApi("no_encontrado", 404)
    return dataset, proyecto


@router.get("/analisis/{analisis_id}/plantillas", summary="Plantillas de mensaje de un análisis")
def listar_plantillas(
    analisis_id: uuid.UUID, empresa: EmpresaActual, db: Db
) -> list[PlantillaSalida]:
    analisis = obtener_o_404(db, Analisis, analisis_id, empresa.id)
    _dataset, proyecto = _dataset_y_proyecto(db, analisis)
    combos = combinaciones_de_analisis(db, analisis)
    cacheadas = plantillas.obtener_cacheadas(
        db, empresa.id, proyecto.idioma_mensajes, proyecto.tono, [c.clave for c in combos]
    )
    return [_salida(cacheadas[c.clave]) for c in combos if c.clave in cacheadas]


class EditarPlantilla(BaseModel):
    texto: str


@router.patch("/plantillas-mensaje/{plantilla_id}", summary="Editar una plantilla a mano")
def editar_plantilla(
    plantilla_id: uuid.UUID, cuerpo: EditarPlantilla, empresa: EmpresaActual, db: Db
) -> PlantillaSalida:
    fila = obtener_o_404(db, PlantillaMensaje, plantilla_id, empresa.id)
    try:
        validado = Texto(texto=cuerpo.texto)
    except ValidationError as error:
        raise ErrorApi("plantilla_invalida", 422, detalle=str(error)) from error
    fila.texto = validado.texto
    fila.estado = "editada"
    fila.motivo_revision = None
    db.commit()
    return _salida(fila)


@router.post(
    "/analisis/{analisis_id}/plantillas/regenerar",
    status_code=202,
    summary="Regenerar las plantillas de un análisis",
)
def regenerar_plantillas(analisis_id: uuid.UUID, empresa: EmpresaActual, db: Db) -> dict:
    obtener_o_404(db, Analisis, analisis_id, empresa.id)
    trabajo = cola.encolar(db, empresa.id, "mensajes", {"analisis_id": str(analisis_id)})
    return {"trabajo_id": str(trabajo.id)}
