"""Tests de `datos/mapeo.py` y `api/datasets_mapeo.py` con un Jev falso (sin red): prellenado
vs. revisar, enmascaramiento, regla de EAN, validación, uso de plantilla sin llamar a Jev,
registro de correcciones y aislamiento por empresa."""

from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from typesafe_sdk import ChoiceAnswer, SystemOneResponse, Usage

from predicts.app import crear_app
from predicts.auth.csrf import COOKIE_CSRF
from predicts.config import settings_para_tests
from predicts.datos.deteccion import CandidatoFecha, ColumnaDeteccion, Deteccion
from predicts.datos.mapeo import (
    IGNORAR,
    MapeoColumna,
    MapeoConfirmado,
    SugerenciaProductoIdTipo,
    _tipo_producto_id_por_regla,
    clave_pregunta_columna,
    clave_pregunta_producto_id_tipo,
    enmascarar_valor,
    firma_encabezados,
    sugerir,
    validar,
)
from predicts.db.modelos import Dataset, DecisionJev, Empresa, PlantillaMapeo, Usuario
from predicts.db.sesion import get_db

CONTRASENA = "una-contrasena-larga"


# --- Helpers para construir `Deteccion`/`ColumnaDeteccion` sin pasar por un CSV -------------


def _columna(
    nombre: str,
    valores: list[str],
    tipo: str = "VARCHAR",
    candidatos_fecha: list[CandidatoFecha] | None = None,
) -> ColumnaDeteccion:
    return ColumnaDeteccion(
        nombre=nombre,
        tipo=tipo,
        porcentaje_nulos=0.0,
        valores_muestra=valores,
        candidatos_fecha=candidatos_fecha or [],
        separador_decimal=None,
    )


def _deteccion(columnas: list[ColumnaDeteccion]) -> Deteccion:
    return Deteccion(
        codificacion="utf-8", separador=",", encabezado=True, columnas=columnas, vista_previa=[]
    )


class ClienteJevFalso:
    """Devuelve una `SystemOneResponse` fija y guarda las llamadas para inspección.

    Las preguntas no cubiertas por `respuestas` (p. ej. un `producto_id_tipo` de una columna
    que en el test no es la elegida como `producto_id`) se responden con un valor de relleno,
    para no tener que enumerar cada subpregunta en cada test.
    """

    def __init__(self, respuestas: dict[str, object]) -> None:
        self._respuestas = respuestas
        self.llamadas: list[tuple[object, object]] = []

    def system_one(self, state, questions):
        self.llamadas.append((state, questions))
        answers = {}
        for nombre in questions:
            if nombre in self._respuestas:
                answers[nombre] = self._respuestas[nombre]
            elif nombre.startswith("producto_id_tipo::"):
                answers[nombre] = _eleccion("sku", 0.5)
            else:
                answers[nombre] = _eleccion(IGNORAR, 0.5)
        return SystemOneResponse(
            model="jev-test", usage=Usage(input_tokens=10, output_tokens=2), answers=answers
        )


def _eleccion(campo: str, confianza: float) -> ChoiceAnswer:
    return ChoiceAnswer(choice=campo, confidence=confianza, probabilities={campo: confianza})


# --- Enmascaramiento (sin DB) ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("juan.perez@gmail.com", "j*********@*****.com"),
        ("+55 11 98888-7777", "+** ** *****-**77"),
        ("123.456.789-01", "***.***.***-01"),
    ],
)
def test_enmascarar_valor_email_telefono_cpf(valor: str, esperado: str) -> None:
    assert enmascarar_valor(valor) == esperado


@pytest.mark.parametrize("valor", ["Leche entera", "12345", "Café especial", "SKU-001"])
def test_enmascarar_valor_no_toca_valores_normales(valor: str) -> None:
    assert enmascarar_valor(valor) == valor


# --- Regla de EAN (sin DB) -------------------------------------------------------------------


def test_regla_ean_decide_con_digito_verificador_valido() -> None:
    assert _tipo_producto_id_por_regla(["4006381333931", "4006381333931"]) == "ean"


def test_regla_ean_no_decide_con_digito_verificador_invalido() -> None:
    assert _tipo_producto_id_por_regla(["4006381333930"]) is None


def test_regla_ean_no_decide_con_sku_alfanumerico() -> None:
    assert _tipo_producto_id_por_regla(["SKU-001", "SKU-002"]) is None


def test_regla_ean_no_decide_sin_valores() -> None:
    assert _tipo_producto_id_por_regla([]) is None


