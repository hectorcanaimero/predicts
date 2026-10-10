"""Modelos ORM de todas las tablas de Postgres, ver docs/arch/001-predicts.md#modelo-de-datos
y docs/notas/esquema.md para el diagrama y el porqué de cada índice."""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from predicts.db.base import Base, EmpresaMixin, TimestampMixin, UUIDPKMixin, uuid7


class Empresa(Base):
    __tablename__ = "empresas"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    nombre: Mapped[str] = mapped_column(String, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Usuario(UUIDPKMixin, EmpresaMixin, TimestampMixin, Base):
    __tablename__ = "usuarios"
    __table_args__ = (
        UniqueConstraint("email", name="uq_usuarios_email"),
        CheckConstraint("email = lower(email)", name="ck_usuarios_email_minusculas"),
        CheckConstraint("idioma IN ('pt-BR', 'es', 'en')", name="ck_usuarios_idioma"),
        CheckConstraint("rol IN ('dueno', 'miembro')", name="ck_usuarios_rol"),
    )

    email: Mapped[str] = mapped_column(String, nullable=False)
    hash_contrasena: Mapped[str] = mapped_column(String, nullable=False)
    idioma: Mapped[str] = mapped_column(String, nullable=False)
    rol: Mapped[str] = mapped_column(String, nullable=False)
    ultimo_login_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Sesion(UUIDPKMixin, EmpresaMixin, TimestampMixin, Base):
    __tablename__ = "sesiones"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_sesiones_token_hash"),)

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String, nullable=False)
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String, nullable=True)


class TokenRecuperacion(UUIDPKMixin, EmpresaMixin, TimestampMixin, Base):
    __tablename__ = "tokens_recuperacion"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_tokens_recuperacion_token_hash"),)

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String, nullable=False)
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    usado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IntentoLogin(UUIDPKMixin, Base):
    __tablename__ = "intentos_login"
    __table_args__ = (
        Index("ix_intentos_login_email_creado_en", "email", "creado_en"),
        Index("ix_intentos_login_ip_creado_en", "ip", "creado_en"),
    )

    email: Mapped[str] = mapped_column(String, nullable=False)
    ip: Mapped[str] = mapped_column(INET, nullable=False)
    exitoso: Mapped[bool] = mapped_column(Boolean, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class ApiKey(UUIDPKMixin, EmpresaMixin, TimestampMixin, Base):
    __tablename__ = "api_keys"
    __table_args__ = (UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),)

    nombre: Mapped[str] = mapped_column(String, nullable=False)
    prefijo: Mapped[str] = mapped_column(String, nullable=False, index=True)
    key_hash: Mapped[str] = mapped_column(String, nullable=False)
    ultimo_uso_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revocada_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Proyecto(UUIDPKMixin, EmpresaMixin, TimestampMixin, Base):
    __tablename__ = "proyectos"
    __table_args__ = (
        CheckConstraint(
            "idioma_mensajes IN ('pt-BR', 'es', 'en')", name="ck_proyectos_idioma_mensajes"
        ),
        CheckConstraint("tono IN ('cercano', 'neutro', 'formal')", name="ck_proyectos_tono"),
    )

    nombre: Mapped[str] = mapped_column(String, nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    idioma_mensajes: Mapped[str] = mapped_column(String, nullable=False)
    tono: Mapped[str] = mapped_column(String, nullable=False)


class Dataset(UUIDPKMixin, EmpresaMixin, TimestampMixin, Base):
    __tablename__ = "datasets"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('subido', 'mapeado', 'ingiriendo', 'listo', 'error', 'archivado')",
            name="ck_datasets_estado",
        ),
        Index("ix_datasets_sha256", "sha256"),
    )

    proyecto_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("proyectos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    nombre_archivo: Mapped[str] = mapped_column(String, nullable=False)
    tamano_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    estado: Mapped[str] = mapped_column(String, nullable=False, server_default="subido")
    deteccion: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    mapeo: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    firma_encabezados: Mapped[str | None] = mapped_column(String, nullable=True)
    calidad: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    resumen_ingesta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ruta_original: Mapped[str | None] = mapped_column(String, nullable=True)
    ruta_parquet: Mapped[str | None] = mapped_column(String, nullable=True)
    subido_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    archivado_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PlantillaMapeo(UUIDPKMixin, EmpresaMixin, TimestampMixin, Base):
    __tablename__ = "plantillas_mapeo"
    __table_args__ = (
        UniqueConstraint(
            "empresa_id",
            "firma_encabezados",
            name="uq_plantillas_mapeo_empresa_id_firma_encabezados",
        ),
    )

    firma_encabezados: Mapped[str] = mapped_column(String, nullable=False)
    nombre: Mapped[str] = mapped_column(String, nullable=False)
    mapeo: Mapped[dict] = mapped_column(JSONB, nullable=False)


class GrupoProducto(UUIDPKMixin, EmpresaMixin, TimestampMixin, Base):
    __tablename__ = "grupos_producto"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('propuesto', 'confirmado', 'rechazado')", name="ck_grupos_producto_estado"
        ),
    )

    nombre: Mapped[str] = mapped_column(String, nullable=False)
    estado: Mapped[str] = mapped_column(String, nullable=False, server_default="propuesto")
    similitud: Mapped[float | None] = mapped_column(Float, nullable=True)


