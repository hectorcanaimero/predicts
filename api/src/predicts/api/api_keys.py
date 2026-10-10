"""Router `/api-keys`: `GET/POST /api-keys`, `DELETE /api-keys/{id}` (requieren sesión).

Para el uso programático (MCP, F7) ver `predicts.auth.api_keys.empresa_por_api_key`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field

from predicts.auth import api_keys
from predicts.auth.dependencias import Db, EmpresaActual
from predicts.db.modelos import ApiKey

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


class ApiKeyEntrada(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)


class ApiKeySalida(BaseModel):
    id: str
    nombre: str
    prefijo: str
    creado_en: datetime
    ultimo_uso_en: datetime | None


class ApiKeyCreada(ApiKeySalida):
    clave: str


def _salida(fila: ApiKey) -> ApiKeySalida:
    return ApiKeySalida(
        id=str(fila.id),
        nombre=fila.nombre,
        prefijo=fila.prefijo,
        creado_en=fila.creado_en,
        ultimo_uso_en=fila.ultimo_uso_en,
    )


@router.get("", summary="Listar claves de API de la empresa actual")
def listar(empresa: EmpresaActual, db: Db) -> list[ApiKeySalida]:
    return [_salida(f) for f in api_keys.listar(db, empresa.id)]


@router.post("", status_code=201, summary="Crear una clave de API (el valor completo solo aquí)")
def crear(datos: ApiKeyEntrada, empresa: EmpresaActual, db: Db) -> ApiKeyCreada:
    fila, clave = api_keys.crear(db, empresa.id, datos.nombre)
    return ApiKeyCreada(**_salida(fila).model_dump(), clave=clave)


@router.delete("/{api_key_id}", status_code=204, summary="Revocar una clave de API")
def revocar(api_key_id: uuid.UUID, empresa: EmpresaActual, db: Db) -> None:
    api_keys.revocar(db, empresa.id, api_key_id)
