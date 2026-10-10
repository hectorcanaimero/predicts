"""Hash de contraseñas con Argon2id (parámetros por defecto de `argon2-cffi`) y su validación."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from predicts.errores import ErrorApi

LARGO_MINIMO = 10

_hasher = PasswordHasher()  # Argon2id por defecto

# Hash de una contraseña que nadie conoce: se verifica contra él cuando el email no existe, para
# que el tiempo de respuesta del login sea similar en ambos casos.
HASH_FALSO = _hasher.hash("predicts-contrasena-inexistente")


def hashear(contrasena: str) -> str:
    return _hasher.hash(contrasena)


def verificar(hash_guardado: str, contrasena: str) -> bool:
    try:
        return _hasher.verify(hash_guardado, contrasena)
    except (VerificationError, InvalidHashError):
        return False


def necesita_rehash(hash_guardado: str) -> bool:
    """True si el hash se generó con parámetros distintos a los actuales de la librería."""
    return _hasher.check_needs_rehash(hash_guardado)


def validar_contrasena(contrasena: str, email: str) -> None:
    if len(contrasena) < LARGO_MINIMO:
        raise ErrorApi("contrasena_invalida", 422, motivo="corta", minimo=LARGO_MINIMO)
    if contrasena.strip().lower() == email.strip().lower():
        raise ErrorApi("contrasena_invalida", 422, motivo="igual_al_email")
