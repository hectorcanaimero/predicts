#!/usr/bin/env python3
"""Genera CSVs desordenados para medir `sugerir()` (F3.2.T2) en
`api/tests/fixtures/desordenados/`, cada uno con su mapeo correcto en `<nombre>.esperado.json`.

Combina filas del generador sintético (`predicts.datos.sintetico`) y de Online Retail II
(`predicts.datos.datasets_publicos`) con encabezados en pt-BR, español, inglés y abreviados,
en mayúsculas, columnas extra sin mapeo (sucursal, vendedor, forma de pago), una columna sin
nombre, IDs de cliente numéricos y alfanuméricos, EAN y SKU, y distintos formatos de fecha.

Uso: `uv run --project api python ../scripts/generar_desordenados.py` (o
`api/.venv/bin/python scripts/generar_desordenados.py` desde la raíz del repo). Requiere
`PREDICTS_ENV_FILE` solo si `online_retail_II.xlsx` no está cacheado (ver
`predicts.datos.datasets_publicos.descargar_online_retail`); por defecto usa la copia ya
cacheada en `/mnt/storage/project/predicts/data/raw/`.
"""

from __future__ import annotations

import csv
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pyarrow as pa

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "api" / "src"))

from predicts.datos.datasets_publicos import mapear_online_retail  # noqa: E402
from predicts.datos.sintetico import generar  # noqa: E402

SALIDA = RAIZ / "api" / "tests" / "fixtures" / "desordenados"
RUTA_ONLINE_RETAIL = Path(
    "/mnt/storage/project/predicts/data/raw/online_retail_II.xlsx"
)
SEMILLA_BASE = 20261009
IGNORAR = "ignorar"

# --- Encabezados "desordenados" por estilo, uno por campo del esquema interno -----------------

ENCABEZADOS: dict[str, dict[str, str]] = {
    "ingles": {
        "cliente_id": "Customer ID", "fecha": "Order Date", "producto_id": "Product Code",
        "producto_nombre": "Product Name", "pedido_id": "Order ID", "cantidad": "Qty",
        "precio_unitario": "Unit Price", "valor_total": "Total", "categoria": "Category",
        "marca": "Brand",
    },
    "espanol": {
        "cliente_id": "ID Cliente", "fecha": "Fecha Venta", "producto_id": "Codigo Producto",
        "producto_nombre": "Nombre Producto", "pedido_id": "Pedido", "cantidad": "Cantidad",
        "precio_unitario": "Precio Unitario", "valor_total": "Total", "categoria": "Categoria",
        "marca": "Marca",
    },
    "ptbr": {
        "cliente_id": "ID Cliente", "fecha": "Dt Venda", "producto_id": "Cód. Prod.",
        "producto_nombre": "Nome Produto", "pedido_id": "Pedido", "cantidad": "Quantidade",
        "precio_unitario": "Preço Unit.", "valor_total": "Valor Total", "categoria": "Categoria",
        "marca": "Marca",
    },
    "abreviado": {
        "cliente_id": "cli", "fecha": "Dt Venda", "producto_id": "Cód. Prod.",
        "producto_nombre": "Desc", "pedido_id": "Ped", "cantidad": "Qtd",
        "precio_unitario": "Pr Unit", "valor_total": "Vl Tot", "categoria": "Cat", "marca": "Mca",
    },
}

FORMATOS_FECHA: dict[str, str] = {
    "dd/mm/aaaa": "%d/%m/%Y",
    "aaaa-mm-dd": "%Y-%m-%d",
    "mm/dd/aaaa": "%m/%d/%Y",
    "dd/mm/aaaa hh:mm": "%d/%m/%Y %H:%M",
}

EXTRA_COLUMNAS = ("Sucursal", "Vendedor", "Forma de Pago")
VENDEDORES = ("Juan Perez", "Maria Lima", "Carlos Souza")
FORMAS_PAGO = ("efectivo", "tarjeta", "transferencia")

ESTILOS = tuple(ENCABEZADOS)
TIPOS_CLIENTE = ("numerico", "alfanumerico")
TIPOS_PRODUCTO = ("sku", "ean")
FUENTES = ("sintetico", "online_retail")

# Campos opcionales que solo se incluyen si la fuente tiene valores (Online Retail II no trae
# categoría/marca); `cliente_id`, `fecha` y `producto_id` son siempre obligatorios.
CAMPOS_OPCIONALES = (
    "producto_nombre", "pedido_id", "cantidad", "precio_unitario", "valor_total", "categoria",
    "marca",
)

_tablas_fuente: dict[str, pa.Table] = {}


def _tabla_fuente(fuente: str) -> pa.Table:
    if fuente not in _tablas_fuente:
        if fuente == "online_retail":
            _tablas_fuente[fuente] = mapear_online_retail(RUTA_ONLINE_RETAIL)
        else:
            resultado = generar(n_clientes=200, productos=15, semilla=SEMILLA_BASE)
            _tablas_fuente[fuente] = resultado.compras
    return _tablas_fuente[fuente]


def _muestra_filas(fuente: str, n: int, semilla: int) -> list[dict]:
    tabla = _tabla_fuente(fuente)
    rng = np.random.default_rng(semilla)
    indices = np.sort(rng.choice(tabla.num_rows, size=min(n, tabla.num_rows), replace=False))
    return tabla.take(pa.array(indices)).to_pylist()


