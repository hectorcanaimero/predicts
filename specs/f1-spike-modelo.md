---
type: spec
project_id: predicts
phase: 1
version: 0.1
depends_on:
  - docs/arch/001-predicts.md
consumed_by:
  - orch-atomizer
generated_by: orch-spec
generated_at: 2026-10-09
title: Spike del modelo de recompra (gate)
---

# F1 — Spike del modelo de recompra (gate)

Antes de cualquier pantalla: el modelo de recompra, su línea base y el backtesting, medidos sobre
datos públicos y sobre datos sintéticos con la verdad conocida. **Es un gate:** si el modelo no
supera a la línea base, las fases F4 en adelante esperan a que se ajuste.

Contexto común: el de `specs/f0-base.md` (leer su encabezado). La arquitectura fija los contratos
en *Interfaces → Modelo* y el método en *Componentes → Modelo de recompra*. Todo el cálculo es
SQL de DuckDB + NumPy/SciPy; **ningún LLM** en esta fase. DuckDB siempre con
`memory_limit = DUCKDB_MEMORY_LIMIT`, `threads = DUCKDB_THREADS` y `temp_directory` dentro de
`DATA_DIR/tmp` (helper `conexion_duckdb()` en `datos/duckdb.py`, definido en F1.1.T1).

## F1.1 — Package: datos de prueba

### F1.1.T1 — Esquema interno, conexión DuckDB y generador sintético con verdad conocida

- `api/src/predicts/datos/esquema.py`: `COLUMNAS_COMPRA` (nombre, tipo DuckDB, obligatoria)
  exactamente como la tabla *Modelo de datos → Esquema interno de compras*,
  `validar_parquet(path) -> list[str]` (columnas faltantes, tipos, nulos en obligatorias,
  `producto_id_tipo` fuera de `sku|ean`).
- `api/src/predicts/datos/duckdb.py`: `conexion_duckdb(solo_lectura=False)` con los límites de
  memoria, hilos y temporales de la configuración.
- `api/src/predicts/datos/sintetico.py`: `generar(n_clientes, productos, semilla, ...)` que
  escribe un Parquet con el esquema interno donde **cada par cliente–producto tiene un ciclo
  verdadero conocido** (log-normal alrededor del ciclo del producto, con variación por cliente),
  compras con ruido, clientes que abandonan en una fecha conocida, productos durables (una sola
  compra) y productos de recompra; devuelve también la tabla de verdad (`ciclo_real`,
  `abandono_en`). Comando `predicts sintetico --clientes N --salida ...` en
  `comandos/sintetico.py`.
- Fixtures chicos en `api/tests/fixtures/` (un Parquet sintético de ~2.000 filas y su verdad)
  generados con semilla fija por un script, no a mano.

Done when: tests verifican que el sintético cumple el esquema (`validar_parquet` vacío), que los
intervalos generados tienen la mediana esperada por par (± 10 %) y que `validar_parquet` detecta
cada tipo de error con Parquets inválidos construidos en el test.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 3h
- **Razón**: Generación de datos con propiedades estadísticas verificables.
- **Dependencies**: F0.1.T1, F0.2.T1
- **Files**:
  - `api/src/predicts/datos/__init__.py`
  - `api/src/predicts/datos/esquema.py`
  - `api/src/predicts/datos/duckdb.py`
  - `api/src/predicts/datos/sintetico.py`
  - `api/src/predicts/comandos/sintetico.py`
  - `api/tests/fixtures/`
  - `api/tests/test_esquema.py`
  - `api/tests/test_sintetico.py`
  - `scripts/generar_fixtures.py`

### F1.1.T2 — Datasets públicos: Online Retail II e Instacart al esquema interno

`api/src/predicts/datos/datasets_publicos.py` y comando (en `comandos/datasets.py`)
`predicts preparar-dataset {online-retail|instacart} --salida data/<nombre>/compras.parquet`:

- **Online Retail II (UCI, CC BY 4.0):** descargar de la fuente oficial de UCI (Excel con dos
  hojas), quedarse con filas con `Customer ID`, sin cancelaciones (`Invoice` que empieza con `C`)
  ni cantidades ≤ 0; mapear `Customer ID → cliente_id`, `InvoiceDate → fecha`,
  `StockCode → producto_id` (`sku`), `Description → producto_nombre`, `Invoice → pedido_id`,
  `Quantity`, `Price`, valor total. Guardar en `data/raw/` el archivo descargado y no volver a
  bajarlo si existe.
