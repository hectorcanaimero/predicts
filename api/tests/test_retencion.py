"""Tests de retención (ver specs/f8-3d-demo-despliegue.md#F8.3.T2): con fechas simuladas, qué
dataset se archiva y cuál no, que el resumen/métricas en Postgres sobreviven, el `dry-run`, la
limpieza de `DATA_DIR/tmp`, el `410 archivo_vencido` en resultados/exportar, el tipo de trabajo
`retencion` y su encolado una vez por hora, y el comando `predicts limpiar --dry-run`.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from predicts import retencion
from predicts.app import crear_app
from predicts.auth.csrf import COOKIE_CSRF
from predicts.cli import app as cli_app
from predicts.config import settings_para_tests
from predicts.db.modelos import Analisis, Dataset, Empresa, Proyecto, Trabajo, Usuario
from predicts.db.sesion import get_db
from predicts.trabajos import eventos, tipos_retencion
from predicts.trabajos.registro import TrabajoEnCurso

pytestmark = pytest.mark.db

AHORA = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
runner = CliRunner()


@pytest.fixture()
def cfg(tmp_path):
    return settings_para_tests(DATA_DIR=str(tmp_path / "data"), RETENCION_DIAS=7)


@pytest.fixture()
def empresa(db: Session) -> Empresa:
    e = Empresa(nombre="Tienda")
    db.add(e)
    db.flush()
    return e


@pytest.fixture()
def proyecto(db: Session, empresa: Empresa) -> Proyecto:
    p = Proyecto(empresa_id=empresa.id, nombre="P", idioma_mensajes="es", tono="neutro")
    db.add(p)
    db.flush()
    return p


def _carpeta(cfg, empresa_id: uuid.UUID, dataset_id: uuid.UUID) -> Path:
    return Path(cfg.DATA_DIR) / str(empresa_id) / str(dataset_id)


def _crear_dataset(db: Session, cfg, empresa: Empresa, proyecto: Proyecto, *, subido_en) -> Dataset:
    """Dataset `listo` con `original.csv`, `compras.parquet` y un `resultados/` de análisis ya en
    disco, como lo dejaría el pipeline real (ver `api/datasets.py`, `analisis/orquestador.py`)."""
    dataset = Dataset(
        empresa_id=empresa.id,
        proyecto_id=proyecto.id,
        nombre_archivo="compras.csv",
        tamano_bytes=10,
        sha256="0" * 64,
        estado="listo",
        subido_en=subido_en,
    )
    db.add(dataset)
    db.flush()

    carpeta = _carpeta(cfg, empresa.id, dataset.id)
    (carpeta / "analisis" / "a1" / "resultados").mkdir(parents=True)
    (carpeta / "original.csv").write_text("a,b\n1,2\n")
    (carpeta / "compras.parquet").write_bytes(b"\x00")
    (carpeta / "analisis" / "a1" / "resultados" / "recompra.parquet").write_bytes(b"\x00")

    dataset.ruta_original = str(carpeta / "original.csv")
    dataset.ruta_parquet = str(carpeta / "compras.parquet")
    db.flush()
    return dataset


def _tocar(ruta: Path, momento: datetime) -> None:
    ts = momento.timestamp()
    os.utime(ruta, (ts, ts))


# --- qué se borra y qué no (fechas simuladas) ------------------------------------------------


def test_archiva_vencido_y_conserva_reciente(db, cfg, empresa, proyecto):
    viejo = _crear_dataset(db, cfg, empresa, proyecto, subido_en=AHORA - timedelta(days=10))
    reciente = _crear_dataset(db, cfg, empresa, proyecto, subido_en=AHORA - timedelta(days=2))
    db.commit()

    resultado = retencion.limpiar(db, cfg, ahora=AHORA)

    assert resultado.datasets_archivados == [viejo.id]
    assert (viejo.estado, viejo.archivado_en) == ("archivado", AHORA)
    assert viejo.ruta_original is None and viejo.ruta_parquet is None
    assert not _carpeta(cfg, empresa.id, viejo.id).exists()

    assert reciente.estado == "listo"
    assert _carpeta(cfg, empresa.id, reciente.id).exists()


def test_limite_exacto_de_dias_no_se_archiva(db, cfg, empresa, proyecto):
    """"Más de RETENCION_DIAS": justo en el límite todavía no se archiva."""
    limite = _crear_dataset(
        db, cfg, empresa, proyecto, subido_en=AHORA - timedelta(days=cfg.RETENCION_DIAS)
    )
    db.commit()

    resultado = retencion.limpiar(db, cfg, ahora=AHORA)

    assert resultado.datasets_archivados == []
    assert limite.estado == "listo"


def test_ya_archivado_no_se_vuelve_a_tocar(db, cfg, empresa, proyecto):
    ya = _crear_dataset(db, cfg, empresa, proyecto, subido_en=AHORA - timedelta(days=30))
    ya.estado = "archivado"
    ya.archivado_en = AHORA - timedelta(days=1)
    db.commit()

    resultado = retencion.limpiar(db, cfg, ahora=AHORA)

    assert resultado.datasets_archivados == []
    assert ya.archivado_en == AHORA - timedelta(days=1)  # no se reescribe


def test_empresa_id_filtra_a_una_sola_empresa(db, cfg):
    e1, e2 = Empresa(nombre="A"), Empresa(nombre="B")
    db.add_all([e1, e2])
    db.flush()
    p1 = Proyecto(empresa_id=e1.id, nombre="P", idioma_mensajes="es", tono="neutro")
    p2 = Proyecto(empresa_id=e2.id, nombre="P", idioma_mensajes="es", tono="neutro")
    db.add_all([p1, p2])
    db.flush()
    d1 = _crear_dataset(db, cfg, e1, p1, subido_en=AHORA - timedelta(days=30))
    d2 = _crear_dataset(db, cfg, e2, p2, subido_en=AHORA - timedelta(days=30))
    db.commit()

    resultado = retencion.limpiar(db, cfg, empresa_id=e1.id, ahora=AHORA)

    assert resultado.datasets_archivados == [d1.id]
    assert d1.estado == "archivado"
    assert d2.estado == "listo"


def test_conserva_resumen_metricas_en_postgres(db, cfg, empresa, proyecto):
    viejo = _crear_dataset(db, cfg, empresa, proyecto, subido_en=AHORA - timedelta(days=30))
    resultados_dir = _carpeta(cfg, empresa.id, viejo.id) / "analisis" / "a1" / "resultados"
    analisis = Analisis(
        empresa_id=empresa.id,
        dataset_id=viejo.id,
        tipos=["recompra"],
        estado="listo",
        resumen={"ok": True},
        metricas={"precision": 0.9},
        ruta_resultados=str(resultados_dir),
    )
    db.add(analisis)
    db.commit()

    retencion.limpiar(db, cfg, ahora=AHORA)

    db.expire_all()
    fila = db.get(Analisis, analisis.id)
    assert fila.resumen == {"ok": True}
    assert fila.metricas == {"precision": 0.9}
    assert not resultados_dir.exists()


# --- dry-run ----------------------------------------------------------------------------------


def test_dry_run_no_borra_ni_archiva(db, cfg, empresa, proyecto):
    viejo = _crear_dataset(db, cfg, empresa, proyecto, subido_en=AHORA - timedelta(days=30))
    db.commit()

    resultado = retencion.limpiar(db, cfg, ahora=AHORA, dry_run=True)

    assert resultado.datasets_archivados == [viejo.id]
    db.expire_all()
    fila = db.get(Dataset, viejo.id)
    assert fila.estado == "listo" and fila.ruta_original is not None
    assert _carpeta(cfg, empresa.id, viejo.id).exists()


# --- limpieza de DATA_DIR/tmp -------------------------------------------------------------------


def test_limpia_tmp_viejos_conserva_recientes(db, cfg):
    tmp_dir = Path(cfg.DATA_DIR) / "tmp"
    tmp_dir.mkdir(parents=True)
    viejo, reciente = tmp_dir / "spill-viejo.tmp", tmp_dir / "spill-reciente.tmp"
    viejo.write_bytes(b"x")
    reciente.write_bytes(b"x")
    _tocar(viejo, AHORA - timedelta(days=2))
    _tocar(reciente, AHORA - timedelta(hours=1))

    resultado = retencion.limpiar(db, cfg, ahora=AHORA)

    assert resultado.tmp_borrados == [viejo]
    assert not viejo.exists()
    assert reciente.exists()


def test_limpia_tmp_dry_run(db, cfg):
    tmp_dir = Path(cfg.DATA_DIR) / "tmp"
    tmp_dir.mkdir(parents=True)
    viejo = tmp_dir / "spill-viejo.tmp"
    viejo.write_bytes(b"x")
    _tocar(viejo, AHORA - timedelta(days=2))

    resultado = retencion.limpiar(db, cfg, ahora=AHORA, dry_run=True)

    assert resultado.tmp_borrados == [viejo]
    assert viejo.exists()


def test_sin_carpeta_tmp_no_falla(db, cfg):
    assert retencion.limpiar(db, cfg, ahora=AHORA).tmp_borrados == []


# --- 410 archivo_vencido en resultados/exportar ------------------------------------------------


@pytest.fixture()
def app(db: Session, cfg, monkeypatch):
    monkeypatch.setattr("predicts.auth.sesiones.settings", lambda: cfg)
    monkeypatch.setattr("predicts.api.analisis.settings", lambda: cfg)
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


@pytest.fixture()
def ana(app) -> TestClient:
    cliente = TestClient(app)
    r = cliente.post(
        "/auth/registro",
        json={
            "email": "ana@ejemplo.com",
            "contrasena": "una-contrasena-larga",
            "nombre_empresa": "Tienda Ana",
        },
    )
    assert r.status_code == 201
    return cliente


def _csrf(cliente: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": cliente.cookies[COOKIE_CSRF]}


@pytest.fixture()
def analisis_listo(db: Session, ana, cfg) -> Analisis:
    empresa_id = db.scalar(select(Usuario.empresa_id).where(Usuario.email == "ana@ejemplo.com"))
    proyecto = Proyecto(empresa_id=empresa_id, nombre="P", idioma_mensajes="es", tono="neutro")
    db.add(proyecto)
    db.flush()
    dataset = Dataset(
        empresa_id=empresa_id,
        proyecto_id=proyecto.id,
        nombre_archivo="c.csv",
        tamano_bytes=1,
        sha256="0" * 64,
        estado="listo",
    )
    db.add(dataset)
    db.flush()
    analisis = Analisis(
        empresa_id=empresa_id,
        dataset_id=dataset.id,
        tipos=["recompra", "contactar"],
        estado="listo",
        ruta_resultados=str(Path(cfg.DATA_DIR) / "noexiste"),
    )
    db.add(analisis)
    db.commit()
    return analisis


def _archivar_dataset(db: Session, analisis: Analisis) -> None:
    dataset = db.get(Dataset, analisis.dataset_id)
    dataset.estado = "archivado"
    db.commit()


def test_resultados_410_si_dataset_archivado(db, ana, analisis_listo):
    _archivar_dataset(db, analisis_listo)
    r = ana.get(f"/analisis/{analisis_listo.id}/resultados", params={"tipo": "recompra"})
    assert r.status_code == 410 and r.json()["codigo"] == "archivo_vencido"


def test_resultados_sigue_dando_409_si_no_archivado(db, ana, analisis_listo):
    analisis_listo.estado = "en_cola"
    db.commit()
    r = ana.get(f"/analisis/{analisis_listo.id}/resultados", params={"tipo": "recompra"})
    assert r.status_code == 409 and r.json()["codigo"] == "analisis_no_listo"


def test_exportar_410_si_dataset_archivado(db, ana, analisis_listo):
    _archivar_dataset(db, analisis_listo)
    r = ana.get(f"/analisis/{analisis_listo.id}/exportar", params={"tipo": "recordatorios"})
    assert r.status_code == 410 and r.json()["codigo"] == "archivo_vencido"


# --- tipo de trabajo `retencion` y su encolado una vez por hora --------------------------------


def test_tipo_trabajo_retencion_archiva_su_empresa(db, cfg, empresa, proyecto, monkeypatch):
    monkeypatch.setattr(tipos_retencion, "settings", lambda: cfg)
    url_db = db.get_bind().engine.url.render_as_string(hide_password=False)
    eventos.configurar(url_db)

    viejo = _crear_dataset(db, cfg, empresa, proyecto, subido_en=AHORA - timedelta(days=30))
    trabajo_id = uuid.uuid4()
    db.add(Trabajo(id=trabajo_id, empresa_id=empresa.id, tipo="retencion", estado="corriendo"))
    db.commit()

    tipos_retencion.retencion(TrabajoEnCurso(trabajo_id, empresa.id, "retencion", {}))

    db.expire_all()
    assert db.get(Dataset, viejo.id).estado == "archivado"


def test_encolar_si_corresponde_una_vez_por_hora(db, empresa):
    otra = Empresa(nombre="Otra")
    db.add(otra)
    db.commit()

    assert tipos_retencion.encolar_si_corresponde(db, ahora=AHORA) == 2
    tipos = db.scalars(select(Trabajo).where(Trabajo.tipo == "retencion")).all()
    assert {t.empresa_id for t in tipos} == {empresa.id, otra.id}

    # `creado_en` lo pone `func.now()` del servidor (la hora real), no `ahora`: lo fijamos al
    # momento simulado del primer encolado para poder seguir probando con fechas simuladas.
    db.execute(update(Trabajo).where(Trabajo.tipo == "retencion").values(creado_en=AHORA))
    db.commit()

    assert tipos_retencion.encolar_si_corresponde(db, ahora=AHORA + timedelta(minutes=30)) == 0
    assert tipos_retencion.encolar_si_corresponde(db, ahora=AHORA + timedelta(hours=2)) == 2


# --- comando `predicts limpiar --dry-run` -------------------------------------------------------


def test_cli_limpiar_dry_run(db, cfg, empresa, proyecto, monkeypatch):
    monkeypatch.setattr("predicts.comandos.limpiar.settings", lambda: cfg)
    monkeypatch.setattr(
        "predicts.comandos.limpiar.SessionLocal",
        lambda: Session(bind=db.get_bind(), autoflush=False, expire_on_commit=False),
    )
    viejo = _crear_dataset(
        db, cfg, empresa, proyecto, subido_en=datetime.now(UTC) - timedelta(days=30)
    )
    db.commit()

    resultado = runner.invoke(cli_app, ["limpiar", "--dry-run"])

    assert resultado.exit_code == 0, resultado.output
    assert "datasets a archivar: 1" in resultado.output
    assert str(viejo.id) in resultado.output

    db.expire_all()
    assert db.get(Dataset, viejo.id).estado == "listo"
    assert _carpeta(cfg, empresa.id, viejo.id).exists()
