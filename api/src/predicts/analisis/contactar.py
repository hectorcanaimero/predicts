"""¿Contactar? (FR-20): una decisión por cliente con algo que decirle (recordatorio o riesgo).

Entran los clientes con algún par a `p ≥ umbral − MARGEN` o alguna fila en `res_riesgo`.

- **Casos límite → Jev** (`decidir_lote`, un `Noul` por cliente, `TAMANO_LOTE` por llamada):
  - alguna probabilidad a ±`MARGEN` del umbral;
  - `≥ 2` recordatorios (`p ≥ umbral`) con la misma fecha probable (varios el mismo día);
  - en riesgo y en recompra a la vez.
  Sí con confianza ≥ `CONFIANZA_JEV` → `contactar`; no → `no_contactar`; confianza por debajo →
  `revisar` (lo decide la persona). Cada decisión queda en `decisiones_jev` (tipo `contactar`,
  referencia = el análisis, `cliente_id` en la entrada).
- **Casos claros → regla en código** (sin Jev): recordatorios todos por encima de
  `umbral + MARGEN` → `contactar` (recordatorio); solo en riesgo → `contactar` (reactivación).
  Los clientes sin nada por encima de `umbral − MARGEN` ni riesgo no se contactan y no se listan.
"""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

import pyarrow as pa
from sqlalchemy.orm import Session
from typesafe_sdk import Noul, TypeSafeClient

from predicts.config import Settings
from predicts.ia import Contador, decidir_lote, registrar_decision
from predicts.modelo import Ajuste

NOMBRE = "contactar.parquet"
MARGEN = 0.1
TAMANO_LOTE = 50
MAX_ITEMS_CONTEXTO = 10

_PREGUNTA = (
    "¿Vale la pena contactar hoy a este cliente con un recordatorio u oferta? Decí que no si "
    "molestarlo parece poco útil (probabilidades bajas o dudosas, demasiados avisos juntos, o "
    "señales de que se fue y un recordatorio no lo traería de vuelta). Usa los recordatorios "
    "(producto, probabilidad de compra en el horizonte, fecha probable), el umbral y las "
    "señales de abandono."
)


def _casos(ajuste: Ajuste, prediccion: str, nombres: str, riesgo: str, umbral: float) -> pa.Table:
    tabla = ajuste.con.execute(
        f"""
        WITH cand AS (
            SELECT p.*, n.producto_nombre FROM {prediccion} p
            LEFT JOIN {nombres} n USING (producto_id)
            WHERE p >= $umbral - $margen
        ),
        mismo_dia AS (
            SELECT cliente_id, max(n) AS mismo_dia FROM (
                SELECT cliente_id, fecha_probable, count(*) AS n FROM cand WHERE p >= $umbral
                GROUP BY ALL
            ) GROUP BY 1
        ),
        rec AS (
            SELECT cliente_id, count(*) FILTER (WHERE p >= $umbral) AS recordatorios,
                   bool_or(abs(p - $umbral) <= $margen) AS cerca_umbral, max(p) AS p_max,
                   list({{'producto': producto_nombre, 'p': round(p, 2),
                          'fecha_probable': CAST(fecha_probable AS VARCHAR)}}
                        ORDER BY p DESC)[1:{MAX_ITEMS_CONTEXTO}] AS items
            FROM cand GROUP BY 1
        ),
        ries AS (
            SELECT cliente_id, list(motivo ORDER BY atraso DESC) AS motivos_riesgo
            FROM {riesgo} GROUP BY 1
        )
        SELECT coalesce(rec.cliente_id, ries.cliente_id) AS cliente_id,
               coalesce(rec.recordatorios, 0) AS recordatorios,
               coalesce(rec.cerca_umbral, false) AS cerca_umbral,
               coalesce(md.mismo_dia, 0) AS mismo_dia,
               ries.cliente_id IS NOT NULL AS en_riesgo, rec.p_max,
               rec.items,
               ries.motivos_riesgo[1:{MAX_ITEMS_CONTEXTO}] AS motivos_riesgo
        FROM rec FULL JOIN ries USING (cliente_id)
        LEFT JOIN mismo_dia md USING (cliente_id)
        ORDER BY cliente_id
        """,
        {"umbral": umbral, "margen": MARGEN},
    ).arrow()
    return tabla.read_all() if isinstance(tabla, pa.RecordBatchReader) else tabla


