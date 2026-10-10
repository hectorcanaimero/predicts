"""Tests del servidor MCP (F7.1.T3, ver specs/f7-agente.md#F7.1.T3): cada herramienta con el
cliente MCP del SDK en memoria, el rechazo sin API key y el aislamiento entre empresas."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable

import pytest
import test_agente as agente_base
import test_analisis_recompra as base
from mcp.client._memory import InMemoryTransport
from mcp.client.session import ClientSession
from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult
from sqlalchemy.orm import Session

from predicts.agente import grafo
from predicts.agente.mcp import crear_servidor
from predicts.auth import api_keys
from predicts.db.modelos import Empresa

pytestmark = pytest.mark.db

cfg = base.cfg
dataset = base.dataset


@pytest.fixture()
def db_factory(db: Session) -> Callable[[], Session]:
    def _factory() -> Session:
        return Session(bind=db.get_bind(), autoflush=False, expire_on_commit=False)

    return _factory


@pytest.fixture()
def beto(db: Session) -> Empresa:
    empresa = Empresa(nombre="Tienda Beto")
    db.add(empresa)
    db.commit()
    return empresa


@pytest.fixture()
def clave_ana(db: Session, dataset) -> str:
    _, clave = api_keys.crear(db, dataset.empresa_id, "ana-mcp")
    return clave


@pytest.fixture()
def clave_beto(db: Session, beto: Empresa) -> str:
    _, clave = api_keys.crear(db, beto.id, "beto-mcp")
    return clave


@pytest.fixture()
def analisis(db: Session, dataset, cfg):
    fila, _ = base._correr(db, dataset, cfg, tipos=["recompra", "ciclos", "riesgo", "ofertas"])
    fila.estado = "listo"
    db.commit()
    return fila


def _llamar(servidor: MCPServer, nombre: str, **args: object) -> CallToolResult:
    async def ir() -> CallToolResult:
        async with InMemoryTransport(servidor) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await session.call_tool(nombre, args)

    return asyncio.run(ir())


def _datos(r: CallToolResult) -> object:
    assert not r.is_error, r.content
    if r.structured_content is not None:
        return r.structured_content.get("result", r.structured_content)
    return json.loads(r.content[0].text)  # type: ignore[union-attr]


# --- herramientas ------------------------------------------------------------------------------


def test_listar_proyectos(db_factory, dataset, clave_ana) -> None:
    servidor = crear_servidor(db_factory, clave_ana)
    proyectos = _datos(_llamar(servidor, "listar_proyectos"))
    assert [p["id"] for p in proyectos] == [str(dataset.proyecto_id)]
    assert proyectos[0]["nombre"] == "P"


def test_listar_datasets(db_factory, dataset, clave_ana) -> None:
    servidor = crear_servidor(db_factory, clave_ana)
    datasets = _datos(_llamar(servidor, "listar_datasets"))
    assert [d["id"] for d in datasets] == [str(dataset.id)]
    assert datasets[0]["estado"] == "listo"


def test_recordatorios(db_factory, clave_ana, analisis) -> None:
    servidor = crear_servidor(db_factory, clave_ana)
    r = _datos(
        _llamar(servidor, "recordatorios", analisis_id=str(analisis.id), dias=36500, limite=3)
    )
    assert len(r) <= 3
    assert r == sorted(r, key=lambda f: f["p"], reverse=True)
    assert all({"cliente_id", "producto_id", "fecha_probable", "motivo"} <= set(f) for f in r)

    vacio = _datos(
        _llamar(servidor, "recordatorios", analisis_id=str(analisis.id), dias=0, limite=50)
    )
    assert vacio == []


def test_ciclos_producto(db_factory, clave_ana, analisis) -> None:
    servidor = crear_servidor(db_factory, clave_ana)
    r = _datos(
        _llamar(servidor, "ciclos_producto", analisis_id=str(analisis.id), producto="producto-002")
    )
    assert r and r[0]["producto_id"] == "producto-002"
    assert r[0]["ciclo_mediano"] > 0

    por_nombre = _datos(
        _llamar(
            servidor,
            "ciclos_producto",
            analisis_id=str(analisis.id),
            producto=r[0]["producto_nombre"][:10],
        )
    )
    assert any(f["producto_id"] == "producto-002" for f in por_nombre)

    sin_match = _datos(
        _llamar(servidor, "ciclos_producto", analisis_id=str(analisis.id), producto="no-existe-123")
    )
    assert sin_match == []


def test_clientes_en_riesgo(db_factory, clave_ana, analisis) -> None:
    servidor = crear_servidor(db_factory, clave_ana)
    r = _datos(_llamar(servidor, "clientes_en_riesgo", analisis_id=str(analisis.id), limite=5))
    assert len(r) <= 5
    assert all(f["nivel"] in ("producto", "tienda") for f in r)


def test_preguntar(db_factory, clave_ana, dataset, monkeypatch) -> None:
    servidor = crear_servidor(db_factory, clave_ana)
    guion = iter([agente_base._final("Hay clientes.")])
    monkeypatch.setattr(grafo, "llm_texto", lambda: agente_base.LLMFalso(lambda m, h: next(guion)))

    r = _datos(_llamar(servidor, "preguntar", dataset_id=str(dataset.id), pregunta="¿Cuántos?"))

    assert r["respuesta"] == "Hay clientes."


# --- autenticación y aislamiento ----------------------------------------------------------------


def test_rechaza_sin_api_key(db_factory) -> None:
    servidor = crear_servidor(db_factory, clave=None)
    r = _llamar(servidor, "listar_proyectos")
    assert r.is_error


def test_rechaza_api_key_invalida(db_factory) -> None:
    servidor = crear_servidor(db_factory, clave="pk_inventada")
    r = _llamar(servidor, "listar_proyectos")
    assert r.is_error


def test_aislamiento_entre_empresas(db_factory, dataset, clave_ana, clave_beto, analisis) -> None:
    servidor_beto = crear_servidor(db_factory, clave_beto)

    assert _datos(_llamar(servidor_beto, "listar_proyectos")) == []
    assert _datos(_llamar(servidor_beto, "listar_datasets")) == []

    r = _llamar(servidor_beto, "recordatorios", analisis_id=str(analisis.id), dias=365)
    assert r.is_error
    r = _llamar(servidor_beto, "ciclos_producto", analisis_id=str(analisis.id), producto="x")
    assert r.is_error
    r = _llamar(servidor_beto, "clientes_en_riesgo", analisis_id=str(analisis.id))
    assert r.is_error
    r = _llamar(servidor_beto, "preguntar", dataset_id=str(dataset.id), pregunta="¿Algo?")
    assert r.is_error

    r = _llamar(servidor_beto, "recordatorios", analisis_id=str(uuid.uuid4()), dias=365)
    assert r.is_error