class Producto(UUIDPKMixin, EmpresaMixin, TimestampMixin, Base):
    __tablename__ = "productos"
    __table_args__ = (
        UniqueConstraint(
            "empresa_id", "nombre_normalizado", name="uq_productos_empresa_id_nombre_normalizado"
        ),
        CheckConstraint(
            "categoria_origen IS NULL OR categoria_origen IN ('csv', 'jev', 'persona')",
            name="ck_productos_categoria_origen",
        ),
        CheckConstraint(
            "tipo IN ('recompra', 'durable', 'desconocido')", name="ck_productos_tipo"
        ),
        CheckConstraint(
            "tipo_origen IS NULL OR tipo_origen IN ('regla', 'jev', 'persona')",
            name="ck_productos_tipo_origen",
        ),
        CheckConstraint(
            "estado_revision IN ('ok', 'revisar')", name="ck_productos_estado_revision"
        ),
        Index(
            "ix_productos_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    nombre_normalizado: Mapped[str] = mapped_column(String, nullable=False)
    nombre: Mapped[str] = mapped_column(String, nullable=False)
    producto_id_origen: Mapped[str | None] = mapped_column(String, nullable=True)
    categoria: Mapped[str | None] = mapped_column(String, nullable=True)
    categoria_origen: Mapped[str | None] = mapped_column(String, nullable=True)
    tipo: Mapped[str] = mapped_column(String, nullable=False, server_default="desconocido")
    tipo_origen: Mapped[str | None] = mapped_column(String, nullable=True)
    confianza: Mapped[float | None] = mapped_column(Float, nullable=True)
    estado_revision: Mapped[str] = mapped_column(String, nullable=False, server_default="ok")
    estadisticas: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    grupo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("grupos_producto.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


class Trabajo(UUIDPKMixin, EmpresaMixin, TimestampMixin, Base):
    __tablename__ = "trabajos"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('en_cola', 'corriendo', 'listo', 'error', 'cancelado')",
            name="ck_trabajos_estado",
        ),
        Index("ix_trabajos_estado_creado_en", "estado", "creado_en"),
    )

    tipo: Mapped[str] = mapped_column(String, nullable=False)
    parametros: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    estado: Mapped[str] = mapped_column(String, nullable=False, server_default="en_cola")
    error_codigo: Mapped[str | None] = mapped_column(String, nullable=True)
    error_detalle: Mapped[str | None] = mapped_column(Text, nullable=True)
    iniciado_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    terminado_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duracion_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    memoria_pico_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    intentos: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class Analisis(UUIDPKMixin, EmpresaMixin, TimestampMixin, Base):
    __tablename__ = "analisis"

    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tipos: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    parametros: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    estado: Mapped[str] = mapped_column(String, nullable=False)
    version_modelo: Mapped[str | None] = mapped_column(String, nullable=True)
    metricas: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    resumen: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ruta_resultados: Mapped[str | None] = mapped_column(String, nullable=True)
    costo_ia: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    trabajo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trabajos.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


class EventoTrabajo(UUIDPKMixin, EmpresaMixin, TimestampMixin, Base):
    __tablename__ = "eventos_trabajo"
    __table_args__ = (
        UniqueConstraint(
            "trabajo_id", "secuencia", name="uq_eventos_trabajo_trabajo_id_secuencia"
        ),
    )

    trabajo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trabajos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    secuencia: Mapped[int] = mapped_column(Integer, nullable=False)
    etapa: Mapped[str] = mapped_column(String, nullable=False)
    contadores: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    progreso: Mapped[float | None] = mapped_column(Float, nullable=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class DecisionJev(UUIDPKMixin, EmpresaMixin, TimestampMixin, Base):
    __tablename__ = "decisiones_jev"
    __table_args__ = (
        CheckConstraint(
            "tipo IN "
            "('mapeo_columna', 'tipo_producto', 'categoria', 'contactar', 'revision_mensaje')",
            name="ck_decisiones_jev_tipo",
        ),
        Index("ix_decisiones_jev_tipo_referencia", "tipo", "referencia"),
    )

    tipo: Mapped[str] = mapped_column(String, nullable=False)
    referencia: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    entrada_resumida: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    opcion: Mapped[str] = mapped_column(String, nullable=False)
    confianza: Mapped[float | None] = mapped_column(Float, nullable=True)
    corregida_a: Mapped[str | None] = mapped_column(String, nullable=True)
    corregida_por: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("usuarios.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    corregida_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PlantillaMensaje(UUIDPKMixin, EmpresaMixin, TimestampMixin, Base):
    __tablename__ = "plantillas_mensaje"
    __table_args__ = (
        UniqueConstraint(
            "empresa_id",
            "clave",
            "idioma",
            "tono",
            name="uq_plantillas_mensaje_empresa_id_clave_idioma_tono",
        ),
        CheckConstraint(
            "tipo IN ('recordatorio', 'oferta', 'reactivacion')", name="ck_plantillas_mensaje_tipo"
        ),
        CheckConstraint("idioma IN ('pt-BR', 'es', 'en')", name="ck_plantillas_mensaje_idioma"),
        CheckConstraint(
            "tono IN ('cercano', 'neutro', 'formal')", name="ck_plantillas_mensaje_tono"
        ),
        CheckConstraint(
            "estado IN ('ok', 'revisar', 'editada')", name="ck_plantillas_mensaje_estado"
        ),
    )

    clave: Mapped[str] = mapped_column(String, nullable=False)
    tipo: Mapped[str] = mapped_column(String, nullable=False)
    idioma: Mapped[str] = mapped_column(String, nullable=False)
    tono: Mapped[str] = mapped_column(String, nullable=False)
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    estado: Mapped[str] = mapped_column(String, nullable=False, server_default="ok")
    motivo_revision: Mapped[str | None] = mapped_column(Text, nullable=True)
