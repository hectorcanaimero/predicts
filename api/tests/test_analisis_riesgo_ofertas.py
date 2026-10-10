"""Tests de riesgo de abandono, ofertas y ¿contactar? (ver specs/f4-analisis.md#F4.3.T2): riesgo
contra `abandono_en` del sintético (precisión y cobertura reportadas), lift calculado a mano en un
caso chico, la lista de ofertas (ruta y uso en el análisis) y que Jev solo recibe los casos límite.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import duckdb
import pytest
import test_analisis_recompra as base
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from typesafe_sdk import NoulAnswer, SystemOneResponse, Usage

from predicts.analisis import contactar, ofertas, orquestador
from predicts.api.datasets_ofertas import leer_lista
from predicts.app import crear_app
from predicts.auth.csrf import COOKIE_CSRF
from predicts.db.modelos import DecisionJev, Usuario
from predicts.db.sesion import get_db
from predicts.errores import ErrorApi
from predicts.modelo import Ajuste, ParamsModelo

H = 14
COMPRAS, VERDAD, _correr, _leer = base.COMPRAS, base.VERDAD, base._correr, base._leer
cfg, dataset = base.cfg, base.dataset  # fixtures compartidas con los tests de recompra


class JevFalso:
    """Contesta cada `Noul` con el mismo valor y guarda las preguntas de cada llamada."""

    def __init__(self, noul: float) -> None:
        self.noul = noul
        self.llamadas: list[dict] = []

    def system_one(self, state: object, questions: dict) -> SystemOneResponse:
        self.llamadas.append(dict(questions))
        return SystemOneResponse(
            model="jev-test",
            usage=Usage(input_tokens=1, output_tokens=1),
            answers={k: NoulAnswer(noul=self.noul) for k in questions},
        )

    def clientes(self) -> list[str]:
        return [k.removeprefix("cliente::") for lote in self.llamadas for k in lote]


# --- riesgo ---------------------------------------------------------------------------------


@pytest.mark.db
def test_riesgo_contra_abandono_en(db, dataset, cfg) -> None:
    fila, emitidos = _correr(db, dataset, cfg, tipos=["riesgo"])
    filas = _leer(fila, "riesgo.parquet")
    pares = {(f["cliente_id"], f["producto_id"]) for f in filas if f["nivel"] == "producto"}
    # Verdad: pares regulares (≥ MIN_COMPRAS días de compra) que abandonaron antes de fecha_ref.
    abandonados = {
        (c, p)
        for c, p in duckdb.sql(
            f"""
            SELECT v.cliente_id, v.producto_id FROM '{VERDAD}' v
            JOIN (SELECT cliente_id, producto_id, count(DISTINCT CAST(fecha AS DATE)) AS n
                  FROM '{COMPRAS}' GROUP BY ALL) c USING (cliente_id, producto_id)
            WHERE v.abandono_en IS NOT NULL AND c.n >= {cfg.MIN_COMPRAS}
            """
        ).fetchall()
    }
    aciertos = len(pares & abandonados)
    precision, cobertura = aciertos / len(pares), aciertos / len(abandonados)
    print(
        f"\nriesgo (factor 2): precisión {precision:.2f}, cobertura {cobertura:.2f} "
        f"({aciertos}/{len(pares)} marcados, {len(abandonados)} abandonos reales)"
    )
    assert precision >= 0.9 and cobertura >= 0.75

    # Orden por valor histórico (el sintético tiene precio), motivo legible y nivel tienda.
    valores = [f["valor"] for f in filas]
    assert valores == sorted(valores, reverse=True)
    assert all(f["dias_desde_ultima"] > f["ciclo"] + 2 * f["dispersion"] for f in filas)
    assert any(f["nivel"] == "tienda" and f["producto_id"] is None for f in filas)
    assert "más de lo habitual" in filas[0]["motivo"]
    assert fila.resumen["riesgo"]["pares"] == len(pares)
    assert dict(emitidos)["riesgo"]["pares"] == len(pares)

    # El factor es configurable: más chico, más marcados.
    laxo, _ = _correr(db, dataset, cfg, tipos=["riesgo"], factor_riesgo=0.0)
    assert len(_leer(laxo, "riesgo.parquet")) >= len(filas)


# --- ofertas: lift a mano -------------------------------------------------------------------


def _chico(
    resultados: Path, lista: Path | None = None, max_ofertas: int = 5
) -> tuple[duckdb.DuckDBPyConnection, dict]:
    """5 clientes; A: c1 c2; B: c1 c2 c3; C: c3 c4 c5.

    lift(A,B) = n_ab·N / (n_a·n_b) = 2·5 / (2·3) = 5/3. B–C tiene un solo cliente en común
    (c3) y A–C ninguno: no pasan el soporte mínimo.
    """
    con = duckdb.connect()
    filas = [("c1", "A"), ("c2", "A"), ("c1", "B"), ("c2", "B"), ("c3", "B"),
             ("c3", "C"), ("c4", "C"), ("c5", "C")]  # fmt: skip
    con.execute(
        "CREATE TABLE compras (cliente_id VARCHAR, producto_id VARCHAR, producto_id_origen VARCHAR,"
        " fecha TIMESTAMP)"
    )
    con.executemany("INSERT INTO compras VALUES (?, ?, ?, TIMESTAMP '2024-01-01')",
                    [(c, p, p) for c, p in filas])  # fmt: skip
    con.execute("CREATE TABLE nombres AS SELECT * FROM (VALUES ('A', 'Café'), ('B', 'Leche'), "
                "('C', 'Pan')) t(producto_id, producto_nombre)")  # fmt: skip
    con.execute("CREATE TABLE pred (cliente_id VARCHAR, producto_id VARCHAR, p DOUBLE)")
    resumen = ofertas.calcular(
        Ajuste(con, ParamsModelo()),
        "compras",
        "nombres",
        "pred",
        0.5,
        7,
        lista,
        max_ofertas,
        resultados,
    )
    return con, resumen


def test_lift_calculado_a_mano(tmp_path) -> None:
    con, resumen = _chico(tmp_path)
    lift = {(a, b): (n, x) for a, b, n, x in con.execute(
        "SELECT producto_a, producto_b, n_ab, lift FROM ofertas_lift").fetchall()}  # fmt: skip
    assert lift.keys() == {("A", "B"), ("B", "A")}
    assert lift[("A", "B")][0] == 2
    assert lift[("A", "B")][1] == pytest.approx(5 / 3)

    # c3 compra B y no A → A por co-compra, puntaje 1 − 1/lift = 0,4.
    ofertas_ = con.execute(
        "SELECT cliente_id, producto_id, puntaje, fuentes, motivo FROM res_ofertas"
    ).fetchall()
    assert [(c, p, f) for c, p, _, f, _ in ofertas_] == [("c3", "A", ["cocompra"])]
    assert ofertas_[0][2] == pytest.approx(1 - 3 / 5)
    assert "«Leche»" in ofertas_[0][4] and "1.7 veces" in ofertas_[0][4]
    assert resumen["pares_lift"] == 2 and resumen["lista_productos"] == 0


def test_lista_de_ofertas_suma_candidatos_y_sube_el_puntaje(tmp_path) -> None:
    lista = tmp_path / ofertas.LISTA
    duckdb.sql("SELECT * FROM (VALUES ('A', 0.2), ('C', 0.5), ('Z', 0.9)) t(producto_id, "
               "descuento)").write_parquet(str(lista))  # fmt: skip
    con, resumen = _chico(tmp_path, lista)
    filas = {(c, p): (x, f, d, m) for c, p, x, f, d, m in con.execute(
        "SELECT cliente_id, producto_id, puntaje, fuentes, descuento, motivo FROM res_ofertas"
    ).fetchall()}  # fmt: skip
    # Co-compra con descuento: 0,4 · 1,2.
    assert filas[("c3", "A")][0] == pytest.approx(0.4 * 1.2)
    assert "20 % de descuento" in filas[("c3", "A")][3]
    # C en oferta y ya comprado por c3, c4, c5: BASE_OFERTA_HISTORIAL · 1,5.
    for c in ("c3", "c4", "c5"):
        x, f, d, _ = filas[(c, "C")]
        assert f == ["oferta"] and d == 0.5
        assert x == pytest.approx(ofertas.BASE_OFERTA_HISTORIAL * 1.5)
    # A en oferta y ya comprado por c1 y c2: también entra por la lista.
    assert filas[("c1", "A")][1] == ["oferta"]
    assert filas[("c1", "A")][0] == pytest.approx(ofertas.BASE_OFERTA_HISTORIAL * 1.2)
    assert resumen["lista_productos"] == 2  # Z no está en las compras

    # Tope de N por cliente: c3 tiene dos candidatos, con N = 1 queda el de mayor puntaje.
    con, _ = _chico(tmp_path, lista, max_ofertas=1)
    assert con.execute("SELECT cliente_id, producto_id FROM res_ofertas WHERE cliente_id = 'c3'"
                       ).fetchall() == [("c3", "A")]  # fmt: skip


def test_leer_lista_valida_y_normaliza() -> None:
    assert leer_lista(b"producto_id,descuento\nA,0.2\nB,15\nA,0.3\n") == {"A": 0.3, "B": 0.15}
    assert leer_lista("﻿Producto_ID;Descuento\nA;0,25\n".encode()) == {"A": 0.25}
    for malo in (b"producto,precio\nA,1\n", b"producto_id,descuento\nA,0\n",
                 b"producto_id,descuento\nA,abc\n", b"producto_id,descuento\n",
                 b"producto_id,descuento\nA,100\n"):  # fmt: skip
        with pytest.raises(ErrorApi):
            leer_lista(malo)


@pytest.mark.db
def test_ofertas_en_el_analisis_con_la_lista(db, dataset, cfg) -> None:
    sin, _ = _correr(db, dataset, cfg, tipos=["ofertas"], horizonte=H, max_ofertas=3)
    filas = _leer(sin, "ofertas.parquet")
    assert filas and all(f["descuento"] == 0 for f in filas)
    por_cliente: dict[str, int] = {}
    for f in filas:
        por_cliente[f["cliente_id"]] = por_cliente.get(f["cliente_id"], 0) + 1
    assert max(por_cliente.values()) <= 3

    duckdb.sql("SELECT 'producto-004' AS producto_id, 0.3 AS descuento").write_parquet(
        str(Path(dataset.ruta_parquet).parent / ofertas.LISTA)
    )
    con_lista, _ = _correr(db, dataset, cfg, tipos=["ofertas"], horizonte=H, max_ofertas=3)
    filas = _leer(con_lista, "ofertas.parquet")
    en_oferta = [f for f in filas if f["producto_id"] == "producto-004"]
    assert en_oferta and all(f["descuento"] == pytest.approx(0.3) for f in en_oferta)
    assert con_lista.resumen["ofertas"]["lista_productos"] == 1
    assert {f["producto_id"] for f in filas} - {"producto-004"}  # no solo la lista


# --- ruta POST /datasets/{id}/ofertas -------------------------------------------------------


@pytest.fixture()
def app(db: Session, cfg, monkeypatch):
    monkeypatch.setattr("predicts.auth.sesiones.settings", lambda: cfg)
    monkeypatch.setattr("predicts.api.datasets_ingesta.settings", lambda: cfg)
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


@pytest.mark.db
def test_ruta_subir_lista_de_ofertas(db, dataset, app, cfg) -> None:
    ana = _cliente(app, "Tienda Ana", "ana@ejemplo.com")
    beto = _cliente(app, "Tienda Beto", "beto@ejemplo.com")
    dataset.empresa_id = db.scalar(
        select(Usuario.empresa_id).where(Usuario.email == "ana@ejemplo.com")
    )
    db.commit()
    url = f"/datasets/{dataset.id}/ofertas"

    def subir(cliente: TestClient, contenido: bytes):
        return cliente.post(
            url,
            files={"archivo": ("ofertas.csv", contenido, "text/csv")},
            headers={"X-CSRF-Token": cliente.cookies[COOKIE_CSRF]},
        )

    r = subir(ana, b"producto_id,descuento\nproducto-004,30\nproducto-005,0.1\n")
    assert r.status_code == 201 and r.json() == {"productos": 2}
    ruta = Path(cfg.DATA_DIR) / str(dataset.empresa_id) / str(dataset.id) / ofertas.LISTA
    assert dict(duckdb.sql(f"SELECT * FROM '{ruta}'").fetchall()) == pytest.approx(
        {"producto-004": 0.3, "producto-005": 0.1}
    )
    assert subir(ana, b"producto_id,descuento\nproducto-004,-1\n").status_code == 422
    assert subir(beto, b"producto_id,descuento\nproducto-004,30\n").status_code == 404


# --- ¿contactar? ----------------------------------------------------------------------------


def _limite_esperado(db, dataset, cfg, umbral: float) -> tuple[set[str], set[str]]:
    """Casos límite y todos los clientes candidatos, recalculados desde los Parquet de recompra
    (con umbral − margen) y riesgo, sin pasar por `contactar`."""
    fila, _ = _correr(
        db, dataset, cfg, tipos=["recompra", "riesgo"], horizonte=H,
        umbral=umbral - contactar.MARGEN,
    )  # fmt: skip
    rec = _leer(fila, "recompra.parquet")
    en_riesgo = {f["cliente_id"] for f in _leer(fila, "riesgo.parquet")}
    con_rec = {f["cliente_id"] for f in rec}
    cerca = {f["cliente_id"] for f in rec if abs(f["p"] - umbral) <= contactar.MARGEN}
    dias: dict[tuple, int] = {}
    for f in rec:
        if f["p"] >= umbral:
            clave = (f["cliente_id"], f["fecha_probable"])
            dias[clave] = dias.get(clave, 0) + 1
    mismo_dia = {c for (c, _), n in dias.items() if n >= 2}
    return cerca | mismo_dia | (en_riesgo & con_rec), con_rec | en_riesgo


@pytest.mark.db
def test_jev_solo_recibe_los_casos_limite(db, dataset, cfg) -> None:
    umbral = 0.5
    limite, candidatos = _limite_esperado(db, dataset, cfg, umbral)
    jev = JevFalso(noul=0.95)
    fila = _correr_contactar(db, dataset, cfg, jev, umbral)

    preguntados = jev.clientes()
    print(f"\ncontactar: {len(candidatos)} clientes, {len(preguntados)} a Jev")
    assert limite and set(preguntados) == limite and len(preguntados) == len(limite)
    assert all(len(lote) <= contactar.TAMANO_LOTE for lote in jev.llamadas)

    filas = _leer(fila, "contactar.parquet")
    assert {f["cliente_id"] for f in filas} == candidatos
    regla = [f for f in filas if f["origen"] == "regla"]
    assert regla and not {f["cliente_id"] for f in regla} & limite
    assert all(f["decision"] == "contactar" for f in filas)
    assert all(f["confianza"] == pytest.approx(0.95) for f in filas if f["origen"] == "jev")

    decisiones = db.scalars(select(DecisionJev).where(DecisionJev.referencia == fila.id)).all()
    assert {d.entrada_resumida["cliente_id"] for d in decisiones} == limite
    assert all(d.tipo == "contactar" for d in decisiones)
    assert fila.resumen["contactar"]["por_jev"] == len(limite)
    assert fila.costo_ia["llamadas"]["jev"] == len(jev.llamadas)


@pytest.mark.db
@pytest.mark.parametrize(("noul", "esperado"), [(0.6, "revisar"), (0.1, "no_contactar")])
def test_confianza_baja_va_a_revisar(db, dataset, cfg, noul, esperado) -> None:
    fila = _correr_contactar(db, dataset, cfg, JevFalso(noul=noul), 0.5)
    jev = [f for f in _leer(fila, "contactar.parquet") if f["origen"] == "jev"]
    assert jev and all(f["decision"] == esperado for f in jev)


def _correr_contactar(db, dataset, cfg, jev: JevFalso, umbral: float):
    fila = base._analisis(db, dataset, ["contactar"], horizonte=H, umbral=umbral)
    orquestador.ejecutar(db, fila, lambda *_: None, cfg, cliente_jev=jev)
    return fila
