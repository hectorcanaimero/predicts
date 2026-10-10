"""`pytest -m db`: crea la base temporal (fixture `db`), inserta y lee una fila de cada tabla."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from predicts.db.modelos import (
    Analisis,
    ApiKey,
    Dataset,
    DecisionJev,
    Empresa,
    EventoTrabajo,
    GrupoProducto,
    IntentoLogin,
    PlantillaMapeo,
    PlantillaMensaje,
    Producto,
    Proyecto,
    Sesion,
    TokenRecuperacion,
    Trabajo,
    Usuario,
)

pytestmark = pytest.mark.db


def test_crea_lee_una_fila_de_cada_tabla(db) -> None:
    empresa = Empresa(nombre="Acme")
    db.add(empresa)
    db.flush()

    usuario = Usuario(
        empresa_id=empresa.id,
        email="dueno@acme.test",
        hash_contrasena="hash",
        idioma="es",
        rol="dueno",
    )
    db.add(usuario)
    db.flush()

    sesion = Sesion(
        empresa_id=empresa.id,
        usuario_id=usuario.id,
        token_hash="token-hash-1",
        expira_en="2030-01-01T00:00:00+00:00",
        ip="127.0.0.1",
        user_agent="pytest",
    )
    token_recuperacion = TokenRecuperacion(
        empresa_id=empresa.id,
        usuario_id=usuario.id,
        token_hash="recuperacion-hash-1",
        expira_en="2030-01-01T00:00:00+00:00",
    )
    intento_login = IntentoLogin(email="dueno@acme.test", ip="127.0.0.1", exitoso=True)
    api_key = ApiKey(
        empresa_id=empresa.id, nombre="clave CI", prefijo="pk_live", key_hash="api-key-hash-1"
    )
    proyecto = Proyecto(
        empresa_id=empresa.id,
        nombre="Proyecto demo",
        descripcion="demo",
        idioma_mensajes="es",
        tono="neutro",
    )
    db.add_all([sesion, token_recuperacion, intento_login, api_key, proyecto])
    db.flush()

    dataset = Dataset(
        empresa_id=empresa.id,
        proyecto_id=proyecto.id,
        nombre_archivo="compras.csv",
        tamano_bytes=1024,
        sha256="a" * 64,
    )
    plantilla_mapeo = PlantillaMapeo(
        empresa_id=empresa.id,
        firma_encabezados="firma-1",
        nombre="mapeo estándar",
        mapeo={"cliente_id": "customer_id"},
    )
    grupo_producto = GrupoProducto(empresa_id=empresa.id, nombre="Lácteos")
    db.add_all([dataset, plantilla_mapeo, grupo_producto])
    db.flush()

    producto = Producto(
        empresa_id=empresa.id,
        nombre_normalizado="leche-1l",
        nombre="Leche 1L",
        grupo_id=grupo_producto.id,
        embedding=[0.0] * 1536,
    )
    trabajo = Trabajo(empresa_id=empresa.id, tipo="analisis_recompra")
    db.add_all([producto, trabajo])
    db.flush()

    analisis = Analisis(
        empresa_id=empresa.id,
        dataset_id=dataset.id,
        trabajo_id=trabajo.id,
        tipos=["recompra"],
        estado="listo",
    )
    evento_trabajo = EventoTrabajo(
        empresa_id=empresa.id, trabajo_id=trabajo.id, secuencia=1, etapa="inicio"
    )
    decision_jev = DecisionJev(
        empresa_id=empresa.id,
        tipo="tipo_producto",
        referencia=producto.id,
        opcion="recompra",
        corregida_por=usuario.id,
    )
    plantilla_mensaje = PlantillaMensaje(
        empresa_id=empresa.id,
        clave=f"producto:{producto.id}:recordatorio",
        tipo="recordatorio",
        idioma="es",
        tono="neutro",
        texto="¡Hora de volver a comprar!",
    )
    db.add_all([analisis, evento_trabajo, decision_jev, plantilla_mensaje])
    db.commit()

    for modelo in (
        Empresa,
        Usuario,
        Sesion,
        TokenRecuperacion,
        IntentoLogin,
        ApiKey,
        Proyecto,
        Dataset,
        PlantillaMapeo,
        GrupoProducto,
        Producto,
        Trabajo,
        Analisis,
        EventoTrabajo,
        DecisionJev,
        PlantillaMensaje,
    ):
        filas = db.scalars(select(modelo)).all()
        assert len(filas) == 1, f"se esperaba exactamente 1 fila en {modelo.__tablename__}"

    assert db.get(Producto, producto.id).embedding is not None
