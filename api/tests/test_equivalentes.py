"""Tests de `predicts.productos.equivalentes` y `api/productos_grupos.py`: propuestas por
similitud de embeddings, el umbral, la condición de marca/categoría, confirmar/rechazar/separar
y el aislamiento por empresa (ver specs/f4-analisis.md#F4.2.T2)."""

from __future__ import annotations

import math
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from predicts.app import crear_app
from predicts.auth.csrf import COOKIE_CSRF
from predicts.config import settings_para_tests
from predicts.db.modelos import Empresa, GrupoProducto, Producto, Usuario
from predicts.db.sesion import get_db
from predicts.productos.equivalentes import (
    UMBRAL_EQUIVALENTES,
    generar_embeddings,
    generar_propuestas,
)

pytestmark = pytest.mark.db

CONTRASENA = "una-contrasena-larga"
_DIM = 1536

# Ángulos elegidos para que `cos(angulo)` quede claramente por encima/debajo de
# UMBRAL_EQUIVALENTES (0.85), para tener casos deterministas sin llamar a ningún embeddings real.
_ANGULO_SIMILAR = 20.0
_ANGULO_DISTINTO = 40.0
assert math.cos(math.radians(_ANGULO_SIMILAR)) >= UMBRAL_EQUIVALENTES
assert math.cos(math.radians(_ANGULO_DISTINTO)) < UMBRAL_EQUIVALENTES


def _vector(angulo_grados: float) -> list[float]:
    """Vector unitario con solo las dos primeras dimensiones distintas de cero: la similitud
    coseno contra `_vector(0)` es exactamente `cos(angulo_grados)`."""
    radianes = math.radians(angulo_grados)
    vector = [0.0] * _DIM
    vector[0] = math.cos(radianes)
    vector[1] = math.sin(radianes)
    return vector


@pytest.fixture()
def empresa(db: Session) -> Empresa:
    empresa = Empresa(nombre="Tienda")
    db.add(empresa)
    db.flush()
    return empresa


def _producto(
    db: Session,
    empresa_id,
    nombre: str,
    *,
    categoria: str | None = None,
    marca: str | None = None,
    embedding: list[float] | None = None,
) -> Producto:
    producto = Producto(
        empresa_id=empresa_id,
        nombre_normalizado=nombre.lower(),
        nombre=nombre,
        categoria=categoria,
        categoria_origen="csv" if categoria is not None else None,
        estadisticas={"marca": marca} if marca is not None else None,
        embedding=embedding,
    )
    db.add(producto)
    db.flush()
    return producto


# --- generar_embeddings: solo productos sin embedding ------------------------------------------


def test_generar_embeddings_solo_productos_sin_embedding(db, empresa) -> None:
    con_embedding = _producto(db, empresa.id, "Leche", embedding=_vector(0))
    sin_embedding = _producto(db, empresa.id, "Queso")

    llamadas: list[list[str]] = []

    def calcular_falso(textos):
        llamadas.append(list(textos))
        return [_vector(0) for _ in textos]

    tocados = generar_embeddings(db, empresa.id, calcular=calcular_falso)
    db.commit()

    assert [p.id for p in tocados] == [sin_embedding.id]
    assert llamadas == [["queso"]]
    assert sin_embedding.embedding is not None
    assert list(con_embedding.embedding) == pytest.approx(_vector(0))


def test_generar_embeddings_sin_pendientes_no_llama_a_calcular(db, empresa) -> None:
    _producto(db, empresa.id, "Leche", embedding=_vector(0))
    llamadas: list[list[str]] = []

    tocados = generar_embeddings(db, empresa.id, calcular=lambda textos: llamadas.append(textos))

    assert tocados == []
    assert llamadas == []


# --- generar_propuestas: similitud, umbral y condición de marca/categoría ----------------------


def test_propone_grupo_cuando_similitud_supera_umbral_y_categoria_coincide(db, empresa) -> None:
    a = _producto(db, empresa.id, "Leche Entera 1L", categoria="lacteos", embedding=_vector(0))
    b = _producto(
        db, empresa.id, "Leche Entera 1 Litro", categoria="lacteos",
        embedding=_vector(_ANGULO_SIMILAR),
    )

    grupos = generar_propuestas(db, empresa.id)
    db.commit()

    assert len(grupos) == 1
    assert grupos[0].estado == "propuesto"
    assert grupos[0].similitud == pytest.approx(math.cos(math.radians(_ANGULO_SIMILAR)), abs=1e-4)
    assert a.grupo_id == b.grupo_id == grupos[0].id


def test_no_propone_grupo_por_debajo_del_umbral(db, empresa) -> None:
    a = _producto(db, empresa.id, "Leche", categoria="lacteos", embedding=_vector(0))
    b = _producto(
        db, empresa.id, "Jugo", categoria="lacteos", embedding=_vector(_ANGULO_DISTINTO)
    )

    grupos = generar_propuestas(db, empresa.id)

    assert grupos == []
    assert a.grupo_id is None
    assert b.grupo_id is None


