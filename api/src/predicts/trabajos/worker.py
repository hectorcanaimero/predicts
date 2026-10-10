"""Worker: toma trabajos de la cola y ejecuta cada uno en un subproceso con tope de memoria.

Cada trabajo corre en un hijo `multiprocessing` con contexto `spawn` (proceso limpio, sin heredar
el estado ni las conexiones del worker). Si el hijo revienta, el trabajo queda en `error` y el
worker sigue con el siguiente.

Tope de memoria: `RLIMIT_DATA`, no `RLIMIT_AS`. `RLIMIT_AS` cuenta todo el espacio virtual, y
DuckDB, NumPy/OpenBLAS y glibc reservan mucho más del que tocan (arenas por hilo, mmap de
archivos, regiones `PROT_NONE`): con un tope realista el hijo fallaría sin usar memoria real.
`RLIMIT_DATA` (Linux ≥ 4.7) cuenta solo heap y mapeos privados escribibles, que es lo que crece
cuando un trabajo usa memoria de verdad; los archivos mapeados (Parquet) y las reservas
`PROT_NONE` no cuentan. Al pasarse, `malloc` falla y Python/NumPy lanzan `MemoryError` (DuckDB,
`OutOfMemoryException`), que el hijo informa como `memoria_excedida`. Si el kernel lo mata con
`SIGKILL` (OOM killer del contenedor) también se informa `memoria_excedida`.

Duración (`duracion_s`) y pico de memoria del hijo (`memoria_pico_mb`) se guardan en el trabajo.
El pico lo informa el hijo antes de salir; si muere de golpe queda vacío. Se lee `VmHWM` de
`/proc/self/status` (el pico de RSS, como `ru_maxrss`) porque `ru_maxrss` sobrevive al `exec`
de `spawn` y arrastra el RSS que tenía el worker al hacer el fork.
"""

from __future__ import annotations

import logging
import multiprocessing
import resource
import signal
import threading
import time
import traceback
import uuid
from multiprocessing.connection import Connection

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from predicts.db.modelos import EventoTrabajo, Trabajo
from predicts.trabajos import cola, eventos, registro
from predicts.trabajos.registro import FuncionTrabajo, TrabajoEnCurso
from predicts.trabajos.tipos_retencion import encolar_si_corresponde

log = logging.getLogger(__name__)

_MAX_DETALLE = 4000
_INTERVALO_SONDEO_S = 0.2
_INTERVALO_CANCELACION_S = 1.0


def _pico_rss_mb() -> int:
    with open("/proc/self/status") as status:
        for linea in status:
            if linea.startswith("VmHWM:"):
                return int(linea.split()[1]) // 1024  # kB
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024


def _hijo(
    func: FuncionTrabajo,
    trabajo: TrabajoEnCurso,
    url_db: str,
    max_memoria_mb: int,
    conexion: Connection,
) -> None:
    limite = max_memoria_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_DATA, (limite, limite))
    eventos.configurar(url_db)
    try:
        func(trabajo)
        eventos.vaciar(trabajo.id)
        resultado: dict = {"estado": "listo"}
    except BaseException as exc:  # noqa: BLE001 - todo fallo del trabajo se informa al worker
        memoria = isinstance(exc, MemoryError) or "OutOfMemory" in type(exc).__name__
        resultado = {
            "estado": "error",
            "codigo": "memoria_excedida" if memoria else "error_interno",
            "detalle": traceback.format_exc()[-_MAX_DETALLE:],
        }
    resultado["memoria_pico_mb"] = _pico_rss_mb()
    conexion.send(resultado)
    conexion.close()


def _estado(db: Session, trabajo_id: uuid.UUID) -> str | None:
    estado = db.scalar(select(Trabajo.estado).where(Trabajo.id == trabajo_id))
    db.commit()
    return estado


