"""Rutas de mapeo de columnas: sugerencias (con Jev o plantilla), confirmación y plantillas
por empresa (ver `predicts.datos.mapeo` y docs/arch/001-predicts.md#datos-de-entrada).

Aisladas por empresa (ver `predicts.tenancy`). Al confirmar un mapeo, las correcciones de la
persona respecto de lo que sugirió Jev se guardan en `decisiones_jev.corregida_a`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from predicts.auth.dependencias import Db, EmpresaActual, UsuarioActual
from predicts.datos.deteccion import Deteccion
from predicts.datos.mapeo import (
    MapeoColumna,
    MapeoConfirmado,
    Sugerencias,
    firma_encabezados,
    sugerir,
    validar,
)
from predicts.db.modelos import Dataset, DecisionJev, PlantillaMapeo
from predicts.errores import ErrorApi
from predicts.tenancy import obtener_o_404

router = APIRouter(tags=["mapeo"])


class MapeoColumnaEntrada(BaseModel):
    columna: str
    campo: str


class MapeoEntrada(BaseModel):
    columnas: list[MapeoColumnaEntrada]
    producto_id_tipo: str
    formato_fecha: str
    guardar_como_plantilla: bool = False
    nombre_plantilla: str | None = None


class ConfirmarMapeoSalida(BaseModel):
    id: str
    estado: str
    mapeo: dict


class PlantillaMapeoSalida(BaseModel):
    id: str
    nombre: str
    firma_encabezados: str
    mapeo: dict


def _plantilla_salida(plantilla: PlantillaMapeo) -> PlantillaMapeoSalida:
    return PlantillaMapeoSalida(
        id=str(plantilla.id),
        nombre=plantilla.nombre,
        firma_encabezados=plantilla.firma_encabezados,
        mapeo=plantilla.mapeo,
    )


def _deteccion_del_dataset(dataset: Dataset) -> Deteccion:
    if not dataset.deteccion:
        raise ErrorApi("dataset_sin_deteccion", 422)
    return Deteccion.model_validate(dataset.deteccion)


@router.get("/datasets/{dataset_id}/mapeo", summary="Sugerir el mapeo de columnas de un dataset")
def obtener_mapeo(dataset_id: uuid.UUID, empresa: EmpresaActual, db: Db) -> Sugerencias:
    dataset = obtener_o_404(db, Dataset, dataset_id, empresa.id)
    deteccion = _deteccion_del_dataset(dataset)

    sugerencias = sugerir(deteccion, db, empresa.id, dataset.id)
    dataset.firma_encabezados = sugerencias.firma_encabezados
    db.commit()
    return sugerencias


def _registrar_correcciones(
    db: Session, empresa_id: uuid.UUID, usuario_id: uuid.UUID, dataset_id: uuid.UUID,
    mapeo: MapeoConfirmado,
) -> None:
    decisiones = db.scalars(
        select(DecisionJev).where(
            DecisionJev.empresa_id == empresa_id,
            DecisionJev.tipo == "mapeo_columna",
            DecisionJev.referencia == dataset_id,
        )
    ).all()
    por_columna = {
        d.entrada_resumida.get("columna"): d
        for d in decisiones
        if d.entrada_resumida and "sub_pregunta" not in d.entrada_resumida
    }
    decision_tipo = next(
        (
            d
            for d in decisiones
            if d.entrada_resumida and d.entrada_resumida.get("sub_pregunta") == "producto_id_tipo"
        ),
        None,
    )
    ahora = datetime.now(UTC)

    for col in mapeo.columnas:
        decision = por_columna.get(col.columna)
        if decision is not None and decision.opcion != col.campo and decision.corregida_a is None:
            decision.corregida_a = col.campo
            decision.corregida_por = usuario_id
            decision.corregida_en = ahora

    if (
        decision_tipo is not None
        and decision_tipo.opcion != mapeo.producto_id_tipo
        and decision_tipo.corregida_a is None
    ):
        decision_tipo.corregida_a = mapeo.producto_id_tipo
        decision_tipo.corregida_por = usuario_id
        decision_tipo.corregida_en = ahora


def _guardar_plantilla(
    db: Session, empresa_id: uuid.UUID, dataset: Dataset, mapeo: MapeoConfirmado, nombre: str | None
) -> None:
    existente = db.scalar(
        select(PlantillaMapeo).where(
            PlantillaMapeo.empresa_id == empresa_id,
            PlantillaMapeo.firma_encabezados == dataset.firma_encabezados,
        )
    )
    if existente is not None:
        existente.mapeo = mapeo.model_dump()
        if nombre:
            existente.nombre = nombre
    else:
        db.add(
            PlantillaMapeo(
                empresa_id=empresa_id,
                firma_encabezados=dataset.firma_encabezados,
                nombre=nombre or dataset.nombre_archivo,
                mapeo=mapeo.model_dump(),
            )
        )


@router.put("/datasets/{dataset_id}/mapeo", summary="Confirmar el mapeo de columnas de un dataset")
def confirmar_mapeo(
    dataset_id: uuid.UUID,
    entrada: MapeoEntrada,
    usuario: UsuarioActual,
    empresa: EmpresaActual,
    db: Db,
) -> ConfirmarMapeoSalida:
    dataset = obtener_o_404(db, Dataset, dataset_id, empresa.id)
    deteccion = _deteccion_del_dataset(dataset)

    mapeo = MapeoConfirmado(
        columnas=[MapeoColumna(columna=c.columna, campo=c.campo) for c in entrada.columnas],
        producto_id_tipo=entrada.producto_id_tipo,
        formato_fecha=entrada.formato_fecha,
    )
    errores = validar(mapeo, deteccion)
    if errores:
        raise ErrorApi("mapeo_invalido", 422, errores=[e.model_dump() for e in errores])

    _registrar_correcciones(db, empresa.id, usuario.id, dataset.id, mapeo)

    if not dataset.firma_encabezados:
        dataset.firma_encabezados = firma_encabezados([c.nombre for c in deteccion.columnas])
    dataset.mapeo = mapeo.model_dump()
    dataset.estado = "mapeado"

    if entrada.guardar_como_plantilla:
        _guardar_plantilla(db, empresa.id, dataset, mapeo, entrada.nombre_plantilla)

    db.commit()
    return ConfirmarMapeoSalida(id=str(dataset.id), estado=dataset.estado, mapeo=dataset.mapeo)


@router.get("/plantillas-mapeo", summary="Listar las plantillas de mapeo de la empresa")
def listar_plantillas(empresa: EmpresaActual, db: Db) -> list[PlantillaMapeoSalida]:
    plantillas = db.scalars(
        select(PlantillaMapeo)
        .where(PlantillaMapeo.empresa_id == empresa.id)
        .order_by(PlantillaMapeo.creado_en)
    ).all()
    return [_plantilla_salida(p) for p in plantillas]


@router.delete(
    "/plantillas-mapeo/{plantilla_id}", status_code=204, summary="Borrar una plantilla de mapeo"
)
def borrar_plantilla(plantilla_id: uuid.UUID, empresa: EmpresaActual, db: Db) -> None:
    plantilla = obtener_o_404(db, PlantillaMapeo, plantilla_id, empresa.id)
    db.delete(plantilla)
    db.commit()
