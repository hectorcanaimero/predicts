"""Tests de `/api-keys`: creación (clave en claro solo en la respuesta de creación), uso de la
clave para `empresa_por_api_key`, revocación, aislamiento entre empresas y que la clave nunca
queda en claro en la base."""

from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from predicts.app import crear_app
from predicts.auth import api_keys
from predicts.auth.csrf import COOKIE_CSRF
from predicts.config import settings_para_tests
from predicts.db.modelos import ApiKey
from predicts.db.sesion import get_db

pytestmark = pytest.mark.db

CONTRASENA = "una-contrasena-larga"


@pytest.fixture()
def app(db: Session, monkeypatch):
    monkeypatch.setattr("predicts.auth.sesiones.settings", lambda: settings_para_tests())
    app = crear_app()

    # Ruta de prueba que depende de `empresa_por_api_key`, igual a lo que usará el MCP (F7).
    router = APIRouter()

    @router.get("/_prueba/empresa-por-api-key")
    def _quien(empresa: api_keys.EmpresaPorApiKey) -> dict:
        return {"empresa_id": str(empresa.id)}

    app.include_router(router)

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


def _crear(cliente: TestClient, nombre: str = "MCP") -> dict:
    r = cliente.post("/api-keys", json={"nombre": nombre}, headers=_csrf(cliente))
    assert r.status_code == 201
    return r.json()


def test_crear_devuelve_la_clave_completa_una_sola_vez(ana) -> None:
    creada = _crear(ana)

    assert creada["clave"].startswith("pk_")
    assert len(creada["clave"]) > len("pk_") + 20
    assert creada["nombre"] == "MCP"
    assert creada["prefijo"] == creada["clave"][: len(creada["prefijo"])]
    assert creada["ultimo_uso_en"] is None

    r = ana.get("/api-keys")
    assert r.status_code == 200
    listado = r.json()
    assert len(listado) == 1
    assert "clave" not in listado[0]
    assert listado[0]["prefijo"] == creada["prefijo"]
    assert listado[0]["id"] == creada["id"]


def test_la_clave_nunca_queda_en_claro_en_la_base(ana, db) -> None:
    creada = _crear(ana)

    fila = db.scalar(select(ApiKey).where(ApiKey.id == uuid.UUID(creada["id"])))
    assert fila is not None
    assert creada["clave"] not in fila.key_hash
    assert fila.key_hash == api_keys.hash_clave(creada["clave"])
    assert fila.key_hash != creada["clave"]


def test_usar_la_clave_identifica_la_empresa_y_actualiza_ultimo_uso(ana, db) -> None:
    creada = _crear(ana)
    anonimo = TestClient(ana.app)

    r = anonimo.get(
        "/_prueba/empresa-por-api-key", headers={"Authorization": f"Bearer {creada['clave']}"}
    )

    assert r.status_code == 200
    r_yo = ana.get("/auth/yo")
    assert r.json()["empresa_id"] == r_yo.json()["empresa"]["id"]

    fila = db.scalar(select(ApiKey).where(ApiKey.id == uuid.UUID(creada["id"])))
    assert fila.ultimo_uso_en is not None


def test_clave_invalida_o_ausente_responde_401(ana) -> None:
    anonimo = TestClient(ana.app)

    assert anonimo.get("/_prueba/empresa-por-api-key").status_code == 401
    assert (
        anonimo.get(
            "/_prueba/empresa-por-api-key", headers={"Authorization": "Bearer pk_inventada"}
        ).status_code
        == 401
    )
    assert (
        anonimo.get(
            "/_prueba/empresa-por-api-key", headers={"Authorization": "Token abc"}
        ).status_code
        == 401
    )


def test_revocar_impide_seguir_usando_la_clave(ana) -> None:
    creada = _crear(ana)
    anonimo = TestClient(ana.app)

    r = ana.delete(f"/api-keys/{creada['id']}", headers=_csrf(ana))
    assert r.status_code == 204

    assert (
        anonimo.get(
            "/_prueba/empresa-por-api-key", headers={"Authorization": f"Bearer {creada['clave']}"}
        ).status_code
        == 401
    )
    assert ana.get("/api-keys").json() == []


def test_revocar_dos_veces_es_idempotente(ana) -> None:
    creada = _crear(ana)
    ana.delete(f"/api-keys/{creada['id']}", headers=_csrf(ana))

    r = ana.delete(f"/api-keys/{creada['id']}", headers=_csrf(ana))

    assert r.status_code == 204


def test_otra_empresa_no_ve_las_claves_de_la_otra(ana, beto) -> None:
    _crear(ana)

    r = beto.get("/api-keys")

    assert r.status_code == 200
    assert r.json() == []


def test_otra_empresa_no_puede_revocar_una_clave_ajena(ana, beto, db) -> None:
    de_ana = _crear(ana)

    r = beto.delete(f"/api-keys/{de_ana['id']}", headers=_csrf(beto))

    assert r.status_code == 404
    assert r.json()["codigo"] == "no_encontrado"
    fila = db.scalar(select(ApiKey).where(ApiKey.id == uuid.UUID(de_ana["id"])))
    assert fila.revocada_en is None


def test_id_inexistente_responde_404(ana) -> None:
    r = ana.delete(f"/api-keys/{uuid.uuid4()}", headers=_csrf(ana))

    assert r.status_code == 404
    assert r.json()["codigo"] == "no_encontrado"


def test_crear_rechaza_nombre_vacio(ana) -> None:
    r = ana.post("/api-keys", json={"nombre": ""}, headers=_csrf(ana))
    assert r.status_code == 422


def test_sin_sesion_no_puede_administrar_claves(app) -> None:
    anonimo = TestClient(app)
    assert anonimo.get("/api-keys").status_code == 401
    assert anonimo.post("/api-keys", json={"nombre": "x"}).status_code == 401


def test_dos_claves_generadas_son_distintas() -> None:
    a = api_keys.generar_clave()
    b = api_keys.generar_clave()
    assert a != b
    assert a.startswith("pk_")
    assert b.startswith("pk_")
