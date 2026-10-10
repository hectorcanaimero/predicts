"""Clasificación de productos (ver specs/f4-analisis.md#F4.2.T1):

- **Recompra o durable**: regla previa sin Jev (`_regla_tipo`); solo lo ambiguo va a Jev, en
  lotes de `TAMANO_LOTE` productos por llamada a `decidir_lote` (una pregunta `Noul` por
  producto). Confianza por debajo de `CONFIANZA_JEV` → `estado_revision = "revisar"`.
- **Categoría**: `Choice` sobre `taxonomia.json`, solo para productos sin categoría (la del CSV
  siempre gana, ver `catalogo.py`).
- Caché: un producto con `tipo_origen`/`categoria_origen` ya puesto no se vuelve a preguntar,
  salvo `forzar=True` (la persona lo pide explícitamente).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator, Sequence
from pathlib import Path

from sqlalchemy.orm import Session
from typesafe_sdk import Choice, Noul, Question, TypeSafeClient

from predicts.config import Settings, settings
from predicts.db.modelos import Producto
from predicts.ia import Contador, decidir_lote, registrar_decision

TAMANO_LOTE = 50

# Regla previa (sin Jev) para recompra/durable.
PORCENTAJE_RECOMPRA_MIN = 0.30
DIAS_RECOMPRA_MAX = 120
CLIENTES_DURABLE_MIN = 50

_TAXONOMIA_RUTA = Path(__file__).parent / "taxonomia.json"

_PREGUNTA_TIPO = (
    "¿Este producto es de recompra habitual (la gente lo vuelve a comprar periódicamente, "
    "p. ej. un consumible) o es durable (se compra una vez y dura mucho, p. ej. un "
    "electrodoméstico o un mueble)? Usa el nombre, la categoría si la hay y las estadísticas "
    "de compra para decidir."
)

_PREGUNTA_CATEGORIA = (
    "¿A qué categoría de la lista pertenece este producto? Usa el nombre y las estadísticas "
    "de compra para decidir."
)


def _cargar_taxonomia() -> dict[str, dict[str, str]]:
    return json.loads(_TAXONOMIA_RUTA.read_text(encoding="utf-8"))


def _criterios_categoria(taxonomia: dict[str, dict[str, str]]) -> dict[str, str]:
    return {slug: " / ".join(nombres.values()) for slug, nombres in taxonomia.items()}


def _regla_tipo(producto: Producto) -> str | None:
    """`"recompra"`/`"durable"` si la regla decide sin Jev; `None` si es ambiguo."""
    stats = producto.estadisticas or {}
    clientes = stats.get("clientes") or 0
    clientes_recompra = stats.get("clientes_recompra") or 0
    mediana = stats.get("mediana_intervalo_dias")

    if (
        clientes > 0
        and clientes_recompra / clientes >= PORCENTAJE_RECOMPRA_MIN
        and mediana is not None
        and mediana < DIAS_RECOMPRA_MAX
    ):
        return "recompra"
    if clientes_recompra == 0 and clientes >= CLIENTES_DURABLE_MIN:
        return "durable"
    return None


def _contexto_producto(producto: Producto) -> dict:
    stats = producto.estadisticas or {}
    return {
        "nombre": producto.nombre,
        "categoria": producto.categoria,
        "clientes": stats.get("clientes"),
        "clientes_recompra": stats.get("clientes_recompra"),
        "mediana_intervalo_dias": stats.get("mediana_intervalo_dias"),
        "precio_medio": stats.get("precio_medio"),
    }


def _clave_tipo(producto_id: uuid.UUID) -> str:
    return f"tipo::{producto_id}"


def _clave_categoria(producto_id: uuid.UUID) -> str:
    return f"categoria::{producto_id}"


def _en_lotes(productos: Sequence[Producto], tamano: int) -> Iterator[Sequence[Producto]]:
    for inicio in range(0, len(productos), tamano):
        yield productos[inicio : inicio + tamano]


def clasificar_productos(
    db: Session,
    empresa_id: uuid.UUID,
    productos: Sequence[Producto],
    *,
    cliente: TypeSafeClient | None = None,
    contador: Contador | None = None,
    forzar: bool = False,
    cfg: Settings | None = None,
) -> None:
    """Clasifica `productos` en tipo (recompra/durable) y categoría.

    La regla previa decide el tipo sin llamar a Jev cuando puede; lo ambiguo (y, si el CSV no
    trae categoría, la categoría) va a Jev en lotes de `TAMANO_LOTE`. Si un producto ya tiene
    `tipo_origen`/`categoria_origen` puesto, no se vuelve a preguntar a menos que `forzar=True`.
    """
    cfg = cfg or settings()
    pendientes_tipo: list[Producto] = []
    pendientes_categoria: list[Producto] = []

    for producto in productos:
        if forzar or producto.tipo_origen is None:
            tipo_regla = _regla_tipo(producto)
            if tipo_regla is not None:
                producto.tipo = tipo_regla
                producto.tipo_origen = "regla"
                producto.confianza = None
                producto.estado_revision = "ok"
            else:
                pendientes_tipo.append(producto)

        if producto.categoria_origen != "csv" and (forzar or producto.categoria_origen is None):
            pendientes_categoria.append(producto)

    if pendientes_tipo:
        for lote in _en_lotes(pendientes_tipo, TAMANO_LOTE):
            preguntas: dict[str, Question] = {
                _clave_tipo(p.id): Noul(
                    instructions={"pregunta": _PREGUNTA_TIPO, **_contexto_producto(p)}
                )
                for p in lote
            }
            decisiones = decidir_lote(
                {"empresa_id": str(empresa_id)}, preguntas, cliente=cliente, contador=contador
            )
            for p in lote:
                decision = decisiones[_clave_tipo(p.id)]
                p.tipo = "recompra" if decision.opcion == "si" else "durable"
                p.tipo_origen = "jev"
                p.confianza = decision.confianza
                p.estado_revision = "ok" if decision.confianza >= cfg.CONFIANZA_JEV else "revisar"
                registrar_decision(
                    db, empresa_id, "tipo_producto", p.id, _contexto_producto(p), decision
                )

    if pendientes_categoria:
        criterios_categoria = _criterios_categoria(_cargar_taxonomia())
        for lote in _en_lotes(pendientes_categoria, TAMANO_LOTE):
            preguntas = {
                _clave_categoria(p.id): Choice(
                    instructions={"pregunta": _PREGUNTA_CATEGORIA, **_contexto_producto(p)},
                    criteria=criterios_categoria,
                )
                for p in lote
            }
            decisiones = decidir_lote(
                {"empresa_id": str(empresa_id)}, preguntas, cliente=cliente, contador=contador
            )
            for p in lote:
                decision = decisiones[_clave_categoria(p.id)]
                p.categoria = decision.opcion
                p.categoria_origen = "jev"
                if decision.confianza < cfg.CONFIANZA_JEV:
                    p.estado_revision = "revisar"
                registrar_decision(
                    db, empresa_id, "categoria", p.id, _contexto_producto(p), decision
                )
