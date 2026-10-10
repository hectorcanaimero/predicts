# Datasets públicos

Preparados por `predicts preparar-dataset {online-retail|instacart} --salida ...`
(`api/src/predicts/datos/datasets_publicos.py`, `api/src/predicts/comandos/datasets.py`).
Ambos escriben el **esquema interno de compras** (`api/src/predicts/datos/esquema.py`).

## Online Retail II (UCI)

- **Origen:** https://archive.ics.uci.edu/dataset/502/online+retail+ii — descarga directa
  `https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip` (zip con
  `online_retail_II.xlsx`, dos hojas: "Year 2009-2010" y "Year 2010-2011").
- **Licencia:** CC BY 4.0. Cita: Chen, D. (2012). *Online Retail II* [Dataset]. UCI Machine
  Learning Repository. https://doi.org/10.24432/C5CG6D.
- **Descarga:** `predicts preparar-dataset online-retail` baja el zip a `DATA_DIR/raw/` la
  primera vez (`online-retail-ii.zip` y `online_retail_II.xlsx` extraído junto a él) y no lo
  vuelve a bajar si ya existe.
- **Filtros aplicados** (por fila, antes de mapear): se descartan filas sin `Customer ID`,
  cancelaciones (`Invoice` que empieza con `C`) y `Quantity <= 0`.
- **Mapeo:** `Customer ID → cliente_id`, `InvoiceDate → fecha`, `StockCode → producto_id`
  (`producto_id_tipo = "sku"`), `Description → producto_nombre`, `Invoice → pedido_id`,
  `Quantity → cantidad`, `Price → precio_unitario`, `valor_total = cantidad * precio_unitario`.
  No hay `categoria` ni `marca` en la fuente.
- **Conteos medidos** (corrida real, sin `--muestra`, 2026-10-09):
  - 805.620 filas, 5.881 clientes, 4.631 productos.
  - Rango de fechas: 2009-12-01 07:45 a 2011-12-09 12:50.
- **Limitaciones:** solo UK-centric (clientes mayormente del Reino Unido); varios productos se
  compran una sola vez por cliente en el rango disponible (poca recompra real medible, algo que
  el backtest de F1.3 tiene que tener en cuenta al comparar contra el sintético).

## Instacart Market Basket Analysis

- **Origen real:** competencia de Kaggle de 2017,
  `https://www.kaggle.com/competitions/instacart-market-basket-analysis` — requiere cuenta de
  Kaggle y aceptar las reglas de la competencia para descargar los CSV
  (`orders.csv`, `order_products__prior.csv`, `order_products__train.csv`, `products.csv`,
  `aisles.csv`, `departments.csv`). Terceros documentan su licencia como "específica de la
  competencia, uso de investigación"; Kaggle no publica un texto de licencia más preciso en la
  página de la competencia.
- **Búsqueda de un espejo sin login (antes de usar ninguno, como pide la tarea):** se buscó en
  Hugging Face Hub y en la web en general (2026-10-09) un espejo descargable sin login con
  licencia clara. No se encontró ninguno: la copia más cercana (un espacio de OpenI) no declara
  licencia y no es Hugging Face. Por eso **no hay descarga automática** para Instacart.
- **Motivo exacto por el que no se pudo preparar con datos reales en este PR:** sin una fuente
  sin login confirmada, y sin poder loguearse a Kaggle desde este entorno automatizado, no hay
  CSV reales disponibles para correr `preparar_instacart` de punta a punta. El comando
  `predicts preparar-dataset instacart --salida ...` sin `--desde` falla con un mensaje que
  explica esto mismo y dónde conseguir los archivos.
- **Si se tiene la carpeta con los CSV** (`--desde <carpeta>`):
  - `producto_id = product_id` (`producto_id_tipo = "sku"`), `producto_nombre = product_name`,
    `categoria = department || " / " || aisle`, `pedido_id = order_id`, `cliente_id = user_id`,
    `cantidad = 1.0` (Instacart no registra cantidad por línea, cada fila es una unidad agregada
    al carrito), sin `precio_unitario` ni `valor_total` (la fuente no trae precios).
  - **Fechas sintéticas:** Instacart no publica la fecha real de cada pedido, solo
    `order_number` y `days_since_prior_order`. `fecha = FECHA_BASE_INSTACART (2023-01-01)` +
    suma acumulada de `days_since_prior_order` por `user_id`, ordenado por `order_number`
    (`days_since_prior_order` nulo del primer pedido cuenta como 0). **Estas fechas no son
    reales** — solo preservan los intervalos entre pedidos de cada usuario, que es lo único que
    necesita el modelo de recompra.
  - Verificado con un fixture chico (`api/tests/fixtures/publicos/instacart/`, 2 usuarios, 5
    pedidos, 4 productos): `test_datasets_publicos.py::test_preparar_instacart_construye_fechas_sinteticas_acumuladas`
    confirma el cálculo de fechas y que el Parquet resultante pasa `validar_parquet`.
  - `--muestra N` también aplica acá, tomando N `user_id` al azar con `--semilla`.

## Opción `--muestra N`

Ambos datasets aceptan `--muestra N --semilla S`: elige N clientes al azar (semilla fija para
reproducibilidad) *después* de mapear, filtrando el resto. Pensada para iterar rápido en el
modelo sin esperar el dataset completo.
