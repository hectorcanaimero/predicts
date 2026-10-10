"""Tests de las rutas de análisis (`api/analisis.py`, ver specs/f4-analisis.md#F4.3.T3):
lanzar (tipos/parámetros válidos e inválidos), listar, estado/resumen/métricas, resultados
paginados y ordenados sobre el Parquet, borrado, y aislamiento por empresa.

Reusa las fixtures `cfg`/`dataset` y los helpers `_analisis`/`_correr`/`_leer` de
`test_analisis_recompra` (mismo patrón que `test_analisis_riesgo_ofertas.py`).
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
import test_analisis_recompra as base
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from predicts.app import crear_app
from predicts.auth.csrf import COOKIE_CSRF
from predicts.db.modelos import Analisis, Trabajo, Usuario
from predicts.db.sesion import get_db

pytestmark = pytest.mark.db

H = 14
cfg, dataset = base.cfg, base.dataset  # fixtures compartidas con los tests de recompra/ciclos
_analisis, _correr, _leer = base._analisis, base._correr, base._leer


def _completo(db, dataset, cfg, **parametros):
    """`_correr` deja `estado == "en_cola"` (no pasa por el trabajo real, ver
    `orquestador.analisis`); las rutas de resultados exigen `listo`."""
    fila, _ = _correr(db, dataset, cfg, **parametros)
    fila.estado = "listo"
    db.commit()
    return fila


@pytest.fixture()
def app(db: Session, cfg, monkeypatch):
    monkeypatch.setattr("predicts.auth.sesiones.settings", lambda: cfg)
    monkeypatch.setattr("predicts.api.analisis.settings", lambda: cfg)
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


def _csrf(cliente: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": cliente.cookies[COOKIE_CSRF]}


@pytest.fixture()
def ana(app, db, dataset) -> TestClient:
    """Cliente autenticado cuya empresa es la del `dataset` (reasignado desde la de la fixture)."""
    cliente = _cliente(app, "Tienda Ana", "ana@ejemplo.com")
    dataset.empresa_id = db.scalar(
        select(Usuario.empresa_id).where(Usuario.email == "ana@ejemplo.com")
    )
    db.commit()
    return cliente


@pytest.fixture()
def beto(app) -> TestClient:
    return _cliente(app, "Tienda Beto", "beto@ejemplo.com")


# --- POST /datasets/{id}/analisis ------------------------------------------------------------


def test_lanzar_analisis_crea_trabajo(db, dataset, ana) -> None:
    r = ana.post(
        f"/datasets/{dataset.id}/analisis",
        json={"tipos": ["recompra", "ciclos"], "parametros": {"umbral": 0.4}},
        headers=_csrf(ana),
    )
    assert r.status_code == 202
    cuerpo = r.json()
    assert cuerpo["estado"] == "en_cola" and cuerpo["tipos"] == ["recompra", "ciclos"]

    analisis = db.get(Analisis, cuerpo["id"])
    assert analisis.parametros == {"umbral": 0.4}
    trabajo = db.get(Trabajo, cuerpo["trabajo_id"])
    assert trabajo.tipo == "analisis" and trabajo.estado == "en_cola"
    assert trabajo.parametros == {"analisis_id": cuerpo["id"]}


def test_lanzar_analisis_tipos_invalidos(dataset, ana) -> None:
    r = ana.post(
        f"/datasets/{dataset.id}/analisis", json={"tipos": ["magia"]}, headers=_csrf(ana)
    )
    assert r.status_code == 422 and r.json()["codigo"] == "tipos_invalidos"

    r = ana.post(f"/datasets/{dataset.id}/analisis", json={"tipos": []}, headers=_csrf(ana))
    assert r.status_code == 422 and r.json()["codigo"] == "tipos_invalidos"


def test_lanzar_analisis_parametros_invalidos(dataset, ana) -> None:
    r = ana.post(
        f"/datasets/{dataset.id}/analisis",
        json={"tipos": ["recompra"], "parametros": {"umbral": 2}},
        headers=_csrf(ana),
    )
    assert r.status_code == 422 and r.json()["codigo"] == "parametros_invalidos"


def test_lanzar_analisis_dataset_no_listo(db, dataset, ana) -> None:
    dataset.estado = "mapeado"
    db.commit()
    r = ana.post(
        f"/datasets/{dataset.id}/analisis", json={"tipos": ["recompra"]}, headers=_csrf(ana)
    )
    assert r.status_code == 409 and r.json()["codigo"] == "dataset_no_listo"


# --- GET /datasets/{id}/analisis y GET /analisis/{id} ----------------------------------------


def test_listar_y_obtener_analisis(db, dataset, cfg, ana) -> None:
    listo = _completo(db, dataset, cfg, tipos=["ciclos"])
    r = ana.post(
        f"/datasets/{dataset.id}/analisis", json={"tipos": ["recompra"]}, headers=_csrf(ana)
    )
    assert r.status_code == 202
    en_cola_id = r.json()["id"]

    r = ana.get(f"/datasets/{dataset.id}/analisis")
    assert r.status_code == 200
    por_id = {a["id"]: a for a in r.json()}
    assert set(por_id) == {str(listo.id), en_cola_id}
    assert por_id[str(listo.id)]["estado"] == "listo"
    assert por_id[en_cola_id]["estado"] == "en_cola"

    r = ana.get(f"/analisis/{listo.id}")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["estado"] == "listo"
    assert cuerpo["resumen"]["ciclos"]["productos"] > 0
    assert cuerpo["version_modelo"] == listo.version_modelo


def test_obtener_analisis_no_encontrado(ana) -> None:
    import uuid

    assert ana.get(f"/analisis/{uuid.uuid4()}").status_code == 404


# --- GET /analisis/{id}/resultados: paginación, orden, tipos inválidos -----------------------


def test_resultados_paginacion_cubre_todo_sin_duplicar(db, dataset, cfg, ana) -> None:
    fila = _completo(db, dataset, cfg, tipos=["recompra"], umbral=0.0, horizonte=H)
    totales = _leer(fila, "recompra.parquet")
    assert len(totales) > 10  # el sintético da de sobra para paginar en páginas chicas

    vistos: list[tuple[str, str]] = []
    pagina = 1
    while True:
        r = ana.get(
            f"/analisis/{fila.id}/resultados",
            params={"tipo": "recompra", "pagina": pagina, "tam_pagina": 7},
        )
        assert r.status_code == 200
        cuerpo = r.json()
        assert cuerpo["total"] == len(totales)
        if not cuerpo["resultados"]:
            break
        vistos += [(f["cliente_id"], f["producto_id"]) for f in cuerpo["resultados"]]
        pagina += 1

    assert len(vistos) == len(totales) == len(set(vistos))


def test_resultados_orden_asc_desc_y_defecto(db, dataset, cfg, ana) -> None:
    fila = _completo(db, dataset, cfg, tipos=["recompra"], umbral=0.0, horizonte=H)

    def _p(orden: str | None) -> list[float]:
        params = {"tipo": "recompra", "tam_pagina": 500}
        if orden is not None:
            params["orden"] = orden
        r = ana.get(f"/analisis/{fila.id}/resultados", params=params)
        assert r.status_code == 200
        return [f["p"] for f in r.json()["resultados"]]

    ascendente, descendente, defecto = _p("p"), _p("-p"), _p(None)
    assert ascendente == sorted(ascendente)
    assert descendente == sorted(descendente, reverse=True)
    assert defecto == descendente  # "-p" es el orden por defecto de recompra


def test_resultados_orden_invalido(db, dataset, cfg, ana) -> None:
    fila = _completo(db, dataset, cfg, tipos=["recompra"], umbral=0.0)
    r = ana.get(
        f"/analisis/{fila.id}/resultados", params={"tipo": "recompra", "orden": "columna_rara"}
    )
    assert r.status_code == 422 and r.json()["codigo"] == "orden_invalido"


def test_resultados_tipo_invalido(db, dataset, cfg, ana) -> None:
    fila = _completo(db, dataset, cfg, tipos=["recompra"], umbral=0.0)
    for tipo in ("magia", "contactar"):
        r = ana.get(f"/analisis/{fila.id}/resultados", params={"tipo": tipo})
        assert r.status_code == 422 and r.json()["codigo"] == "tipo_invalido"


def test_resultados_tipo_no_solicitado(db, dataset, cfg, ana) -> None:
    fila = _completo(db, dataset, cfg, tipos=["ciclos"])
    r = ana.get(f"/analisis/{fila.id}/resultados", params={"tipo": "recompra"})
    assert r.status_code == 404 and r.json()["codigo"] == "tipo_no_solicitado"


def test_resultados_analisis_no_listo(db, dataset, ana) -> None:
    fila = _analisis(db, dataset, ["recompra"])
    db.commit()
    r = ana.get(f"/analisis/{fila.id}/resultados", params={"tipo": "recompra"})
    assert r.status_code == 409 and r.json()["codigo"] == "analisis_no_listo"


# --- DELETE /analisis/{id} --------------------------------------------------------------------


def test_borrar_analisis(db, dataset, cfg, ana) -> None:
    fila, _ = _correr(db, dataset, cfg, tipos=["ciclos"])
    db.commit()
    r = ana.delete(f"/analisis/{fila.id}", headers=_csrf(ana))
    assert r.status_code == 204
    assert ana.get(f"/analisis/{fila.id}").status_code == 404


def test_borrar_analisis_corriendo_no_se_puede(db, dataset, ana) -> None:
    fila = _analisis(db, dataset, ["recompra"])
    fila.estado = "corriendo"
    db.commit()
    r = ana.delete(f"/analisis/{fila.id}", headers=_csrf(ana))
    assert r.status_code == 409 and r.json()["codigo"] == "analisis_corriendo"


# --- aislamiento por empresa -------------------------------------------------------------------


def test_aislamiento_por_empresa(db, dataset, cfg, ana, beto) -> None:
    fila, _ = _correr(db, dataset, cfg, tipos=["ciclos"])
    db.commit()

    assert beto.get(f"/analisis/{fila.id}").status_code == 404
    assert beto.get(f"/datasets/{dataset.id}/analisis").status_code == 404
    assert (
        beto.get(f"/analisis/{fila.id}/resultados", params={"tipo": "ciclos"}).status_code == 404
    )
    assert beto.delete(f"/analisis/{fila.id}", headers=_csrf(beto)).status_code == 404
    r = beto.post(
        f"/datasets/{dataset.id}/analisis", json={"tipos": ["ciclos"]}, headers=_csrf(beto)
    )
    assert r.status_code == 404  # dataset de otra empresa
