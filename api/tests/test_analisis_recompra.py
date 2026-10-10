"""Tests del análisis de recompra y ciclos sobre el sintético con verdad conocida (ver
specs/f4-analisis.md#F4.3.T1): ciclos ±15 %, los pares que compran en el horizonte tienen más
probabilidad, durables fuera, grupos confirmados aplicados, métricas y resumen guardados, y el
tipo de trabajo `analisis` de punta a punta."""

from __future__ import annotations

import shutil
from datetime import timedelta
from pathlib import Path

import duckdb
import pytest
from sqlalchemy.orm import Session

from predicts.analisis import orquestador
from predicts.config import settings_para_tests
from predicts.db.modelos import (
    Analisis,
    Dataset,
    Empresa,
    EventoTrabajo,
    GrupoProducto,
    Producto,
    Proyecto,
    Trabajo,
)
from predicts.productos.catalogo import actualizar_catalogo
from predicts.trabajos import eventos, registro
from predicts.trabajos.registro import TrabajoEnCurso

pytestmark = pytest.mark.db

FIXTURES = Path(__file__).parent / "fixtures"
COMPRAS = FIXTURES / "sintetico_compras.parquet"
VERDAD = FIXTURES / "sintetico_compras.verdad.parquet"
H = 14


def _durables() -> set[str]:
    return {
        f[0]
        for f in duckdb.sql(
            f"SELECT producto_id FROM '{VERDAD}' GROUP BY 1 HAVING count(ciclo_real) = 0"
        ).fetchall()
    }


@pytest.fixture()
def cfg(tmp_path):
    return settings_para_tests(DATA_DIR=str(tmp_path / "data"))


@pytest.fixture()
def dataset(db: Session, tmp_path, cfg) -> Dataset:
    """Dataset ingerido con el sintético, catálogo actualizado y durables marcados como lo
    haría la clasificación (sin Jev)."""
    empresa = Empresa(nombre="Tienda")
    db.add(empresa)
    db.flush()
    proyecto = Proyecto(empresa_id=empresa.id, nombre="P", idioma_mensajes="es", tono="neutro")
    db.add(proyecto)
    db.flush()
    carpeta = tmp_path / "data" / str(empresa.id) / "ds"
    carpeta.mkdir(parents=True)
    shutil.copy(COMPRAS, carpeta / "compras.parquet")
    dataset = Dataset(
        empresa_id=empresa.id,
        proyecto_id=proyecto.id,
        nombre_archivo="s.csv",
        tamano_bytes=1,
        sha256="0" * 64,
        estado="listo",
        ruta_parquet=str(carpeta / "compras.parquet"),
    )
    db.add(dataset)
    db.flush()
    durables = _durables()
    for producto in actualizar_catalogo(db, dataset, cfg):
        producto.tipo = "durable" if producto.producto_id_origen in durables else "recompra"
    db.flush()
    return dataset


def _analisis(db: Session, dataset: Dataset, tipos=("recompra", "ciclos"), **parametros):
    fila = Analisis(
        empresa_id=dataset.empresa_id,
        dataset_id=dataset.id,
        tipos=list(tipos),
        parametros=parametros,
        estado="en_cola",
    )
    db.add(fila)
    db.flush()
    return fila


def _correr(db, dataset, cfg, tipos=("recompra", "ciclos"), **parametros):
    fila = _analisis(db, dataset, tipos, **parametros)
    emitidos: list[tuple[str, dict]] = []
    orquestador.ejecutar(db, fila, lambda e, c: emitidos.append((e, c)), cfg)
    return fila, emitidos


def _leer(fila: Analisis, nombre: str) -> list[dict]:
    rel = duckdb.sql(f"SELECT * FROM '{Path(fila.ruta_resultados) / nombre}'")
    return [dict(zip(rel.columns, f, strict=True)) for f in rel.fetchall()]


