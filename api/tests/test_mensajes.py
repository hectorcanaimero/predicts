"""Tests de plantillas de mensaje con LLM y Jev falsos (ver specs/f5-mensajes.md#F5.1.T1):
lotes de hasta `TAMANO_LOTE` combinaciones, caché por (empresa, clave, idioma, tono),
regeneración única tras un rechazo de Jev, render sin marcadores sueltos, y que editar una
plantilla la saca del ciclo de regeneración. También las rutas de la API y el paso opcional del
orquestador de análisis.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Generator

import pytest
import test_analisis_recompra as base
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from sqlalchemy import select
from sqlalchemy.orm import Session
from typesafe_sdk import ChoiceAnswer, SystemOneResponse, Usage

from predicts.analisis import orquestador
from predicts.app import crear_app
from predicts.auth.csrf import COOKIE_CSRF
from predicts.db.modelos import DecisionJev, Empresa, Usuario
from predicts.db.sesion import get_db
from predicts.mensajes import plantillas, render, revision
from predicts.mensajes.plantillas import Combinacion

cfg, dataset = base.cfg, base.dataset  # fixtures compartidas con los tests de recompra

# --- fakes ------------------------------------------------------------------------------------

_CLAVE_EN_PROMPT = re.compile(r'- "([^"]+)":')


class LlmFalso:
    """Lee en el prompt las claves pedidas (las líneas `- "clave": ...`) y devuelve un texto
    válido para cada una, calculado por `texto(clave)`. Guarda los prompts para inspección."""

    def __init__(self, texto: Callable[[str], str] | None = None) -> None:
        self._texto = texto or (lambda clave: f"Mensaje para {clave}.")
        self.llamadas: list[str] = []

    def invoke(self, mensajes):
        prompt = mensajes[-1].content
        self.llamadas.append(prompt)
        claves = _CLAVE_EN_PROMPT.findall(prompt)
        cuerpo = json.dumps({"plantillas": {c: {"texto": self._texto(c)} for c in claves}})
        return AIMessage(
            content=cuerpo,
            usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        )


class JevFalso:
    """Elige, para cada pregunta, la opción que devuelva `elegir(clave, pregunta)` (por
    defecto, siempre aprueba). Guarda los lotes de preguntas para inspección."""

    def __init__(self, elegir: Callable[[str, object], str] | None = None) -> None:
        self._elegir = elegir or (lambda clave, pregunta: "aprobada")
        self.llamadas: list[dict] = []

    def system_one(self, state, questions):
        self.llamadas.append(dict(questions))
        respuestas = {
            clave: ChoiceAnswer(
                choice=(opcion := self._elegir(clave, pregunta)),
                confidence=0.9,
                probabilities={opcion: 0.9},
            )
            for clave, pregunta in questions.items()
        }
        return SystemOneResponse(
            model="jev-test", usage=Usage(input_tokens=1, output_tokens=1), answers=respuestas
        )


def _empresa(db: Session) -> Empresa:
    empresa = Empresa(nombre="Tienda")
    db.add(empresa)
    db.flush()
    return empresa


def _combos(n: int, tipo: str = "recordatorio") -> list[Combinacion]:
    return [Combinacion(f"producto:{i}", tipo, f"Producto {i}") for i in range(n)]


# --- render ------------------------------------------------------------------------------------


def test_render_reemplaza_los_marcadores_presentes() -> None:
    texto = "Hola, {producto} te espera en {nombre_tienda} (quedan {dias} días)."
    resultado = render.render(
        texto, {"producto": "Café", "nombre_tienda": "La Esquina", "dias": "3"}
    )
    assert resultado == "Hola, Café te espera en La Esquina (quedan 3 días)."


def test_render_falla_si_queda_un_marcador_sin_reemplazar() -> None:
    with pytest.raises(ValueError, match="oferta"):
        render.render("Tenés {oferta} % en {producto}", {"producto": "Café"})


def test_render_no_exige_marcadores_que_no_estan_en_el_texto() -> None:
    assert render.render("Mensaje general sin marcadores.", {"producto": "Café"}) == (
        "Mensaje general sin marcadores."
    )


# --- plantillas: validación y lotes --------------------------------------------------------


def test_texto_rechaza_mas_de_300_caracteres() -> None:
    with pytest.raises(ValueError):
        plantillas.Texto(texto="x" * 301)


def test_texto_rechaza_marcadores_no_permitidos() -> None:
    with pytest.raises(ValueError):
        plantillas.Texto(texto="Hola {nombre_cliente}, tenemos algo para vos.")


def test_generar_lote_falla_si_pasan_mas_de_tamano_lote() -> None:
    with pytest.raises(ValueError, match="máximo"):
        plantillas.generar_lote(_combos(plantillas.TAMANO_LOTE + 1), "es", "neutro", llm=LlmFalso())


def test_generar_lote_una_sola_llamada_hasta_el_tamano_maximo() -> None:
    combos = _combos(plantillas.TAMANO_LOTE)
    llm = LlmFalso()
    textos = plantillas.generar_lote(combos, "es", "neutro", llm=llm)
    assert len(llm.llamadas) == 1
    assert set(textos) == {c.clave for c in combos}


@pytest.mark.db
def test_generar_plantillas_hace_lotes_de_hasta_tamano_lote(db) -> None:
    empresa = _empresa(db)
    combos = _combos(25)  # 2 lotes: 20 + 5
    llm = LlmFalso()

    resultado = plantillas.generar_plantillas(db, empresa.id, combos, "es", "neutro", llm=llm)

    assert len(llm.llamadas) == 2
    tamanos = [len(_CLAVE_EN_PROMPT.findall(p)) for p in llm.llamadas]
    assert sorted(tamanos) == [5, 20]
    assert len(resultado.nuevas) == 25
    assert all(f.estado == "ok" for f in resultado.nuevas)


# --- caché ----------------------------------------------------------------------------------


@pytest.mark.db
def test_generar_plantillas_usa_la_cache_en_la_segunda_llamada(db) -> None:
    empresa = _empresa(db)
    combos = _combos(3)
    llm = LlmFalso()

    primero = plantillas.generar_plantillas(db, empresa.id, combos, "es", "neutro", llm=llm)
    db.commit()
    assert len(primero.nuevas) == 3
    assert len(llm.llamadas) == 1

    segundo = plantillas.generar_plantillas(db, empresa.id, combos, "es", "neutro", llm=llm)
    assert len(segundo.nuevas) == 0, "no debe pedirle nada nuevo al LLM: ya está en caché"
    assert len(llm.llamadas) == 1, "la caché no debe llamar al LLM de nuevo"
    assert segundo.filas.keys() == primero.filas.keys()
    assert {f.id for f in segundo.filas.values()} == {f.id for f in primero.filas.values()}


@pytest.mark.db
def test_generar_plantillas_distingue_idioma_y_tono(db) -> None:
    empresa = _empresa(db)
    combos = _combos(1)
    llm = LlmFalso()

    plantillas.generar_plantillas(db, empresa.id, combos, "es", "neutro", llm=llm)
    plantillas.generar_plantillas(db, empresa.id, combos, "en", "neutro", llm=llm)
    plantillas.generar_plantillas(db, empresa.id, combos, "es", "formal", llm=llm)

    assert len(llm.llamadas) == 3, "cada (idioma, tono) es una entrada de caché distinta"


@pytest.mark.db
def test_forzar_regenera_lo_cacheado_pero_no_lo_editado(db) -> None:
    empresa = _empresa(db)
    combos = _combos(2)
    llm = LlmFalso()

    resultado = plantillas.generar_plantillas(db, empresa.id, combos, "es", "neutro", llm=llm)
    db.commit()
    editada = resultado.filas[combos[0].clave]
    editada.texto, editada.estado = "Texto puesto a mano.", "editada"
    db.commit()

    forzado = plantillas.generar_plantillas(
        db, empresa.id, combos, "es", "neutro", llm=llm, forzar=True
    )

    assert {f.clave for f in forzado.nuevas} == {combos[1].clave}, "la editada no se regenera"
    assert forzado.filas[combos[0].clave].texto == "Texto puesto a mano."
    assert forzado.filas[combos[0].clave].estado == "editada"


# --- revisión con Jev y regeneración única --------------------------------------------------


@pytest.mark.db
def test_jev_aprueba_sin_regenerar(db) -> None:
    empresa = _empresa(db)
    combos = _combos(2)
    llm = LlmFalso()
    jev = JevFalso()

    resultado = plantillas.generar_plantillas(db, empresa.id, combos, "es", "neutro", llm=llm)
    revision.revisar_y_regenerar(
        db, empresa.id, combos, resultado, "es", "neutro", llm=llm, cliente=jev
    )

    assert len(llm.llamadas) == 1, "no debe regenerar nada: Jev aprobó todo"
    assert len(jev.llamadas) == 1
    assert all(f.estado == "ok" and f.motivo_revision is None for f in resultado.nuevas)

    decisiones = db.scalars(select(DecisionJev).where(DecisionJev.empresa_id == empresa.id)).all()
    assert len(decisiones) == 2 and all(d.tipo == "revision_mensaje" for d in decisiones)


@pytest.mark.db
def test_rechazada_se_regenera_una_vez_y_queda_ok(db) -> None:
    empresa = _empresa(db)
    combos = _combos(1)

    vistos: set[str] = set()

    def texto_por_version(clave: str) -> str:
        if clave not in vistos:
            vistos.add(clave)
            return "¡Solo hoy, date prisa!"
        return "Mensaje corregido, sin apuro."

    llm = LlmFalso(texto_por_version)
    jev = JevFalso(
        elegir=lambda clave, pregunta: (
            "promesa_no_garantizada" if "solo hoy" in pregunta.instructions.lower() else "aprobada"
        )
    )

    resultado = plantillas.generar_plantillas(db, empresa.id, combos, "es", "neutro", llm=llm)
    revision.revisar_y_regenerar(
        db, empresa.id, combos, resultado, "es", "neutro", llm=llm, cliente=jev
    )

    assert len(llm.llamadas) == 2, "la generación inicial y una sola regeneración"
    assert len(jev.llamadas) == 2, "la revisión inicial y una sola re-revisión"
    fila = resultado.filas[combos[0].clave]
    assert fila.estado == "ok" and fila.motivo_revision is None
    assert fila.texto == "Mensaje corregido, sin apuro."


@pytest.mark.db
def test_si_sigue_fallando_tras_regenerar_queda_revisar(db) -> None:
    empresa = _empresa(db)
    combos = _combos(1)
    llm = LlmFalso()
    jev = JevFalso(elegir=lambda clave, pregunta: "datos_sensibles")

    resultado = plantillas.generar_plantillas(db, empresa.id, combos, "es", "neutro", llm=llm)
    revision.revisar_y_regenerar(
        db, empresa.id, combos, resultado, "es", "neutro", llm=llm, cliente=jev
    )

    assert len(llm.llamadas) == 2
    assert len(jev.llamadas) == 2, "no se revisa una tercera vez"
    fila = resultado.filas[combos[0].clave]
    assert fila.estado == "revisar"
    assert "datos personales" in fila.motivo_revision


@pytest.mark.db
def test_revision_no_toca_las_que_ya_estaban_en_cache(db) -> None:
    empresa = _empresa(db)
    combos = _combos(2)
    llm = LlmFalso()
    jev = JevFalso()

    primero = plantillas.generar_plantillas(db, empresa.id, combos, "es", "neutro", llm=llm)
    db.commit()
    segundo = plantillas.generar_plantillas(db, empresa.id, combos, "es", "neutro", llm=llm)

    revision.revisar_y_regenerar(
        db, empresa.id, combos, segundo, "es", "neutro", llm=llm, cliente=jev
    )

    assert not jev.llamadas, "nada nuevo que revisar: todo venía de caché"
    assert len(primero.nuevas) == 2 and not segundo.nuevas


# --- API: listar, editar, regenerar -----------------------------------------------------------


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


def _correr_con_mensajes(db, dataset, cfg, llm, jev):
    fila = base._analisis(db, dataset, ["recompra", "mensajes"], horizonte=14)
    orquestador.ejecutar(db, fila, lambda *_: None, cfg, cliente_jev=jev, llm=llm)
    return fila


@pytest.mark.db
def test_paso_mensajes_del_orquestador_genera_y_revisa(db, dataset, cfg) -> None:
    llm = LlmFalso()
    jev = JevFalso()

    fila = _correr_con_mensajes(db, dataset, cfg, llm, jev)

    assert "mensajes" in fila.resumen
    assert fila.resumen["mensajes"]["combinaciones"] > 0
    assert fila.resumen["mensajes"]["nuevas"] == fila.resumen["mensajes"]["combinaciones"]
    assert fila.costo_ia["llamadas"]["jev"] >= 1


@pytest.mark.db
def test_ruta_listar_editar_y_regenerar_plantillas(db, dataset, app, cfg) -> None:
    ana = _cliente(app, "Tienda Ana", "ana@ejemplo.com")
    beto = _cliente(app, "Tienda Beto", "beto@ejemplo.com")
    empresa_id = db.scalar(select(Usuario.empresa_id).where(Usuario.email == "ana@ejemplo.com"))
    dataset.empresa_id = empresa_id
    db.commit()

    llm, jev = LlmFalso(), JevFalso()
    fila = _correr_con_mensajes(db, dataset, cfg, llm, jev)
    db.commit()

    r = ana.get(f"/analisis/{fila.id}/plantillas")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo and all(p["estado"] == "ok" for p in cuerpo)

    assert beto.get(f"/analisis/{fila.id}/plantillas").status_code == 404

    plantilla_id = cuerpo[0]["id"]
    r = ana.patch(
        f"/plantillas-mensaje/{plantilla_id}",
        json={"texto": "Un mensaje escrito a mano."},
        headers={"X-CSRF-Token": ana.cookies[COOKIE_CSRF]},
    )
    assert r.status_code == 200
    assert r.json()["estado"] == "editada" and r.json()["texto"] == "Un mensaje escrito a mano."

    r = ana.patch(
        f"/plantillas-mensaje/{plantilla_id}",
        json={"texto": "x" * 301},
        headers={"X-CSRF-Token": ana.cookies[COOKIE_CSRF]},
    )
    assert r.status_code == 422

    r = ana.post(
        f"/analisis/{fila.id}/plantillas/regenerar",
        headers={"X-CSRF-Token": ana.cookies[COOKIE_CSRF]},
    )
    assert r.status_code == 202 and "trabajo_id" in r.json()
