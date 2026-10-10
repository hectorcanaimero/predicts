"""Router `/auth`: registro, login, logout y `GET/PATCH /auth/yo`."""

from __future__ import annotations

import ipaddress
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from predicts.auth import seguridad, sesiones
from predicts.auth.dependencias import (
    Db,
    EmpresaActual,
    SesionActual,
    TokenActual,
    UsuarioActual,
)
from predicts.db.modelos import Empresa, IntentoLogin, Usuario
from predicts.errores import ErrorApi

router = APIRouter(prefix="/auth", tags=["auth"])

Idioma = Literal["pt-BR", "es", "en"]

VENTANA_INTENTOS = timedelta(minutes=15)
MAX_FALLOS_EMAIL = 5
MAX_FALLOS_IP = 20


class Registro(BaseModel):
    email: EmailStr
    contrasena: str = Field(max_length=1024)
    nombre_empresa: str = Field(min_length=1, max_length=200)
    idioma: Idioma = "pt-BR"


class Login(BaseModel):
    email: str = Field(max_length=320)
    contrasena: str = Field(max_length=1024)


class CambioYo(BaseModel):
    idioma: Idioma


class UsuarioSalida(BaseModel):
    id: str
    email: str
    rol: str


class EmpresaSalida(BaseModel):
    id: str
    nombre: str


class Yo(BaseModel):
    usuario: UsuarioSalida
    empresa: EmpresaSalida
    idioma: Idioma


def _yo(usuario: Usuario, empresa: Empresa) -> Yo:
    return Yo(
        usuario=UsuarioSalida(id=str(usuario.id), email=usuario.email, rol=usuario.rol),
        empresa=EmpresaSalida(id=str(empresa.id), nombre=empresa.nombre),
        idioma=usuario.idioma,  # type: ignore[arg-type]
    )


def _normalizar_email(email: str) -> str:
    return email.strip().lower()


def _ip(request: Request) -> str | None:
    host = request.client.host if request.client else None
    try:
        return str(ipaddress.ip_address(host)) if host else None
    except ValueError:
        return None


def _verificar_limite(db: Session, email: str, ip: str, ahora: datetime) -> None:
    """429 si hay ≥5 fallos del email o ≥20 de la IP en la ventana; `reintentar_en_s` es cuánto
    falta para que el fallo que completa el límite salga de la ventana."""
    desde = ahora - VENTANA_INTENTOS
    espera = 0.0
    for columna, valor, limite in (
        (IntentoLogin.email, email, MAX_FALLOS_EMAIL),
        (IntentoLogin.ip, ip, MAX_FALLOS_IP),
    ):
        limite_en = db.scalar(
            select(IntentoLogin.creado_en)
            .where(
                columna == valor, IntentoLogin.exitoso.is_(False), IntentoLogin.creado_en > desde
            )
            .order_by(IntentoLogin.creado_en.desc())
            .offset(limite - 1)
            .limit(1)
        )
        if limite_en is not None:
            espera = max(espera, (limite_en + VENTANA_INTENTOS - ahora).total_seconds())
    if espera > 0:
        raise ErrorApi("demasiados_intentos", 429, reintentar_en_s=max(1, round(espera)))


@router.post("/registro", status_code=201, summary="Crear empresa y usuario dueño")
def registro(datos: Registro, request: Request, response: Response, db: Db) -> Yo:
    email = _normalizar_email(datos.email)
    seguridad.validar_contrasena(datos.contrasena, email)

    empresa = Empresa(nombre=datos.nombre_empresa.strip())
    db.add(empresa)
    db.flush()
    usuario = Usuario(
        empresa_id=empresa.id,
        email=email,
        hash_contrasena=seguridad.hashear(datos.contrasena),
        idioma=datos.idioma,
        rol="dueno",
    )
    db.add(usuario)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ErrorApi("email_en_uso", 409) from None
    token = sesiones.crear_sesion(db, usuario, _ip(request), request.headers.get("user-agent"))
    db.commit()

    sesiones.poner_cookies(response, token)
    return _yo(usuario, empresa)


@router.post("/login", summary="Iniciar sesión")
def login(datos: Login, request: Request, response: Response, db: Db) -> Yo:
    email = _normalizar_email(datos.email)
    ip = _ip(request)
    # ponytail: sin IP (p. ej. socket unix) todos comparten el balde de 0.0.0.0.
    ip_intento = ip or "0.0.0.0"
    ahora = datetime.now(UTC)
    _verificar_limite(db, email, ip_intento, ahora)

    usuario = db.scalar(select(Usuario).where(Usuario.email == email))
    # Con email inexistente se verifica igual contra un hash falso: mismo error y tiempo similar.
    ok = seguridad.verificar(
        usuario.hash_contrasena if usuario else seguridad.HASH_FALSO, datos.contrasena
    )
    ok = ok and usuario is not None
    db.add(IntentoLogin(email=email, ip=ip_intento, exitoso=ok, creado_en=ahora))
    if not ok or usuario is None:
        db.commit()
        raise ErrorApi("credenciales_invalidas", 401)

    if seguridad.necesita_rehash(usuario.hash_contrasena):
        usuario.hash_contrasena = seguridad.hashear(datos.contrasena)
    usuario.ultimo_login_en = ahora
    token = sesiones.crear_sesion(db, usuario, ip, request.headers.get("user-agent"))
    db.commit()

    sesiones.poner_cookies(response, token)
    empresa = db.get(Empresa, usuario.empresa_id)
    assert empresa is not None
    return _yo(usuario, empresa)


@router.post("/logout", status_code=204, summary="Cerrar sesión")
def logout(
    response: Response,
    _sesion: SesionActual,
    token: TokenActual,
    db: Db,
) -> None:
    sesiones.cerrar_sesion(db, token)
    sesiones.borrar_cookies(response)


@router.get("/yo", summary="Usuario, empresa e idioma de la sesión actual")
def yo(usuario: UsuarioActual, empresa: EmpresaActual) -> Yo:
    return _yo(usuario, empresa)


@router.patch("/yo", summary="Cambiar el idioma preferido")
def cambiar_yo(
    datos: CambioYo,
    usuario: UsuarioActual,
    empresa: EmpresaActual,
    db: Db,
) -> Yo:
    usuario.idioma = datos.idioma
    db.commit()
    return _yo(usuario, empresa)
