"""App FastAPI de predicts: `crear_app()` arma la app, descubre los routers de
`predicts.api` y registra el manejador de errores estándar (ver docs/arch/001-predicts.md#api)."""

from __future__ import annotations

import importlib
import os
import pkgutil
from types import ModuleType

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from predicts import __version__
from predicts import api as _paquete_api_por_defecto
from predicts.errores import ErrorApi


def _descubrir_routers(app: FastAPI, paquete: ModuleType) -> None:
    for info in pkgutil.iter_modules(paquete.__path__, f"{paquete.__name__}."):
        modulo = importlib.import_module(info.name)
        router = getattr(modulo, "router", None)
        if router is not None:
            app.include_router(router)


def crear_app(*, paquete_routers: ModuleType = _paquete_api_por_defecto) -> FastAPI:
    """Arma la app FastAPI: CORS, manejador de `ErrorApi` y descubrimiento de routers."""
    app = FastAPI(
        title="predicts API",
        description="Predicción de recompra y recordatorios a partir del historial de compras.",
        version=__version__,
    )

    # CORS vía env var (no en Settings: solo concierne a esta app, no al resto del proyecto).
    origenes = [
        o.strip()
        for o in os.environ.get("CORS_ORIGENES", "http://localhost:5173").split(",")
        if o.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origenes,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ErrorApi)
    async def _manejar_error_api(request: Request, exc: ErrorApi) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status,
            content={"codigo": exc.codigo, "parametros": exc.parametros},
        )

    _descubrir_routers(app, paquete_routers)
    return app
