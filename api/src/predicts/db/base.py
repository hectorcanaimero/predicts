"""Base declarativa y mixins comunes a las tablas de negocio.

Ver docs/arch/001-predicts.md#modelo-de-datos. Todas las tablas de negocio llevan `id`
(UUID v7), `empresa_id` (FK a `empresas`) y los timestamps `creado_en`/`actualizado_en`; las
excepciones (`empresas`, `intentos_login`) se definen con sus columnas exactas en `modelos.py`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import uuid_utils
from sqlalchemy import DateTime, ForeignKey, MetaData, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    # Los `CheckConstraint` de este módulo siempre traen un `name` explícito
    # (`ck_<tabla>_<columna>`); si esta clave tuviera el prefijo `ck_%(table_name)s_`
    # de nuevo, SQLAlchemy lo reaplicaría sobre ese nombre y lo duplicaría.
    "ck": "%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def uuid7() -> uuid.UUID:
    """UUID v7 (ordenable por tiempo de creación): mejor localidad de índice que v4 en PK."""
    return uuid.UUID(bytes=uuid_utils.uuid7().bytes)


class UUIDPKMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)


class TimestampMixin:
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class EmpresaMixin:
    empresa_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("empresas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
