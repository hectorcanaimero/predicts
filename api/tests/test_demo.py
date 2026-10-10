"""Tests de `POST /demo`: crea el proyecto "Demo" con la muestra de Online Retail II, el dataset
ya "listo" con su mapeo identidad y el análisis completo encolado.

Usa el Excel de fixture de `test_datasets_publicos.py` en vez de descargar el dataset real."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from predicts.analisis.orquestador import TIPOS
from predicts.app import crear_app
from predicts.auth.csrf import COOKIE_CSRF
from predicts.config import settings_para_tests
from predicts.db.modelos import Analisis, Dataset, Proyecto, Trabajo
from predicts.db.sesion import get_db

pytestmark = pytest.mark.db

CONTRASENA = "una-contrasena-larga"
FIXTURES = Path(__file__).parent / "fixtures" / "publicos"
XLSX_ONLINE_RETAIL = FIXTURES / "online_retail_ii_fixture.xlsx"


@pytest.fixture()
def app(db: Session, monkeypatch, tmp_path):
    monkeypatch.setattr("predicts.auth.sesiones.settings", lambda: settings_para_tests())
    monkeypatch.setattr(
        "predicts.api.demo.settings", lambda: settings_para_tests(DATA_DIR=str(tmp_path))
    )
    monkeypatch.setattr(
        "predicts.datos.datasets_publicos.descargar_online_retail",
        lambda cfg=None: XLSX_ONLINE_RETAIL,
    )
    app = crear_app()

    def _get_db() -> Generator[Session]:
        s = Session(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _get_db
    return app


def _empresa(app, nombre_empresa: str, email: str) -> TestClient:
    cliente = TestClient(app)
    r = cliente.post(
        "/auth/registro",
        json={"email": email, "contrasena": CONTRASENA, "nombre_empresa": nombre_empresa},
    )
    assert r.status_code == 201
    return cliente


def _csrf(cliente: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": cliente.cookies[COOKIE_CSRF]}


@pytest.fixture()
def ana(app) -> TestClient:
    return _empresa(app, "Tienda Ana", "ana@ejemplo.com")


@pytest.fixture()
def beto(app) -> TestClient:
    return _empresa(app, "Tienda Beto", "beto@ejemplo.com")


def test_crea_proyecto_dataset_listo_y_analisis_encolado(ana, db, tmp_path) -> None:
    r = ana.post("/demo", headers=_csrf(ana))

    assert r.status_code == 201
    cuerpo = r.json()

    proyecto = db.get(Proyecto, uuid.UUID(cuerpo["proyecto_id"]))
    assert proyecto.nombre == "Demo"
    assert "CC BY 4.0" in proyecto.descripcion

    dataset = db.get(Dataset, uuid.UUID(cuerpo["dataset_id"]))
    assert dataset.estado == "listo"
    assert dataset.mapeo is not None
    assert Path(dataset.ruta_parquet).exists()
    assert Path(dataset.ruta_parquet).is_relative_to(tmp_path)

    analisis = db.get(Analisis, uuid.UUID(cuerpo["analisis_id"]))
    assert analisis.estado == "en_cola"
    assert set(analisis.tipos) == set(TIPOS)
    assert analisis.dataset_id == dataset.id

    trabajo = db.get(Trabajo, analisis.trabajo_id)
    assert trabajo.tipo == "analisis"
    assert trabajo.estado == "en_cola"
    assert trabajo.parametros == {"analisis_id": str(analisis.id)}


def test_cachea_la_muestra_entre_llamadas(ana, beto, tmp_path, monkeypatch) -> None:
    ana.post("/demo", headers=_csrf(ana))
    ruta_muestra = tmp_path / "demo" / "compras.parquet"
    assert ruta_muestra.exists()

    def _falla(*args, **kwargs):
        raise AssertionError("no debería volver a descargar/mapear: la muestra ya está cacheada")

    monkeypatch.setattr("predicts.datos.datasets_publicos.descargar_online_retail", _falla)

    r = beto.post("/demo", headers=_csrf(beto))

    assert r.status_code == 201


def test_cada_empresa_tiene_su_propio_dataset_y_proyecto(ana, beto, db) -> None:
    de_ana = ana.post("/demo", headers=_csrf(ana)).json()
    de_beto = beto.post("/demo", headers=_csrf(beto)).json()

    assert de_ana["proyecto_id"] != de_beto["proyecto_id"]
    assert de_ana["dataset_id"] != de_beto["dataset_id"]

    proyecto_ana = db.get(Proyecto, uuid.UUID(de_ana["proyecto_id"]))
    proyecto_beto = db.get(Proyecto, uuid.UUID(de_beto["proyecto_id"]))
    assert proyecto_ana.empresa_id != proyecto_beto.empresa_id


def test_sin_sesion_responde_401(app) -> None:
    anonimo = TestClient(app)
    assert anonimo.post("/demo").status_code == 401
