"""Tests de la exportación a CSV (`predicts.exportar`, `api/exportar.py`, ver
specs/f5-mensajes.md#F5.2.T1): columnas, separador, BOM, encabezados en los tres idiomas,
filtros por `contactar`, mensaje renderizado, streaming con memoria acotada (1 M de filas,
`lento`) y aislamiento por empresa.

Reusa las fixtures `cfg`/`dataset` de `test_analisis_recompra` y el `JevFalso` de
`test_analisis_riesgo_ofertas` (mismo patrón que los demás tests de `analisis`/`mensajes`).
"""

from __future__ import annotations

import csv
import io
import resource
import uuid
from collections.abc import Generator
from datetime import date

import duckdb
import pytest
import test_analisis_recompra as base
import test_analisis_riesgo_ofertas as riesgo_base
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from predicts import exportar
from predicts.analisis import orquestador
from predicts.app import crear_app
from predicts.auth.csrf import COOKIE_CSRF
from predicts.config import settings_para_tests
from predicts.db.modelos import Analisis, PlantillaMensaje, Proyecto, Usuario
from predicts.db.sesion import get_db

pytestmark = pytest.mark.db

H = 14
cfg, dataset = base.cfg, base.dataset  # fixtures compartidas con los tests de recompra
_leer = base._leer
JevFalso = riesgo_base.JevFalso


def _correr_export(
    db: Session,
    dataset,
    cfg,
    *,
    tipos=("recompra", "riesgo", "ofertas", "contactar"),
    umbral: float = 0.3,
    horizonte: int = H,
    jev: JevFalso | None = None,
) -> Analisis:
    """Análisis completo (sin pasar por el trabajo real) con un Jev falso: `noul=0.6` deja los
    casos límite en `revisar` (confianza 0.2 < `CONFIANZA_JEV`) y los claros en `contactar` por
    regla, así que de entrada ya hay filas de ambos tipos para probar `incluir_revisar`."""
    fila = base._analisis(db, dataset, list(tipos), horizonte=horizonte, umbral=umbral)
    orquestador.ejecutar(db, fila, lambda *_: None, cfg, cliente_jev=jev or JevFalso(noul=0.6))
    fila.estado = "listo"
    db.commit()
    return fila


# --- API: app/clientes autenticados (igual patrón que test_analisis_api.py) ------------------


@pytest.fixture()
def app(db: Session, cfg, monkeypatch):
    monkeypatch.setattr("predicts.auth.sesiones.settings", lambda: cfg)
    monkeypatch.setattr("predicts.api.exportar.settings", lambda: cfg)
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
    cliente = _cliente(app, "Tienda Ana", "ana@ejemplo.com")
    dataset.empresa_id = db.scalar(
        select(Usuario.empresa_id).where(Usuario.email == "ana@ejemplo.com")
    )
    db.commit()
    return cliente


@pytest.fixture()
def beto(app) -> TestClient:
    return _cliente(app, "Tienda Beto", "beto@ejemplo.com")


def _descargar(ana: TestClient, analisis_id, tipo: str, **params) -> tuple[int, bytes, dict]:
    r = ana.get(f"/analisis/{analisis_id}/exportar", params={"tipo": tipo, **params})
    return r.status_code, r.content, r.headers


def _filas(contenido: bytes, separador: str = ",") -> tuple[list[str], list[list[str]]]:
    texto = contenido.decode("utf-8-sig")
    lector = list(csv.reader(io.StringIO(texto), delimiter=separador))
    return lector[0], lector[1:]


# --- columnas, BOM, separador, filtros --------------------------------------------------------


def test_exportar_recordatorios_columnas_bom_y_filtro_por_defecto(db, dataset, cfg, ana) -> None:
    fila = _correr_export(db, dataset, cfg)
    status, contenido, headers = _descargar(ana, fila.id, "recordatorios")
    assert status == 200
    assert contenido.startswith(exportar.BOM)
    assert headers["content-type"].startswith("text/csv")
    assert "attachment" in headers["content-disposition"]

    encabezado, filas = _filas(contenido)
    assert encabezado == list(exportar.ENCABEZADOS["es"].values())

    contactar_parquet = _leer(fila, "contactar.parquet")
    esperadas = {f["cliente_id"] for f in contactar_parquet if f["decision"] == "contactar"}
    assert esperadas  # la regla siempre deja algún "contactar" claro
    idx_cliente = encabezado.index(exportar.ENCABEZADOS["es"]["cliente_id"])
    idx_contactar = encabezado.index(exportar.ENCABEZADOS["es"]["contactar"])
    assert filas  # recompra.parquet tiene algún cruce con "esperadas"
    assert {f[idx_cliente] for f in filas} <= esperadas
    assert all(f[idx_contactar] == "sí" for f in filas)


