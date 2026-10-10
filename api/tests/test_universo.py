"""Tests del universo de clientes (`api/universo.py`, `analisis/universo.py`, ver
specs/f8-3d-demo-despliegue.md#F8.2.T1): tamaño de la muestra, estratificación por estado,
grupos de k-means, historial de un cliente y aislamiento por empresa.

Reusa las fixtures `cfg`/`dataset` y el helper `_analisis` de `test_analisis_recompra`, y el
patrón de app/cliente de `test_analisis_api.py`.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Generator
from datetime import timedelta

import duckdb
import pytest
import test_analisis_recompra as base
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from predicts.analisis import universo
from predicts.app import crear_app
from predicts.db.modelos import Usuario
from predicts.db.sesion import get_db

pytestmark = pytest.mark.db

cfg, dataset = base.cfg, base.dataset  # fixtures compartidas con los tests de recompra
_analisis = base._analisis
RUTA = str(base.COMPRAS)
N_CLIENTES = 35  # total de clientes del sintético (ver test_analisis_recompra.COMPRAS)


@pytest.fixture()
def app(db: Session, cfg, monkeypatch):
    monkeypatch.setattr("predicts.auth.sesiones.settings", lambda: cfg)
    monkeypatch.setattr("predicts.api.universo.settings", lambda: cfg)
    app = crear_app()

    def _get_db() -> Generator[Session]:
        s = Session(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _get_db
    return app


def _cliente(app, empresa: str, email: str) -> TestClient:
    cliente = TestClient(app)
    r = cliente.post(
        "/auth/registro",
        json={"email": email, "contrasena": "una-contrasena-larga", "nombre_empresa": empresa},
    )
    assert r.status_code == 201
    return cliente


@pytest.fixture()
def ana(app, db, dataset) -> TestClient:
    cliente = _cliente(app, "Tienda Ana", "ana@ejemplo.com")
    dataset.empresa_id = db.scalar(
        select(Usuario.empresa_id).where(Usuario.email == "ana@ejemplo.com")
    )
    db.commit()
    return cliente


@pytest.fixture()
def beto(app) -> TestClient:
    return _cliente(app, "Tienda Beto", "beto@ejemplo.com")


@pytest.fixture()
def fila(db, dataset, ana):
    """`ana` debe resolverse antes: reasigna `dataset.empresa_id` a la empresa de Ana."""
    f = _analisis(db, dataset, ["ciclos"])
    db.commit()
    return f


# --- analisis.universo (puro, sin API) --------------------------------------------------------


def _con() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(":memory:")


def test_universo_puro_estados_y_grupos() -> None:
    con = _con()
    filas = universo.calcular_universo(con, RUTA, max_muestra=10_000)
    assert len(filas) == N_CLIENTES
    assert {f["cliente_id"] for f in filas} == {f["cliente_id"] for f in filas}  # sin duplicados
    assert len({f["cliente_id"] for f in filas}) == N_CLIENTES
    estados = Counter(f["estado"] for f in filas)
    assert set(estados) <= {"activo", "en_recompra", "en_riesgo"}
    assert estados["en_riesgo"] > 0 and estados["activo"] > 0  # el sintético tiene de los dos

    grupos = {f["grupo"] for f in filas}
    assert grupos <= set(range(universo.K_DEFECTO))
    assert len(grupos) > 1  # con 35 clientes variados, k=4 no colapsa todo a un grupo


def test_universo_puro_k_configurable() -> None:
    con = _con()
    solo_uno = universo.calcular_universo(con, RUTA, k=1, max_muestra=10_000)
    assert {f["grupo"] for f in solo_uno} == {0}


def test_universo_puro_muestra_cubre_todo_si_no_hace_falta_recortar() -> None:
    con = _con()
    filas = universo.calcular_universo(con, RUTA, max_muestra=1_000_000)
    assert len(filas) == N_CLIENTES


def test_universo_puro_tamano_de_muestra_y_estratificacion() -> None:
    con = _con()
    todos = universo.calcular_universo(con, RUTA, max_muestra=10_000)
    completo = Counter(f["estado"] for f in todos)

    muestra = universo.calcular_universo(con, RUTA, max_muestra=20)
    assert len(muestra) == 20
    por_estado = Counter(f["estado"] for f in muestra)
    # estratificado, no al azar simple: el estado minoritario (2 de 35) sigue representado.
    assert por_estado["en_riesgo"] >= 1
    for estado, total in completo.items():
        proporcion_esperada = round(20 * total / N_CLIENTES)
        assert abs(por_estado[estado] - proporcion_esperada) <= 1


def test_historial_cliente_productos_ciclo_y_proxima_compra() -> None:
    con = _con()
    [primero] = universo.calcular_universo(con, RUTA, max_muestra=1)
    historial = universo.historial_cliente(con, RUTA, primero["cliente_id"])
    assert historial["cliente_id"] == primero["cliente_id"]
    assert historial["productos"]
    for p in historial["productos"]:
        assert p["n_compras"] > 0
        if p["ciclo"] is not None:
            assert p["proxima_compra"] == p["ultima_compra"] + timedelta(days=round(p["ciclo"]))
        else:
            assert p["proxima_compra"] is None


def test_historial_cliente_inexistente_queda_vacio() -> None:
    con = _con()
    historial = universo.historial_cliente(con, RUTA, "cliente-que-no-existe")
    assert historial["productos"] == []


# --- API ----------------------------------------------------------------------------------------


def test_api_universo_tamano_de_muestra(fila, ana) -> None:
    r = ana.get(f"/analisis/{fila.id}/universo", params={"max": 10})
    assert r.status_code == 200
    cuerpo = r.json()
    assert len(cuerpo) == 10
    assert len({c["cliente_id"] for c in cuerpo}) == 10


def test_api_universo_sin_max_devuelve_todos(fila, ana) -> None:
    r = ana.get(f"/analisis/{fila.id}/universo")
    assert r.status_code == 200
    assert len(r.json()) == N_CLIENTES


def test_api_universo_estratificacion_por_estado(fila, ana) -> None:
    r = ana.get(f"/analisis/{fila.id}/universo", params={"max": 20})
    assert r.status_code == 200
    estados = Counter(c["estado"] for c in r.json())
    assert estados["en_riesgo"] >= 1
    assert set(estados) <= {"activo", "en_recompra", "en_riesgo"}


def test_api_universo_grupos(fila, ana) -> None:
    r = ana.get(f"/analisis/{fila.id}/universo", params={"k": 1})
    assert r.status_code == 200
    assert {c["grupo"] for c in r.json()} == {0}

    r = ana.get(f"/analisis/{fila.id}/universo", params={"k": 4})
    assert r.status_code == 200
    assert {c["grupo"] for c in r.json()} <= {0, 1, 2, 3}


def test_api_historial_cliente(fila, ana) -> None:
    cliente_id = ana.get(f"/analisis/{fila.id}/universo", params={"max": 1}).json()[0]["cliente_id"]
    r = ana.get(f"/analisis/{fila.id}/universo/{cliente_id}")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["cliente_id"] == cliente_id
    assert cuerpo["productos"]


def test_api_historial_cliente_no_encontrado(fila, ana) -> None:
    r = ana.get(f"/analisis/{fila.id}/universo/cliente-que-no-existe")
    assert r.status_code == 404 and r.json()["codigo"] == "no_encontrado"


def test_api_universo_aislamiento_por_empresa(fila, ana, beto) -> None:
    cliente_id = ana.get(f"/analisis/{fila.id}/universo", params={"max": 1}).json()[0]["cliente_id"]
    assert beto.get(f"/analisis/{fila.id}/universo").status_code == 404
    assert beto.get(f"/analisis/{fila.id}/universo/{cliente_id}").status_code == 404
