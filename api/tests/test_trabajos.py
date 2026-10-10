"""Tests de `predicts.trabajos`: cola, worker con subprocesos y eventos.

Los tipos de trabajo falsos están a nivel de módulo porque el hijo `spawn` los importa por
referencia (vuelve a importar este archivo).
"""

from __future__ import annotations

import os
import signal
import threading
import time
import uuid
from collections.abc import Generator

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from predicts.db.modelos import Empresa, EventoTrabajo, Trabajo
from predicts.trabajos import cola, eventos
from predicts.trabajos.registro import TrabajoEnCurso, tipo_trabajo
from predicts.trabajos.worker import procesar_siguiente

pytestmark = pytest.mark.db

MEMORIA_MB = 400
TIMEOUT_S = 30


@tipo_trabajo("prueba_ok")
def _ok(trabajo: TrabajoEnCurso) -> None:
    eventos.emitir(trabajo.id, "leyendo", {"filas": trabajo.parametros["filas"]}, 0.5)


@tipo_trabajo("prueba_excepcion")
def _excepcion(trabajo: TrabajoEnCurso) -> None:
    raise ValueError("boom")


@tipo_trabajo("prueba_memoria")
def _memoria(trabajo: TrabajoEnCurso) -> None:
    bytearray(2 * MEMORIA_MB * 1024 * 1024)


@tipo_trabajo("prueba_dormir")
def _dormir(trabajo: TrabajoEnCurso) -> None:
    time.sleep(trabajo.parametros["s"])


@tipo_trabajo("prueba_senal")
def _senal(trabajo: TrabajoEnCurso) -> None:
    os.kill(os.getpid(), signal.SIGTERM)


@pytest.fixture()
def engine(db: Session) -> Engine:
    return db.get_bind()


@pytest.fixture()
def url_db(engine: Engine) -> str:
    return engine.url.render_as_string(hide_password=False)


@pytest.fixture()
def empresa_id(db: Session) -> uuid.UUID:
    empresa = Empresa(nombre="Acme")
    db.add(empresa)
    db.commit()
    return empresa.id


@pytest.fixture()
def db_worker(engine: Engine) -> Generator[Session]:
    """Sesión ligada a una conexión fija, como la del worker real."""
    with engine.connect() as conexion, Session(bind=conexion) as sesion:
        yield sesion


def _procesar(db_worker: Session, url_db: str, timeout_s: float = TIMEOUT_S) -> uuid.UUID | None:
    return procesar_siguiente(db_worker, url_db, MEMORIA_MB, timeout_s)


def _leer(db: Session, trabajo_id: uuid.UUID) -> Trabajo:
    db.expire_all()
    return db.get(Trabajo, trabajo_id)


def _eventos(db: Session, trabajo_id: uuid.UUID) -> list[EventoTrabajo]:
    db.expire_all()
    return list(db.scalars(
        select(EventoTrabajo)
        .where(EventoTrabajo.trabajo_id == trabajo_id)
        .order_by(EventoTrabajo.secuencia)
    ))


# --- worker ---------------------------------------------------------------------------------


def test_exito_guarda_duracion_memoria_y_eventos(db, db_worker, url_db, empresa_id):
    trabajo = cola.encolar(db, empresa_id, "prueba_ok", {"filas": 10})
    assert trabajo.estado == "en_cola"

    assert _procesar(db_worker, url_db) == trabajo.id

    fila = _leer(db, trabajo.id)
    assert fila.estado == "listo"
    assert fila.error_codigo is None
    assert fila.intentos == 1
    assert fila.duracion_s > 0
    assert fila.memoria_pico_mb > 0
    assert fila.iniciado_en is not None and fila.terminado_en is not None
    assert [(e.etapa, e.contadores, e.progreso) for e in _eventos(db, trabajo.id)] == [
        ("leyendo", {"filas": 10}, 0.5),
        ("listo", {"filas": 10}, 1.0),
    ]
    assert _procesar(db_worker, url_db) is None


def test_excepcion_queda_en_error_interno(db, db_worker, url_db, empresa_id):
    trabajo = cola.encolar(db, empresa_id, "prueba_excepcion", {})
    _procesar(db_worker, url_db)

    fila = _leer(db, trabajo.id)
    assert fila.estado == "error"
    assert fila.error_codigo == "error_interno"
    assert "ValueError: boom" in fila.error_detalle
    assert [e.etapa for e in _eventos(db, trabajo.id)] == ["error"]


def test_memoria_excedida_y_el_worker_sigue(db, db_worker, url_db, empresa_id):
    grande = cola.encolar(db, empresa_id, "prueba_memoria", {})
    siguiente = cola.encolar(db, empresa_id, "prueba_ok", {"filas": 1})

    _procesar(db_worker, url_db)
    _procesar(db_worker, url_db)

    fila = _leer(db, grande.id)
    assert fila.estado == "error"
    assert fila.error_codigo == "memoria_excedida"
    assert fila.memoria_pico_mb < MEMORIA_MB
    assert _leer(db, siguiente.id).estado == "listo"


def test_muerte_por_senal_es_error_interno(db, db_worker, url_db, empresa_id):
    trabajo = cola.encolar(db, empresa_id, "prueba_senal", {})
    _procesar(db_worker, url_db)

    fila = _leer(db, trabajo.id)
    assert (fila.estado, fila.error_codigo) == ("error", "error_interno")
    assert "SIGTERM" in fila.error_detalle


def test_tipo_desconocido_es_error_interno(db, db_worker, url_db, empresa_id):
    trabajo = cola.encolar(db, empresa_id, "no_existe", {})
    _procesar(db_worker, url_db)
    assert _leer(db, trabajo.id).error_codigo == "error_interno"


