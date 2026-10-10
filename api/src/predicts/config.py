"""Configuración de la aplicación (`Settings`), ver docs/arch/001-predicts.md#config."""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    ENTORNO: str = "dev"
    SECRET_KEY: str | None = None

    DATABASE_URL: str
    TEST_DATABASE_URL: str | None = None
    DATA_DIR: str

    ROUTER_BASE_URL: str
    ROUTER_API_KEY: str
    ROUTER_MODEL: str
    ROUTER_EMBEDDINGS_MODEL: str = "openai/text-embedding-3-small"

    TYPESAFE_API_KEY: str
    TYPESAFE_MODEL: str = "jev-latest"

    SMTP_HOST: str | None = None
    SMTP_PORT: int | None = None
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM: str | None = None

    MAX_CSV_MB: int = 500
    MIN_COMPRAS: int = 3
    HORIZONTE_DIAS: int = 7
    VENTANA_VALIDACION_SEMANAS: int = 4
    CONFIANZA_MAPEO: float = Field(default=0.8, ge=0, le=1)
    CONFIANZA_JEV: float = Field(default=0.7, ge=0, le=1)
    RETENCION_DIAS: int = 7

    DUCKDB_MEMORY_LIMIT: str = Field(default="3GB", pattern=r"^\d+(GB|MB)$")
    DUCKDB_THREADS: int = 4
    MAX_MEMORIA_TRABAJO_MB: int = Field(default=4096, gt=512)
    TIMEOUT_TRABAJO_S: int = 1800

    @model_validator(mode="after")
    def _secret_key_obligatoria_fuera_de_dev(self) -> Settings:
        if self.ENTORNO != "dev" and not self.SECRET_KEY:
            raise ValueError("SECRET_KEY es obligatoria cuando ENTORNO != 'dev'")
        return self


@lru_cache
def settings() -> Settings:
    env_file = os.environ.get("PREDICTS_ENV_FILE", ".env")
    return Settings(_env_file=env_file)  # type: ignore[call-arg]


_OVERRIDES_MINIMAS = {
    "DATABASE_URL": "postgresql://predicts:predicts@localhost/predicts_test",
    "DATA_DIR": "/tmp/predicts-test",
    "ROUTER_BASE_URL": "https://router.test",
    "ROUTER_API_KEY": "test",
    "ROUTER_MODEL": "test-model",
    "TYPESAFE_API_KEY": "test",
}


def settings_para_tests(**overrides: object) -> Settings:
    """`Settings` hermética para tests: ignora `.env`, con mínimos requeridos + overrides."""
    valores = {**_OVERRIDES_MINIMAS, **overrides}
    return Settings(_env_file=None, **valores)  # type: ignore[call-arg, arg-type]
