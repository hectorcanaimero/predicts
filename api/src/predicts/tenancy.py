"""Aislamiento por empresa: ver docs/notas/tenancy.md para la regla completa."""

from __future__ import annotations

import uuid

from sqlalchemy import Select
from sqlalchemy.orm import Session

from predicts.errores import ErrorApi


def de_empresa[ModeloT](query: Select[ModeloT], empresa_id: uuid.UUID) -> Select[ModeloT]:
    """Agrega `WHERE <modelo>.empresa_id = :empresa_id` a un `select(Modelo)...`."""
    entidad = query.column_descriptions[0]["entity"]
    return query.where(entidad.empresa_id == empresa_id)


def obtener_o_404[ModeloT](
    db: Session, modelo: type[ModeloT], id: uuid.UUID, empresa_id: uuid.UUID
) -> ModeloT:
    """Busca `modelo` por `id`; si no existe o es de otra empresa, `404 no_encontrado`
    (nunca `403`: no revela que el recurso existe)."""
    fila = db.get(modelo, id)
    if fila is None or fila.empresa_id != empresa_id:  # type: ignore[attr-defined]
        raise ErrorApi("no_encontrado", 404)
    return fila