# --- Firma de encabezados (sin DB) -----------------------------------------------------------


def test_firma_encabezados_ignora_mayusculas_acentos_espacios_y_orden() -> None:
    a = firma_encabezados(["Cliente ID", "Fecha", "Preço"])
    b = firma_encabezados(["fecha", "preco", "clienteid"])
    assert a == b


def test_firma_encabezados_distingue_conjuntos_distintos() -> None:
    assert firma_encabezados(["a", "b"]) != firma_encabezados(["a", "c"])


# --- Validación (sin DB) ----------------------------------------------------------------------


def _deteccion_valida() -> Deteccion:
    return _deteccion(
        [
            _columna("cliente", ["1", "2"]),
            _columna(
                "fecha_venta",
                ["01/02/2024"],
                candidatos_fecha=[CandidatoFecha(formato="dd/mm/aaaa", porcentaje=1.0)],
            ),
            _columna("producto", ["4006381333931"]),
        ]
    )


def _mapeo_valido() -> MapeoConfirmado:
    return MapeoConfirmado(
        columnas=[
            MapeoColumna(columna="cliente", campo="cliente_id"),
            MapeoColumna(columna="fecha_venta", campo="fecha"),
            MapeoColumna(columna="producto", campo="producto_id"),
        ],
        producto_id_tipo="ean",
        formato_fecha="dd/mm/aaaa",
    )


def test_validar_mapeo_correcto_no_tiene_errores() -> None:
    assert validar(_mapeo_valido(), _deteccion_valida()) == []


def test_validar_detecta_campo_obligatorio_faltante() -> None:
    mapeo = _mapeo_valido()
    mapeo.columnas[0] = MapeoColumna(columna="cliente", campo=IGNORAR)

    errores = validar(mapeo, _deteccion_valida())

    assert any(
        e.codigo == "campo_obligatorio_faltante" and e.parametros["campo"] == "cliente_id"
        for e in errores
    )


def test_validar_detecta_campo_duplicado() -> None:
    mapeo = _mapeo_valido()
    mapeo.columnas[1] = MapeoColumna(columna="fecha_venta", campo="cliente_id")

    errores = validar(mapeo, _deteccion_valida())

    assert any(
        e.codigo == "campo_duplicado" and e.parametros["campo"] == "cliente_id" for e in errores
    )
    # también falta 'fecha' como consecuencia de la duplicación
    assert any(
        e.codigo == "campo_obligatorio_faltante" and e.parametros["campo"] == "fecha"
        for e in errores
    )


def test_validar_detecta_formato_de_fecha_invalido() -> None:
    mapeo = _mapeo_valido()
    mapeo.formato_fecha = "mm/dd/aaaa"

    errores = validar(mapeo, _deteccion_valida())

    assert any(e.codigo == "formato_fecha_invalido" for e in errores)


def test_validar_detecta_tipo_identificador_producto_invalido() -> None:
    mapeo = _mapeo_valido()
    mapeo.producto_id_tipo = "upc"

    errores = validar(mapeo, _deteccion_valida())

    assert any(e.codigo == "tipo_identificador_producto_invalido" for e in errores)


def test_validar_detecta_columna_desconocida() -> None:
    mapeo = _mapeo_valido()
    mapeo.columnas.append(MapeoColumna(columna="no_existe", campo="marca"))

    errores = validar(mapeo, _deteccion_valida())

    assert any(e.codigo == "columna_desconocida" for e in errores)


# --- `sugerir()` con un Jev falso (con DB real, para `decisiones_jev` y plantillas) ----------


@pytest.fixture()
def empresa(db) -> uuid.UUID:
    fila = Empresa(nombre="Acme")
    db.add(fila)
    db.flush()
    return fila.id


@pytest.mark.db
def test_sugerir_prellenado_cuando_confianza_alta_y_revisar_cuando_baja(db, empresa) -> None:
    deteccion = _deteccion_valida()
    cliente = ClienteJevFalso(
        {
            clave_pregunta_columna("cliente"): _eleccion("cliente_id", 0.95),
            clave_pregunta_columna("fecha_venta"): _eleccion("fecha", 0.5),
            clave_pregunta_columna("producto"): _eleccion("producto_id", 0.9),
        }
    )

    sugerencias = sugerir(
        deteccion, db, empresa, uuid.uuid4(), cliente=cliente, cfg=settings_para_tests()
    )

    por_columna = {s.columna: s for s in sugerencias.columnas}
    assert por_columna["cliente"].estado == "prellenado"
    assert por_columna["fecha_venta"].estado == "revisar"
    assert por_columna["producto"].estado == "prellenado"
    assert sugerencias.origen == "jev"