- **Instacart Market Basket:** buscar una fuente descargable sin login (por ejemplo un espejo
  público en Hugging Face). **Antes de usarla, leer y anotar su licencia** en
  `docs/notas/datasets.md`. Si no hay fuente sin login, el comando acepta
  `--desde <carpeta con los CSV>` y explica en el mensaje dónde conseguirlos; no inventar URLs.
  Construir fechas sintéticas por usuario: fecha base fija + suma acumulada de
  `days_since_prior_order` por `order_number`; `producto_id` = `product_id` (`sku`),
  `producto_nombre` y `categoria` (aisle/department). Documentar que las fechas son sintéticas.
- Opción `--muestra N` que toma N clientes al azar con semilla, para pruebas rápidas.
- `docs/notas/datasets.md`: origen, licencia, filtros aplicados, filas/clientes/productos y rango
  de fechas resultantes (medidos al correr), y limitaciones.

Done when: `predicts preparar-dataset online-retail` produce un Parquet que pasa
`validar_parquet`, y el PR trae los conteos medidos; Instacart queda preparado o documentado con
el motivo exacto por el que no se pudo; tests sin red del mapeo con un Excel/CSV mínimo de
fixture.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 3h
- **Razón**: ETL con verificación de licencias y datos reales.
- **Dependencies**: F1.1.T1
- **Files**:
  - `api/src/predicts/datos/datasets_publicos.py`
  - `api/src/predicts/comandos/datasets.py`
  - `api/tests/test_datasets_publicos.py`
  - `api/tests/fixtures/publicos/`
  - `docs/notas/datasets.md`

## F1.2 — Package: modelo

### F1.2.T1 — Intervalos y ciclo por par (contracción hacia el producto)

En `api/src/predicts/modelo/` implementar `intervalos()` y `ajustar()` con las firmas de
*Interfaces → Modelo*:

- Trabajar sobre **días de compra distintos** por par (varias líneas el mismo día = una compra).
- Intervalos entre compras consecutivas por par; por producto: mediana, MAD y número de
  clientes recurrentes; por par: mediana, MAD, `n` intervalos.
- Ciclo contraído `(n·med_cliente + k·med_producto) / (n + k)` con `k` en `ParamsModelo`
  (default 2); desvío log por producto agrupado entre clientes (estimador robusto, documentado).
- Pares con menos de `MIN_COMPRAS` compras quedan fuera del ajuste con el motivo.
- `ParamsModelo` y `Ajuste` como dataclasses/Pydantic; `VERSION_MODELO` en `modelo/__init__.py`.
- Cada fórmula documentada en el docstring con su porqué.

Done when: sobre el sintético de F1.1.T1 el ciclo estimado queda dentro del ±15 % del
`ciclo_real` en al menos el 80 % de los pares con ≥ 4 compras (test), la contracción hacia el
producto mejora el error en pares con 2–3 intervalos frente a usar solo el par (test), y el
ajuste de 1 M de filas sintéticas corre en < 60 s con `DUCKDB_MEMORY_LIMIT=2GB` (anotado en el
PR, no en la CI).

- **Modelo**: claude/claude-opus-5-5
- **Estimación**: 4h
- **Razón**: Núcleo estadístico; errores aquí invalidan todo lo demás.
- **Dependencies**: F1.1.T1
- **Files**:
  - `api/src/predicts/modelo/__init__.py`
  - `api/src/predicts/modelo/ciclos.py`
  - `api/tests/test_modelo_ciclos.py`

### F1.2.T2 — Probabilidad de compra en el horizonte y línea base

- `predecir(ajuste, fecha_ref, horizonte)`: log-normal por par con media `log(ciclo)` y el desvío
  del producto; con `t` = días desde la última compra, `P = (F(t+H) − F(t)) / (1 − F(t))`;
  fecha probable = mediana condicional; rango = percentiles 25–75 condicionales; manejo
  numérico estable cuando `1 − F(t)` es muy chico (cliente muy atrasado → probabilidad baja,
  marcado como posible abandono, sin dividir por cero).
