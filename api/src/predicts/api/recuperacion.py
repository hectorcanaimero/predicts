"""Router `/auth`: recuperación de contraseña. `POST /auth/recuperar` siempre responde `204`
(exista o no el email, para no filtrar cuentas) y comparte el límite de intentos con
`/auth/login` (misma tabla `intentos_login`, 5 por email o 20 por IP en 15 minutos)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from predicts import correo
from predicts.api.auth import _ip, _normalizar_email, _verificar_limite
from predicts.auth import recuperacion, seguridad
from predicts.auth.dependencias import Db
from predicts.db.modelos import IntentoLogin, Usuario
from predicts.errores import ErrorApi

router = APIRouter(prefix="/auth", tags=["auth"])


class Recuperar(BaseModel):
    email: EmailStr


class Restablecer(BaseModel):
    token: str
    contrasena: str = Field(max_length=1024)


def _registrar_intento(db: Session, email: str, ip: str, ahora: datetime) -> None:
    db.add(IntentoLogin(email=email, ip=ip, exitoso=False, creado_en=ahora))


@router.post("/recuperar", status_code=204, summary="Pedir recuperación de contraseña")
def recuperar(datos: Recuperar, request: Request, db: Db) -> None:
    email = _normalizar_email(datos.email)
    ip = _ip(request) or "0.0.0.0"
    ahora = datetime.now(UTC)
    _verificar_limite(db, email, ip, ahora)
    _registrar_intento(db, email, ip, ahora)

    usuario = db.scalar(select(Usuario).where(Usuario.email == email))
    if usuario is not None:
        token = recuperacion.crear_token(db, usuario)
        correo.enviar(usuario.email, usuario.idioma, "recuperacion", {"token": token})
    db.commit()


@router.post("/restablecer", status_code=204, summary="Restablecer contraseña con el token")
def restablecer(datos: Restablecer, db: Db) -> None:
    fila = recuperacion.token_vigente(db, datos.token)
    if fila is None:
        raise ErrorApi("token_invalido", 400)

    usuario = db.get(Usuario, fila.usuario_id)
    assert usuario is not None
    seguridad.validar_contrasena(datos.contrasena, usuario.email)
    recuperacion.restablecer(db, fila, seguridad.hashear(datos.contrasena))
    db.commit()