@pytest.mark.db
def test_sugerir_usa_regla_ean_sin_preguntar_el_tipo_a_jev(db, empresa) -> None:
    deteccion = _deteccion_valida()  # "producto" tiene un EAN válido
    cliente = ClienteJevFalso(
        {
            clave_pregunta_columna("cliente"): _eleccion("cliente_id", 0.95),
            clave_pregunta_columna("fecha_venta"): _eleccion("fecha", 0.95),
            clave_pregunta_columna("producto"): _eleccion("producto_id", 0.95),
        }
    )

    sugerencias = sugerir(
        deteccion, db, empresa, uuid.uuid4(), cliente=cliente, cfg=settings_para_tests()
    )

    assert clave_pregunta_producto_id_tipo("producto") not in cliente.llamadas[0][1]
    assert sugerencias.producto_id_tipo is not None
    assert sugerencias.producto_id_tipo.tipo == "ean"
    assert sugerencias.producto_id_tipo.origen == "regla"


@pytest.mark.db
def test_sugerir_pregunta_el_tipo_a_jev_cuando_la_regla_no_decide(db, empresa) -> None:
    deteccion = _deteccion(
        [
            _columna("cliente", ["1", "2"]),
            _columna(
                "fecha_venta",
                ["01/02/2024"],
                candidatos_fecha=[CandidatoFecha(formato="dd/mm/aaaa", porcentaje=1.0)],
            ),
            _columna("producto", ["SKU-001", "SKU-002"]),
        ]
    )
    cliente = ClienteJevFalso(
        {
            clave_pregunta_columna("cliente"): _eleccion("cliente_id", 0.95),
            clave_pregunta_columna("fecha_venta"): _eleccion("fecha", 0.95),
            clave_pregunta_columna("producto"): _eleccion("producto_id", 0.95),
            clave_pregunta_producto_id_tipo("cliente"): _eleccion("sku", 0.6),
            clave_pregunta_producto_id_tipo("fecha_venta"): _eleccion("sku", 0.6),
            clave_pregunta_producto_id_tipo("producto"): _eleccion("sku", 0.88),
        }
    )

    sugerencias = sugerir(
        deteccion, db, empresa, uuid.uuid4(), cliente=cliente, cfg=settings_para_tests()
    )

    assert len(cliente.llamadas) == 1, "sugerir debe hacer una sola llamada a decidir_lote"
    assert sugerencias.producto_id_tipo == SugerenciaProductoIdTipo(
        tipo="sku", confianza=0.88, origen="jev"
    )


@pytest.mark.db
def test_sugerir_guarda_una_decision_jev_por_columna(db, empresa) -> None:
    deteccion = _deteccion_valida()
    dataset_id = uuid.uuid4()
    cliente = ClienteJevFalso(
        {
            clave_pregunta_columna("cliente"): _eleccion("cliente_id", 0.95),
            clave_pregunta_columna("fecha_venta"): _eleccion("fecha", 0.95),
            clave_pregunta_columna("producto"): _eleccion("producto_id", 0.95),
        }
    )

    sugerir(deteccion, db, empresa, dataset_id, cliente=cliente, cfg=settings_para_tests())
    db.commit()

    decisiones = db.scalars(
        select(DecisionJev).where(
            DecisionJev.tipo == "mapeo_columna", DecisionJev.referencia == dataset_id
        )
    ).all()
    assert {d.entrada_resumida["columna"] for d in decisiones} == {
        "cliente",
        "fecha_venta",
        "producto",
    }
    assert all(d.empresa_id == empresa for d in decisiones)


@pytest.mark.db
def test_sugerir_enmascara_los_valores_de_muestra_en_el_contexto_de_jev(db, empresa) -> None:
    deteccion = _deteccion(
        [_columna("correo", ["juan.perez@gmail.com"])] + _deteccion_valida().columnas[1:]
    )
    cliente = ClienteJevFalso(
        {
            clave_pregunta_columna("correo"): _eleccion("cliente_id", 0.95),
            clave_pregunta_columna("fecha_venta"): _eleccion("fecha", 0.95),
            clave_pregunta_columna("producto"): _eleccion("producto_id", 0.95),
        }
    )

    sugerir(deteccion, db, empresa, uuid.uuid4(), cliente=cliente, cfg=settings_para_tests())

    preguntas = cliente.llamadas[0][1]
    muestras = preguntas[clave_pregunta_columna("correo")].instructions["valores_muestra"]
    assert muestras == ["j*********@*****.com"]


