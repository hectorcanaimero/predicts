"""Lista de productos en oferta de un dataset (FR-14): `POST /datasets/{id}/ofertas` con un CSV
`producto_id,descuento`. Reemplaza la lista anterior; la usa el próximo análisis de `ofertas`.

`producto_id` es el del CSV de compras. `descuento` es una fracción (`0.15`) o un porcentaje
(`15`): valores ≥ 1 se dividen por 100; acepta coma decimal. Se guarda como Parquet junto al del
dataset (`analisis/ofertas.py` → `LISTA`); un producto repetido queda con el mayor descuento.
"""

from __future__ import annotations

import csv
import io
import uuid

import pyarrow as pa
import pyarrow.parquet as pq
from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel

from predicts.analisis.ofertas import LISTA
from predicts.api.datasets_ingesta import _carpeta_dataset
from predicts.auth.dependencias import Db, EmpresaActual
from predicts.db.modelos import Dataset
from predicts.errores import ErrorApi
from predicts.tenancy import obtener_o_404

router = APIRouter(tags=["ofertas"])

MAX_BYTES = 5 * 1024 * 1024


class OfertasSalida(BaseModel):
    productos: int


def _descuento(valor: str) -> float | None:
    try:
        d = float(valor.strip().replace(",", "."))
    except ValueError:
        return None
    d = d / 100 if d >= 1 else d
    return d if 0 < d < 1 else None


def leer_lista(contenido: bytes) -> dict[str, float]:
    """CSV → {producto_id: descuento}. `ErrorApi` 422 si el formato o algún valor no sirve."""
    try:
        texto = contenido.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise ErrorApi("ofertas_codificacion", 422) from e
    try:
        dialecto = csv.Sniffer().sniff(texto[:4096], delimiters=",;\t")
    except csv.Error:
        dialecto = csv.excel
    lector = csv.DictReader(io.StringIO(texto), dialect=dialecto)
    columnas = {c.strip().lower() for c in lector.fieldnames or []}
    if not {"producto_id", "descuento"} <= columnas:
        raise ErrorApi("ofertas_columnas", 422, requeridas=["producto_id", "descuento"])
    lista: dict[str, float] = {}
    for n, fila in enumerate(lector, start=2):
        fila = {(k or "").strip().lower(): (v or "") for k, v in fila.items()}
        producto, d = fila["producto_id"].strip(), _descuento(fila["descuento"])
        if not producto or d is None:
            raise ErrorApi("ofertas_fila_invalida", 422, linea=n)
        lista[producto] = max(d, lista.get(producto, 0.0))
    if not lista:
        raise ErrorApi("ofertas_vacia", 422)
    return lista


@router.post("/datasets/{dataset_id}/ofertas", status_code=201, summary="Subir la lista de ofertas")
def subir_ofertas(
    dataset_id: uuid.UUID,
    empresa: EmpresaActual,
    db: Db,
    archivo: UploadFile = File(...),  # noqa: B008
) -> OfertasSalida:
    dataset = obtener_o_404(db, Dataset, dataset_id, empresa.id)
    contenido = archivo.file.read(MAX_BYTES + 1)
    if len(contenido) > MAX_BYTES:
        raise ErrorApi("ofertas_muy_grande", 413, max_bytes=MAX_BYTES)
    lista = leer_lista(contenido)
    carpeta = _carpeta_dataset(empresa.id, dataset.id)
    carpeta.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.table(
            {"producto_id": list(lista), "descuento": list(lista.values())},
            schema=pa.schema([("producto_id", pa.string()), ("descuento", pa.float64())]),
        ),
        carpeta / LISTA,
    )
    return OfertasSalida(productos=len(lista))
