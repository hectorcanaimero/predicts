"""Dependencias FastAPI de autenticación: `sesion_actual`, `usuario_actual`, `empresa_actual`.

`sesion_actual` exige además el header CSRF en POST/PUT/PATCH/DELETE.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from predicts.auth.csrf import verificar_csrf
from predicts.auth.sesiones import COOKIE_SESION, poner_cookies, sesion_vigente
from predicts.db.modelos import Empresa, Sesion, Usuario
from predicts.db.sesion import get_db
from predicts.errores import ErrorApi

Db = Annotated[Session, Depends(get_db)]


def token_actual(request: Request) -> str:
    token = request.cookies.get(COOKIE_SESION)
    if not token:
        raise ErrorApi("no_autenticado", 401)
    return token


TokenActual = Annotated[str, Depends(token_actual)]


def sesion_actual(request: Request, response: Response, token: TokenActual, db: Db) -> Sesion:
    sesion, renovada = sesion_vigente(db, token)
    if sesion is None:
        raise ErrorApi("no_autenticado", 401)
    verificar_csrf(request, token)
    if renovada:
        poner_cookies(response, token)
    return sesion


SesionActual = Annotated[Sesion, Depends(sesion_actual)]


def usuario_actual(sesion: SesionActual, db: Db) -> Usuario:
    usuario = db.get(Usuario, sesion.usuario_id)
    if usuario is None:  # borrado entre medio; la FK en cascada también borra la sesión
        raise ErrorApi("no_autenticado", 401)
    return usuario


UsuarioActual = Annotated[Usuario, Depends(usuario_actual)]


def empresa_actual(usuario: UsuarioActual, db: Db) -> Empresa:
    empresa = db.get(Empresa, usuario.empresa_id)
    if empresa is None:
        raise ErrorApi("no_autenticado", 401)
    return empresa


EmpresaActual = Annotated[Empresa, Depends(empresa_actual)]