@pytest.mark.db
def test_sugerir_usa_plantilla_sin_llamar_a_jev(db, empresa) -> None:
    deteccion = _deteccion_valida()
    firma = firma_encabezados([c.nombre for c in deteccion.columnas])
    plantilla = PlantillaMapeo(
        empresa_id=empresa,
        firma_encabezados=firma,
        nombre="Plantilla A",
        mapeo={
            "columnas": [
                {"columna": "cliente", "campo": "cliente_id"},
                {"columna": "fecha_venta", "campo": "fecha"},
                {"columna": "producto", "campo": "producto_id"},
            ],
            "producto_id_tipo": "ean",
            "formato_fecha": "dd/mm/aaaa",
        },
    )
    db.add(plantilla)
    db.flush()

    class ClienteQueExplota:
        def system_one(self, *args, **kwargs):
            raise AssertionError("no debe llamarse a Jev si hay una plantilla")

    sugerencias = sugerir(
        deteccion, db, empresa, uuid.uuid4(), cliente=ClienteQueExplota(), cfg=settings_para_tests()
    )

    assert sugerencias.origen == "plantilla"
    assert all(s.confianza == 1.0 and s.origen == "plantilla" for s in sugerencias.columnas)
    assert sugerencias.producto_id_tipo.tipo == "ean"
    assert sugerencias.producto_id_tipo.origen == "plantilla"


@pytest.mark.db
def test_sugerir_no_usa_plantilla_de_otra_empresa(db, empresa) -> None:
    otra_empresa = Empresa(nombre="Otra")
    db.add(otra_empresa)
    db.flush()

    deteccion = _deteccion_valida()
    firma = firma_encabezados([c.nombre for c in deteccion.columnas])
    db.add(
        PlantillaMapeo(
            empresa_id=otra_empresa.id,
            firma_encabezados=firma,
            nombre="Plantilla de otra",
            mapeo={"columnas": [], "producto_id_tipo": "ean", "formato_fecha": "dd/mm/aaaa"},
        )
    )
    db.flush()

    cliente = ClienteJevFalso(
        {
            clave_pregunta_columna("cliente"): _eleccion("cliente_id", 0.95),
            clave_pregunta_columna("fecha_venta"): _eleccion("fecha", 0.95),
            clave_pregunta_columna("producto"): _eleccion("producto_id", 0.95),
        }
    )

    sugerencias = sugerir(
        deteccion, db, empresa, uuid.uuid4(), cliente=cliente, cfg=settings_para_tests()
    )

    assert sugerencias.origen == "jev"
    assert len(cliente.llamadas) == 1


# --- API: `/datasets/{id}/mapeo` y `/plantillas-mapeo` ----------------------------------------


def _deteccion_api() -> Deteccion:
    return _deteccion(
        [
            _columna("cliente", ["100", "101"]),
            _columna(
                "data_venda",
                ["01/02/2024"],
                candidatos_fecha=[CandidatoFecha(formato="dd/mm/aaaa", porcentaje=1.0)],
            ),
            _columna("produto", ["4006381333931"]),
            _columna("categoria_x", ["Lacteos", "Bebidas"]),
        ]
    )


def _cliente_jev_api() -> ClienteJevFalso:
    return ClienteJevFalso(
        {
            clave_pregunta_columna("cliente"): _eleccion("cliente_id", 0.95),
            clave_pregunta_columna("data_venda"): _eleccion("fecha", 0.95),
            clave_pregunta_columna("produto"): _eleccion("producto_id", 0.95),
            clave_pregunta_columna("categoria_x"): _eleccion("ignorar", 0.55),
        }
    )


@pytest.fixture()
def app(db: Session, monkeypatch):
    monkeypatch.setattr("predicts.auth.sesiones.settings", lambda: settings_para_tests())
    monkeypatch.setattr("predicts.datos.mapeo.settings", lambda: settings_para_tests())
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