def test_timeout_mata_al_hijo(db, db_worker, url_db, empresa_id):
    trabajo = cola.encolar(db, empresa_id, "prueba_dormir", {"s": 60})
    inicio = time.monotonic()
    _procesar(db_worker, url_db, timeout_s=2)

    assert time.monotonic() - inicio < 10
    fila = _leer(db, trabajo.id)
    assert (fila.estado, fila.error_codigo) == ("error", "tiempo_excedido")
    assert fila.duracion_s >= 2


def test_cancelar_en_cola(db, db_worker, url_db, empresa_id):
    trabajo = cola.encolar(db, empresa_id, "prueba_ok", {"filas": 1})
    assert cola.cancelar(db, trabajo.id)
    assert _procesar(db_worker, url_db) is None
    assert _leer(db, trabajo.id).estado == "cancelado"
    assert not cola.cancelar(db, trabajo.id)


def test_cancelar_corriendo_mata_al_hijo(db, db_worker, url_db, empresa_id):
    trabajo = cola.encolar(db, empresa_id, "prueba_dormir", {"s": 60})
    hilo = threading.Thread(target=_procesar, args=(db_worker, url_db))
    hilo.start()
    limite = time.monotonic() + 10
    while _leer(db, trabajo.id).estado != "corriendo" and time.monotonic() < limite:
        time.sleep(0.1)

    assert cola.cancelar(db, trabajo.id)
    hilo.join(timeout=10)

    assert not hilo.is_alive()
    assert _leer(db, trabajo.id).estado == "cancelado"
    assert _eventos(db, trabajo.id) == []


# --- cola -----------------------------------------------------------------------------------


def test_recuperar_interrumpidos_respeta_los_de_otro_worker_vivo(db, engine, empresa_id):
    huerfano = Trabajo(empresa_id=empresa_id, tipo="prueba_ok", estado="corriendo")
    vivo = Trabajo(empresa_id=empresa_id, tipo="prueba_ok", estado="corriendo")
    listo = Trabajo(empresa_id=empresa_id, tipo="prueba_ok", estado="listo")
    db.add_all([huerfano, vivo, listo])
    db.commit()

    with engine.connect() as otro_worker:
        otro_worker.execute(text("SELECT pg_advisory_lock(:k)"), {"k": cola.clave_lock(vivo.id)})
        with engine.connect() as conexion, Session(bind=conexion) as db_worker:
            assert cola.recuperar_interrumpidos(db_worker) == 1

    fila = _leer(db, huerfano.id)
    assert (fila.estado, fila.error_codigo) == ("error", "interrumpido")
    assert _leer(db, vivo.id).estado == "corriendo"
    assert _leer(db, listo.id).estado == "listo"


def test_dos_workers_no_toman_el_mismo_trabajo(db, engine, empresa_id):
    ids = {cola.encolar(db, empresa_id, "prueba_ok", {}).id for _ in range(20)}
    tomados: list[uuid.UUID] = []
    barrera = threading.Barrier(4)

    def worker() -> None:
        with engine.connect() as conexion, Session(bind=conexion) as sesion:
            barrera.wait()
            while (trabajo := cola.tomar_siguiente(sesion)) is not None:
                tomados.append(trabajo.id)

    hilos = [threading.Thread(target=worker) for _ in range(4)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert sorted(tomados) == sorted(ids)


def test_tomar_salta_el_trabajo_bloqueado_por_otro(db, engine, empresa_id):
    primero = cola.encolar(db, empresa_id, "prueba_ok", {})
    segundo = cola.encolar(db, empresa_id, "prueba_ok", {})

    with engine.connect() as a, engine.connect() as b:
        a.execute(
            select(Trabajo.id).where(Trabajo.id == primero.id).with_for_update()
        )  # transacción abierta con el primero bloqueado
        with Session(bind=b) as sesion_b:
            assert cola.tomar_siguiente(sesion_b).id == segundo.id


# --- eventos --------------------------------------------------------------------------------


class _Reloj:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def test_eventos_maximo_uno_por_segundo(db, url_db, empresa_id, monkeypatch):
    reloj = _Reloj()
    monkeypatch.setattr(eventos.time, "monotonic", reloj)
    eventos.configurar(url_db)
    trabajo = cola.encolar(db, empresa_id, "prueba_ok", {})

    assert eventos.emitir(trabajo.id, "leyendo", {"filas": 1}, 0.1)
    for i in range(5):
        reloj.t += 0.1
        assert not eventos.emitir(trabajo.id, "leyendo", {"filas": 2 + i}, 0.2)
    assert len(_eventos(db, trabajo.id)) == 1

    reloj.t += 0.6  # 1,1 s desde el primero
    assert eventos.emitir(trabajo.id, "calidad", {"filas": 10}, 0.5)
    reloj.t += 0.1
    assert not eventos.emitir(trabajo.id, "calidad", {"filas": 99}, 0.9)
    eventos.vaciar(trabajo.id)  # el último descartado se guarda al terminar
    reloj.t += 0.1
    assert eventos.emitir(trabajo.id, "listo", {"filas": 99}, 1.0)  # los finales nunca se descartan

    assert [(e.secuencia, e.etapa, e.contadores) for e in _eventos(db, trabajo.id)] == [
        (1, "leyendo", {"filas": 1}),
        (2, "calidad", {"filas": 10}),
        (3, "calidad", {"filas": 99}),
        (4, "listo", {"filas": 99}),
    ]
    assert all(e.empresa_id == empresa_id for e in _eventos(db, trabajo.id))
