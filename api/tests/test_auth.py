"""Tests de `/auth`: registro, login, sesiones, CSRF, límite de intentos e idioma."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from predicts.app import crear_app
from predicts.auth import seguridad
from predicts.auth.csrf import COOKIE_CSRF
from predicts.auth.sesiones import COOKIE_SESION, hash_token
from predicts.config import settings_para_tests
from predicts.db.modelos import Empresa, Sesion, Usuario
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


def _cliente(app, ip: str = "10.0.0.1") -> TestClient:
    return TestClient(app, client=(ip, 50000))


@pytest.fixture()
def cliente(app) -> TestClient:
    return _cliente(app)


def _registrar(cliente: TestClient, email: str = "Ana@Ejemplo.com", **extra):
    datos = {"email": email, "contrasena": CONTRASENA, "nombre_empresa": "Tienda Ana", **extra}
    return cliente.post("/auth/registro", json=datos)


def _csrf(cliente: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": cliente.cookies[COOKIE_CSRF]}


def test_registro_crea_empresa_y_dueno_con_email_normalizado(cliente, db) -> None:
    r = _registrar(cliente, idioma="es")

    assert r.status_code == 201
    cuerpo = r.json()
    assert cuerpo["usuario"]["email"] == "ana@ejemplo.com"
    assert cuerpo["usuario"]["rol"] == "dueno"
    assert cuerpo["empresa"]["nombre"] == "Tienda Ana"
    assert cuerpo["idioma"] == "es"
    usuario = db.scalar(select(Usuario))
    assert usuario.hash_contrasena.startswith("$argon2id$")
    assert str(usuario.empresa_id) == cuerpo["empresa"]["id"]
    # queda con sesión iniciada
    assert cliente.get("/auth/yo").json()["usuario"]["email"] == "ana@ejemplo.com"


def test_cookie_de_sesion_httponly_lax_y_csrf_legible(cliente) -> None:
    r = _registrar(cliente)
    cookies = r.headers.get_list("set-cookie")
    sesion = next(c for c in cookies if c.startswith(f"{COOKIE_SESION}="))
    csrf = next(c for c in cookies if c.startswith(f"{COOKIE_CSRF}="))
    assert "HttpOnly" in sesion and "samesite=lax" in sesion.lower()
    assert "HttpOnly" not in csrf


def test_email_duplicado_no_crea_otra_empresa(cliente, db) -> None:
    assert _registrar(cliente).status_code == 201

    r = _registrar(cliente, email="ANA@ejemplo.com ")

    assert r.status_code == 409
    assert r.json()["codigo"] == "email_en_uso"
    assert len(db.scalars(select(Empresa)).all()) == 1


@pytest.mark.parametrize(
    ("contrasena", "motivo"), [("corta", "corta"), ("ana@ejemplo.com", "igual_al_email")]
)
def test_registro_rechaza_contrasena_debil(cliente, contrasena, motivo) -> None:
    r = cliente.post(
        "/auth/registro",
        json={"email": "ana@ejemplo.com", "contrasena": contrasena, "nombre_empresa": "X"},
    )
    assert r.status_code == 422
    assert r.json() == {"codigo": "contrasena_invalida", "parametros": r.json()["parametros"]}
    assert r.json()["parametros"]["motivo"] == motivo


def test_login_correcto(app, cliente) -> None:
    _registrar(cliente)
    otro = _cliente(app)

    r = otro.post("/auth/login", json={"email": " ANA@ejemplo.com", "contrasena": CONTRASENA})

    assert r.status_code == 200
    assert r.json()["usuario"]["email"] == "ana@ejemplo.com"
    assert otro.get("/auth/yo").status_code == 200


def test_login_fallido_mismo_error_para_email_inexistente_y_contrasena_mala(cliente) -> None:
    _registrar(cliente)
    cliente.cookies.clear()

    mala = cliente.post("/auth/login", json={"email": "ana@ejemplo.com", "contrasena": "x" * 12})
    nadie = cliente.post("/auth/login", json={"email": "no@ejemplo.com", "contrasena": "x" * 12})

    assert mala.status_code == nadie.status_code == 401
    assert mala.json() == nadie.json() == {"codigo": "credenciales_invalidas", "parametros": {}}
    assert COOKIE_SESION not in cliente.cookies


def test_login_rehashea_si_cambian_los_parametros(cliente, db, monkeypatch) -> None:
    _registrar(cliente)
    viejo = db.scalar(select(Usuario.hash_contrasena))
    monkeypatch.setattr(seguridad, "necesita_rehash", lambda h: True)

    cliente.post("/auth/login", json={"email": "ana@ejemplo.com", "contrasena": CONTRASENA})

    db.expire_all()
    nuevo = db.scalar(select(Usuario.hash_contrasena))
    assert nuevo != viejo and seguridad.verificar(nuevo, CONTRASENA)


def test_sin_sesion_responde_401(cliente) -> None:
    r = cliente.get("/auth/yo")
    assert r.status_code == 401
    assert r.json()["codigo"] == "no_autenticado"


def test_sesion_expirada_responde_401_y_borra_la_fila(cliente, db) -> None:
    _registrar(cliente)
    db.execute(update(Sesion).values(expira_en=datetime.now(UTC) - timedelta(seconds=1)))
    db.commit()

    r = cliente.get("/auth/yo")

    assert r.status_code == 401
    assert db.scalars(select(Sesion)).all() == []


def test_expiracion_deslizante(cliente, db) -> None:
    _registrar(cliente)
    casi_vencida = datetime.now(UTC) + timedelta(days=2)
    db.execute(update(Sesion).values(expira_en=casi_vencida))
    db.commit()

    r = cliente.get("/auth/yo")

    assert r.status_code == 200
    assert COOKIE_SESION in r.cookies
    db.expire_all()
    assert db.scalar(select(Sesion.expira_en)) > datetime.now(UTC) + timedelta(days=29)


def test_logout_borra_la_sesion(cliente, db) -> None:
    _registrar(cliente)
    token = cliente.cookies[COOKIE_SESION]

    r = cliente.post("/auth/logout", headers=_csrf(cliente))

    assert r.status_code == 204
    assert db.scalars(select(Sesion)).all() == []
    cliente.cookies.set(COOKIE_SESION, token)  # reusar el token viejo no sirve
    assert cliente.get("/auth/yo").status_code == 401


@pytest.mark.parametrize("header", [None, "", "token-falso"])
def test_csrf_faltante_o_invalido_responde_403(cliente, header) -> None:
    _registrar(cliente)
    headers = {} if header is None else {"X-CSRF-Token": header}

    r = cliente.patch("/auth/yo", json={"idioma": "en"}, headers=headers)

    assert r.status_code == 403
    assert r.json()["codigo"] == "csrf_invalido"


def test_csrf_de_otra_sesion_no_sirve(app, cliente) -> None:
    _registrar(cliente)
    otro = _cliente(app)
    _registrar(otro, email="beto@ejemplo.com")

    r = cliente.post("/auth/logout", headers=_csrf(otro))

    assert r.status_code == 403


def test_cambio_de_idioma(cliente) -> None:
    _registrar(cliente)

    r = cliente.patch("/auth/yo", json={"idioma": "en"}, headers=_csrf(cliente))

    assert r.status_code == 200
    assert r.json()["idioma"] == "en"
    assert cliente.get("/auth/yo").json()["idioma"] == "en"
    malo = cliente.patch("/auth/yo", json={"idioma": "fr"}, headers=_csrf(cliente))
    assert malo.status_code == 422


def test_limite_de_intentos_por_email(app, cliente) -> None:
    _registrar(cliente)
    for i in range(5):
        r = _cliente(app, f"10.0.1.{i}").post(
            "/auth/login", json={"email": "ana@ejemplo.com", "contrasena": "mala-mala-mala"}
        )
        assert r.status_code == 401

    # bloqueado aun con la contraseña correcta y desde otra IP
    r = _cliente(app, "10.0.2.1").post(
        "/auth/login", json={"email": "ana@ejemplo.com", "contrasena": CONTRASENA}
    )

    assert r.status_code == 429
    assert r.json()["codigo"] == "demasiados_intentos"
    assert 0 < r.json()["parametros"]["reintentar_en_s"] <= 15 * 60


def test_limite_de_intentos_por_ip(app) -> None:
    cliente = _cliente(app, "10.9.9.9")
    for i in range(20):
        r = cliente.post(
            "/auth/login", json={"email": f"u{i}@ejemplo.com", "contrasena": "mala-mala-mala"}
        )
        assert r.status_code == 401

    r = cliente.post("/auth/login", json={"email": "nuevo@ejemplo.com", "contrasena": "x" * 12})
    assert r.status_code == 429
    assert r.json()["parametros"]["reintentar_en_s"] > 0
    # otra IP no está bloqueada
    otra = _cliente(app, "10.9.9.10").post(
        "/auth/login", json={"email": "nuevo@ejemplo.com", "contrasena": "x" * 12}
    )
    assert otra.status_code == 401


def test_el_token_nunca_se_guarda_en_claro(cliente, db) -> None:
    _registrar(cliente)
    token = cliente.cookies[COOKIE_SESION]

    sesion = db.scalar(select(Sesion))

    assert sesion.token_hash == hash_token(token) != token
    columnas = [str(getattr(sesion, c.key)) for c in Sesion.__table__.columns]
    assert all(token not in valor for valor in columnas)
