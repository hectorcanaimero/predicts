"""Mapeo de columnas del CSV detectado al esquema interno de compras, con sugerencias de Jev
y plantillas por empresa (ver docs/arch/001-predicts.md#datos-de-entrada).

`sugerir` hace **una sola llamada** a `decidir_lote` (`predicts.ia`): una pregunta `Choice` por
columna (campo del esquema interno, o `ignorar`) y, para las columnas donde la regla de EAN no
decide, otra pregunta `Choice` de `sku`/`ean` (se usa solo la de la columna que termine elegida
como `producto_id`). Si existe una plantilla de la empresa con la misma firma de encabezados, se
usa esa en vez de llamar a Jev.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from typesafe_sdk import Choice, Question, TypeSafeClient

from predicts.config import Settings, settings
from predicts.datos.deteccion import Deteccion
from predicts.datos.esquema import COLUMNAS_COMPRA
from predicts.db.modelos import PlantillaMapeo
from predicts.ia import Contador, decidir_lote, registrar_decision

IGNORAR = "ignorar"

# Campos del esquema interno que se pueden elegir para una columna del CSV (`producto_id_tipo`
# no está acá: no se elige mapeando una columna, se decide aparte para la columna que resulte
# `producto_id`). Cada descripción es la que ve Jev como criterio de la pregunta `Choice`.
CAMPOS_ESQUEMA: dict[str, str] = {
    "cliente_id": "Identificador único de la persona o empresa que compra: ID, documento, "
    "email o teléfono del cliente.",
    "fecha": "Fecha (y hora, si la tiene) en que ocurrió la compra o el pedido.",
    "producto_id": "Identificador único del producto: SKU/código interno o EAN/código de barras.",
    "producto_nombre": "Nombre o descripción del producto.",
    "pedido_id": "Identificador del pedido o la transacción, agrupa varias líneas de un mismo "
    "pedido.",
    "cantidad": "Cantidad de unidades compradas en esta línea.",
    "precio_unitario": "Precio de una sola unidad del producto.",
    "valor_total": "Valor total de la línea (cantidad × precio, o el total ya calculado).",
    "categoria": "Categoría o familia del producto.",
    "marca": "Marca del producto.",
}

_CRITERIOS_CAMPOS: dict[str, str] = {
    **CAMPOS_ESQUEMA,
    IGNORAR: "La columna no corresponde a ningún campo del esquema interno y debe ignorarse "
    "(p. ej. sucursal, vendedor, forma de pago).",
}

_CRITERIOS_PRODUCTO_ID_TIPO: dict[str, str] = {
    "sku": "Código interno propio de la empresa, no es un código de barras estándar.",
    "ean": "Código de barras estándar (EAN/UPC/GTIN) de 8, 12, 13 o 14 dígitos.",
}

_CAMPOS_OBLIGATORIOS: tuple[str, ...] = tuple(
    c.nombre for c in COLUMNAS_COMPRA if c.obligatoria and c.nombre != "producto_id_tipo"
)


class SugerenciaColumna(BaseModel):
    columna: str
    campo: str
    confianza: float
    origen: str  # "jev" | "plantilla"
    estado: str  # "prellenado" | "revisar"


class SugerenciaProductoIdTipo(BaseModel):
    tipo: str  # "sku" | "ean"
    confianza: float
    origen: str  # "regla" | "jev" | "plantilla"


class Sugerencias(BaseModel):
    columnas: list[SugerenciaColumna]
    producto_id_tipo: SugerenciaProductoIdTipo | None
    origen: str  # "jev" | "plantilla"
    firma_encabezados: str


class MapeoColumna(BaseModel):
    columna: str
    campo: str


class MapeoConfirmado(BaseModel):
    columnas: list[MapeoColumna]
    producto_id_tipo: str
    formato_fecha: str


class ErrorValidacionMapeo(BaseModel):
    codigo: str
    parametros: dict[str, Any] = {}


# --- Enmascaramiento de valores de muestra (email, teléfono, CPF) --------------------------

# Email: local@dominio.tld, sin espacios ni '@' de más.
_RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# CPF formateado (el único patrón no ambiguo con un teléfono): 000.000.000-00.
_RE_CPF_FORMATEADO = re.compile(r"^\d{3}\.\d{3}\.\d{3}-\d{2}$")
# Teléfono: solo dígitos, espacios, '+', '()' y '-', con entre 8 y 15 dígitos en total (rango de
# números de teléfono reales); evita enmascarar por error ids numéricos cortos o largos.
_RE_TELEFONO_CARACTERES = re.compile(r"^\+?[\d\s().-]+$")


def _es_telefono(valor: str) -> bool:
    if not _RE_TELEFONO_CARACTERES.match(valor):
        return False
    digitos = sum(c.isdigit() for c in valor)
    return 8 <= digitos <= 15


def _enmascarar_digitos(valor: str, mantener_final: int = 2) -> str:
    """Oculta todos los dígitos de `valor` excepto los últimos `mantener_final`."""
    posiciones_digito = [i for i, c in enumerate(valor) if c.isdigit()]
    ocultar = set(posiciones_digito[:-mantener_final])
    return "".join("*" if i in ocultar else c for i, c in enumerate(valor))


def _enmascarar_dominio(dominio: str) -> str:
    """Oculta el dominio de un email, conservando el último segmento (el TLD)."""
    partes = dominio.rsplit(".", 1)
    if len(partes) != 2:
        return "*" * len(dominio)
    nombre, tld = partes
    return f"{'*' * len(nombre)}.{tld}"


def enmascarar_valor(valor: str) -> str:
    """Enmascara `valor` si parece email, teléfono o CPF; si no, lo deja igual."""
    if _RE_EMAIL.match(valor):
        local, _, dominio = valor.partition("@")
        local_enmascarado = local[0] + "*" * (len(local) - 1) if local else local
        return f"{local_enmascarado}@{_enmascarar_dominio(dominio)}"
    if _RE_CPF_FORMATEADO.match(valor):
        return _enmascarar_digitos(valor)
    if _es_telefono(valor):
        return _enmascarar_digitos(valor)
    return valor


def _muestras_enmascaradas(valores: Sequence[str]) -> list[str]:
    return [enmascarar_valor(v) for v in valores]


# --- Regla de EAN (dígito verificador GTIN-8/12/13/14) -----------------------------------


def _digito_verificador_ean_valido(codigo: str) -> bool:
    if not codigo.isdigit() or len(codigo) not in (8, 12, 13, 14):
        return False
    digitos = [int(c) for c in codigo]
    cuerpo, verificador = digitos[:-1], digitos[-1]
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(cuerpo)))
    return (10 - total % 10) % 10 == verificador


def _tipo_producto_id_por_regla(valores: Sequence[str]) -> str | None:
    """`"ean"` si todos los valores de muestra son un EAN con dígito verificador válido;
    `None` si la regla no puede decidir (hay que preguntarle a Jev)."""
    if not valores:
        return None
    return "ean" if all(_digito_verificador_ean_valido(v) for v in valores) else None


# --- Firma de encabezados (plantillas) ----------------------------------------------------


def _normalizar_encabezado(nombre: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", "", sin_acentos.lower())


def firma_encabezados(columnas: Sequence[str]) -> str:
    """SHA-256 de los encabezados normalizados (minúsculas, sin acentos ni espacios, ordenados)."""
    normalizados = sorted(_normalizar_encabezado(c) for c in columnas)
    return hashlib.sha256("|".join(normalizados).encode("utf-8")).hexdigest()


# --- Preguntas a Jev ------------------------------------------------------------------------


def clave_pregunta_columna(nombre_columna: str) -> str:
    return f"columna::{nombre_columna}"


def clave_pregunta_producto_id_tipo(nombre_columna: str) -> str:
    return f"producto_id_tipo::{nombre_columna}"


def _pregunta_columna(
    columna_nombre: str, columna_tipo: str, valores_muestra: Sequence[str]
) -> Choice:
    return Choice(
        instructions={
            "pregunta": "¿A qué campo del esquema interno de compras corresponde esta columna "
            "del CSV subido? Si no corresponde a ninguno, elige 'ignorar'.",
            "columna": columna_nombre,
            "tipo_detectado": columna_tipo,
            "valores_muestra": _muestras_enmascaradas(valores_muestra),
        },
        criteria=_CRITERIOS_CAMPOS,
    )


def _pregunta_producto_id_tipo(columna_nombre: str, valores_muestra: Sequence[str]) -> Choice:
    return Choice(
        instructions={
            "pregunta": "Si esta columna fuera el identificador del producto, ¿es un SKU "
            "(código interno de la empresa) o un EAN (código de barras estándar)?",
            "columna": columna_nombre,
            "valores_muestra": _muestras_enmascaradas(valores_muestra),
        },
        criteria=_CRITERIOS_PRODUCTO_ID_TIPO,
    )


def _sugerencias_desde_plantilla(
    plantilla: PlantillaMapeo, deteccion: Deteccion, firma: str
) -> Sugerencias:
    por_normalizado = {
        _normalizar_encabezado(c["columna"]): c for c in plantilla.mapeo.get("columnas", [])
    }
    columnas_sugeridas = []
    for columna in deteccion.columnas:
        entrada = por_normalizado.get(_normalizar_encabezado(columna.nombre))
        campo = entrada["campo"] if entrada is not None else IGNORAR
        columnas_sugeridas.append(
            SugerenciaColumna(
                columna=columna.nombre, campo=campo, confianza=1.0, origen="plantilla",
                estado="prellenado",
            )
        )

    producto_id_tipo = None
    if plantilla.mapeo.get("producto_id_tipo"):
        producto_id_tipo = SugerenciaProductoIdTipo(
            tipo=plantilla.mapeo["producto_id_tipo"], confianza=1.0, origen="plantilla"
        )

    return Sugerencias(
        columnas=columnas_sugeridas, producto_id_tipo=producto_id_tipo, origen="plantilla",
        firma_encabezados=firma,
    )


def sugerir(
    deteccion: Deteccion,
    db: Session,
    empresa_id: uuid.UUID,
    dataset_id: uuid.UUID,
    cliente: TypeSafeClient | None = None,
    contador: Contador | None = None,
    cfg: Settings | None = None,
) -> Sugerencias:
    """Sugiere el mapeo de columnas de `deteccion` al esquema interno.

    Si hay una plantilla de la empresa con la misma firma de encabezados, se usa esa (confianza
    1, origen `plantilla`) sin llamar a Jev. Si no, una sola llamada a `decidir_lote` decide el
    campo de cada columna y, para las que la regla de EAN no resuelve, si serían `sku` o `ean`
    (solo se usa la respuesta de la columna que termine elegida como `producto_id`).
    """
    cfg = cfg or settings()
    nombres_columnas = [c.nombre for c in deteccion.columnas]
    firma = firma_encabezados(nombres_columnas)

    plantilla = db.scalar(
        select(PlantillaMapeo).where(
            PlantillaMapeo.empresa_id == empresa_id,
            PlantillaMapeo.firma_encabezados == firma,
        )
    )
    if plantilla is not None:
        return _sugerencias_desde_plantilla(plantilla, deteccion, firma)

    preguntas: dict[str, Question] = {}
    tipo_por_regla: dict[str, str] = {}
    for columna in deteccion.columnas:
        preguntas[clave_pregunta_columna(columna.nombre)] = _pregunta_columna(
            columna.nombre, columna.tipo, columna.valores_muestra
        )
        decidido = _tipo_producto_id_por_regla(columna.valores_muestra)
        if decidido is not None:
            tipo_por_regla[columna.nombre] = decidido
        else:
            preguntas[clave_pregunta_producto_id_tipo(columna.nombre)] = _pregunta_producto_id_tipo(
                columna.nombre, columna.valores_muestra
            )

    decisiones = decidir_lote(
        {"dataset_id": str(dataset_id)}, preguntas, cliente=cliente, contador=contador
    )

    columnas_sugeridas: list[SugerenciaColumna] = []
    columna_producto_id: str | None = None
    for columna in deteccion.columnas:
        decision = decisiones[clave_pregunta_columna(columna.nombre)]
        estado = "prellenado" if decision.confianza >= cfg.CONFIANZA_MAPEO else "revisar"
        columnas_sugeridas.append(
            SugerenciaColumna(
                columna=columna.nombre, campo=decision.opcion, confianza=decision.confianza,
                origen="jev", estado=estado,
            )
        )
        registrar_decision(
            db, empresa_id, "mapeo_columna", dataset_id,
            {
                "columna": columna.nombre, "tipo_detectado": columna.tipo,
                "valores_muestra": _muestras_enmascaradas(columna.valores_muestra),
            },
            decision,
        )
        if decision.opcion == "producto_id" and columna_producto_id is None:
            columna_producto_id = columna.nombre

    producto_id_tipo: SugerenciaProductoIdTipo | None = None
    if columna_producto_id is not None:
        if columna_producto_id in tipo_por_regla:
            producto_id_tipo = SugerenciaProductoIdTipo(
                tipo=tipo_por_regla[columna_producto_id], confianza=1.0, origen="regla"
            )
        else:
            decision_tipo = decisiones[clave_pregunta_producto_id_tipo(columna_producto_id)]
            producto_id_tipo = SugerenciaProductoIdTipo(
                tipo=decision_tipo.opcion, confianza=decision_tipo.confianza, origen="jev"
            )
            registrar_decision(
                db, empresa_id, "mapeo_columna", dataset_id,
                {"columna": columna_producto_id, "sub_pregunta": "producto_id_tipo"},
                decision_tipo,
            )

    return Sugerencias(
        columnas=columnas_sugeridas, producto_id_tipo=producto_id_tipo, origen="jev",
        firma_encabezados=firma,
    )


def validar(mapeo: MapeoConfirmado, deteccion: Deteccion) -> list[ErrorValidacionMapeo]:
    """Valida un mapeo confirmado: campos obligatorios presentes y únicos, formato de fecha
    elegido y tipo de identificador de producto. Devuelve los errores encontrados (vacía si es
    válido), cada uno con un código."""
    errores: list[ErrorValidacionMapeo] = []
    nombres_deteccion = {c.nombre for c in deteccion.columnas}

    por_campo: dict[str, list[str]] = {}
    for col in mapeo.columnas:
        if col.columna not in nombres_deteccion:
            errores.append(
                ErrorValidacionMapeo(
                    codigo="columna_desconocida", parametros={"columna": col.columna}
                )
            )
            continue
        if col.campo == IGNORAR:
            continue
        if col.campo not in CAMPOS_ESQUEMA:
            errores.append(
                ErrorValidacionMapeo(codigo="campo_desconocido", parametros={"campo": col.campo})
            )
            continue
        por_campo.setdefault(col.campo, []).append(col.columna)

    for campo, columnas in por_campo.items():
        if len(columnas) > 1:
            errores.append(
                ErrorValidacionMapeo(
                    codigo="campo_duplicado", parametros={"campo": campo, "columnas": columnas}
                )
            )

    for campo in _CAMPOS_OBLIGATORIOS:
        if campo not in por_campo:
            errores.append(
                ErrorValidacionMapeo(
                    codigo="campo_obligatorio_faltante", parametros={"campo": campo}
                )
            )

    if mapeo.producto_id_tipo not in _CRITERIOS_PRODUCTO_ID_TIPO:
        errores.append(
            ErrorValidacionMapeo(
                codigo="tipo_identificador_producto_invalido",
                parametros={"tipo": mapeo.producto_id_tipo},
            )
        )

    if "fecha" in por_campo:
        columna_fecha = next(c for c in deteccion.columnas if c.nombre == por_campo["fecha"][0])
        formatos_validos = {c.formato for c in columna_fecha.candidatos_fecha}
        if mapeo.formato_fecha not in formatos_validos:
            errores.append(
                ErrorValidacionMapeo(
                    codigo="formato_fecha_invalido", parametros={"formato": mapeo.formato_fecha}
                )
            )

    return errores
