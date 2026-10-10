"""Tests de `/proyectos`: aislamiento por empresa, CRUD y validación de campos."""

from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from predicts.app import crear_app
from predicts.auth.csrf import COOKIE_CSRF
from predicts.config import settings_para_tests
from predicts.db.modelos import Analisis, Dataset, Proyecto
from predicts.db.sesion import get_db

pytestmark = pytest.mark.db

CONTRASENA = "una-contrasena-larga"


@pytest.fixture()
def app(db: Session, monkeypatch):
    monkeypatch.setattr("predicts.auth.sesiones.settings", lambda: settings_para_tests())
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
    """Cliente logueado como dueño de una empresa nueva."""
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


def _crear(cliente: TestClient, **extra) -> dict:
    datos = {"nombre": "Campaña verano", **extra}
    r = cliente.post("/proyectos", json=datos, headers=_csrf(cliente))
    assert r.status_code == 201
    return r.json()


def test_crear_y_obtener_proyecto(ana) -> None:
    creado = _crear(ana, idioma_mensajes="es", tono="formal", descripcion="desc")

    r = ana.get(f"/proyectos/{creado['id']}")

    assert r.status_code == 200
    assert r.json() == creado
    assert creado["nombre"] == "Campaña verano"
    assert creado["idioma_mensajes"] == "es"
    assert creado["tono"] == "formal"


def test_valores_por_defecto(ana) -> None:
    creado = _crear(ana)

    assert creado["idioma_mensajes"] == "pt-BR"
    assert creado["tono"] == "neutro"
    assert creado["descripcion"] is None


def test_listar_solo_trae_proyectos_de_la_empresa_actual(ana, beto) -> None:
    propio = _crear(ana)
    _crear(beto)

    r = ana.get("/proyectos")

    assert r.status_code == 200
    ids = [p["id"] for p in r.json()]
    assert ids == [propio["id"]]


def test_otra_empresa_no_ve_el_proyecto_aunque_adivine_el_id(ana, beto) -> None:
    de_ana = _crear(ana)

    r = beto.get(f"/proyectos/{de_ana['id']}")

    assert r.status_code == 404
    assert r.json()["codigo"] == "no_encontrado"


def test_id_inexistente_responde_404(ana) -> None:
    r = ana.get(f"/proyectos/{uuid.uuid4()}")

    assert r.status_code == 404
    assert r.json()["codigo"] == "no_encontrado"


def test_otra_empresa_no_puede_editar(ana, beto, db) -> None:
    de_ana = _crear(ana)

    r = beto.patch(
        f"/proyectos/{de_ana['id']}",
        json={"nombre": "Secuestrado"},
        headers=_csrf(beto),
    )

    assert r.status_code == 404
    assert r.json()["codigo"] == "no_encontrado"
    assert db.scalar(select(Proyecto.nombre)) == "Campaña verano"


def test_otra_empresa_no_puede_borrar(ana, beto, db) -> None:
    de_ana = _crear(ana)

    r = beto.delete(f"/proyectos/{de_ana['id']}", headers=_csrf(beto))

    assert r.status_code == 404
    assert r.json()["codigo"] == "no_encontrado"
    assert db.scalar(select(Proyecto).where(Proyecto.id == uuid.UUID(de_ana["id"]))) is not None


def test_actualizar_parcial_no_toca_los_campos_no_enviados(ana) -> None:
    creado = _crear(ana, idioma_mensajes="es", tono="formal", descripcion="desc")

    r = ana.patch(
        f"/proyectos/{creado['id']}", json={"nombre": "Campaña invierno"}, headers=_csrf(ana)
    )

    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["nombre"] == "Campaña invierno"
    assert cuerpo["idioma_mensajes"] == "es"
    assert cuerpo["tono"] == "formal"
    assert cuerpo["descripcion"] == "desc"


def test_propia_empresa_puede_borrar_y_luego_404(ana) -> None:
    creado = _crear(ana)

    r = ana.delete(f"/proyectos/{creado['id']}", headers=_csrf(ana))

    assert r.status_code == 204
    assert ana.get(f"/proyectos/{creado['id']}").status_code == 404


def test_borrar_proyecto_borra_en_cascada_datasets_y_analisis(ana, db) -> None:
    creado = _crear(ana)
    proyecto_id = uuid.UUID(creado["id"])
    empresa_id = db.scalar(select(Proyecto.empresa_id).where(Proyecto.id == proyecto_id))
    dataset = Dataset(
        empresa_id=empresa_id,
        proyecto_id=proyecto_id,
        nombre_archivo="compras.csv",
        tamano_bytes=10,
        sha256="a" * 64,
    )
    db.add(dataset)
    db.flush()
    analisis = Analisis(
        empresa_id=empresa_id,
        dataset_id=dataset.id,
        tipos=["recompra"],
        estado="en_cola",
    )
    db.add(analisis)
    db.commit()
    dataset_id, analisis_id = dataset.id, analisis.id

    r = ana.delete(f"/proyectos/{creado['id']}", headers=_csrf(ana))

    assert r.status_code == 204
    db.expire_all()
    assert db.scalar(select(Dataset).where(Dataset.id == dataset_id)) is None
    assert db.scalar(select(Analisis).where(Analisis.id == analisis_id)) is None


@pytest.mark.parametrize(
    "datos",
    [
        {"nombre": ""},
        {"nombre": "x" * 201},
        {"nombre": "ok", "idioma_mensajes": "fr"},
        {"nombre": "ok", "tono": "agresivo"},
    ],
)
def test_crear_rechaza_campos_invalidos(ana, datos) -> None:
    r = ana.post("/proyectos", json=datos, headers=_csrf(ana))
    assert r.status_code == 422


def test_crear_rechaza_nombre_faltante(ana) -> None:
    r = ana.post("/proyectos", json={}, headers=_csrf(ana))
    assert r.status_code == 422


def test_actualizar_rechaza_campos_invalidos(ana) -> None:
    creado = _crear(ana)

    r = ana.patch(f"/proyectos/{creado['id']}", json={"tono": "agresivo"}, headers=_csrf(ana))

    assert r.status_code == 422


def test_sin_sesion_responde_401(app) -> None:
    anonimo = TestClient(app)
    assert anonimo.get("/proyectos").status_code == 401
