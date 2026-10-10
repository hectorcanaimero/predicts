"""API keys por empresa: para el servidor MCP y usos programáticos (F7).

Formato `pk_<32 bytes en base62>`; en la base solo el SHA-256 (`api_keys.key_hash`), igual que
`auth/sesiones.py` con el token de sesión. El valor completo solo se devuelve al crearla.
"""

from __future__ import annotations

import hashlib
import secrets
import string
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from predicts.auth.dependencias import Db
from predicts.db.modelos import ApiKey, Empresa
from predicts.errores import ErrorApi
from predicts.tenancy import de_empresa, obtener_o_404

PREFIJO = "pk_"
LARGO_PREFIJO_VISIBLE = len(PREFIJO) + 8  # suficiente para reconocer la key sin revelarla

_ALFABETO_BASE62 = string.digits + string.ascii_uppercase + string.ascii_lowercase


def _base62(datos: bytes) -> str:
    numero = int.from_bytes(datos, "big")
    digitos = []
    while numero:
        numero, resto = divmod(numero, 62)
        digitos.append(_ALFABETO_BASE62[resto])
    return "".join(reversed(digitos)) or _ALFABETO_BASE62[0]


def generar_clave() -> str:
    return PREFIJO + _base62(secrets.token_bytes(32))


def hash_clave(clave: str) -> str:
    return hashlib.sha256(clave.encode()).hexdigest()


def crear(db: Session, empresa_id: uuid.UUID, nombre: str) -> tuple[ApiKey, str]:
    """Crea la fila (con commit) y devuelve `(fila, clave_en_claro)`; la clave no se recupera
    después de esta llamada."""
    clave = generar_clave()
    fila = ApiKey(
        empresa_id=empresa_id,
        nombre=nombre,
        prefijo=clave[:LARGO_PREFIJO_VISIBLE],
        key_hash=hash_clave(clave),
    )
    db.add(fila)
    db.commit()
    return fila, clave


def listar(db: Session, empresa_id: uuid.UUID) -> list[ApiKey]:
    """Claves activas de la empresa (las revocadas dejan de listarse, igual que un borrado)."""
    consulta = de_empresa(select(ApiKey), empresa_id).where(ApiKey.revocada_en.is_(None))
    return list(db.scalars(consulta.order_by(ApiKey.creado_en)).all())


def revocar(db: Session, empresa_id: uuid.UUID, api_key_id: uuid.UUID) -> None:
    fila = obtener_o_404(db, ApiKey, api_key_id, empresa_id)
    fila.revocada_en = datetime.now(UTC)
    db.commit()


def _empresa_por_clave(db: Session, clave: str) -> Empresa | None:
    fila = db.scalar(
        select(ApiKey).where(
            ApiKey.key_hash == hash_clave(clave), ApiKey.revocada_en.is_(None)
        )
    )
    if fila is None:
        return None
    fila.ultimo_uso_en = datetime.now(UTC)
    db.commit()
    return db.get(Empresa, fila.empresa_id)


def empresa_por_api_key(
    db: Db, authorization: Annotated[str | None, Header()] = None
) -> Empresa:
    """Dependencia FastAPI: lee `Authorization: Bearer pk_...` y actualiza `ultimo_uso_en`."""
    if not authorization or not authorization.startswith("Bearer "):
        raise ErrorApi("no_autenticado", 401)
    clave = authorization.removeprefix("Bearer ").strip()
    if not clave.startswith(PREFIJO):
        raise ErrorApi("no_autenticado", 401)
    empresa = _empresa_por_clave(db, clave)
    if empresa is None:
        raise ErrorApi("no_autenticado", 401)
    return empresa


EmpresaPorApiKey = Annotated[Empresa, Depends(empresa_por_api_key)]
