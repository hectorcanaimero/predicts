"""Tests de `predicts.productos` (catálogo, clasificación) y `api/productos.py`: la regla
previa sin Jev, el lote, el umbral de confianza, la caché, la corrección por la persona y el
aislamiento por empresa (ver specs/f4-analisis.md#F4.2.T1)."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from typesafe_sdk import ChoiceAnswer, Noul, NoulAnswer, SystemOneResponse, Usage

from predicts.app import crear_app
from predicts.auth.csrf import COOKIE_CSRF
from predicts.config import settings_para_tests
from predicts.db.modelos import Dataset, DecisionJev, Empresa, Producto, Usuario
from predicts.db.sesion import get_db
from predicts.productos.catalogo import actualizar_catalogo
from predicts.productos.clasificacion import TAMANO_LOTE, clasificar_productos

pytestmark = pytest.mark.db

CONTRASENA = "una-contrasena-larga"
_CFG = settings_para_tests()


# --- cliente Jev falso que responde según el tipo de pregunta recibida (Noul o Choice) ------


class ClienteJevLoteFalso:
    """Responde con un `Noul`/`Choice` fijo para cualquier clave del lote; guarda cada llamada
    (estado + preguntas) para poder revisar cuántas llamadas hizo y con qué tamaño de lote."""

    def __init__(
        self, noul: float = 0.5, opcion_choice: str | None = None, confianza_choice: float = 0.9
    ) -> None:
        self._noul = noul
        self._opcion_choice = opcion_choice
        self._confianza_choice = confianza_choice
        self.llamadas: list[tuple[object, dict]] = []

    def system_one(self, state: object, questions: dict) -> SystemOneResponse:
        self.llamadas.append((state, dict(questions)))
        respuestas: dict[str, object] = {}
        for clave, pregunta in questions.items():
            if isinstance(pregunta, Noul):
                respuestas[clave] = NoulAnswer(noul=self._noul)
            else:
                opcion = self._opcion_choice or next(iter(pregunta.criteria))
                respuestas[clave] = ChoiceAnswer(
                    choice=opcion, confidence=self._confianza_choice,
                    probabilities={opcion: self._confianza_choice},
                )
        return SystemOneResponse(
            model="jev-test", usage=Usage(input_tokens=1, output_tokens=1), answers=respuestas
        )


@pytest.fixture()
def empresa(db: Session) -> Empresa:
    empresa = Empresa(nombre="Tienda")
    db.add(empresa)
    db.flush()
    return empresa


def _producto(db: Session, empresa_id, nombre: str, **estadisticas: object) -> Producto:
    """Producto de prueba con categoría ya puesta por el CSV (por defecto), para que los tests
    de la regla de tipo no disparen de paso una pregunta de categoría a Jev; los tests de
    categoría la quitan explícitamente (`producto.categoria_origen = None`)."""
    producto = Producto(
        empresa_id=empresa_id, nombre_normalizado=nombre.lower(), nombre=nombre,
        categoria="otros", categoria_origen="csv", estadisticas=dict(estadisticas),
    )
    db.add(producto)
    db.flush()
    return producto


# --- regla previa sin Jev --------------------------------------------------------------------


def test_regla_previa_recompra_no_llama_a_jev(db, empresa) -> None:
    producto = _producto(
        db, empresa.id, "Leche", clientes=10, clientes_recompra=4, mediana_intervalo_dias=30,
        precio_medio=5.0,
    )
    cliente = ClienteJevLoteFalso()

    clasificar_productos(db, empresa.id, [producto], cliente=cliente, cfg=_CFG)

    assert producto.tipo == "recompra"
    assert producto.tipo_origen == "regla"
    assert producto.estado_revision == "ok"
    assert cliente.llamadas == []


def test_regla_previa_durable_no_llama_a_jev(db, empresa) -> None:
    producto = _producto(
        db, empresa.id, "Mesa", clientes=60, clientes_recompra=0, mediana_intervalo_dias=None,
        precio_medio=200.0,
    )
    cliente = ClienteJevLoteFalso()

    clasificar_productos(db, empresa.id, [producto], cliente=cliente, cfg=_CFG)

    assert producto.tipo == "durable"
    assert producto.tipo_origen == "regla"
    assert cliente.llamadas == []


def test_producto_ambiguo_va_a_jev(db, empresa) -> None:
    # 20% de recompra (< 30%) y mediana alta: ni recompra ni durable (tiene recompradores).
    producto = _producto(
        db, empresa.id, "Termo", clientes=10, clientes_recompra=2, mediana_intervalo_dias=200,
        precio_medio=30.0,
    )
    cliente = ClienteJevLoteFalso(noul=0.9)

    clasificar_productos(db, empresa.id, [producto], cliente=cliente, cfg=_CFG)

    assert len(cliente.llamadas) == 1
    assert producto.tipo == "recompra"
    assert producto.tipo_origen == "jev"
    assert producto.confianza == pytest.approx(0.9)


# --- lote de 50 productos por llamada ---------------------------------------------------------


def test_productos_ambiguos_se_piden_en_lotes_de_50(db, empresa) -> None:
    cantidad = TAMANO_LOTE + 1
    productos = [
        _producto(
            db, empresa.id, f"Producto {i}", clientes=10, clientes_recompra=2,
            mediana_intervalo_dias=200, precio_medio=10.0,
        )
        for i in range(cantidad)
    ]
    cliente = ClienteJevLoteFalso(noul=0.9)

    clasificar_productos(db, empresa.id, productos, cliente=cliente, cfg=_CFG)

    assert len(cliente.llamadas) == 2, "51 productos ambiguos deben hacer 2 llamadas (50 + 1)"
    tamanos = sorted(len(preguntas) for _, preguntas in cliente.llamadas)
    assert tamanos == [1, TAMANO_LOTE]
    assert all(p.tipo_origen == "jev" for p in productos)


# --- umbral de CONFIANZA_JEV: confianza baja -> revisar ---------------------------------------


def test_confianza_baja_marca_revisar(db, empresa) -> None:
    producto = _producto(
        db, empresa.id, "Termo", clientes=10, clientes_recompra=2, mediana_intervalo_dias=200,
        precio_medio=30.0,
    )
    cfg = settings_para_tests()
    # noul >= 0.5 -> opcion "si", confianza = noul (por debajo de CONFIANZA_JEV).
    cliente = ClienteJevLoteFalso(noul=cfg.CONFIANZA_JEV - 0.1)

    clasificar_productos(db, empresa.id, [producto], cliente=cliente, cfg=cfg)

    assert producto.confianza < cfg.CONFIANZA_JEV
    assert producto.estado_revision == "revisar"


def test_confianza_alta_queda_ok(db, empresa) -> None:
    producto = _producto(
        db, empresa.id, "Termo", clientes=10, clientes_recompra=2, mediana_intervalo_dias=200,
        precio_medio=30.0,
    )
    cfg = settings_para_tests()
    cliente = ClienteJevLoteFalso(noul=cfg.CONFIANZA_JEV + 0.1)

    clasificar_productos(db, empresa.id, [producto], cliente=cliente, cfg=cfg)

    assert producto.confianza >= cfg.CONFIANZA_JEV
    assert producto.estado_revision == "ok"


# --- caché: un producto ya clasificado no se vuelve a preguntar -------------------------------


def test_cache_no_vuelve_a_preguntar_salvo_forzar(db, empresa) -> None:
    producto = _producto(
        db, empresa.id, "Termo", clientes=10, clientes_recompra=2, mediana_intervalo_dias=200,
        precio_medio=30.0,
    )
    cliente = ClienteJevLoteFalso(noul=0.9)
    clasificar_productos(db, empresa.id, [producto], cliente=cliente, cfg=_CFG)
    assert len(cliente.llamadas) == 1

    clasificar_productos(db, empresa.id, [producto], cliente=cliente, cfg=_CFG)
    assert len(cliente.llamadas) == 1, "ya clasificado: no debe volver a preguntar"

    clasificar_productos(db, empresa.id, [producto], cliente=cliente, forzar=True, cfg=_CFG)
    assert len(cliente.llamadas) == 2, "forzar=True sí debe volver a preguntar"


# --- categoría: solo si el CSV no la trae ------------------------------------------------------


def test_categoria_se_pregunta_solo_si_falta(db, empresa) -> None:
    sin_categoria = _producto(db, empresa.id, "Termo", clientes=5, clientes_recompra=0)
    sin_categoria.categoria, sin_categoria.categoria_origen = None, None
    con_categoria_csv = _producto(db, empresa.id, "Taza", clientes=5, clientes_recompra=0)
    con_categoria_csv.categoria = "menaje_cocina"
    db.flush()

    cliente = ClienteJevLoteFalso(opcion_choice="herramientas")
    clasificar_productos(
        db, empresa.id, [sin_categoria, con_categoria_csv], cliente=cliente, cfg=_CFG
    )

    llamadas_categoria = [
        preguntas
        for _, preguntas in cliente.llamadas
        if any(clave.startswith("categoria::") for clave in preguntas)
    ]
    assert len(llamadas_categoria) == 1
    assert sin_categoria.categoria == "herramientas"
    assert sin_categoria.categoria_origen == "jev"
    assert con_categoria_csv.categoria == "menaje_cocina"
    assert con_categoria_csv.categoria_origen == "csv"


def test_registra_decision_jev_para_tipo_y_categoria(db, empresa) -> None:
    producto = _producto(db, empresa.id, "Termo", clientes=10, clientes_recompra=2,
                          mediana_intervalo_dias=200, precio_medio=30.0)
    producto.categoria, producto.categoria_origen = None, None
    db.flush()
    cliente = ClienteJevLoteFalso(noul=0.9, opcion_choice="otros")

    clasificar_productos(db, empresa.id, [producto], cliente=cliente, cfg=_CFG)
    db.commit()

    decisiones = db.query(DecisionJev).filter(DecisionJev.referencia == producto.id).all()
    tipos = sorted(d.tipo for d in decisiones)
    assert tipos == ["categoria", "tipo_producto"]


# --- catalogo.actualizar_catalogo: estadísticas y categoría del CSV ---------------------------


def _escribir_parquet(ruta: Path) -> None:
    con = duckdb.connect(":memory:")
    try:
        con.execute(
            """
            CREATE TABLE t AS SELECT * FROM (VALUES
                ('c1', 'SKU1', 'Leche Entera', 'lacteos', 5.0, TIMESTAMP '2024-01-01'),
                ('c1', 'SKU1', 'Leche Entera', 'lacteos', 5.0, TIMESTAMP '2024-01-10'),
                ('c1', 'SKU1', 'Leche Entera', 'lacteos', 5.5, TIMESTAMP '2024-01-20'),
                ('c2', 'SKU1', 'leche entera', NULL, 5.2, TIMESTAMP '2024-02-01'),
                ('c3', 'SKU2', 'Mesa de Madera', NULL, 100.0, TIMESTAMP '2024-01-01')
            ) AS t(cliente_id, producto_id, producto_nombre, categoria, precio_unitario, fecha)
            """
        )
        con.execute("COPY t TO ? (FORMAT PARQUET)", [str(ruta)])
    finally:
        con.close()


class _DatasetFalso:
    def __init__(self, empresa_id, ruta_parquet: str) -> None:
        self.empresa_id = empresa_id
        self.ruta_parquet = ruta_parquet


def test_actualizar_catalogo_calcula_estadisticas_y_usa_categoria_del_csv(
    db, empresa, tmp_path
) -> None:
    ruta = tmp_path / "compras.parquet"
    _escribir_parquet(ruta)
    dataset = _DatasetFalso(empresa.id, str(ruta))

    tocados = actualizar_catalogo(db, dataset, cfg=settings_para_tests())
    db.commit()

    por_nombre = {p.nombre_normalizado: p for p in tocados}
    leche = por_nombre["leche entera"]
    assert leche.estadisticas["clientes"] == 2
    assert leche.estadisticas["clientes_recompra"] == 1
    assert leche.estadisticas["mediana_intervalo_dias"] == pytest.approx(9.5)
    assert leche.estadisticas["precio_medio"] == pytest.approx(5.175)
    assert leche.categoria == "lacteos"
    assert leche.categoria_origen == "csv"

    mesa = por_nombre["mesa de madera"]
    assert mesa.estadisticas["clientes"] == 1
    assert mesa.estadisticas["clientes_recompra"] == 0
    assert mesa.categoria is None


def test_actualizar_catalogo_hace_upsert_por_empresa_y_nombre(db, empresa, tmp_path) -> None:
    ruta = tmp_path / "compras.parquet"
    _escribir_parquet(ruta)
    dataset = _DatasetFalso(empresa.id, str(ruta))

    actualizar_catalogo(db, dataset, cfg=settings_para_tests())
    db.commit()
    total_antes = db.query(Producto).filter(Producto.empresa_id == empresa.id).count()

    actualizar_catalogo(db, dataset, cfg=settings_para_tests())
    db.commit()
    total_despues = db.query(Producto).filter(Producto.empresa_id == empresa.id).count()

    assert total_antes == total_despues == 2


# --- API: listar, corregir y aislamiento por empresa ------------------------------------------


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


def _crear_proyecto(cliente: TestClient) -> str:
    r = cliente.post("/proyectos", json={"nombre": "Campaña"}, headers=_csrf(cliente))
    assert r.status_code == 201
    return r.json()["id"]


def _crear_dataset(db: Session, empresa_id, proyecto_id: str) -> str:
    dataset = Dataset(
        empresa_id=empresa_id, proyecto_id=proyecto_id, nombre_archivo="compras.csv",
        tamano_bytes=10, sha256="a" * 64,
    )
    db.add(dataset)
    db.commit()
    return str(dataset.id)


def test_listar_productos_filtra_por_estado(db, ana) -> None:
    empresa_id = db.scalar(select(Usuario.empresa_id).where(Usuario.email == "ana@ejemplo.com"))
    dataset_id = _crear_dataset(db, empresa_id, _crear_proyecto(ana))

    ok = _producto(db, empresa_id, "Leche", clientes=1)
    ok.tipo, ok.tipo_origen, ok.estado_revision = "recompra", "regla", "ok"
    revisar = _producto(db, empresa_id, "Termo", clientes=1)
    revisar.tipo, revisar.tipo_origen, revisar.estado_revision = "recompra", "jev", "revisar"
    db.commit()

    r = ana.get(f"/datasets/{dataset_id}/productos?estado=revisar")
    assert r.status_code == 200
    nombres = [p["nombre"] for p in r.json()]
    assert nombres == ["Termo"]

    r = ana.get(f"/datasets/{dataset_id}/productos")
    assert r.status_code == 200
    assert sorted(p["nombre"] for p in r.json()) == ["Leche", "Termo"]


def test_corregir_producto_registra_decision_jev(db, ana) -> None:
    empresa_id = db.scalar(select(Usuario.empresa_id).where(Usuario.email == "ana@ejemplo.com"))
    producto = _producto(db, empresa_id, "Termo", clientes=10, clientes_recompra=2)
    decision = DecisionJev(
        empresa_id=empresa_id, tipo="tipo_producto", referencia=producto.id,
        opcion="durable", confianza=0.55,
    )
    producto.tipo, producto.tipo_origen = "durable", "jev"
    db.add(decision)
    db.commit()

    r = ana.patch(
        f"/productos/{producto.id}", json={"tipo": "recompra"}, headers=_csrf(ana)
    )
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["tipo"] == "recompra"
    assert cuerpo["tipo_origen"] == "persona"
    assert cuerpo["estado_revision"] == "ok"

    db.expire_all()
    guardada = db.get(DecisionJev, decision.id)
    assert guardada.corregida_a == "recompra"
    assert guardada.corregida_por is not None
    assert guardada.corregida_en is not None


def test_corregir_sin_nada_falla(db, ana) -> None:
    empresa_id = db.scalar(select(Usuario.empresa_id).where(Usuario.email == "ana@ejemplo.com"))
    producto = _producto(db, empresa_id, "Termo", clientes=1)
    db.commit()

    r = ana.patch(f"/productos/{producto.id}", json={}, headers=_csrf(ana))
    assert r.status_code == 422
    assert r.json()["codigo"] == "nada_que_corregir"


def test_otra_empresa_no_ve_ni_corrige_el_producto(db, ana, beto) -> None:
    empresa_id = db.scalar(select(Usuario.empresa_id).where(Usuario.email == "ana@ejemplo.com"))
    dataset_id = _crear_dataset(db, empresa_id, _crear_proyecto(ana))
    producto = _producto(db, empresa_id, "Termo", clientes=1)
    db.commit()

    assert beto.get(f"/datasets/{dataset_id}/productos").status_code == 404
    r = beto.patch(f"/productos/{producto.id}", json={"tipo": "durable"}, headers=_csrf(beto))
    assert r.status_code == 404
