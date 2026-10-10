"""Tests de `predicts.app`: descubrimiento de routers, formato de error de `ErrorApi` y
`/salud`."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Generator

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from predicts.app import crear_app
from predicts.config import settings_para_tests
from predicts.errores import ErrorApi


@pytest.fixture()
def paquete_con_router_de_prueba(tmp_path, monkeypatch) -> Generator:
    """Paquete temporal `paquete_prueba_app` con un módulo que expone `router`, para
    verificar que `crear_app()` lo descubre e incluye sin configuración manual."""
    paquete_dir = tmp_path / "paquete_prueba_app"
    paquete_dir.mkdir()
    (paquete_dir / "__init__.py").write_text("")
    (paquete_dir / "ruta_prueba.py").write_text(
        "from fastapi import APIRouter\n\n"
        "router = APIRouter()\n\n\n"
        "@router.get('/ping-prueba')\n"
        "def ping():\n"
        "    return {'ok': True}\n"
    )

    monkeypatch.syspath_prepend(str(tmp_path))
    modulo = importlib.import_module("paquete_prueba_app")
    yield modulo
    sys.modules.pop("paquete_prueba_app.ruta_prueba", None)
    sys.modules.pop("paquete_prueba_app", None)


def test_descubre_routers_del_paquete_automaticamente(paquete_con_router_de_prueba) -> None:
    app = crear_app(paquete_routers=paquete_con_router_de_prueba)
    cliente = TestClient(app)

    respuesta = cliente.get("/ping-prueba")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"ok": True}


def test_formato_de_error_api() -> None:
    app = crear_app()
    router = APIRouter()

    @router.get("/falla-prueba")
    def falla() -> None:
        raise ErrorApi("algo_fallo", 422, campo="cantidad")

    app.include_router(router)
    cliente = TestClient(app)

    respuesta = cliente.get("/falla-prueba")

    assert respuesta.status_code == 422
    assert respuesta.json() == {"codigo": "algo_fallo", "parametros": {"campo": "cantidad"}}


class _ConexionFalsa:
    def __enter__(self) -> _ConexionFalsa:
        return self

    def __exit__(self, *_: object) -> bool:
        return False

    def execute(self, *_: object, **__: object) -> None:
        return None


class _EngineFalso:
    def connect(self) -> _ConexionFalsa:
        return _ConexionFalsa()


def test_salud_ok_cuando_postgres_y_data_dir_responden(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("predicts.api.salud.get_engine", lambda: _EngineFalso())
    monkeypatch.setattr(
        "predicts.api.salud.settings",
        lambda: settings_para_tests(DATA_DIR=str(tmp_path)),
    )

    cliente = TestClient(crear_app())
    respuesta = cliente.get("/salud")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"ok": True, "postgres": True, "data_dir": True}


def test_salud_falla_si_postgres_no_responde(tmp_path, monkeypatch) -> None:
    def _engine_que_falla() -> None:
        raise RuntimeError("sin conexión")

    monkeypatch.setattr("predicts.api.salud.get_engine", _engine_que_falla)
    monkeypatch.setattr(
        "predicts.api.salud.settings",
        lambda: settings_para_tests(DATA_DIR=str(tmp_path)),
    )

    cliente = TestClient(crear_app())
    respuesta = cliente.get("/salud")

    assert respuesta.status_code == 503
    cuerpo = respuesta.json()
    assert cuerpo["ok"] is False
    assert cuerpo["postgres"] is False
    assert cuerpo["data_dir"] is True


def test_salud_falla_si_data_dir_no_existe(monkeypatch) -> None:
    monkeypatch.setattr("predicts.api.salud.get_engine", lambda: _EngineFalso())
    monkeypatch.setattr(
        "predicts.api.salud.settings",
        lambda: settings_para_tests(DATA_DIR="/no/existe/seguro-para-tests"),
    )

    cliente = TestClient(crear_app())
    respuesta = cliente.get("/salud")

    assert respuesta.status_code == 503
    cuerpo = respuesta.json()
    assert cuerpo["ok"] is False
    assert cuerpo["data_dir"] is False
