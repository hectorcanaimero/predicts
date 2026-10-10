"""Jev revisa cada plantilla recién generada, en lotes: sí (`aprobada`) o no con un motivo
(`promesa_no_garantizada`, `datos_sensibles`, `tono_distinto` o `marcador_mal_usado`), vía
`decidir_lote` (un `Choice` por plantilla; la opción elegida es el motivo).

Rechazada → se regenera una vez con el motivo (`plantillas.generar_lote`) y se revisa de nuevo;
si vuelve a fallar queda `estado="revisar"`. Cada decisión de Jev queda en `decisiones_jev`
(tipo `revision_mensaje`, referencia = la plantilla).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session
from typesafe_sdk import Choice, TypeSafeClient

from predicts.db.modelos import PlantillaMensaje as PlantillaMensajeFila
from predicts.ia import Contador, decidir_lote, registrar_decision
from predicts.mensajes import plantillas

TAMANO_LOTE = 20

_CRITERIOS = {
    "aprobada": "El mensaje está bien para enviar: no promete nada que el sistema no garantiza, "
    "no tiene datos personales del cliente, el tono es el pedido y los marcadores están bien "
    "usados.",
    "promesa_no_garantizada": "Promete algo que el sistema no garantiza (p. ej. un descuento, "
    "una fecha exacta o una cantidad que no vino en los datos).",
    "datos_sensibles": "Incluye datos personales o sensibles del cliente.",
    "tono_distinto": "El tono del mensaje no es el que se pidió.",
    "marcador_mal_usado": "Usa mal los marcadores ({producto}, {dias}, {oferta}, "
    "{nombre_tienda}): le faltan, están de más, hay uno inventado, o el texto no tiene sentido "
    "con el valor que van a tener.",
}

_PREGUNTA = (
    'Revisá este mensaje para clientes, con tono "{tono}" pedido: "{texto}". ¿Está bien para '
    "enviar tal cual, o hay que rechazarlo? Elegí el motivo si hay que rechazarlo."
)


@dataclass(frozen=True)
class Resultado:
    aprobada: bool
    motivo: str | None


def _revisar_lote_jev(
    db: Session,
    empresa_id: uuid.UUID,
    filas: Sequence[PlantillaMensajeFila],
    tono: str,
    cliente: TypeSafeClient | None,
    contador: Contador | None,
) -> dict[uuid.UUID, Resultado]:
    resultados: dict[uuid.UUID, Resultado] = {}
    for inicio in range(0, len(filas), TAMANO_LOTE):
        lote = filas[inicio : inicio + TAMANO_LOTE]
        preguntas = {
            str(f.id): Choice(
                instructions=_PREGUNTA.format(tono=tono, texto=f.texto), criteria=_CRITERIOS
            )
            for f in lote
        }
        decisiones = decidir_lote(
            {"tono_pedido": tono}, preguntas, cliente=cliente, contador=contador
        )
        for f in lote:
            decision = decisiones[str(f.id)]
            aprobada = decision.opcion == "aprobada"
            motivo = None if aprobada else _CRITERIOS[decision.opcion]
            resultados[f.id] = Resultado(aprobada, motivo)
            registrar_decision(
                db,
                empresa_id,
                "revision_mensaje",
                f.id,
                {"clave": f.clave, "opcion": decision.opcion},
                decision,
            )
    return resultados


def revisar_y_regenerar(
    db: Session,
    empresa_id: uuid.UUID,
    combos: Sequence[plantillas.Combinacion],
    resultado: plantillas.ResultadoGeneracion,
    idioma: str,
    tono: str,
    *,
    llm=None,
    cliente: TypeSafeClient | None = None,
    contador: Contador | None = None,
) -> None:
    """Revisa con Jev las plantillas `nuevas` de `resultado` (no toca las que ya estaban en
    caché). Muta las filas in place: `estado` queda en `ok` o `revisar`, y `motivo_revision` en
    el motivo del rechazo final (si quedó `revisar`)."""
    nuevas_ids = {f.id for f in resultado.nuevas}
    combos_por_clave = {c.clave: c for c in combos}
    pendientes = {
        clave: fila
        for clave, fila in resultado.filas.items()
        if fila.id in nuevas_ids and clave in combos_por_clave
    }
    for ultimo_intento in (False, True):
        if not pendientes:
            return
        resultados_jev = _revisar_lote_jev(
            db, empresa_id, list(pendientes.values()), tono, cliente, contador
        )
        siguientes: dict[str, PlantillaMensajeFila] = {}
        motivos: dict[str, str] = {}
        for clave, fila in pendientes.items():
            decision = resultados_jev[fila.id]
            if decision.aprobada:
                fila.estado, fila.motivo_revision = "ok", None
            elif ultimo_intento:
                fila.estado, fila.motivo_revision = "revisar", decision.motivo
            else:
                siguientes[clave] = fila
                motivos[clave] = decision.motivo or ""
        if not siguientes or ultimo_intento:
            return
        claves = list(siguientes)
        for inicio in range(0, len(claves), plantillas.TAMANO_LOTE):
            lote_claves = claves[inicio : inicio + plantillas.TAMANO_LOTE]
            lote_combos = [combos_por_clave[c] for c in lote_claves]
            textos = plantillas.generar_lote(
                lote_combos,
                idioma,
                tono,
                llm=llm,
                contador=contador,
                motivos={c: motivos[c] for c in lote_claves},
            )
            for clave in lote_claves:
                siguientes[clave].texto = textos[clave]
        pendientes = siguientes