def test_similitud_alta_pero_categoria_distinta_no_agrupa(db, empresa) -> None:
    a = _producto(db, empresa.id, "Leche", categoria="lacteos", embedding=_vector(0))
    b = _producto(
        db, empresa.id, "Leche (otra)", categoria="limpieza", embedding=_vector(_ANGULO_SIMILAR)
    )

    grupos = generar_propuestas(db, empresa.id)

    assert grupos == []
    assert a.grupo_id is None
    assert b.grupo_id is None


def test_marca_coincide_agrupa_aunque_categoria_difiera(db, empresa) -> None:
    a = _producto(db, empresa.id, "Leche", categoria="lacteos", marca="acme", embedding=_vector(0))
    b = _producto(
        db, empresa.id, "Leche (otra)", categoria="limpieza", marca="acme",
        embedding=_vector(_ANGULO_SIMILAR),
    )

    grupos = generar_propuestas(db, empresa.id)

    assert len(grupos) == 1
    assert a.grupo_id == b.grupo_id == grupos[0].id


def test_categoria_igual_agrupa_aunque_marca_difiera(db, empresa) -> None:
    # "coincide marca O categoria": basta con que una de las dos coincida.
    a = _producto(db, empresa.id, "Leche", categoria="lacteos", marca="acme", embedding=_vector(0))
    b = _producto(
        db, empresa.id, "Leche (otra)", categoria="lacteos", marca="otra-marca",
        embedding=_vector(_ANGULO_SIMILAR),
    )

    grupos = generar_propuestas(db, empresa.id)

    assert len(grupos) == 1
    assert a.grupo_id == b.grupo_id == grupos[0].id


def test_marca_y_categoria_distintas_no_agrupa(db, empresa) -> None:
    a = _producto(db, empresa.id, "Leche", categoria="lacteos", marca="acme", embedding=_vector(0))
    b = _producto(
        db, empresa.id, "Leche (otra)", categoria="limpieza", marca="otra-marca",
        embedding=_vector(_ANGULO_SIMILAR),
    )

    grupos = generar_propuestas(db, empresa.id)

    assert grupos == []
    assert a.grupo_id is None
    assert b.grupo_id is None


def test_sin_marca_ni_categoria_usa_solo_similitud(db, empresa) -> None:
    a = _producto(db, empresa.id, "Leche", embedding=_vector(0))
    b = _producto(db, empresa.id, "Leche (otra)", embedding=_vector(_ANGULO_SIMILAR))

    grupos = generar_propuestas(db, empresa.id)

    assert len(grupos) == 1
    assert a.grupo_id == b.grupo_id == grupos[0].id


def test_producto_ya_agrupado_no_se_vuelve_a_proponer(db, empresa) -> None:
    _producto(db, empresa.id, "Leche", categoria="lacteos", embedding=_vector(0))
    _producto(
        db, empresa.id, "Leche (otra)", categoria="lacteos", embedding=_vector(_ANGULO_SIMILAR)
    )
    generar_propuestas(db, empresa.id)
    db.commit()

    c = _producto(
        db, empresa.id, "Leche (tercera)", categoria="lacteos", embedding=_vector(_ANGULO_SIMILAR)
    )
    grupos = generar_propuestas(db, empresa.id)

    assert grupos == [], "a y b ya están en un grupo propuesto: no se tocan de nuevo"
    assert c.grupo_id is None


# --- aislamiento por empresa --------------------------------------------------------------------


def test_no_propone_grupos_entre_empresas(db) -> None:
    empresa_a = Empresa(nombre="A")
    empresa_b = Empresa(nombre="B")
    db.add_all([empresa_a, empresa_b])
    db.flush()

    a = _producto(db, empresa_a.id, "Leche", categoria="lacteos", embedding=_vector(0))
    b = _producto(
        db, empresa_b.id, "Leche", categoria="lacteos", embedding=_vector(_ANGULO_SIMILAR)
    )

    grupos_a = generar_propuestas(db, empresa_a.id)
    grupos_b = generar_propuestas(db, empresa_b.id)

    assert grupos_a == []
    assert grupos_b == []
    assert a.grupo_id is None
    assert b.grupo_id is None


# --- API: listar, confirmar, rechazar, separar y aislamiento -------------------------------------


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


def _empresa_cliente(app, nombre_empresa: str, email: str) -> TestClient:
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
    return _empresa_cliente(app, "Tienda Ana", "ana@ejemplo.com")


@pytest.fixture()
def beto(app) -> TestClient:
    return _empresa_cliente(app, "Tienda Beto", "beto@ejemplo.com")


def _empresa_id(db: Session, email: str):
    return db.scalar(select(Usuario.empresa_id).where(Usuario.email == email))


