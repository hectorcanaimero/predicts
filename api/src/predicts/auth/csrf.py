"""CSRF por doble envío: cookie `predicts_csrf` (legible por JS) + header `X-CSRF-Token`.

El valor se deriva del token de sesión con HMAC, así que una cookie inyectada por un tercero no
sirve sin conocer la sesión, y no hace falta guardarlo en la base.
"""

from __future__ import annotations

import hashlib
import hmac

from fastapi import Request

from predicts.errores import ErrorApi

COOKIE_CSRF = "predicts_csrf"
HEADER_CSRF = "X-CSRF-Token"
METODOS_PROTEGIDOS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def token_csrf(token_sesion: str) -> str:
    return hmac.new(token_sesion.encode(), b"predicts_csrf", hashlib.sha256).hexdigest()


def verificar_csrf(request: Request, token_sesion: str) -> None:
    if request.method not in METODOS_PROTEGIDOS:
        return
    enviado = request.headers.get(HEADER_CSRF, "").encode()
    if not hmac.compare_digest(enviado, token_csrf(token_sesion).encode()):
        raise ErrorApi("csrf_invalido", 403)