def test_ciclos_contra_la_verdad(db, dataset, cfg) -> None:
    fila, _ = _correr(db, dataset, cfg, tipos=["ciclos"])

    verdad = dict(
        duckdb.sql(
            f"SELECT producto_id, median(ciclo_real) FROM '{VERDAD}' "
            "WHERE ciclo_real IS NOT NULL GROUP BY 1"
        ).fetchall()
    )
    filas = _leer(fila, "ciclos.parquet")
    assert {f["producto_id"] for f in filas} == set(verdad)
    for f in filas:
        assert abs(f["ciclo_mediano"] - verdad[f["producto_id"]]) <= 0.15 * verdad[f["producto_id"]]
        assert f["clientes_recurrentes"] > 0 and f["dispersion"] >= 0
        assert f["producto_nombre"].startswith("Producto sintético")
    assert fila.metricas is None  # sin recompra no hay backtest


def test_recompra_compradores_del_horizonte_tienen_mas_probabilidad(db, dataset, cfg) -> None:
    (fecha_max,) = duckdb.sql(f"SELECT CAST(max(fecha) AS DATE) FROM '{COMPRAS}'").fetchone()
    corte = fecha_max - timedelta(days=60)
    fila, _ = _correr(db, dataset, cfg, hasta=corte.isoformat(), horizonte=H, umbral=0.0)

    assert fila.resumen["fecha_ref"] <= corte.isoformat()
    compradores = {
        (c, p)
        for c, p in duckdb.sql(
            f"SELECT DISTINCT cliente_id, producto_id FROM '{COMPRAS}' "
            f"WHERE CAST(fecha AS DATE) > DATE '{fila.resumen['fecha_ref']}' "
            f"AND CAST(fecha AS DATE) <= DATE '{fila.resumen['fecha_ref']}' + {H}"
        ).fetchall()
    }
    filas = _leer(fila, "recompra.parquet")
    si = [f["p"] for f in filas if (f["cliente_id"], f["producto_id"]) in compradores]
    no = [f["p"] for f in filas if (f["cliente_id"], f["producto_id"]) not in compradores]
    assert si and no
    assert sum(si) / len(si) > 2 * sum(no) / len(no)

    primera = filas[0]
    assert {"ciclo", "p", "fecha_probable", "fecha_min", "fecha_max", "n_compras"} <= set(primera)
    assert primera["producto_nombre"].startswith("Producto sintético")
    assert f"{H} días" in primera["motivo"]
    assert [f["p"] for f in filas] == sorted((f["p"] for f in filas), reverse=True)


def test_umbral_filtra(db, dataset, cfg) -> None:
    fila, _ = _correr(db, dataset, cfg, tipos=["recompra"], umbral=0.6)
    filas = _leer(fila, "recompra.parquet")
    assert all(f["p"] >= 0.6 for f in filas)
    assert len(filas) == fila.resumen["recompra"]["recordatorios"]
    assert fila.resumen["recompra"]["pares_evaluados"] > len(filas)


def test_durables_quedan_fuera(db, dataset, cfg) -> None:
    fila, _ = _correr(db, dataset, cfg, umbral=0.0)
    durables = _durables()
    assert durables
    for nombre in ("recompra.parquet", "ciclos.parquet"):
        assert not {f["producto_id"] for f in _leer(fila, nombre)} & durables
    assert fila.resumen["totales"]["productos_durables_excluidos"] == len(durables)


def test_grupos_confirmados_se_aplican(db, dataset, cfg) -> None:
    confirmado = GrupoProducto(
        empresa_id=dataset.empresa_id, nombre="Grupo 2+3", estado="confirmado"
    )
    propuesto = GrupoProducto(empresa_id=dataset.empresa_id, nombre="Grupo 4", estado="propuesto")
    db.add_all([confirmado, propuesto])
    db.flush()
    for producto in db.query(Producto).filter(Producto.empresa_id == dataset.empresa_id):
        if producto.producto_id_origen in ("producto-002", "producto-003"):
            producto.grupo_id = confirmado.id
        elif producto.producto_id_origen == "producto-004":
            producto.grupo_id = propuesto.id
    db.flush()

    fila, _ = _correr(db, dataset, cfg, umbral=0.0)

    for nombre in ("recompra.parquet", "ciclos.parquet"):
        ids = {f["producto_id"] for f in _leer(fila, nombre)}
        assert f"grupo:{confirmado.id}" in ids
        assert not ids & {"producto-002", "producto-003"}
        assert "producto-004" in ids  # grupo solo propuesto: no se aplica
    ciclo = next(f for f in _leer(fila, "ciclos.parquet") if f["producto_id"].startswith("grupo:"))
    assert ciclo["producto_nombre"] == "Grupo 2+3"
    assert fila.resumen["totales"]["grupos_aplicados"] == 1


