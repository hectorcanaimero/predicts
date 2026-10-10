"""Tests de `comandos/medir_mapeo.py` con un Jev falso (sin red ni costo real): acierto por
columna, por campo, del prellenado y costo, sobre un set chico de fixtures armado en `tmp_path`
con el mismo formato que `api/tests/fixtures/desordenados/`."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from typesafe_sdk import ChoiceAnswer, SystemOneResponse, Usage

from predicts.comandos.medir_mapeo import medir
from predicts.config import settings_para_tests
from predicts.db.modelos import Empresa


def _eleccion(campo: str, confianza: float) -> ChoiceAnswer:
    return ChoiceAnswer(choice=campo, confidence=confianza, probabilities={campo: confianza})


class ClienteJevFalso:
    """Responde según `respuestas` (clave `columna::<nombre>` o `producto_id_tipo::<nombre>`);
    lo que no está ahí se contesta con `ignorar`/`sku` de relleno y confianza baja."""

    def __init__(self, respuestas: dict[str, ChoiceAnswer]) -> None:
        self._respuestas = respuestas

    def system_one(self, state, questions):
        answers = {}
        for nombre in questions:
            if nombre in self._respuestas:
                answers[nombre] = self._respuestas[nombre]
            elif nombre.startswith("producto_id_tipo::"):
                answers[nombre] = _eleccion("sku", 0.5)
            else:
                answers[nombre] = _eleccion("ignorar", 0.5)
        return SystemOneResponse(
            model="jev-test", usage=Usage(input_tokens=7, output_tokens=3), answers=answers
        )


def _escribir_fixture(
    carpeta: Path, nombre: str, encabezados: list[str], filas: list[list[str]], esperado: dict
) -> None:
    (carpeta / f"{nombre}.csv").write_text(
        "\n".join([",".join(encabezados)] + [",".join(f) for f in filas]) + "\n", encoding="utf-8"
    )
    (carpeta / f"{nombre}.esperado.json").write_text(json.dumps(esperado), encoding="utf-8")


@pytest.fixture()
def empresa(db) -> uuid.UUID:
    fila = Empresa(nombre="Acme")
    db.add(fila)
    db.flush()
    return fila.id


@pytest.fixture()
def fixtures_chicos(tmp_path: Path) -> Path:
    carpeta = tmp_path / "desordenados"
    carpeta.mkdir()

    # Un archivo donde Jev acierta las 3 columnas con confianza alta (prellenado y correcto).
    _escribir_fixture(
        carpeta,
        "ok",
        ["cli", "fecha_venda", "produto"],
        [["1", "01/02/2024", "4006381333931"], ["2", "02/02/2024", "4006381333931"]],
        {
            "columnas": {"cli": "cliente_id", "fecha_venda": "fecha", "produto": "producto_id"},
            "producto_id_tipo": "ean",
        },
    )
    # Un archivo donde Jev se equivoca en una columna (confianza alta, pero campo incorrecto) y
    # tiene baja confianza en otra (revisar).
    _escribir_fixture(
        carpeta,
        "con_error",
        ["cliente", "sucursal"],
        [["10", "SUC-01"], ["20", "SUC-02"]],
        {"columnas": {"cliente": "cliente_id", "sucursal": "ignorar"}, "producto_id_tipo": "sku"},
    )
    return carpeta


@pytest.mark.db
def test_medir_calcula_acierto_total_por_campo_prellenado_y_costo(db, empresa, fixtures_chicos):
    cliente = ClienteJevFalso(
        {
            "columna::cli": _eleccion("cliente_id", 0.95),
            "columna::fecha_venda": _eleccion("fecha", 0.9),
            "columna::produto": _eleccion("producto_id", 0.9),
            "columna::cliente": _eleccion("cliente_id", 0.95),
            # "sucursal" no mapeada a propósito: Jev la manda a un campo equivocado, con alta
            # confianza (queda prellenada e incorrecta).
            "columna::sucursal": _eleccion("marca", 0.85),
        }
    )

    medicion = medir(fixtures_chicos, db, empresa, cliente=cliente, cfg=settings_para_tests())

    assert len(medicion.columnas) == 5
    # 4 de 5 columnas aciertan (todas salvo "sucursal" -> "marca" en vez de "ignorar").
    assert medicion.acierto_total == pytest.approx(4 / 5)
    assert medicion.acierto_por_campo()["cliente_id"] == pytest.approx(1.0)
    assert medicion.acierto_por_campo()["ignorar"] == pytest.approx(0.0)
    # Las 5 quedaron con confianza >= CONFIANZA_MAPEO (0.8 por defecto): prellenado 100%, pero
    # con el error de "sucursal" adentro el acierto del prellenado es el mismo 4/5.
    assert medicion.porcentaje_prellenado() == pytest.approx(1.0)
    assert medicion.acierto_prellenado() == pytest.approx(4 / 5)
    assert medicion.acierto_producto_id_tipo() == pytest.approx(1.0)
    assert medicion.costo["llamadas"]["jev"] == 2  # una llamada a decidir_lote por archivo
    errores = medicion.errores()
    assert len(errores) == 1
    assert errores[0].columna == "sucursal" and errores[0].campo_esperado == "ignorar"


@pytest.mark.db
def test_medir_cuenta_revisar_cuando_la_confianza_es_baja(db, empresa, fixtures_chicos):
    cliente = ClienteJevFalso(
        {
            "columna::cli": _eleccion("cliente_id", 0.5),  # confianza baja -> revisar
            "columna::fecha_venda": _eleccion("fecha", 0.9),
            "columna::produto": _eleccion("producto_id", 0.9),
            "columna::cliente": _eleccion("cliente_id", 0.95),
            "columna::sucursal": _eleccion("ignorar", 0.95),
        }
    )

    medicion = medir(fixtures_chicos, db, empresa, cliente=cliente, cfg=settings_para_tests())

    assert medicion.acierto_total == pytest.approx(1.0)
    # 4 de 5 columnas quedaron con confianza alta (todas salvo "cli").
    assert medicion.porcentaje_prellenado() == pytest.approx(4 / 5)
    assert medicion.acierto_prellenado() == pytest.approx(1.0)
    assert medicion.errores() == []
