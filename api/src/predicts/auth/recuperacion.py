"""Recuperación de contraseña: token de un solo uso (32 bytes, solo su SHA-256 en la base),
válido 1 hora. Pedir uno nuevo invalida los anteriores; al restablecer se cierran todas las
sesiones del usuario."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from predicts.auth.sesiones import hash_token
from predicts.db.modelos import Sesion, TokenRecuperacion, Usuario

DURACION = timedelta(hours=1)


def crear_token(db: Session, usuario: Usuario) -> str:
    """Invalida los tokens anteriores del usuario y crea uno nuevo (sin commit)."""
    db.execute(delete(TokenRecuperacion).where(TokenRecuperacion.usuario_id == usuario.id))
    token = secrets.token_urlsafe(32)
    db.add(
        TokenRecuperacion(
            empresa_id=usuario.empresa_id,
            usuario_id=usuario.id,
            token_hash=hash_token(token),
            expira_en=datetime.now(UTC) + DURACION,
        )
    )
    return token


def token_vigente(db: Session, token: str) -> TokenRecuperacion | None:
    """La fila del token si existe, no venció y no fue usado; `None` si no sirve (inválido,
    vencido o reusado)."""
    fila = db.scalar(
        select(TokenRecuperacion).where(TokenRecuperacion.token_hash == hash_token(token))
    )
    if fila is None or fila.usado_en is not None or fila.expira_en <= datetime.now(UTC):
        return None
    return fila


def restablecer(db: Session, fila: TokenRecuperacion, hash_contrasena: str) -> None:
    """Marca el token usado, guarda la nueva contraseña y cierra todas las sesiones del usuario
    del token (sin commit)."""
    fila.usado_en = datetime.now(UTC)
    usuario = db.get(Usuario, fila.usuario_id)
    assert usuario is not None  # FK a usuarios, no se borra sin borrar el token (ondelete CASCADE)
    usuario.hash_contrasena = hash_contrasena
    db.execute(delete(Sesion).where(Sesion.usuario_id == usuario.id))
