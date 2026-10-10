"""Engine y `SessionLocal` de SQLAlchemy desde `DATABASE_URL`, y dependencia FastAPI `get_db`."""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from predicts.config import settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(settings().DATABASE_URL, pool_pre_ping=True)


@lru_cache
def _sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def SessionLocal() -> Session:  # noqa: N802 - nombre convencional de SQLAlchemy
    """Crea una nueva sesión ligada al engine de `DATABASE_URL`."""
    return _sessionmaker()()


def get_db() -> Generator[Session]:
    """Dependencia FastAPI: entrega una sesión y la cierra al terminar la request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
