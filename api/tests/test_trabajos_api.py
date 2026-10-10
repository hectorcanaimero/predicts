"""Tests de punta a punta de `api/trabajos.py`, `trabajos/tipos_datos.py` y
`api/datasets_ingesta.py`: suben el fixture, confirman el mapeo, corren el worker real
(`trabajos.worker.correr`) en un hilo, leen los eventos por SSE con un cliente de prueba
(incluida la reconexión con `Last-Event-ID`) y el informe de calidad; más aislamiento por
empresa y los estados de error de la API.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

import predicts.trabajos.tipos_datos  # noqa: F401 - registra "ingesta"/"calidad" en `registro`
from predicts.app import crear_app
from predicts.auth.csrf import COOKIE_CSRF
from predicts.config import settings_para_tests
from predicts.db.modelos import Trabajo, Usuario
from predicts.db.sesion import get_db
from predicts.trabajos import cola, eventos
from predicts.trabajos.worker import correr

pytestmark = pytest.mark.db

CONTRASENA = "una-contrasena-larga"
MEMORIA_MB = 2048  # duckdb/pyarrow/numpy/scipy ya ocupan varios cientos de MB al importarse
TIMEOUT_S = 30
INTERVALO_WORKER_S = 0.05

FIXTURES = Path(__file__).parent / "fixtures" / "csv"


# --- app / clientes autenticados (mismo patrón que test_subida.py / test_mapeo.py) ---------


@pytest.fixture()
def app(db: Session, monkeypatch, tmp_path):
    monkeypatch.setattr("predicts.auth.sesiones.settings", lambda: settings_para_tests())
    cfg_datos = lambda: settings_para_tests(DATA_DIR=str(tmp_path))  # noqa: E731
    monkeypatch.setattr("predicts.api.datasets.settings", cfg_datos)
    monkeypatch.setattr("predicts.api.datasets_ingesta.settings", cfg_datos)
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


def _empresa_id(db: Session, email: str) -> uuid.UUID:
    return db.scalar(select(Usuario.empresa_id).where(Usuario.email == email))


# --- worker real en un hilo, para el/los test(s) de punta a punta --------------------------


@pytest.fixture()
def worker_en_hilo(db: Session, tmp_path, monkeypatch):
    """Corre `trabajos.worker.correr` real en un hilo de prueba.

    El worker arranca cada trabajo en un subproceso `spawn` (proceso nuevo, no hereda el
    `monkeypatch` de `settings`): por eso acá se fijan variables de entorno de verdad, que
    sí se heredan al hijo, con los mínimos que pide `Settings` (ver `_OVERRIDES_MINIMAS`).
    """
    engine = db.get_bind()
    url_db = engine.url.render_as_string(hide_password=False)
    for nombre, valor in {
        "DATABASE_URL": url_db,
        "DATA_DIR": str(tmp_path),
        "ROUTER_BASE_URL": "https://router.test",
        "ROUTER_API_KEY": "test",
        "ROUTER_MODEL": "test-model",
        "TYPESAFE_API_KEY": "test",
    }.items():
        monkeypatch.setenv(nombre, valor)

    detener = threading.Event()
    hilo = threading.Thread(
        target=correr,
        args=(url_db, MEMORIA_MB, TIMEOUT_S),
        kwargs={"intervalo_s": INTERVALO_WORKER_S, "detener": detener},
        daemon=True,
    )
    hilo.start()
    try:
        yield
    finally:
        detener.set()
        hilo.join(timeout=10)


# --- helpers de dominio ----------------------------------------------------------------------


def _crear_proyecto(cliente: TestClient) -> dict:
    r = cliente.post("/proyectos", json={"nombre": "Campaña"}, headers=_csrf(cliente))
    assert r.status_code == 201
    return r.json()


def _subir(cliente: TestClient, proyecto_id: str) -> str:
    contenido = (FIXTURES / "utf8.csv").read_bytes()
    r = cliente.post(
        f"/proyectos/{proyecto_id}/datasets",
        files={"archivo": ("compras.csv", contenido, "text/csv")},
        headers=_csrf(cliente),
    )
    assert r.status_code == 201
    return r.json()["id"]


def _confirmar_mapeo(cliente: TestClient, dataset_id: str) -> None:
    r = cliente.put(
        f"/datasets/{dataset_id}/mapeo",
        json={
            "columnas": [
                {"columna": "cliente_id", "campo": "cliente_id"},
                {"columna": "fecha", "campo": "fecha"},
                {"columna": "producto_id", "campo": "producto_id"},
                {"columna": "producto_id_tipo", "campo": "ignorar"},
                {"columna": "producto_nombre", "campo": "producto_nombre"},
                {"columna": "cantidad", "campo": "cantidad"},
                {"columna": "precio_unitario", "campo": "precio_unitario"},
            ],
            "producto_id_tipo": "sku",
            "formato_fecha": "aaaa-mm-dd",
        },
        headers=_csrf(cliente),
    )
    assert r.status_code == 200, r.json()
    assert r.json()["estado"] == "mapeado"


def _subir_y_mapear(cliente: TestClient) -> str:
    dataset_id = _subir(cliente, _crear_proyecto(cliente)["id"])
    _confirmar_mapeo(cliente, dataset_id)
    return dataset_id


def _leer_eventos_sse(
    cliente: TestClient, trabajo_id: str, last_event_id: str | None = None
) -> list[dict[str, str]]:
    headers = {"Last-Event-ID": last_event_id} if last_event_id is not None else {}
    vistos: list[dict[str, str]] = []
    actual: dict[str, str] = {}
    with cliente.stream("GET", f"/trabajos/{trabajo_id}/eventos", headers=headers) as resp:
        assert resp.status_code == 200
        for linea in resp.iter_lines():
            if linea == "":
                if actual:
                    vistos.append(actual)
                    actual = {}
                continue
            clave, _, valor = linea.partition(": ")
            actual[clave] = valor
    if actual:
        vistos.append(actual)
    return vistos


# --- de punta a punta: subir, mapear, ingerir, SSE, calidad ---------------------------------


def test_ingesta_calidad_sse_y_cola_de_calidad(ana, db, worker_en_hilo) -> None:
    dataset_id = _subir_y_mapear(ana)

    r = ana.post(f"/datasets/{dataset_id}/ingesta", headers=_csrf(ana))
    assert r.status_code == 202
    cuerpo = r.json()
    assert cuerpo["estado"] == "ingiriendo"
    trabajo_id = cuerpo["trabajo_id"]

    eventos_sse = _leer_eventos_sse(ana, trabajo_id)
    assert [e["event"] for e in eventos_sse] == ["leyendo", "listo"]
    ultimo = json.loads(eventos_sse[-1]["data"])
    assert ultimo["progreso"] == 1.0
    assert ultimo["contadores"]["validas"] == 3

    r = ana.get(f"/trabajos/{trabajo_id}")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["estado"] == "listo"
    assert cuerpo["duracion_s"] > 0
    assert cuerpo["memoria_pico_mb"] > 0

    # la ingesta encola la calidad: esperar a que el worker la termine también
    limite = time.monotonic() + 10
    trabajo_calidad = None
    while time.monotonic() < limite:
        db.expire_all()
        trabajo_calidad = db.scalar(select(Trabajo).where(Trabajo.tipo == "calidad"))
        if trabajo_calidad is not None and trabajo_calidad.estado not in ("en_cola", "corriendo"):
            break
        time.sleep(0.05)
    assert trabajo_calidad is not None and trabajo_calidad.estado == "listo"

    r = ana.get(f"/datasets/{dataset_id}/calidad")
    assert r.status_code == 200
    informe = r.json()
    assert (informe["filas"], informe["clientes"], informe["productos"]) == (3, 3, 3)

    db.expire_all()
    assert db.scalar(select(Trabajo.empresa_id).where(Trabajo.id == uuid.UUID(trabajo_id))) == (
        _empresa_id(db, "ana@ejemplo.com")
    )


# --- SSE: eventos guardados y reconexión con Last-Event-ID (deterministas, sin worker) ------


def test_eventos_sse_envia_los_guardados_y_reconecta_con_last_event_id(ana, db) -> None:
    empresa_id = _empresa_id(db, "ana@ejemplo.com")
    trabajo = Trabajo(empresa_id=empresa_id, tipo="prueba", estado="listo")
    db.add(trabajo)
    db.flush()
    eventos.registrar(db, trabajo.id, "leyendo", {"filas": 1}, 0.5)
    eventos.registrar(db, trabajo.id, "listo", {"filas": 1}, 1.0)
    db.commit()

    completos = _leer_eventos_sse(ana, str(trabajo.id))
    assert [e["event"] for e in completos] == ["leyendo", "listo"]
    assert [e["id"] for e in completos] == ["1", "2"]

    reconectados = _leer_eventos_sse(ana, str(trabajo.id), last_event_id="1")
    assert [e["event"] for e in reconectados] == ["listo"]


# --- estados de error de la API ---------------------------------------------------------------


def test_ingesta_requiere_mapeo_confirmado(ana) -> None:
    dataset_id = _subir(ana, _crear_proyecto(ana)["id"])

    r = ana.post(f"/datasets/{dataset_id}/ingesta", headers=_csrf(ana))

    assert r.status_code == 409
    assert r.json()["codigo"] == "mapeo_no_confirmado"


def test_calidad_no_disponible_antes_de_calcularse(ana) -> None:
    dataset_id = _subir_y_mapear(ana)

    r = ana.get(f"/datasets/{dataset_id}/calidad")

    assert r.status_code == 404
    assert r.json()["codigo"] == "calidad_no_disponible"


def test_cancelar_en_cola_y_no_se_puede_cancelar_dos_veces(ana, db) -> None:
    empresa_id = _empresa_id(db, "ana@ejemplo.com")
    trabajo = cola.encolar(db, empresa_id, "prueba", {})

    r = ana.post(f"/trabajos/{trabajo.id}/cancelar", headers=_csrf(ana))
    assert r.status_code == 204
    assert ana.get(f"/trabajos/{trabajo.id}").json()["estado"] == "cancelado"

    r = ana.post(f"/trabajos/{trabajo.id}/cancelar", headers=_csrf(ana))
    assert r.status_code == 409
    assert r.json()["codigo"] == "trabajo_no_cancelable"


def test_trabajo_inexistente_responde_404(ana) -> None:
    assert ana.get(f"/trabajos/{uuid.uuid4()}").status_code == 404


# --- aislamiento por empresa -------------------------------------------------------------------


def test_otra_empresa_no_ve_ni_cancela_el_trabajo(ana, beto, db) -> None:
    empresa_id = _empresa_id(db, "ana@ejemplo.com")
    trabajo = cola.encolar(db, empresa_id, "prueba", {})

    assert beto.get(f"/trabajos/{trabajo.id}").status_code == 404
    assert beto.get(f"/trabajos/{trabajo.id}/eventos").status_code == 404
    r = beto.post(f"/trabajos/{trabajo.id}/cancelar", headers=_csrf(beto))
    assert r.status_code == 404
    assert ana.get(f"/trabajos/{trabajo.id}").status_code == 200


def test_otra_empresa_no_inicia_ingesta_ni_ve_la_calidad(ana, beto) -> None:
    dataset_id = _subir_y_mapear(ana)

    r = beto.post(f"/datasets/{dataset_id}/ingesta", headers=_csrf(beto))
    assert r.status_code == 404

    assert beto.get(f"/datasets/{dataset_id}/calidad").status_code == 404