def test_exportar_incluir_revisar_suma_las_dudosas(db, dataset, cfg, ana) -> None:
    fila = _correr_export(db, dataset, cfg)
    _, sin_revisar, _ = _descargar(ana, fila.id, "recordatorios")
    _, con_revisar, _ = _descargar(ana, fila.id, "recordatorios", incluir_revisar=True)

    _, filas_sin = _filas(sin_revisar)
    encabezado, filas_con = _filas(con_revisar)
    idx_contactar = encabezado.index(exportar.ENCABEZADOS["es"]["contactar"])

    assert len(filas_con) > len(filas_sin)
    assert {f[idx_contactar] for f in filas_sin} == {"sí"}
    assert {f[idx_contactar] for f in filas_con} == {"sí", "revisar"}


def test_exportar_separador_punto_y_coma(db, dataset, cfg, ana) -> None:
    fila = _correr_export(db, dataset, cfg)
    status, contenido, _ = _descargar(ana, fila.id, "recordatorios", separador=";")
    assert status == 200
    encabezado, filas = _filas(contenido, separador=";")
    assert encabezado == list(exportar.ENCABEZADOS["es"].values())
    assert filas  # alcanza con que se haya podido parsear con ';'


def test_exportar_separador_invalido(db, dataset, cfg, ana) -> None:
    fila = _correr_export(db, dataset, cfg)
    status, _, _ = _descargar(ana, fila.id, "recordatorios", separador="|")
    assert status == 422


def test_exportar_tipo_invalido(db, dataset, cfg, ana) -> None:
    fila = _correr_export(db, dataset, cfg)
    status, _, _ = _descargar(ana, fila.id, "magia")
    assert status == 422


def test_exportar_tipo_no_solicitado(db, dataset, cfg, ana) -> None:
    fila = _correr_export(db, dataset, cfg, tipos=("recompra", "contactar"))
    status, _, _ = _descargar(ana, fila.id, "riesgo")
    assert status == 404


def test_exportar_analisis_no_listo(db, dataset, ana) -> None:
    fila = base._analisis(db, dataset, ["recompra", "contactar"])
    db.commit()
    status, _, _ = _descargar(ana, fila.id, "recordatorios")
    assert status == 409


# --- ofertas y riesgo: columnas que no comparten con recordatorios ---------------------------


def test_exportar_ofertas_sin_fechas_con_puntaje_como_probabilidad(db, dataset, cfg, ana) -> None:
    fila = _correr_export(db, dataset, cfg)
    status, contenido, _ = _descargar(ana, fila.id, "ofertas")
    assert status == 200
    encabezado, filas = _filas(contenido)
    idx_fecha = encabezado.index(exportar.ENCABEZADOS["es"]["fecha_sugerida"])
    idx_prob = encabezado.index(exportar.ENCABEZADOS["es"]["probabilidad"])
    if filas:
        assert all(f[idx_fecha] == "" for f in filas)
        assert all(f[idx_prob] != "" for f in filas)


def test_exportar_riesgo_sin_probabilidad(db, dataset, cfg, ana) -> None:
    fila = _correr_export(db, dataset, cfg)
    status, contenido, _ = _descargar(ana, fila.id, "riesgo")
    assert status == 200
    encabezado, filas = _filas(contenido)
    idx_prob = encabezado.index(exportar.ENCABEZADOS["es"]["probabilidad"])
    if filas:
        assert all(f[idx_prob] == "" for f in filas)


# --- encabezados en los tres idiomas ----------------------------------------------------------


@pytest.mark.parametrize("idioma", ["es", "en", "pt-BR"])
def test_exportar_encabezados_en_el_idioma_del_proyecto(db, dataset, cfg, ana, idioma) -> None:
    proyecto = db.get(Proyecto, dataset.proyecto_id)
    proyecto.idioma_mensajes = idioma
    db.commit()
    fila = _correr_export(db, dataset, cfg)
    status, contenido, headers = _descargar(ana, fila.id, "recordatorios")
    assert status == 200
    encabezado, _ = _filas(contenido)
    assert encabezado == list(exportar.ENCABEZADOS[idioma].values())
    assert str(date.today()) in headers["content-disposition"]
    assert "recordatorios" in headers["content-disposition"]