def _crear_dataset(db: Session, cliente: TestClient, email: str, deteccion: Deteccion) -> Dataset:
    empresa_id = db.scalar(select(Usuario.empresa_id).where(Usuario.email == email))
    r = cliente.post("/proyectos", json={"nombre": "Campaña"}, headers=_csrf(cliente))
    proyecto_id = uuid.UUID(r.json()["id"])

    dataset = Dataset(
        empresa_id=empresa_id,
        proyecto_id=proyecto_id,
        nombre_archivo="compras.csv",
        tamano_bytes=10,
        sha256="a" * 64,
        estado="subido",
        deteccion=deteccion.model_dump(),
    )
    db.add(dataset)
    db.commit()
    return dataset


@pytest.mark.db
def test_obtener_mapeo_devuelve_sugerencias_de_jev(db, app, ana, monkeypatch) -> None:
    dataset = _crear_dataset(db, ana, "ana@ejemplo.com", _deteccion_api())
    monkeypatch.setattr("predicts.ia.cliente_jev", lambda cfg=None: _cliente_jev_api())

    r = ana.get(f"/datasets/{dataset.id}/mapeo")

    assert r.status_code == 200
    cuerpo = r.json()
    por_columna = {c["columna"]: c for c in cuerpo["columnas"]}
    assert por_columna["cliente"]["campo"] == "cliente_id"
    assert por_columna["cliente"]["estado"] == "prellenado"
    assert por_columna["categoria_x"]["estado"] == "revisar"
    assert cuerpo["producto_id_tipo"]["tipo"] == "ean"
    assert cuerpo["producto_id_tipo"]["origen"] == "regla"


@pytest.mark.db
def test_confirmar_mapeo_invalido_responde_422(db, app, ana, monkeypatch) -> None:
    dataset = _crear_dataset(db, ana, "ana@ejemplo.com", _deteccion_api())
    monkeypatch.setattr("predicts.ia.cliente_jev", lambda cfg=None: _cliente_jev_api())

    r = ana.put(
        f"/datasets/{dataset.id}/mapeo",
        json={
            "columnas": [{"columna": "cliente", "campo": "ignorar"}],
            "producto_id_tipo": "ean",
            "formato_fecha": "dd/mm/aaaa",
        },
        headers=_csrf(ana),
    )

    assert r.status_code == 422
    assert r.json()["codigo"] == "mapeo_invalido"


@pytest.mark.db
def test_confirmar_mapeo_registra_correcciones_de_la_persona(db, app, ana, monkeypatch) -> None:
    dataset = _crear_dataset(db, ana, "ana@ejemplo.com", _deteccion_api())
    monkeypatch.setattr("predicts.ia.cliente_jev", lambda cfg=None: _cliente_jev_api())
    assert ana.get(f"/datasets/{dataset.id}/mapeo").status_code == 200

    r = ana.put(
        f"/datasets/{dataset.id}/mapeo",
        json={
            "columnas": [
                {"columna": "cliente", "campo": "cliente_id"},
                {"columna": "data_venda", "campo": "fecha"},
                {"columna": "produto", "campo": "producto_id"},
                {"columna": "categoria_x", "campo": "categoria"},
            ],
            "producto_id_tipo": "ean",
            "formato_fecha": "dd/mm/aaaa",
        },
        headers=_csrf(ana),
    )

    assert r.status_code == 200
    assert r.json()["estado"] == "mapeado"

    db.expire_all()
    decisiones = db.scalars(
        select(DecisionJev).where(
            DecisionJev.tipo == "mapeo_columna", DecisionJev.referencia == dataset.id
        )
    ).all()
    por_columna = {d.entrada_resumida["columna"]: d for d in decisiones}
    assert por_columna["categoria_x"].corregida_a == "categoria"
    assert por_columna["categoria_x"].corregida_por is not None
    assert por_columna["categoria_x"].corregida_en is not None
    assert por_columna["cliente"].corregida_a is None