def _ejecutar(
    db: Session, trabajo: Trabajo, url_db: str, max_memoria_mb: int, timeout_s: float
) -> dict:
    """Corre `trabajo` en un subproceso y devuelve `{estado, codigo, detalle, memoria_pico_mb}`."""
    func = registro.obtener(trabajo.tipo)
    if func is None:
        return {"estado": "error", "codigo": "error_interno",
                "detalle": f"tipo de trabajo desconocido: {trabajo.tipo}"}

    ctx = multiprocessing.get_context("spawn")
    lector, escritor = ctx.Pipe(duplex=False)
    en_curso = TrabajoEnCurso(
        trabajo.id, trabajo.empresa_id, trabajo.tipo, trabajo.parametros or {}
    )
    proceso = ctx.Process(
        target=_hijo,
        args=(func, en_curso, url_db, max_memoria_mb, escritor),
        name=f"trabajo-{trabajo.id}",
        daemon=True,
    )
    inicio = time.monotonic()
    proceso.start()
    escritor.close()

    resultado: dict | None = None
    motivo: str | None = None
    ultima_revision = inicio
    while resultado is None:
        # Leer el resultado mientras el hijo vive: si se esperara a que termine, un mensaje más
        # grande que el buffer del pipe lo dejaría bloqueado en `send`.
        if lector.poll(_INTERVALO_SONDEO_S):
            try:
                resultado = lector.recv()
            except EOFError:
                break  # el hijo murió sin informar (el pipe queda en EOF)
            continue
        ahora = time.monotonic()
        if ahora - inicio > timeout_s:
            motivo = "tiempo_excedido"
            break
        if ahora - ultima_revision >= _INTERVALO_CANCELACION_S:
            ultima_revision = ahora
            if _estado(db, trabajo.id) == "cancelado":
                motivo = "cancelado"
                break

    if motivo is not None:
        proceso.kill()
    proceso.join()
    lector.close()

    if motivo == "cancelado":
        return {"estado": "cancelado"}
    if motivo == "tiempo_excedido":
        return {"estado": "error", "codigo": "tiempo_excedido",
                "detalle": f"superó {timeout_s} s"}
    if resultado is not None:
        return resultado
    if proceso.exitcode == -signal.SIGKILL:
        return {"estado": "error", "codigo": "memoria_excedida",
                "detalle": "el subproceso recibió SIGKILL (probable OOM killer)"}
    if proceso.exitcode is not None and proceso.exitcode < 0:
        detalle = f"el subproceso murió por la señal {signal.Signals(-proceso.exitcode).name}"
    else:
        detalle = f"el subproceso terminó con código {proceso.exitcode} sin informar"
    return {"estado": "error", "codigo": "error_interno", "detalle": detalle}


def _evento_final(db: Session, trabajo_id: uuid.UUID, etapa: str) -> None:
    """Evento `listo`/`error` con los últimos contadores que emitió el trabajo."""
    contadores = db.scalar(
        select(EventoTrabajo.contadores)
        .where(EventoTrabajo.trabajo_id == trabajo_id)
        .order_by(EventoTrabajo.secuencia.desc())
        .limit(1)
    )
    eventos.registrar(db, trabajo_id, etapa, contadores, 1.0 if etapa == "listo" else None)


def procesar_siguiente(
    db: Session, url_db: str, max_memoria_mb: int, timeout_s: float
) -> uuid.UUID | None:
    """Toma y ejecuta un trabajo; devuelve su id o `None` si la cola estaba vacía.

    `db` debe estar ligada a una conexión fija (ver `cola`).
    """
    trabajo = cola.tomar_siguiente(db)
    if trabajo is None:
        return None
    log.info("trabajo %s (%s) iniciado", trabajo.id, trabajo.tipo)
    inicio = time.monotonic()
    try:
        resultado = _ejecutar(db, trabajo, url_db, max_memoria_mb, timeout_s)
    except Exception:  # el worker no se cae por un trabajo
        log.exception("fallo al ejecutar el trabajo %s", trabajo.id)
        resultado = {"estado": "error", "codigo": "error_interno",
                     "detalle": traceback.format_exc()[-_MAX_DETALLE:]}
    duracion = time.monotonic() - inicio

    if resultado["estado"] != "cancelado":
        cerrado = cola.terminar(
            db,
            trabajo.id,
            resultado["estado"],
            codigo=resultado.get("codigo"),
            detalle=resultado.get("detalle"),
            duracion_s=duracion,
            memoria_pico_mb=resultado.get("memoria_pico_mb"),
        )
        if cerrado:
            _evento_final(db, trabajo.id, resultado["estado"])
    cola.soltar(db, trabajo.id)
    log.info("trabajo %s terminado: %s %s", trabajo.id, resultado["estado"],
             resultado.get("codigo") or "")
    return trabajo.id


def correr(
    url_db: str,
    max_memoria_mb: int,
    timeout_s: float,
    *,
    intervalo_s: float = 1.0,
    detener: threading.Event | None = None,
) -> None:
    """Bucle del worker: recupera los interrumpidos y procesa la cola hasta `detener`."""
    detener = detener or threading.Event()
    engine = create_engine(url_db, pool_pre_ping=True)
    try:
        with engine.connect() as conexion, Session(bind=conexion) as db:
            recuperados = cola.recuperar_interrumpidos(db)
            if recuperados:
                log.warning("%d trabajos interrumpidos pasaron a error", recuperados)
            while not detener.is_set():
                encolar_si_corresponde(db)  # retención: sin esto no hay cron externo
                if procesar_siguiente(db, url_db, max_memoria_mb, timeout_s) is None:
                    detener.wait(intervalo_s)
    finally:
        engine.dispose()