def _grupo_propuesto(db: Session, empresa_id, *miembros: Producto) -> GrupoProducto:
    grupo = GrupoProducto(
        empresa_id=empresa_id, nombre=miembros[0].nombre, estado="propuesto", similitud=0.9
    )
    db.add(grupo)
    db.flush()
    for producto in miembros:
        producto.grupo_id = grupo.id
    db.commit()
    return grupo


def test_listar_grupos_filtra_por_estado(db, ana) -> None:
    empresa_id = _empresa_id(db, "ana@ejemplo.com")
    a = _producto(db, empresa_id, "Leche", embedding=_vector(0))
    b = _producto(db, empresa_id, "Leche (otra)", embedding=_vector(_ANGULO_SIMILAR))
    grupo = _grupo_propuesto(db, empresa_id, a, b)

    r = ana.get("/productos/grupos")
    assert r.status_code == 200
    cuerpo = r.json()
    assert len(cuerpo) == 1
    assert cuerpo[0]["id"] == str(grupo.id)
    assert cuerpo[0]["estado"] == "propuesto"
    assert sorted(p["nombre"] for p in cuerpo[0]["productos"]) == ["Leche", "Leche (otra)"]

    assert ana.get("/productos/grupos?estado=confirmado").json() == []


def test_confirmar_grupo(db, ana) -> None:
    empresa_id = _empresa_id(db, "ana@ejemplo.com")
    a = _producto(db, empresa_id, "Leche", embedding=_vector(0))
    b = _producto(db, empresa_id, "Leche (otra)", embedding=_vector(_ANGULO_SIMILAR))
    grupo = _grupo_propuesto(db, empresa_id, a, b)

    r = ana.post(f"/productos/grupos/{grupo.id}/confirmar", headers=_csrf(ana))
    assert r.status_code == 200
    assert r.json()["estado"] == "confirmado"

    db.expire_all()
    assert db.get(GrupoProducto, grupo.id).estado == "confirmado"
    assert db.get(Producto, a.id).grupo_id == grupo.id


def test_rechazar_grupo_libera_los_productos(db, ana) -> None:
    empresa_id = _empresa_id(db, "ana@ejemplo.com")
    a = _producto(db, empresa_id, "Leche", embedding=_vector(0))
    b = _producto(db, empresa_id, "Leche (otra)", embedding=_vector(_ANGULO_SIMILAR))
    grupo = _grupo_propuesto(db, empresa_id, a, b)

    r = ana.post(f"/productos/grupos/{grupo.id}/rechazar", headers=_csrf(ana))
    assert r.status_code == 200
    assert r.json()["estado"] == "rechazado"

    db.expire_all()
    assert db.get(GrupoProducto, grupo.id).estado == "rechazado"
    assert db.get(Producto, a.id).grupo_id is None
    assert db.get(Producto, b.id).grupo_id is None


def test_separar_producto_de_su_grupo(db, ana) -> None:
    empresa_id = _empresa_id(db, "ana@ejemplo.com")
    a = _producto(db, empresa_id, "Leche", embedding=_vector(0))
    b = _producto(db, empresa_id, "Leche (otra)", embedding=_vector(_ANGULO_SIMILAR))
    grupo = _grupo_propuesto(db, empresa_id, a, b)

    r = ana.post(f"/productos/{a.id}/separar", headers=_csrf(ana))
    assert r.status_code == 200

    db.expire_all()
    assert db.get(Producto, a.id).grupo_id is None
    assert db.get(Producto, b.id).grupo_id == grupo.id, "separar solo saca al producto indicado"


def test_separar_producto_sin_grupo_falla(db, ana) -> None:
    empresa_id = _empresa_id(db, "ana@ejemplo.com")
    a = _producto(db, empresa_id, "Leche", embedding=_vector(0))
    db.commit()

    r = ana.post(f"/productos/{a.id}/separar", headers=_csrf(ana))
    assert r.status_code == 422
    assert r.json()["codigo"] == "producto_sin_grupo"


def test_otra_empresa_no_ve_ni_actua_sobre_el_grupo(db, ana, beto) -> None:
    empresa_id = _empresa_id(db, "ana@ejemplo.com")
    a = _producto(db, empresa_id, "Leche", embedding=_vector(0))
    b = _producto(db, empresa_id, "Leche (otra)", embedding=_vector(_ANGULO_SIMILAR))
    grupo = _grupo_propuesto(db, empresa_id, a, b)

    assert beto.get("/productos/grupos").json() == []
    r = beto.post(f"/productos/grupos/{grupo.id}/confirmar", headers=_csrf(beto))
    assert r.status_code == 404
    r = beto.post(f"/productos/grupos/{grupo.id}/rechazar", headers=_csrf(beto))
    assert r.status_code == 404
    r = beto.post(f"/productos/{a.id}/separar", headers=_csrf(beto))
    assert r.status_code == 404

    db.expire_all()
    assert db.get(GrupoProducto, grupo.id).estado == "propuesto"
