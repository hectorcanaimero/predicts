"""Subida del CSV a `DATA_DIR/<empresa>/<dataset>/original.csv`.

Lee en bloques de 1 MiB: nunca el archivo completo en memoria (ver done-when de F3.1.T1:
un CSV de 300 MB no debe superar 200 MB de RSS). Acepta CSV plano, `.csv.gz` y `.zip` con
un único archivo, detectados por los primeros bytes (no por el nombre, que puede mentir).
"""

from __future__ import annotations

import gzip
import hashlib
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import IO, cast

from predicts.errores import ErrorApi

_BLOQUE = 1024 * 1024  # 1 MiB


@dataclass(frozen=True)
class ArchivoGuardado:
    ruta: Path
    tamano_bytes: int
    sha256: str


def guardar_csv(entrada: IO[bytes], destino: Path, max_mb: int) -> ArchivoGuardado:
    """Guarda `entrada` como CSV en `destino`, descomprimiendo si es `.gz` o `.zip`
    (con un solo archivo adentro), leyendo en bloques de 1 MiB.

    Corta con `ErrorApi("archivo_muy_grande", 413)` si el CSV ya descomprimido supera
    `max_mb`. `destino` queda con contenido parcial en ese caso; limpiarlo es
    responsabilidad de quien llama (junto con la fila de `datasets` a medio crear).
    """
    origen = _abrir_csv(entrada)
    destino.parent.mkdir(parents=True, exist_ok=True)
    limite_bytes = max_mb * 1024 * 1024
    digestor = hashlib.sha256()
    total = 0
    try:
        with destino.open("wb") as salida:
            while bloque := origen.read(_BLOQUE):
                total += len(bloque)
                if total > limite_bytes:
                    raise ErrorApi("archivo_muy_grande", 413, max_mb=max_mb)
                digestor.update(bloque)
                salida.write(bloque)
    finally:
        origen.close()
    return ArchivoGuardado(ruta=destino, tamano_bytes=total, sha256=digestor.hexdigest())


def _abrir_csv(entrada: IO[bytes]) -> IO[bytes]:
    """Devuelve un stream del CSV ya descomprimido, a partir de los primeros bytes."""
    cabecera = entrada.read(4)
    entrada.seek(0)
    if cabecera[:2] == b"\x1f\x8b":
        return cast(IO[bytes], gzip.GzipFile(fileobj=entrada))
    if cabecera[:4] == b"PK\x03\x04":
        return _csv_de_zip(entrada)
    return entrada


def _csv_de_zip(entrada: IO[bytes]) -> IO[bytes]:
    zf = zipfile.ZipFile(entrada)
    miembros = [m for m in zf.infolist() if not m.is_dir()]
    if len(miembros) != 1:
        raise ErrorApi("zip_formato_invalido", 400, archivos=len(miembros))
    return zf.open(miembros[0])
