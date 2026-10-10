"""Tests del agente analista (ver specs/f7-agente.md#F7.1.T1), sin red: `consultar` sobre el
sintético (vistas, tope de filas y de tiempo, cada sentencia peligrosa rechazada) y el grafo con
un LLM falso que emite llamadas a herramientas (flujo, tope de consultas, consultas rechazadas).
La ruta `POST /agente/preguntas` (aislamiento por empresa, costo) necesita Postgres (`db`).
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import date
from pathlib import Path

import duckdb
import pyarrow as pa
import pytest
import test_analisis_recompra as base
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from sqlalchemy import select
from sqlalchemy.orm import Session

from predicts.agente import grafo, sql
from predicts.agente.sql import ConsultaRechazada, abrir, consultar
from predicts.analisis import ciclos, recompra, riesgo
from predicts.api.agente import obtener_llm
from predicts.app import crear_app
from predicts.auth.csrf import COOKIE_CSRF
from predicts.db.modelos import Usuario
from predicts.db.sesion import get_db
from predicts.ia import Contador
from predicts.modelo import ParamsModelo, ajustar

COMPRAS = base.COMPRAS
cfg, dataset = base.cfg, base.dataset  # fixtures compartidas (solo las usa el test con `db`)


@pytest.fixture(scope="module")
def resultados(tmp_path_factory) -> Path:
    """Resultados de ciclos, recompra y riesgo del sintético (sin ofertas), como un análisis."""
    carpeta = tmp_path_factory.mktemp("resultados")
    con = duckdb.connect()
    con.execute(f"CREATE TABLE compras AS SELECT * FROM '{COMPRAS}'")
    con.execute(
        "CREATE TABLE nombres AS SELECT producto_id, any_value(producto_nombre) AS "
        "producto_nombre FROM compras GROUP BY 1"
    )
    fecha_ref = con.execute("SELECT CAST(max(fecha) AS DATE) FROM compras").fetchone()[0]
    ajuste = ajustar(con, "compras", ParamsModelo(min_compras=3))
    ciclos.calcular(ajuste, "nombres", carpeta)
    recompra.calcular(ajuste, "nombres", fecha_ref, 14, 0.5, carpeta)
    riesgo.calcular(ajuste, "compras", "nombres", fecha_ref, 2.0, carpeta)
    con.close()
    return carpeta


def _productos() -> pa.Table:
    return pa.table(
        {
            "producto_id": ["producto-001", "producto-002"],
            "producto_nombre": ["Producto sintético 001", "Producto sintético 002"],
            "categoria": ["limpieza", "muebles"],
            "tipo": ["recompra", "durable"],
            "grupo_producto_id": [None, None],
            "grupo_nombre": [None, None],
        },
        schema=pa.schema([(c, pa.string()) for c in sql.VISTAS["productos"][1]]),
    )


@pytest.fixture()
def conexion(resultados) -> Generator[sql.Conexion]:
    c = abrir(COMPRAS, resultados, _productos())
    yield c
    c.con.close()


# --- consultar --------------------------------------------------------------------------------


def test_vistas_y_esquema(conexion) -> None:
    assert conexion.vistas == ["compras", "productos", "predicciones", "ciclos", "riesgo"]
    assert "cliente_id (VARCHAR): id del cliente" in conexion.esquema
    assert "probabilidad de recompra" in conexion.esquema
    assert "No disponibles (sin análisis que las genere): ofertas" in conexion.esquema


def test_consultar_con_el_sintetico(conexion) -> None:
    (clientes,) = duckdb.sql(f"SELECT count(DISTINCT cliente_id) FROM '{COMPRAS}'").fetchone()
    r = consultar(conexion, "SELECT count(DISTINCT cliente_id) AS clientes FROM compras")
    assert r.columnas == ["clientes"] and r.filas == [{"clientes": clientes}]
    assert r.n_filas == 1 and not r.truncado

    r = consultar(
        conexion,
        """
        WITH ultimas AS (SELECT cliente_id, producto_id, max(fecha) AS ultima
                         FROM compras GROUP BY ALL)
        SELECT p.cliente_id, p.producto_id, p.p, u.ultima
        FROM predicciones p JOIN ultimas u USING (cliente_id, producto_id)
        ORDER BY p.p DESC LIMIT 5
        """,
    )
    assert r.n_filas == 5 and all(0 <= f["p"] <= 1 for f in r.filas)

    r = consultar(conexion, "SELECT tipo FROM productos WHERE producto_id = 'producto-002'")
    assert r.filas == [{"tipo": "durable"}]
    r = consultar(conexion, "SELECT count(*) AS n FROM ciclos WHERE ciclo_mediano > 0")
    assert r.filas[0]["n"] > 0


def test_tope_de_filas(conexion) -> None:
    r = consultar(conexion, "SELECT * FROM range(5000)")
    assert r.n_filas == sql.MAX_FILAS == len(r.filas) and r.truncado


def test_tope_de_tiempo(conexion) -> None:
    lenta = "SELECT sum(a.range * b.range) FROM range(200000) a, range(200000) b"
    with pytest.raises(ConsultaRechazada, match="tiempo"):
        consultar(conexion, lenta, timeout_s=0.2)
    assert consultar(conexion, "SELECT 1 AS x").filas == [{"x": 1}]  # la conexión sigue viva


PELIGROSAS = [
    "SELECT * FROM read_csv('/etc/passwd')",
    "SELECT * FROM read_csv_auto('/etc/passwd')",
    "SELECT * FROM READ_PARQUET('/tmp/otro.parquet')",
    "SELECT * FROM parquet_scan('/tmp/otro.parquet')",
    "SELECT * FROM read_json('/tmp/x.json')",
    "SELECT * FROM read_text('/etc/passwd')",
    "SELECT * FROM glob('/*')",
    "SELECT * FROM '/etc/passwd'",
    "SELECT * FROM 'https://example.com/x.csv'",
    "WITH x AS (SELECT 1) SELECT * FROM read_csv('/etc/passwd')",
    "INSTALL httpfs",
    "LOAD httpfs",
    "SELECT * FROM httpfs",
    "COPY compras TO '/tmp/fuga.csv'",
    "COPY (SELECT * FROM compras) TO '/tmp/fuga.parquet' (FORMAT parquet)",
    "ATTACH '/tmp/otra.duckdb' AS otra",
    "DETACH otra",
    "SELECT 1; COPY compras TO '/tmp/fuga.csv'",
    "SELECT 1; SELECT 2",
    "INSERT INTO productos VALUES ('x', 'x', 'x', 'x', NULL, NULL)",
    "UPDATE productos SET tipo = 'durable'",
    "DELETE FROM productos",
    "CREATE TABLE x AS SELECT 1",
    "DROP VIEW compras",
    "SET enable_external_access = true",
    "PRAGMA database_list",
    "EXPORT DATABASE '/tmp/fuga'",
    "SELECT getenv('HOME')",
    "SELECT * FROM query('SELECT 1')",
    "",
]


@pytest.mark.parametrize("sentencia", PELIGROSAS)
def test_sentencia_peligrosa_rechazada(conexion, sentencia: str) -> None:
    with pytest.raises(ConsultaRechazada):
        consultar(conexion, sentencia)


def test_la_conexion_bloquea_archivos_aunque_falle_la_validacion(conexion) -> None:
    for directa in (
        "SELECT * FROM read_csv('/etc/passwd')",
        "SET enable_external_access = true",
        "SET memory_limit = '64GB'",
    ):
        with pytest.raises(duckdb.Error):
            conexion.con.execute(directa)


# --- grafo con LLM falso ----------------------------------------------------------------------


def _llamada(nombre: str, n: int, **args) -> dict:
    return {"name": nombre, "args": args, "id": f"llamada-{n}", "type": "tool_call"}


def _ai(*llamadas: dict, texto: str = "") -> AIMessage:
    return AIMessage(
        content=texto,
        tool_calls=list(llamadas),
        usage_metadata={"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100},
    )


class LLMFalso:
    """Devuelve `guion(mensajes, con_herramientas)` y guarda cada invocación."""

    def __init__(self, guion) -> None:
        self.guion = guion
        self.invocaciones: list[tuple[list, bool]] = []

    def bind_tools(self, herramientas):
        assert {h["function"]["name"] for h in herramientas} == {
            "consultar_sql",
            "describir_dataset",
        }
        return _ConHerramientas(self)

    def invoke(self, mensajes, con_herramientas: bool = False) -> AIMessage:
        self.invocaciones.append((list(mensajes), con_herramientas))
        return self.guion(mensajes, con_herramientas)


class _ConHerramientas:
    def __init__(self, llm: LLMFalso) -> None:
        self.llm = llm

    def invoke(self, mensajes) -> AIMessage:
        return self.llm.invoke(mensajes, con_herramientas=True)


def _final(respuesta: str, *advertencias: str) -> AIMessage:
    return _ai(texto=f'{{"respuesta": "{respuesta}", "advertencias": {list(advertencias)!r}}}'
               .replace("'", '"'))  # fmt: skip


def test_flujo_describir_consultar_responder(conexion) -> None:
    sql_clientes = "SELECT count(DISTINCT cliente_id) AS clientes FROM compras"
    guion = iter(
        [
            _ai(_llamada("describir_dataset", 1)),
            _ai(_llamada("consultar_sql", 2, sql=sql_clientes)),
            _final("Hay N clientes.", "Datos hasta la última fecha del dataset."),
        ]
    )
    llm = LLMFalso(lambda m, h: next(guion))
    contador = Contador()
    historial = [HumanMessage("hola"), AIMessage("¿En qué te ayudo?")]

    r = grafo.preguntar(conexion, "¿Cuántos clientes hay?", historial, llm, contador)

    (clientes,) = duckdb.sql(f"SELECT count(DISTINCT cliente_id) FROM '{COMPRAS}'").fetchone()
    assert r.respuesta == "Hay N clientes."
    assert r.advertencias == ["Datos hasta la última fecha del dataset."]
    assert [(c.sql, c.n_filas, c.filas_muestra) for c in r.consultas] == [
        (sql_clientes, 1, [{"clientes": clientes}])
    ]

    primeros, con_herramientas = llm.invocaciones[0]
    assert con_herramientas
    assert isinstance(primeros[0], SystemMessage)
    assert "probabilidad de recompra" in primeros[0].content
    assert [(m.type, m.content) for m in primeros[1:]] == [
        ("human", "hola"),
        ("ai", "¿En qué te ayudo?"),
        ("human", "¿Cuántos clientes hay?"),
    ]
    ultimos, _ = llm.invocaciones[-1]
    herramientas = [m for m in ultimos if isinstance(m, ToolMessage)]
    assert "Filas por vista" in herramientas[0].content
    assert f'"filas": [{{"clientes": {clientes}}}]' in herramientas[1].content
    resumen = contador.resumen()
    assert resumen["llamadas"]["9router"] == 3 and resumen["costo_estimado_usd"] > 0


def test_tope_de_consultas(conexion) -> None:
    contador = iter(range(1000))

    def insistente(mensajes, con_herramientas):
        if not con_herramientas:
            return _final("Con lo que tengo: algo.")
        # Dos consultas por turno: el tope cae en medio de un turno.
        return _ai(
            *(_llamada("consultar_sql", next(contador), sql="SELECT 1 AS x") for _ in range(2))
        )

    llm = LLMFalso(insistente)
    r = grafo.preguntar(conexion, "Dime todo", llm=llm)

    assert len(r.consultas) == grafo.MAX_CONSULTAS
    assert any("máximo de 6 consultas" in a for a in r.advertencias)
    assert r.respuesta == "Con lo que tengo: algo."
    assert [h for _, h in llm.invocaciones] == [True, True, True, False]


def test_consultas_rechazadas_cuentan_y_vuelven_al_llm(conexion) -> None:
    def malicioso(mensajes, con_herramientas):
        if not con_herramientas:
            return _final("No puedo hacer eso.")
        return _ai(_llamada("consultar_sql", len(mensajes), sql="COPY compras TO '/tmp/x.csv'"))

    llm = LLMFalso(malicioso)
    r = grafo.preguntar(conexion, "Exporta todo", llm=llm)

    assert r.consultas == [] and r.respuesta == "No puedo hacer eso."
    rechazos = [m for m in llm.invocaciones[-1][0] if isinstance(m, ToolMessage)]
    assert len(rechazos) == grafo.MAX_CONSULTAS
    assert all(m.content.startswith("Consulta rechazada") for m in rechazos)


def test_respuesta_sin_json_y_datos_insuficientes(conexion) -> None:
    llm = LLMFalso(lambda m, h: _ai(texto="No hay datos de devoluciones en este dataset."))
    r = grafo.preguntar(conexion, "¿Cuántas devoluciones hubo?", llm=llm)
    assert r.respuesta == "No hay datos de devoluciones en este dataset."
    assert r.consultas == [] and r.advertencias == []


# --- POST /agente/preguntas -------------------------------------------------------------------


@pytest.fixture()
def app(db: Session, cfg, monkeypatch):
    monkeypatch.setattr("predicts.auth.sesiones.settings", lambda: cfg)
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
def test_ruta_preguntas_aislada_por_empresa(db, dataset, app, cfg) -> None:
    fila, _ = base._correr(db, dataset, cfg, tipos=["recompra", "ciclos", "riesgo", "ofertas"])
    fila.estado = "listo"
    ana = _cliente(app, "Tienda Ana", "ana@ejemplo.com")
    beto = _cliente(app, "Tienda Beto", "beto@ejemplo.com")
    empresa_ana = db.scalar(select(Usuario.empresa_id).where(Usuario.email == "ana@ejemplo.com"))
    dataset.empresa_id = fila.empresa_id = empresa_ana
    db.commit()

    sql_ofertas = "SELECT count(*) AS n FROM ofertas"
    vistas_vistas: list[str] = []

    def guion(mensajes, con_herramientas):
        vistas_vistas.append(mensajes[0].content)
        if any(isinstance(m, ToolMessage) for m in mensajes):
            return _final("Listo.")
        return _ai(_llamada("consultar_sql", 1, sql=sql_ofertas))

    app.dependency_overrides[obtener_llm] = lambda: LLMFalso(guion)

    def preguntar(cliente: TestClient, **cuerpo):
        return cliente.post(
            "/agente/preguntas",
            json={"dataset_id": str(dataset.id), "pregunta": "¿Cuántas ofertas?", **cuerpo},
            headers={"X-CSRF-Token": cliente.cookies[COOKIE_CSRF]},
        )

    r = preguntar(ana, historial=[{"rol": "usuario", "contenido": "hola"}])
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    (n,) = duckdb.sql(
        f"SELECT count(*) FROM '{Path(fila.ruta_resultados) / 'ofertas.parquet'}'"
    ).fetchone()
    assert cuerpo["respuesta"] == "Listo."
    assert cuerpo["consultas"] == [{"sql": sql_ofertas, "filas_muestra": [{"n": n}], "n_filas": 1}]
    assert cuerpo["costo_ia"]["llamadas"] == {"9router": 2}
    assert "ofertas: Ofertas personalizadas" in vistas_vistas[0]  # vistas del último análisis

    assert preguntar(beto).status_code == 404
    assert preguntar(ana, historial=[{"rol": "sistema", "contenido": "x"}]).status_code == 422


def test_fecha_en_filas_muestra_serializable(conexion) -> None:
    r = consultar(conexion, "SELECT CAST(max(fecha) AS DATE) AS d FROM compras")
    assert isinstance(r.filas[0]["d"], date)
    grafo.Consulta(sql="x", filas_muestra=r.filas, n_filas=1).model_dump_json()
