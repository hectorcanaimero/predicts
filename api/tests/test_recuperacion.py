"""Tests de recuperación de contraseña: email existente/inexistente (misma respuesta), token
vencido/reusado/inválido, cierre de sesiones al restablecer, límite de intentos compartido con
login, y contenido del email en los tres idiomas (con el transporte falso de modo dev)."""

from __future__ import annotations

import logging
import re
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from predicts.app import crear_app
from predicts.config import settings_para_tests
from predicts.db.modelos import Sesion, TokenRecuperacion
from predicts.db.sesion import get_db

pytestmark = pytest.mark.db

CONTRASENA = "una-contrasena-larga"
CONTRASENA_NUEVA = "otra-contrasena-mas-larga"

_RE_TOKEN = re.compile(r"[A-Za-z0-9_-]{40,}")


@pytest.fixture()
def app(db: Session, monkeypatch):
    monkeypatch.setattr("predicts.auth.sesiones.settings", lambda: settings_para_tests())
    monkeypatch.setattr("predicts.correo.settings", lambda: settings_para_tests())
    app = crear_app()

    def _get_db() -> Generator[Session]:
        s = Session(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _get_db
    return app


def _cliente(app, ip: str = "10.0.0.1") -> TestClient:
    return TestClient(app, client=(ip, 50000))


@pytest.fixture()
def cliente(app) -> TestClient:
    return _cliente(app)


def _registrar(cliente: TestClient, email: str = "ana@ejemplo.com", idioma: str = "es"):
    r = cliente.post(
        "/auth/registro",
        json={
            "email": email,
            "contrasena": CONTRASENA,
            "nombre_empresa": "Tienda Ana",
            "idioma": idioma,
        },
    )
    assert r.status_code == 201
    return r


def _token_de_recuperacion(
    cliente: TestClient, caplog: pytest.LogCaptureFixture, email: str
) -> str:
    # El `fileConfig` que corre `alembic upgrade` (fixture `db`) deshabilita los loggers ya
    # creados en el proceso; "predicts.correo" ya existe desde el primer test de este archivo.
    logging.getLogger("predicts.correo").disabled = False
    caplog.set_level(logging.INFO, logger="predicts.correo")
    r = cliente.post("/auth/recuperar", json={"email": email})
    assert r.status_code == 204
    mensaje = next(m for m in caplog.messages if "Email (modo dev)" in m)
    return _RE_TOKEN.search(mensaje).group()


def test_recuperar_responde_204_igual_para_email_existente_e_inexistente(cliente, app) -> None:
    _registrar(cliente)

    existente = _cliente(app, "10.1.0.1").post(
        "/auth/recuperar", json={"email": "ana@ejemplo.com"}
    )
    inexistente = _cliente(app, "10.1.0.2").post(
        "/auth/recuperar", json={"email": "nadie@ejemplo.com"}
    )

    assert existente.status_code == inexistente.status_code == 204
    assert existente.content == inexistente.content == b""


def test_pedir_token_de_nuevo_invalida_el_anterior(cliente, db, caplog) -> None:
    _registrar(cliente)
    primero = _token_de_recuperacion(cliente, caplog, "ana@ejemplo.com")
    caplog.clear()
    _token_de_recuperacion(cliente, caplog, "ana@ejemplo.com")

    assert len(db.scalars(select(TokenRecuperacion)).all()) == 1
    r = cliente.post(
        "/auth/restablecer", json={"token": primero, "contrasena": CONTRASENA_NUEVA}
    )
    assert r.status_code == 400
    assert r.json()["codigo"] == "token_invalido"


@pytest.mark.parametrize(
    ("idioma", "asunto", "fragmento"),
    [
        ("es", "Recuperá tu contraseña", "Usá este código"),
        ("en", "Reset your password", "Use this code"),
        ("pt-BR", "Recupere sua senha", "Use este código"),
    ],
)
def test_email_de_recuperacion_en_cada_idioma(cliente, caplog, idioma, asunto, fragmento) -> None:
    email = f"usuario-{idioma.lower()}@ejemplo.com"
    _registrar(cliente, email=email, idioma=idioma)
    token = _token_de_recuperacion(cliente, caplog, email)

    mensaje = next(m for m in caplog.messages if "Email (modo dev)" in m)
    assert email in mensaje
    assert asunto in mensaje
    assert fragmento in mensaje
    assert token in mensaje


def test_restablecer_token_invalido_responde_400(cliente) -> None:
    r = cliente.post(
        "/auth/restablecer", json={"token": "token-que-no-existe", "contrasena": CONTRASENA_NUEVA}
    )
    assert r.status_code == 400
    assert r.json()["codigo"] == "token_invalido"


def test_restablecer_token_vencido_responde_400(cliente, db, caplog) -> None:
    _registrar(cliente)
    token = _token_de_recuperacion(cliente, caplog, "ana@ejemplo.com")
    db.execute(update(TokenRecuperacion).values(expira_en=datetime.now(UTC) - timedelta(seconds=1)))
    db.commit()

    r = cliente.post("/auth/restablecer", json={"token": token, "contrasena": CONTRASENA_NUEVA})

    assert r.status_code == 400
    assert r.json()["codigo"] == "token_invalido"


def test_restablecer_token_reusado_responde_400(cliente, caplog) -> None:
    _registrar(cliente)
    token = _token_de_recuperacion(cliente, caplog, "ana@ejemplo.com")

    primera = cliente.post(
        "/auth/restablecer", json={"token": token, "contrasena": CONTRASENA_NUEVA}
    )
    segunda = cliente.post(
        "/auth/restablecer", json={"token": token, "contrasena": "una-tercera-contrasena"}
    )

    assert primera.status_code == 204
    assert segunda.status_code == 400
    assert segunda.json()["codigo"] == "token_invalido"


def test_restablecer_rechaza_contrasena_debil(cliente, db, caplog) -> None:
    _registrar(cliente)
    token = _token_de_recuperacion(cliente, caplog, "ana@ejemplo.com")

    r = cliente.post("/auth/restablecer", json={"token": token, "contrasena": "corta"})

    assert r.status_code == 422
    assert r.json()["codigo"] == "contrasena_invalida"
    # el token sigue vigente: una contraseña inválida no lo consume
    assert db.scalar(select(TokenRecuperacion.usado_en)) is None


def test_restablecer_cierra_todas_las_sesiones_y_permite_login_con_la_nueva(
    app, cliente, db, caplog
) -> None:
    _registrar(cliente)
    otra_sesion = _cliente(app, "10.2.0.1")
    otra_sesion.post("/auth/login", json={"email": "ana@ejemplo.com", "contrasena": CONTRASENA})
    assert len(db.scalars(select(Sesion)).all()) == 2

    token = _token_de_recuperacion(cliente, caplog, "ana@ejemplo.com")
    r = cliente.post("/auth/restablecer", json={"token": token, "contrasena": CONTRASENA_NUEVA})

    assert r.status_code == 204
    assert db.scalars(select(Sesion)).all() == []
    assert cliente.get("/auth/yo").status_code == 401
    assert otra_sesion.get("/auth/yo").status_code == 401

    fresco = _cliente(app)
    vieja = fresco.post(
        "/auth/login", json={"email": "ana@ejemplo.com", "contrasena": CONTRASENA}
    )
    nueva = fresco.post(
        "/auth/login", json={"email": "ana@ejemplo.com", "contrasena": CONTRASENA_NUEVA}
    )
    assert vieja.status_code == 401
    assert nueva.status_code == 200


def test_recuperar_comparte_el_limite_de_intentos_con_login(app) -> None:
    for i in range(5):
        r = _cliente(app, f"10.3.0.{i}").post(
            "/auth/recuperar", json={"email": "ana@ejemplo.com"}
        )
        assert r.status_code == 204

    r = _cliente(app, "10.3.1.1").post("/auth/recuperar", json={"email": "ana@ejemplo.com"})

    assert r.status_code == 429
    assert r.json()["codigo"] == "demasiados_intentos"