@pytest.mark.db
def test_confirmar_mapeo_con_guardar_como_plantilla_la_crea(db, app, ana, monkeypatch) -> None:
    dataset = _crear_dataset(db, ana, "ana@ejemplo.com", _deteccion_api())
    monkeypatch.setattr("predicts.ia.cliente_jev", lambda cfg=None: _cliente_jev_api())
    assert ana.get(f"/datasets/{dataset.id}/mapeo").status_code == 200

    r = ana.put(
        f"/datasets/{dataset.id}/mapeo",
        json={
            "columnas": [
                {"columna": "cliente", "campo": "cliente_id"},
                {"columna": "data_venda", "campo": "fecha"},
                {"columna": "produto", "campo": "producto_id"},
                {"columna": "categoria_x", "campo": "categoria"},
            ],
            "producto_id_tipo": "ean",
            "formato_fecha": "dd/mm/aaaa",
            "guardar_como_plantilla": True,
            "nombre_plantilla": "Mi plantilla",
        },
        headers=_csrf(ana),
    )
    assert r.status_code == 200

    r = ana.get("/plantillas-mapeo")
    assert r.status_code == 200
    plantillas = r.json()
    assert len(plantillas) == 1
    assert plantillas[0]["nombre"] == "Mi plantilla"

    # un segundo dataset con los mismos encabezados usa la plantilla, sin llamar a Jev
    class ClienteQueExplota:
        def system_one(self, *args, **kwargs):
            raise AssertionError("no debe llamarse a Jev si hay una plantilla")

    monkeypatch.setattr("predicts.ia.cliente_jev", lambda cfg=None: ClienteQueExplota())
    dataset2 = _crear_dataset(db, ana, "ana@ejemplo.com", _deteccion_api())

    r = ana.get(f"/datasets/{dataset2.id}/mapeo")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["origen"] == "plantilla"
    por_columna = {c["columna"]: c for c in cuerpo["columnas"]}
    assert por_columna["categoria_x"]["campo"] == "categoria"


@pytest.mark.db
def test_borrar_plantilla(db, app, ana) -> None:
    empresa_id = db.scalar(select(Usuario.empresa_id).where(Usuario.email == "ana@ejemplo.com"))
    plantilla = PlantillaMapeo(
        empresa_id=empresa_id,
        firma_encabezados="x" * 64,
        nombre="P",
        mapeo={"columnas": [], "producto_id_tipo": "ean", "formato_fecha": "dd/mm/aaaa"},
    )
    db.add(plantilla)
    db.commit()

    r = ana.delete(f"/plantillas-mapeo/{plantilla.id}", headers=_csrf(ana))

    assert r.status_code == 204
    assert ana.get("/plantillas-mapeo").json() == []


# --- Aislamiento por empresa -------------------------------------------------------------------


@pytest.mark.db
def test_otra_empresa_no_ve_el_mapeo_del_dataset(db, app, ana, beto, monkeypatch) -> None:
    dataset = _crear_dataset(db, ana, "ana@ejemplo.com", _deteccion_api())
    monkeypatch.setattr("predicts.ia.cliente_jev", lambda cfg=None: _cliente_jev_api())

    r = beto.get(f"/datasets/{dataset.id}/mapeo")

    assert r.status_code == 404
    assert r.json()["codigo"] == "no_encontrado"


@pytest.mark.db
def test_otra_empresa_no_puede_confirmar_el_mapeo(db, app, ana, beto) -> None:
    dataset = _crear_dataset(db, ana, "ana@ejemplo.com", _deteccion_api())

    r = beto.put(
        f"/datasets/{dataset.id}/mapeo",
        json={
            "columnas": [{"columna": "cliente", "campo": "cliente_id"}],
            "producto_id_tipo": "ean",
            "formato_fecha": "dd/mm/aaaa",
        },
        headers=_csrf(beto),
    )

    assert r.status_code == 404


@pytest.mark.db
def test_otra_empresa_no_ve_las_plantillas(db, app, ana, beto) -> None:
    empresa_id = db.scalar(select(Usuario.empresa_id).where(Usuario.email == "ana@ejemplo.com"))
    db.add(
        PlantillaMapeo(
            empresa_id=empresa_id,
            firma_encabezados="y" * 64,
            nombre="De Ana",
            mapeo={"columnas": [], "producto_id_tipo": "ean", "formato_fecha": "dd/mm/aaaa"},
        )
    )
    db.commit()

    assert beto.get("/plantillas-mapeo").json() == []


@pytest.mark.db
def test_otra_empresa_no_puede_borrar_la_plantilla(db, app, ana, beto) -> None:
    empresa_id = db.scalar(select(Usuario.empresa_id).where(Usuario.email == "ana@ejemplo.com"))
    plantilla = PlantillaMapeo(
        empresa_id=empresa_id,
        firma_encabezados="z" * 64,
        nombre="De Ana",
        mapeo={"columnas": [], "producto_id_tipo": "ean", "formato_fecha": "dd/mm/aaaa"},
    )
    db.add(plantilla)
    db.commit()

    r = beto.delete(f"/plantillas-mapeo/{plantilla.id}", headers=_csrf(beto))

    assert r.status_code == 404
    assert db.get(PlantillaMapeo, plantilla.id) is not None
