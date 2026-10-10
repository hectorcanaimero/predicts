"""Generador sintético de compras con verdad conocida (ciclo real y abandono) por par.

Cada producto de recompra tiene un ciclo mediano propio (`ciclo_dias`); cada
par cliente–producto se desvía de ese ciclo con un factor log-normal
(`sigma_cliente`, "variación por cliente"), y las compras observadas se
muestrean de una log-normal centrada en ese ciclo real (`desvio_log` del
producto, "ruido"). La mediana de una log-normal con media `log(ciclo_real)`
es exactamente `ciclo_real` sin importar el desvío, así que la mediana de los
intervalos observados por par converge al `ciclo_real` del par — es lo que
verifica el test de F1.1.T1. Los productos durables generan a lo sumo una
compra por cliente y no tienen `ciclo_real`. Una fracción de los pares de
recompra abandona en una fecha conocida (`abandono_en`) después de al menos
dos ciclos, para que el abandono sea detectable y no trivial.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

_CATEGORIAS = ("limpieza", "alimentos", "cuidado-personal", "bebidas", "hogar")
_MARCAS = ("marca-a", "marca-b", "marca-c")

_ESQUEMA_COMPRAS = pa.schema(
    [
        ("cliente_id", pa.string()),
        ("fecha", pa.timestamp("us")),
        ("producto_id", pa.string()),
        ("producto_id_tipo", pa.string()),
        ("producto_nombre", pa.string()),
        ("pedido_id", pa.string()),
        ("categoria", pa.string()),
        ("marca", pa.string()),
        ("cantidad", pa.float64()),
        ("precio_unitario", pa.float64()),
        ("valor_total", pa.float64()),
    ]
)

_ESQUEMA_VERDAD = pa.schema(
    [
        ("cliente_id", pa.string()),
        ("producto_id", pa.string()),
        ("ciclo_real", pa.float64()),
        ("abandono_en", pa.timestamp("us")),
    ]
)


@dataclass(frozen=True)
class ProductoSintetico:
    producto_id: str
    nombre: str
    producto_id_tipo: str
    categoria: str
    marca: str
    durable: bool
    ciclo_dias: float
    desvio_log: float
    precio_base: float


@dataclass(frozen=True)
class ResultadoSintetico:
    compras: pa.Table
    verdad: pa.Table


def _catalogo(
    n_productos: int, frac_durable: float, rng: np.random.Generator
) -> list[ProductoSintetico]:
    n_durables = round(n_productos * frac_durable)
    productos = [
        ProductoSintetico(
            producto_id=f"producto-{i:03d}",
            nombre=f"Producto sintético {i:03d}",
            producto_id_tipo="sku" if i % 2 == 0 else "ean",
            categoria=_CATEGORIAS[i % len(_CATEGORIAS)],
            marca=_MARCAS[i % len(_MARCAS)],
            durable=i < n_durables,
            ciclo_dias=float(rng.uniform(10, 45)) if i >= n_durables else 0.0,
            desvio_log=float(rng.uniform(0.15, 0.3)) if i >= n_durables else 0.0,
            precio_base=float(rng.uniform(5, 80)),
        )
        for i in range(n_productos)
    ]
    rng.shuffle(productos)
    return productos


def _fila(
    cliente_id: str,
    producto: ProductoSintetico,
    fecha: datetime,
    numero_pedido: int,
    rng: np.random.Generator,
) -> tuple:
    cantidad = float(rng.integers(1, 4))
    precio_unitario = max(0.5, float(rng.normal(producto.precio_base, producto.precio_base * 0.05)))
    return (
        cliente_id,
        fecha,
        producto.producto_id,
        producto.producto_id_tipo,
        producto.nombre,
        f"pedido-{numero_pedido:07d}",
        producto.categoria,
        producto.marca,
        cantidad,
        precio_unitario,
        cantidad * precio_unitario,
    )


def _tabla(filas: list[tuple], esquema: pa.Schema) -> pa.Table:
    if not filas:
        return pa.Table.from_arrays([pa.array([], type=c.type) for c in esquema], schema=esquema)
    columnas = list(zip(*filas, strict=True))
    arrays = [pa.array(col, type=campo.type) for col, campo in zip(columnas, esquema, strict=True)]
    return pa.Table.from_arrays(arrays, schema=esquema)


def generar(
    n_clientes: int,
    productos: int,
    semilla: int,
    *,
    fecha_inicio: date = date(2022, 1, 1),
    fecha_fin: date = date(2025, 1, 1),
    frac_durable: float = 0.3,
    prob_compra: float = 0.7,
    prob_abandono: float = 0.2,
    sigma_cliente: float = 0.15,
) -> ResultadoSintetico:
    """Genera compras sintéticas y su tabla de verdad (`ciclo_real`, `abandono_en`) por par.

    `productos` es la cantidad de productos del catálogo sintético (una
    fracción `frac_durable` de ellos sin recompra); `prob_compra` es la
    probabilidad de que un cliente le compre a un producto dado alguna vez.
    """
    if n_clientes < 1 or productos < 1:
        raise ValueError("n_clientes y productos deben ser >= 1")
    dias_totales = (fecha_fin - fecha_inicio).days
    if dias_totales < 1:
        raise ValueError("fecha_fin debe ser posterior a fecha_inicio")

    rng = np.random.default_rng(semilla)
    catalogo = _catalogo(productos, frac_durable, rng)
    inicio_dt = datetime.combine(fecha_inicio, datetime.min.time())
    fin_dt = datetime.combine(fecha_fin, datetime.min.time())

    filas_compras: list[tuple] = []
    filas_verdad: list[tuple] = []
    numero_pedido = 0

    for indice_cliente in range(n_clientes):
        cliente_id = f"cliente-{indice_cliente:05d}"
        for producto in catalogo:
            if rng.random() >= prob_compra:
                continue

            if producto.durable:
                dia = int(rng.integers(0, dias_totales))
                numero_pedido += 1
                filas_compras.append(
                    _fila(cliente_id, producto, inicio_dt + timedelta(days=dia), numero_pedido, rng)
                )
                filas_verdad.append((cliente_id, producto.producto_id, None, None))
                continue

            factor_cliente = math.exp(rng.normal(0, sigma_cliente))
            ciclo_real = max(float(producto.ciclo_dias * factor_cliente), 1.0)

            fin_ventana = fin_dt
            abandono_en: datetime | None = None
            minimo_abandono = inicio_dt + timedelta(days=int(ciclo_real * 2))
            maximo_abandono = fin_dt - timedelta(days=1)
            if rng.random() < prob_abandono and minimo_abandono < maximo_abandono:
                rango_dias = (minimo_abandono - inicio_dt).days, (maximo_abandono - inicio_dt).days
                dia_abandono = int(rng.integers(*rango_dias))
                abandono_en = inicio_dt + timedelta(days=dia_abandono)
                fin_ventana = abandono_en

            ventana_primera = max(1, min(int(ciclo_real), dias_totales // 3 or 1))
            fecha_actual = inicio_dt + timedelta(days=int(rng.integers(0, ventana_primera)))

            n_compras_par = 0
            while fecha_actual <= fin_ventana:
                numero_pedido += 1
                filas_compras.append(_fila(cliente_id, producto, fecha_actual, numero_pedido, rng))
                n_compras_par += 1
                intervalo_muestreado = rng.lognormal(math.log(ciclo_real), producto.desvio_log)
                intervalo = max(1, round(float(intervalo_muestreado)))
                fecha_actual = fecha_actual + timedelta(days=intervalo)

            if n_compras_par == 0:
                continue
            filas_verdad.append((cliente_id, producto.producto_id, ciclo_real, abandono_en))

    return ResultadoSintetico(
        compras=_tabla(filas_compras, _ESQUEMA_COMPRAS),
        verdad=_tabla(filas_verdad, _ESQUEMA_VERDAD),
    )


def escribir(resultado: ResultadoSintetico, salida: str | Path) -> Path:
    """Escribe `resultado.compras` en `salida` y `resultado.verdad` junto a él
    (mismo nombre con sufijo `.verdad.parquet`). Devuelve la ruta de la verdad.
    """
    ruta_compras = Path(salida)
    ruta_compras.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(resultado.compras, ruta_compras)
    ruta_verdad = ruta_compras.parent / f"{ruta_compras.stem}.verdad.parquet"
    pq.write_table(resultado.verdad, ruta_verdad)
    return ruta_verdad