- `linea_base(con, compras, fecha_ref, horizonte)`: próxima = última + promedio de intervalos;
  "compra en el horizonte" si cae en `(fecha_ref, fecha_ref + H]`; probabilidad 1/0.
- Salidas como vistas DuckDB con las columnas de *Interfaces*; vectorizado (SciPy sobre arrays,
  nunca un bucle Python por par).

Done when: tests verifican la fórmula contra casos calculados a mano (incluidos `t = 0`,
`t ≫ ciclo` y `H` grande), que las probabilidades están en [0, 1], que el rango contiene la
mediana, y que sobre el sintético la probabilidad media de los pares que de verdad compran en el
horizonte es mayor que la de los que no.

- **Modelo**: claude/claude-opus-5-5
- **Estimación**: 3h
- **Razón**: Probabilidad condicional con bordes numéricos delicados.
- **Dependencies**: F1.2.T1
- **Files**:
  - `api/src/predicts/modelo/prediccion.py`
  - `api/src/predicts/modelo/linea_base.py`
  - `api/tests/test_modelo_prediccion.py`

## F1.3 — Package: medición

### F1.3.T1 — Backtesting y métricas

`backtest(con, compras, params, semanas, horizonte) -> MetricasBacktest` según *Interfaces*:

- Corte en `fecha_max − semanas`; ajuste con datos ≤ corte; verdad = compras del par en
  `(corte, corte + H]`.
- Métricas para modelo **y** línea base: precisión y cobertura en el top-K (K configurable, por
  defecto el número de pares que de verdad compran), Brier, calibración por deciles (predicho vs.
  observado), error absoluto medio en días para los pares que compraron, y `n_pares`.
- Varias ventanas (`--repeticiones R`: cortes sucesivos hacia atrás) para dar media y desvío.
- `MetricasBacktest` serializable a JSON (es lo que guardará `analisis.metricas` en F4).

Done when: tests sobre el sintético verifican que con datos sin ruido el modelo logra precisión
alta y la línea base también, que con ruido el modelo supera a la línea base en Brier, y que las
métricas cuadran con un cálculo independiente hecho a mano en un caso de 5 pares.

- **Modelo**: claude/claude-opus-5-5
- **Estimación**: 3h
- **Razón**: Diseño de evaluación; un error aquí da conclusiones falsas.
- **Dependencies**: F1.2.T2
- **Files**:
  - `api/src/predicts/modelo/backtest.py`
  - `api/tests/test_modelo_backtest.py`

### F1.3.T2 — CLI `predicts backtest`, medición real e informe del spike

- Comando (en `comandos/backtest.py`) `predicts backtest <compras.parquet> [--semanas N --horizonte H --k K
  --repeticiones R --salida resultados.json]` que imprime una tabla legible modelo vs. línea base.
- Correr, **con límite de memoria** (`systemd-run --user --scope -p MemoryMax=4G
  -p MemorySwapMax=0 …` y `/usr/bin/time -v`), sobre: el sintético de 1 M de filas, Online Retail
  II completo e Instacart (completo o la muestra más grande que entre en el límite), con
  horizontes de 7 y 14 días.
- Escribir `docs/notas/spike-modelo.md` (español): datos usados, métricas por dataset y
  horizonte (modelo vs. línea base, media ± desvío), tiempo y memoria pico, calibración (tabla
  de deciles), ejemplos concretos de pares bien y mal predichos, limitaciones (fechas sintéticas
  de Instacart, poca recompra en Online Retail II) y una **recomendación explícita**: seguir,
  ajustar (qué) o cambiar de método. No inventar cifras.

Done when: el informe existe con los números medidos y la recomendación, y el CLI tiene tests
con el fixture sintético.

- **Modelo**: claude/claude-opus-5-5
- **Estimación**: 3h
- **Razón**: Requiere juicio para interpretar métricas y recomendar.
- **Dependencies**: F1.3.T1, F1.1.T2
- **Files**:
  - `api/src/predicts/comandos/backtest.py`
  - `api/tests/test_cli_backtest.py`
  - `docs/notas/spike-modelo.md`
