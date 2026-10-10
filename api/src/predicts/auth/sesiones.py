"""Sesiones en la tabla `sesiones`: token aleatorio de 32 bytes en la cookie `predicts_sesion`,
solo su SHA-256 en la base, expiración deslizante de 30 días."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from predicts.auth.csrf import COOKIE_CSRF, token_csrf
from predicts.config import settings
from predicts.db.modelos import Sesion, Usuario

COOKIE_SESION = "predicts_sesion"
DURACION = timedelta(days=30)
# Renovar la expiración como mucho una vez por día: evita un UPDATE en cada request.
_RENOVAR_CADA = timedelta(days=1)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def crear_sesion(db: Session, usuario: Usuario, ip: str | None, user_agent: str | None) -> str:
    """Crea la fila de sesión (sin commit) y devuelve el token en claro, solo para la cookie."""
    token = secrets.token_urlsafe(32)
    db.add(
        Sesion(
            empresa_id=usuario.empresa_id,
            usuario_id=usuario.id,
            token_hash=hash_token(token),
            expira_en=datetime.now(UTC) + DURACION,
            ip=ip,
            user_agent=user_agent,
        )
    )
    return token


def sesion_vigente(db: Session, token: str) -> tuple[Sesion | None, bool]:
    """Busca la sesión del token. Devuelve `(sesion, renovada)`; borra la fila si expiró."""
    sesion = db.scalar(select(Sesion).where(Sesion.token_hash == hash_token(token)))
    if sesion is None:
        return None, False
    ahora = datetime.now(UTC)
    if sesion.expira_en <= ahora:
        db.delete(sesion)
        db.commit()
        return None, False
    if sesion.expira_en - ahora < DURACION - _RENOVAR_CADA:
        sesion.expira_en = ahora + DURACION
        db.commit()
        return sesion, True
    return sesion, False


def cerrar_sesion(db: Session, token: str) -> None:
    db.execute(delete(Sesion).where(Sesion.token_hash == hash_token(token)))
    db.commit()


def poner_cookies(response: Response, token: str) -> None:
    seguro = settings().ENTORNO != "dev"
    edad = int(DURACION.total_seconds())
    response.set_cookie(
        COOKIE_SESION, token, max_age=edad, httponly=True, secure=seguro, samesite="lax"
    )
    response.set_cookie(
        COOKIE_CSRF,
        token_csrf(token),
        max_age=edad,
        httponly=False,
        secure=seguro,
        samesite="lax",
    )


def borrar_cookies(response: Response) -> None:
    seguro = settings().ENTORNO != "dev"
    for nombre, solo_http in ((COOKIE_SESION, True), (COOKIE_CSRF, False)):
        response.delete_cookie(nombre, httponly=solo_http, secure=seguro, samesite="lax")