def test_metricas_resumen_y_eventos(db, dataset, cfg) -> None:
    fila, emitidos = _correr(db, dataset, cfg, horizonte=H, semanas_backtest=8)

    assert fila.metricas["horizonte"] == H and fila.metricas["semanas"] == 8
    assert fila.metricas["n_pares"] > 0
    assert fila.metricas["modelo"]["brier"]["media"] is not None
    assert fila.metricas["linea_base"]["brier"]["media"] is not None

    resumen = fila.resumen
    assert resumen["version_modelo"] == fila.version_modelo == orquestador.VERSION_MODELO
    assert resumen["parametros"]["horizonte"] == H
    assert resumen["parametros"]["min_compras"] == cfg.MIN_COMPRAS
    assert resumen["costo_ia"]["costo_estimado_usd"] == 0 and fila.costo_ia == resumen["costo_ia"]
    assert resumen["totales"]["filas"] > 0
    assert resumen["recompra"]["top_productos"] and resumen["ciclos"]["top_productos"]

    etapas = dict(emitidos)
    assert list(etapas) == ["leyendo", "ciclos", "prediccion", "backtest"]
    assert etapas["leyendo"]["filas"] == resumen["totales"]["filas"]
    assert etapas["ciclos"]["productos"] == resumen["ciclos"]["productos"]
    assert etapas["prediccion"]["pares"] == resumen["recompra"]["pares_evaluados"]
    assert etapas["backtest"]["pares"] == fila.metricas["n_pares"]


def test_parametros_y_tipos_invalidos(db, dataset, cfg) -> None:
    with pytest.raises(ValueError, match="tipos"):
        orquestador.ejecutar(db, _analisis(db, dataset, ["magia"]), lambda *_: None, cfg)
    with pytest.raises(ValueError):
        orquestador.ejecutar(db, _analisis(db, dataset, umbral=2), lambda *_: None, cfg)
    with pytest.raises(ValueError, match="período"):
        orquestador.ejecutar(db, _analisis(db, dataset, hasta="2000-01-01"), lambda *_: None, cfg)


def test_trabajo_analisis_de_punta_a_punta(db, dataset, cfg, monkeypatch) -> None:
    registro.descubrir()
    assert registro.obtener("analisis") is orquestador.analisis
    trabajo = Trabajo(empresa_id=dataset.empresa_id, tipo="analisis", estado="corriendo")
    db.add(trabajo)
    db.flush()
    fila = _analisis(db, dataset)
    fila.trabajo_id = trabajo.id
    db.commit()
    monkeypatch.setattr(orquestador, "settings", lambda: cfg)
    monkeypatch.setattr(eventos, "INTERVALO_MIN_S", 0.0)
    eventos.configurar(db.get_bind().url.render_as_string(hide_password=False))
    otra = _analisis(db, dataset, ["magia"])
    db.commit()
    try:
        orquestador.analisis(
            TrabajoEnCurso(
                trabajo.id, dataset.empresa_id, "analisis", {"analisis_id": str(fila.id)}
            )
        )
        with pytest.raises(ValueError):
            orquestador.analisis(
                TrabajoEnCurso(
                    trabajo.id, dataset.empresa_id, "analisis", {"analisis_id": str(otra.id)}
                )
            )
    finally:
        eventos._engine().dispose()
        eventos.configurar(None)

    db.expire_all()
    assert fila.estado == "listo" and fila.resumen and fila.metricas
    assert otra.estado == "error"
    etapas = [e.etapa for e in db.query(EventoTrabajo).filter_by(trabajo_id=trabajo.id)]
    assert etapas == ["leyendo", "ciclos", "prediccion", "backtest"]
