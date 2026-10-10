"""Cola de trabajos en la tabla `trabajos`.

Estados: `en_cola → corriendo → listo | error | cancelado` (`cancelado` también desde `en_cola`).

Mientras un worker ejecuta un trabajo tiene tomado un advisory lock de sesión con la clave del
trabajo (`clave_lock`). Así `recuperar_interrumpidos` distingue un `corriendo` huérfano (su worker
se cayó y Postgres soltó el lock al cerrar la conexión) de uno que otro worker vivo está
ejecutando. Por eso `tomar_siguiente` necesita una sesión ligada a una conexión fija.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from predicts.db.modelos import Trabajo


def clave_lock(trabajo_id: uuid.UUID) -> int:
    """Clave bigint (con signo) del advisory lock de un trabajo."""
    return int.from_bytes(trabajo_id.bytes[-8:], "big", signed=True)


def encolar(db: Session, empresa_id: uuid.UUID, tipo: str, parametros: dict | None) -> Trabajo:
    trabajo = Trabajo(empresa_id=empresa_id, tipo=tipo, parametros=parametros or {})
    db.add(trabajo)
    db.commit()
    db.refresh(trabajo)
    return trabajo


def tomar_siguiente(db: Session) -> Trabajo | None:
    """Pasa el trabajo `en_cola` más antiguo a `corriendo` y toma su advisory lock.

    `FOR UPDATE SKIP LOCKED` hace que dos workers nunca tomen el mismo trabajo.
    """
    trabajo = db.scalar(
        select(Trabajo)
        .where(Trabajo.estado == "en_cola")
        .order_by(Trabajo.creado_en, Trabajo.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if trabajo is None:
        db.rollback()
        return None
    db.execute(text("SELECT pg_advisory_lock(:k)"), {"k": clave_lock(trabajo.id)})
    trabajo.estado = "corriendo"
    trabajo.iniciado_en = func.now()
    trabajo.intentos = Trabajo.intentos + 1
    db.commit()
    db.refresh(trabajo)
    return trabajo


def soltar(db: Session, trabajo_id: uuid.UUID) -> None:
    db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": clave_lock(trabajo_id)})
    db.commit()


def terminar(
    db: Session,
    trabajo_id: uuid.UUID,
    estado: str,
    *,
    codigo: str | None = None,
    detalle: str | None = None,
    duracion_s: float | None = None,
    memoria_pico_mb: int | None = None,
) -> bool:
    """Cierra un trabajo `corriendo`; no pisa uno que se canceló mientras tanto."""
    resultado = db.execute(
        update(Trabajo)
        .where(Trabajo.id == trabajo_id, Trabajo.estado == "corriendo")
        .values(
            estado=estado,
            error_codigo=codigo,
            error_detalle=detalle,
            terminado_en=func.now(),
            duracion_s=duracion_s,
            memoria_pico_mb=memoria_pico_mb,
        )
    )
    db.commit()
    return resultado.rowcount == 1


def cancelar(db: Session, trabajo_id: uuid.UUID) -> bool:
    """Cancela un trabajo `en_cola` o `corriendo` (el worker mata su subproceso)."""
    resultado = db.execute(
        update(Trabajo)
        .where(Trabajo.id == trabajo_id, Trabajo.estado.in_(("en_cola", "corriendo")))
        .values(estado="cancelado", terminado_en=func.now())
    )
    db.commit()
    return resultado.rowcount == 1


def recuperar_interrumpidos(db: Session) -> int:
    """Pasa a `error` (`interrumpido`) los `corriendo` cuyo worker ya no existe."""
    candidatos = db.scalars(select(Trabajo.id).where(Trabajo.estado == "corriendo")).all()
    db.commit()
    recuperados = 0
    for trabajo_id in candidatos:
        k = clave_lock(trabajo_id)
        if not db.scalar(text("SELECT pg_try_advisory_lock(:k)"), {"k": k}):
            continue  # lo está ejecutando un worker vivo
        recuperados += terminar(db, trabajo_id, "error", codigo="interrumpido")
        soltar(db, trabajo_id)
    return recuperados
