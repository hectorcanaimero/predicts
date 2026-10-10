"""Rutas de trabajos: estado, eventos de progreso por SSE y cancelación.

Aisladas por empresa (`predicts.tenancy`). `GET /trabajos/{id}/eventos` envía los eventos ya
guardados y después los nuevos (sondeando la tabla `eventos_trabajo`) hasta que el trabajo
emite `listo`/`error`, o hasta que deja de estar `en_cola`/`corriendo` sin haberlo emitido
(p. ej. `cancelado`, que no deja un evento final — ver `trabajos.worker`). Soporta
reconexión con el header `Last-Event-ID`.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterator
from datetime import datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from predicts.auth.dependencias import Db, EmpresaActual
from predicts.db.modelos import EventoTrabajo, Trabajo
from predicts.errores import ErrorApi
from predicts.tenancy import obtener_o_404
from predicts.trabajos import cola

router = APIRouter(tags=["trabajos"])

_ESTADOS_ACTIVOS = ("en_cola", "corriendo")
_ETAPAS_FINALES = ("listo", "error")
_INTERVALO_SONDEO_S = 0.2


class TrabajoSalida(BaseModel):
    id: str
    tipo: str
    estado: str
    error_codigo: str | None
    error_detalle: str | None
    duracion_s: float | None
    memoria_pico_mb: int | None
    creado_en: datetime
    iniciado_en: datetime | None
    terminado_en: datetime | None


def _salida(trabajo: Trabajo) -> TrabajoSalida:
    return TrabajoSalida(
        id=str(trabajo.id),
        tipo=trabajo.tipo,
        estado=trabajo.estado,
        error_codigo=trabajo.error_codigo,
        error_detalle=trabajo.error_detalle,
        duracion_s=trabajo.duracion_s,
        memoria_pico_mb=trabajo.memoria_pico_mb,
        creado_en=trabajo.creado_en,
        iniciado_en=trabajo.iniciado_en,
        terminado_en=trabajo.terminado_en,
    )


@router.get("/trabajos/{trabajo_id}", summary="Estado de un trabajo")
def obtener_trabajo(trabajo_id: uuid.UUID, empresa: EmpresaActual, db: Db) -> TrabajoSalida:
    trabajo = obtener_o_404(db, Trabajo, trabajo_id, empresa.id)
    return _salida(trabajo)


def _eventos_desde(db: Session, trabajo_id: uuid.UUID, secuencia: int) -> list[EventoTrabajo]:
    return list(
        db.scalars(
            select(EventoTrabajo)
            .where(EventoTrabajo.trabajo_id == trabajo_id, EventoTrabajo.secuencia >= secuencia)
            .order_by(EventoTrabajo.secuencia)
        )
    )


def _generar_eventos(
    engine: Engine | Connection, trabajo_id: uuid.UUID, desde: int
) -> Iterator[dict]:
    secuencia = desde
    visto_terminal = False
    while True:
        with Session(engine) as db:
            pendientes = _eventos_desde(db, trabajo_id, secuencia)
            estado = db.scalar(select(Trabajo.estado).where(Trabajo.id == trabajo_id))

        for evento in pendientes:
            secuencia = evento.secuencia + 1
            yield {
                "id": str(evento.secuencia),
                "event": evento.etapa,
                "data": json.dumps({"contadores": evento.contadores, "progreso": evento.progreso}),
            }
            if evento.etapa in _ETAPAS_FINALES:
                return

        if estado not in _ESTADOS_ACTIVOS:
            if visto_terminal:
                return
            visto_terminal = True  # una vuelta de gracia por si el evento final aún no se escribió

        time.sleep(_INTERVALO_SONDEO_S)


@router.get("/trabajos/{trabajo_id}/eventos", summary="Eventos de progreso de un trabajo (SSE)")
def eventos_trabajo(
    trabajo_id: uuid.UUID, request: Request, empresa: EmpresaActual, db: Db
) -> EventSourceResponse:
    obtener_o_404(db, Trabajo, trabajo_id, empresa.id)
    ultimo_id = request.headers.get("last-event-id")
    desde = int(ultimo_id) + 1 if ultimo_id is not None else 1
    return EventSourceResponse(_generar_eventos(db.get_bind(), trabajo_id, desde))


@router.post(
    "/trabajos/{trabajo_id}/cancelar", status_code=204, summary="Cancelar un trabajo"
)
def cancelar_trabajo(trabajo_id: uuid.UUID, empresa: EmpresaActual, db: Db) -> None:
    obtener_o_404(db, Trabajo, trabajo_id, empresa.id)
    if not cola.cancelar(db, trabajo_id):
        raise ErrorApi("trabajo_no_cancelable", 409)