def es_limite(caso: dict) -> bool:
    return (
        caso["cerca_umbral"]
        or caso["mismo_dia"] >= 2
        or (caso["en_riesgo"] and caso["p_max"] is not None)
    )


def _regla(caso: dict) -> tuple[str, str]:
    if caso["recordatorios"]:
        return "contactar", f"{caso['recordatorios']} recordatorio(s) con probabilidad alta."
    return "contactar", "Cliente en riesgo de abandono: mensaje de reactivación."


def decidir(
    ajuste: Ajuste,
    prediccion: str,
    nombres: str,
    riesgo: str,
    umbral: float,
    horizonte: int,
    fecha_ref: date,
    resultados: Path,
    *,
    db: Session,
    empresa_id: uuid.UUID,
    analisis_id: uuid.UUID,
    cfg: Settings,
    cliente: TypeSafeClient | None = None,
    contador: Contador | None = None,
) -> dict:
    """Escribe `resultados/contactar.parquet` y devuelve los totales para el resumen.

    Columnas: cliente_id, decision (`contactar`|`no_contactar`|`revisar`), origen
    (`regla`|`jev`), confianza (solo Jev), recordatorios, cerca_umbral, mismo_dia, en_riesgo,
    p_max, motivo.
    """
    casos = _casos(ajuste, prediccion, nombres, riesgo, umbral).to_pylist()
    filas: list[dict] = []
    limite: list[dict] = []
    for caso in casos:
        if es_limite(caso):
            limite.append(caso)
        else:
            decision, motivo = _regla(caso)
            filas.append(
                {
                    **caso,
                    "decision": decision,
                    "origen": "regla",
                    "confianza": None,
                    "motivo": motivo,
                }
            )

    for inicio in range(0, len(limite), TAMANO_LOTE):
        lote = limite[inicio : inicio + TAMANO_LOTE]
        entradas = {
            c["cliente_id"]: {
                "pregunta": _PREGUNTA,
                "umbral": umbral,
                "horizonte_dias": horizonte,
                "fecha": fecha_ref.isoformat(),
                "recordatorios": c["items"] or [],
                "senales_abandono": c["motivos_riesgo"] or [],
            }
            for c in lote
        }
        decisiones = decidir_lote(
            {"empresa_id": str(empresa_id), "analisis_id": str(analisis_id)},
            {f"cliente::{k}": Noul(instructions=v) for k, v in entradas.items()},
            cliente=cliente,
            contador=contador,
        )
        for c in lote:
            d = decisiones[f"cliente::{c['cliente_id']}"]
            registrar_decision(
                db,
                empresa_id,
                "contactar",
                analisis_id,
                {"cliente_id": c["cliente_id"], **entradas[c["cliente_id"]]},
                d,
            )
            if d.confianza < cfg.CONFIANZA_JEV:
                decision = "revisar"
            else:
                decision = "contactar" if d.opcion == "si" else "no_contactar"
            motivo = (
                f"Caso límite decidido por Jev ({d.opcion}, confianza "
                f"{round(100 * d.confianza)} %)."
            )
            filas.append(
                {
                    **c,
                    "decision": decision,
                    "origen": "jev",
                    "confianza": d.confianza,
                    "motivo": motivo,
                }
            )

    esquema = pa.schema(
        [
            ("cliente_id", pa.string()),
            ("decision", pa.string()),
            ("origen", pa.string()),
            ("confianza", pa.float64()),
            ("recordatorios", pa.int64()),
            ("cerca_umbral", pa.bool_()),
            ("mismo_dia", pa.int64()),
            ("en_riesgo", pa.bool_()),
            ("p_max", pa.float64()),
            ("motivo", pa.string()),
        ]
    )
    tabla = pa.Table.from_pylist(filas, schema=esquema).sort_by("cliente_id")
    ajuste.con.register("_contactar", tabla)
    ruta = str(resultados / NOMBRE).replace("'", "''")
    ajuste.con.execute(f"COPY _contactar TO '{ruta}' (FORMAT parquet)")
    ajuste.con.unregister("_contactar")
    por_decision: dict[str, int] = {}
    for f in filas:
        por_decision[f["decision"]] = por_decision.get(f["decision"], 0) + 1
    return {
        "clientes": len(filas),
        "por_jev": len(limite),
        "por_regla": len(filas) - len(limite),
        "por_decision": por_decision,
    }