# --- mensaje: render de F5.1 sobre el resultado real -------------------------------------------


def test_exportar_mensaje_reemplaza_los_marcadores_de_la_plantilla(db, dataset, cfg, ana) -> None:
    fila = _correr_export(db, dataset, cfg)
    contactados = _leer(fila, "contactar.parquet")
    contactar = {f["cliente_id"] for f in contactados if f["decision"] == "contactar"}
    recompra = [f for f in _leer(fila, "recompra.parquet") if f["cliente_id"] in contactar]
    assert recompra
    fila_objetivo = recompra[0]

    proyecto = db.get(Proyecto, dataset.proyecto_id)
    db.add(
        PlantillaMensaje(
            empresa_id=fila.empresa_id,
            clave=f"{fila_objetivo['producto_id']}::recordatorio",
            tipo="recordatorio",
            idioma=proyecto.idioma_mensajes,
            tono=proyecto.tono,
            texto="Hola, {producto} te espera en {nombre_tienda}.",
            estado="ok",
        )
    )
    db.commit()

    status, contenido, _ = _descargar(ana, fila.id, "recordatorios")
    assert status == 200
    encabezado, filas = _filas(contenido)
    idx_cliente = encabezado.index(exportar.ENCABEZADOS["es"]["cliente_id"])
    idx_producto_id = encabezado.index(exportar.ENCABEZADOS["es"]["producto_id"])
    idx_mensaje = encabezado.index(exportar.ENCABEZADOS["es"]["mensaje"])
    fila_csv = next(
        f
        for f in filas
        if f[idx_cliente] == fila_objetivo["cliente_id"]
        and f[idx_producto_id] == fila_objetivo["producto_id"]
    )
    assert fila_csv[idx_mensaje] == (
        f"Hola, {fila_objetivo['producto_nombre']} te espera en {proyecto.nombre}."
    )


# --- aislamiento por empresa -------------------------------------------------------------------


def test_exportar_aislamiento_por_empresa(db, dataset, cfg, ana, beto) -> None:
    fila = _correr_export(db, dataset, cfg)
    status, _, _ = _descargar(beto, fila.id, "recordatorios")
    assert status == 404


def test_exportar_analisis_no_encontrado(ana) -> None:
    status, _, _ = _descargar(ana, uuid.uuid4(), "recordatorios")
    assert status == 404


# --- streaming: memoria acotada con 1 M de filas (lento, fuera de la CI) ---------------------


@pytest.mark.lento
def test_exportar_1_millon_de_filas_memoria_acotada(tmp_path) -> None:
    n = 1_000_000
    resultados = tmp_path / "resultados"
    resultados.mkdir()
    con = duckdb.connect()
    try:
        con.execute(
            f"""
            COPY (
                SELECT
                    'cliente-' || (i % 100000) AS cliente_id,
                    'producto-' || (i % 1000) AS producto_id,
                    'Producto ' || (i % 1000) AS producto_nombre,
                    CURRENT_DATE AS fecha_probable,
                    CURRENT_DATE AS fecha_min,
                    CURRENT_DATE AS fecha_max,
                    0.9 AS p,
                    10 AS dias_desde_ultima,
                    'motivo de prueba' AS motivo
                FROM range({n}) t(i)
            ) TO '{resultados / "recompra.parquet"}' (FORMAT parquet)
            """
        )
        con.execute(
            f"""
            COPY (
                SELECT DISTINCT 'cliente-' || (i % 100000) AS cliente_id, 'contactar' AS decision
                FROM range({n}) t(i)
            ) TO '{resultados / "contactar.parquet"}' (FORMAT parquet)
            """
        )
    finally:
        con.close()

    destino = tmp_path / "salida.csv"
    cfg = settings_para_tests(DATA_DIR=str(tmp_path / "data"))

    antes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # KB en Linux
    exportar.exportar_csv(resultados, "recordatorios", "es", "Tienda", destino, cfg=cfg)
    despues = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    assert destino.exists()
    with destino.open("rb") as f:
        assert f.read(len(exportar.BOM)) == exportar.BOM
    assert (despues - antes) < 400 * 1024
