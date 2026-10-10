"""Eventos de progreso en `eventos_trabajo`.

Formato: docs/arch/001-predicts.md#eventos-de-trabajo-sse.

`emitir` se llama desde el subproceso del trabajo, con su propia conexión (`configurar` la fija el
worker al arrancar el hijo; si no, se usa `DATABASE_URL`). Emite como máximo un evento por
segundo por trabajo: los que llegan antes se descartan, pero el último descartado se guarda al
terminar (`vaciar`) para que los contadores finales no se pierdan. `listo` y `error` nunca se
descartan.
"""

from __future__ import annotations

import time
import uuid
from functools import lru_cache

from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from predicts.db.modelos import EventoTrabajo, Trabajo

INTERVALO_MIN_S = 1.0
_ETAPAS_FINALES = ("listo", "error")

_url: str | None = None
_ultimo: dict[uuid.UUID, float] = {}
_pendiente: dict[uuid.UUID, tuple[str, dict, float | None]] = {}


def configurar(url_db: str) -> None:
    global _url
    _url = url_db
    _engine.cache_clear()


@lru_cache
def _engine() -> Engine:
    if _url is None:
        from predicts.db.sesion import get_engine

        return get_engine()
    return create_engine(_url, pool_size=1, pool_pre_ping=True)


def registrar(
    db: Session,
    trabajo_id: uuid.UUID,
    etapa: str,
    contadores: dict | None,
    progreso: float | None,
) -> EventoTrabajo:
    """Inserta un evento sin limitar frecuencia (un solo escritor por trabajo a la vez)."""
    empresa_id = db.scalar(select(Trabajo.empresa_id).where(Trabajo.id == trabajo_id))
    secuencia = db.scalar(
        select(func.coalesce(func.max(EventoTrabajo.secuencia), 0) + 1).where(
            EventoTrabajo.trabajo_id == trabajo_id
        )
    )
    evento = EventoTrabajo(
        empresa_id=empresa_id,
        trabajo_id=trabajo_id,
        secuencia=secuencia,
        etapa=etapa,
        contadores=contadores or {},
        progreso=progreso,
    )
    db.add(evento)
    db.commit()
    return evento


def emitir(
    trabajo_id: uuid.UUID,
    etapa: str,
    contadores: dict | None = None,
    progreso: float | None = None,
) -> bool:
    """Guarda un evento de progreso; devuelve `False` si se descartó por frecuencia."""
    ahora = time.monotonic()
    ultimo = _ultimo.get(trabajo_id)
    if etapa not in _ETAPAS_FINALES and ultimo is not None and ahora - ultimo < INTERVALO_MIN_S:
        _pendiente[trabajo_id] = (etapa, contadores or {}, progreso)
        return False
    _pendiente.pop(trabajo_id, None)
    _ultimo[trabajo_id] = ahora
    with Session(_engine()) as db:
        registrar(db, trabajo_id, etapa, contadores, progreso)
    return True


def vaciar(trabajo_id: uuid.UUID) -> None:
    """Guarda el último evento descartado de `trabajo_id`, si hay."""
    pendiente = _pendiente.pop(trabajo_id, None)
    if pendiente is not None:
        with Session(_engine()) as db:
            registrar(db, trabajo_id, *pendiente)
