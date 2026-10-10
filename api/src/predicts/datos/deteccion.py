"""Detección de formato de un CSV ya guardado por `subida.py`.

Codificación con `charset-normalizer` sobre los primeros 2 MB; separador, encabezado y tipos
con `duckdb.sniff_csv`; vista previa; y por columna, candidatos de formato de fecha y
separador decimal (ver docs/arch/001-predicts.md#datos-de-entrada).
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import charset_normalizer
import duckdb
from pydantic import BaseModel

from predicts.config import Settings
from predicts.datos.duckdb import conexion_duckdb
from predicts.errores import ErrorApi

_MUESTRA_CODIFICACION_BYTES = 2 * 1024 * 1024
_FILAS_MUESTRA = 500
_FILAS_VISTA_PREVIA = 20

# Las únicas no-UTF-8 que soportamos; restringe charset-normalizer a estas para que no
# adivine una codificación de 8 bits exótica con una muestra chica y ambigua.
_CP_ISOLATION = ["utf_8", "cp1252", "latin_1"]

# Probados en este orden (ver spec F3.1.T1): cada formato, con y sin hora.
CANDIDATOS_FECHA: tuple[tuple[str, str], ...] = (
    ("dd/mm/aaaa", "%d/%m/%Y"),
    ("dd/mm/aaaa hh:mm", "%d/%m/%Y %H:%M"),
    ("aaaa-mm-dd", "%Y-%m-%d"),
    ("aaaa-mm-dd hh:mm", "%Y-%m-%d %H:%M"),
    ("mm/dd/aaaa", "%m/%d/%Y"),
    ("mm/dd/aaaa hh:mm", "%m/%d/%Y %H:%M"),
)

_DECIMAL_COMA = re.compile(r"^-?\d+,\d+$")
_DECIMAL_PUNTO = re.compile(r"^-?\d+\.\d+$")


class CandidatoFecha(BaseModel):
    formato: str
    porcentaje: float


class ColumnaDeteccion(BaseModel):
    nombre: str
    tipo: str
    porcentaje_nulos: float
    valores_muestra: list[str]
    candidatos_fecha: list[CandidatoFecha]
    separador_decimal: str | None  # "coma" | "punto" | None (si no hay decimales)


class Deteccion(BaseModel):
    codificacion: str
    separador: str
    encabezado: bool
    columnas: list[ColumnaDeteccion]
    vista_previa: list[dict[str, str | None]]


def detectar(ruta: str | Path, cfg: Settings | None = None) -> Deteccion:
    """Detecta codificación, separador, encabezado, tipos y candidatos de fecha/decimal.

    Un archivo vacío no es un error: devuelve una `Deteccion` sin columnas. Un archivo que
    no se puede decodificar en ninguna de las codificaciones soportadas, o cuyo dialecto CSV
    no se puede inferir (p. ej. binario disfrazado de `.csv`), corta con `422`.
    """
    ruta = Path(ruta)
    if ruta.stat().st_size == 0:
        return Deteccion(
            codificacion="utf-8", separador=",", encabezado=False, columnas=[], vista_previa=[]
        )

    codificacion = _detectar_codificacion(ruta)
    codificacion_duckdb = "utf-8" if codificacion == "utf-8-sig" else codificacion

    con = conexion_duckdb(cfg=cfg)
    try:
        try:
            sniff = con.execute(
                "SELECT * FROM sniff_csv(?, encoding=?)", [str(ruta), codificacion_duckdb]
            ).fetchone()
        except duckdb.Error as error:
            raise ErrorApi("formato_no_detectado", 422) from error
        if sniff is None:
            raise ErrorApi("formato_no_detectado", 422)

        separador, _quote, _escape, _nl, _comment, _skip, encabezado, columnas_sniff = sniff[:8]

        cursor = con.execute(
            "SELECT * FROM read_csv(?, encoding=?, all_varchar=true) LIMIT ?",
            [str(ruta), codificacion_duckdb, _FILAS_MUESTRA],
        )
        nombres = [d[0] for d in cursor.description]
        filas = cursor.fetchall()
    finally:
        con.close()

    tipos = {c["name"]: c["type"] for c in columnas_sniff}
    columnas = [
        _detectar_columna(nombre, tipos.get(nombre, "VARCHAR"), [fila[i] for fila in filas])
        for i, nombre in enumerate(nombres)
    ]
    vista_previa = [
        dict(zip(nombres, fila, strict=True)) for fila in filas[:_FILAS_VISTA_PREVIA]
    ]

    return Deteccion(
        codificacion=codificacion,
        separador=separador,
        encabezado=bool(encabezado),
        columnas=columnas,
        vista_previa=vista_previa,
    )


def _detectar_columna(nombre: str, tipo: str, valores: list[str | None]) -> ColumnaDeteccion:
    no_nulos = [v for v in valores if v is not None and v != ""]
    porcentaje_nulos = 1 - len(no_nulos) / len(valores) if valores else 0.0
    return ColumnaDeteccion(
        nombre=nombre,
        tipo=tipo,
        porcentaje_nulos=porcentaje_nulos,
        valores_muestra=no_nulos[:10],
        candidatos_fecha=_candidatos_fecha(no_nulos),
        separador_decimal=_separador_decimal(no_nulos),
    )


def _candidatos_fecha(valores: list[str]) -> list[CandidatoFecha]:
    if not valores:
        return []
    candidatos = []
    for nombre, patron in CANDIDATOS_FECHA:
        aciertos = sum(1 for v in valores if _parsea_fecha(v, patron))
        candidatos.append(CandidatoFecha(formato=nombre, porcentaje=aciertos / len(valores)))
    return candidatos


def _parsea_fecha(valor: str, patron: str) -> bool:
    try:
        datetime.strptime(valor.strip(), patron)
    except ValueError:
        return False
    return True


def _separador_decimal(valores: list[str]) -> str | None:
    coma = sum(1 for v in valores if _DECIMAL_COMA.match(v))
    punto = sum(1 for v in valores if _DECIMAL_PUNTO.match(v))
    if coma == 0 and punto == 0:
        return None
    return "coma" if coma >= punto else "punto"


def _detectar_codificacion(ruta: Path) -> str:
    with ruta.open("rb") as f:
        muestra = f.read(_MUESTRA_CODIFICACION_BYTES)
    if muestra.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    resultado = charset_normalizer.from_bytes(muestra, cp_isolation=_CP_ISOLATION).best()
    if resultado is None:
        raise ErrorApi("codificacion_no_detectada", 422)
    if resultado.encoding == "cp1252":
        return "cp1252"
    if resultado.encoding == "latin_1":
        return "latin-1"
    return "utf-8"
