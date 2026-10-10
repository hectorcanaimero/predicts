"""Router `GET /salud`: healthcheck de Postgres y de `DATA_DIR`."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from predicts.config import settings
from predicts.db.sesion import get_engine

router = APIRouter(tags=["salud"])


@router.get("/salud", summary="Estado de salud del servicio")
def salud() -> JSONResponse:
    try:
        with get_engine().connect() as con:
            con.execute(text("SELECT 1"))
        postgres_ok = True
    except Exception:
        postgres_ok = False

    data_dir_ok = Path(settings().DATA_DIR).is_dir()

    contenido = {
        "ok": postgres_ok and data_dir_ok,
        "postgres": postgres_ok,
        "data_dir": data_dir_ok,
    }
    return JSONResponse(status_code=200 if contenido["ok"] else 503, content=contenido)