def _ean13(cuerpo_numerico: int) -> str:
    """EAN-13 válido (dígito verificador GTIN, misma fórmula que `datos/mapeo.py`)."""
    cuerpo = str(cuerpo_numerico % 10**12).zfill(12)
    digitos = [int(c) for c in cuerpo]
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(digitos)))
    return cuerpo + str((10 - total % 10) % 10)


def _escenarios() -> list[dict]:
    combinados = list(itertools.product(ESTILOS, TIPOS_CLIENTE, TIPOS_PRODUCTO, FUENTES))
    formatos = list(FORMATOS_FECHA)
    escenarios = []
    for i, (estilo, tipo_cliente, tipo_producto, fuente) in enumerate(combinados):
        escenarios.append(
            {
                "nombre": f"{i + 1:02d}_{estilo}_{tipo_cliente}_{tipo_producto}_{fuente}",
                "estilo": estilo,
                "tipo_cliente": tipo_cliente,
                "tipo_producto": tipo_producto,
                "fuente": fuente,
                "formato_fecha": formatos[i % len(formatos)],
                "con_extra": i % 3 == 0,
                "con_columna_sin_nombre": i % 4 == 0,
                "mayusculas": i % 5 == 0,
                "semilla": SEMILLA_BASE + i,
                "n_filas": 60 + (i % 5) * 20,  # entre 60 y 140, <= 200
            }
        )
    return escenarios


def _construir(escenario: dict) -> tuple[list[str], list[dict[str, str]], dict]:
    filas_fuente = _muestra_filas(escenario["fuente"], escenario["n_filas"], escenario["semilla"])
    encabezados_campo = ENCABEZADOS[escenario["estilo"]]

    campos_presentes = ["cliente_id", "fecha", "producto_id"] + [
        campo
        for campo in CAMPOS_OPCIONALES
        if any(fila.get(campo) is not None for fila in filas_fuente)
    ]

    cache_cliente: dict[str, str] = {}
    cache_producto: dict[str, str] = {}

    def _id_cliente(original: str) -> str:
        if original not in cache_cliente:
            numero = 100000 + len(cache_cliente)
            cache_cliente[original] = (
                str(numero) if escenario["tipo_cliente"] == "numerico" else f"CLI-{numero}"
            )
        return cache_cliente[original]

    def _id_producto(original: str) -> str:
        if original not in cache_producto:
            if escenario["tipo_producto"] == "ean":
                cache_producto[original] = _ean13(escenario["semilla"] * 1000 + len(cache_producto))
            else:
                cache_producto[original] = original
        return cache_producto[original]

    encabezados: list[str] = [encabezados_campo[campo] for campo in campos_presentes]
    if escenario["con_extra"]:
        encabezados += list(EXTRA_COLUMNAS)
    if escenario["con_columna_sin_nombre"]:
        encabezados.append("")
    if escenario["mayusculas"]:
        encabezados = [e.upper() for e in encabezados]

    patron_fecha = FORMATOS_FECHA[escenario["formato_fecha"]]
    filas_csv: list[dict[str, str]] = []
    for i, fuente_fila in enumerate(filas_fuente):
        fila: dict[str, str] = {}
        for campo, encabezado in zip(campos_presentes, encabezados, strict=False):
            valor = fuente_fila[campo]
            if campo == "cliente_id":
                texto = _id_cliente(str(valor))
            elif campo == "producto_id":
                texto = _id_producto(str(valor))
            elif campo == "fecha":
                texto = valor.strftime(patron_fecha)
            elif isinstance(valor, float):
                texto = f"{valor:.2f}"
            else:
                texto = "" if valor is None else str(valor)
            fila[encabezado] = texto
        if escenario["con_extra"]:
            extras = list(EXTRA_COLUMNAS)
            if escenario["mayusculas"]:
                extras = [e.upper() for e in extras]
            fila[extras[0]] = f"SUC-{i % 5 + 1:02d}"
            fila[extras[1]] = VENDEDORES[i % len(VENDEDORES)]
            fila[extras[2]] = FORMAS_PAGO[i % len(FORMAS_PAGO)]
        if escenario["con_columna_sin_nombre"]:
            fila[""] = str(i)
        filas_csv.append(fila)

    encabezados_de_campo = encabezados[: len(campos_presentes)]
    esperado_columnas = {
        encabezado: campo
        for campo, encabezado in zip(campos_presentes, encabezados_de_campo, strict=True)
    }
    if escenario["con_extra"]:
        extras = list(EXTRA_COLUMNAS)
        if escenario["mayusculas"]:
            extras = [e.upper() for e in extras]
        esperado_columnas.update({e: IGNORAR for e in extras})
    if escenario["con_columna_sin_nombre"]:
        esperado_columnas[""] = IGNORAR

    esperado = {"columnas": esperado_columnas, "producto_id_tipo": escenario["tipo_producto"]}
    return encabezados, filas_csv, esperado


def _escribir_csv(ruta: Path, encabezados: list[str], filas: list[dict[str, str]]) -> None:
    with ruta.open("w", newline="", encoding="utf-8") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=encabezados)
        escritor.writeheader()
        escritor.writerows(filas)


def main() -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    escenarios = _escenarios()
    for escenario in escenarios:
        encabezados, filas, esperado = _construir(escenario)
        _escribir_csv(SALIDA / f"{escenario['nombre']}.csv", encabezados, filas)
        ruta_esperado = SALIDA / f"{escenario['nombre']}.esperado.json"
        ruta_esperado.write_text(
            json.dumps(esperado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(f"{len(escenarios)} CSVs desordenados escritos en {SALIDA}")


if __name__ == "__main__":
    main()
