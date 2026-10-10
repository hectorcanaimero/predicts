"""Fixture `db`: crea una base Postgres temporal, corre `alembic upgrade head` y la borra al
cerrar. Requiere `TEST_DATABASE_URL` (URL de una base "admin" donde el usuario pueda hacer
`CREATE DATABASE`/`DROP DATABASE`, p. ej. `postgresql+psycopg://user:pass@host:puerto/postgres`).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from alembic import command

_ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"
_ALEMBIC_DIR = _ALEMBIC_INI.parent / "alembic"


def _con_nombre(url: str, nombre: str) -> str:
    partes = urlsplit(url)
    return urlunsplit(partes._replace(path=f"/{nombre}"))


@pytest.fixture()
def db() -> Generator[Session]:
    url_admin = os.environ.get("TEST_DATABASE_URL")
    if not url_admin:
        pytest.skip("TEST_DATABASE_URL no está configurada")

    nombre_db = f"predicts_test_{uuid.uuid4().hex[:16]}"
    url_test = _con_nombre(url_admin, nombre_db)

    engine_admin = create_engine(url_admin, isolation_level="AUTOCOMMIT")
    with engine_admin.connect() as con:
        con.execute(text(f'CREATE DATABASE "{nombre_db}"'))
    engine_admin.dispose()

    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_ALEMBIC_DIR))
    cfg.set_main_option("sqlalchemy.url", url_test)
    command.upgrade(cfg, "head")

    engine_test = create_engine(url_test)
    sesion = Session(bind=engine_test)
    try:
        yield sesion
    finally:
        sesion.close()
        engine_test.dispose()

        engine_admin = create_engine(url_admin, isolation_level="AUTOCOMMIT")
        with engine_admin.connect() as con:
            con.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :nombre AND pid <> pg_backend_pid()"
                ),
                {"nombre": nombre_db},
            )
            con.execute(text(f'DROP DATABASE IF EXISTS "{nombre_db}"'))
        engine_admin.dispose()
