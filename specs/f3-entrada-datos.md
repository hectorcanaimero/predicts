---
type: spec
project_id: predicts
phase: 3
version: 0.1
depends_on:
  - docs/arch/001-predicts.md
consumed_by:
  - orch-atomizer
generated_by: orch-spec
generated_at: 2026-10-09
title: Entrada de datos
---

# F3 — Entrada de datos

Del CSV que sube la persona al Parquet con el esquema interno: subida, detección de formato,
mapeo de campos con sugerencias de Jev, plantillas, ingesta e informe de calidad.
Contratos: *Componentes → Datos de entrada*, *Modelo de datos → Esquema interno* e
*Interfaces → API HTTP*.

Contexto común: el de `specs/f0-base.md`. Aislamiento por empresa con `tenancy.py`
(`docs/notas/tenancy.md`). Los archivos van en `DATA_DIR/<empresa_id>/<dataset_id>/`. La ingesta
y la calidad se escriben aquí **como funciones y comando de CLI**; su ejecución como trabajos en
segundo plano y sus rutas HTTP llegan en F4.1 (cuando exista la cola).

## F3.1 — Package: subida y detección

### F3.1.T1 — Subida del CSV por streaming y detección de formato

- `datos/subida.py`: guarda el archivo en `DATA_DIR/<empresa>/<dataset>/original.csv` leyendo en
  bloques (nunca entero en memoria), corta con `413 archivo_muy_grande` al superar `MAX_CSV_MB`,
  calcula SHA-256 y tamaño. Acepta también `.csv.gz` y `.zip` con un solo CSV.
- `datos/deteccion.py`: codificación con `charset-normalizer` sobre los primeros 2 MB (UTF-8,
  UTF-8 con BOM, latin-1, cp1252); separador, encabezado y tipos con `duckdb.sniff_csv`;
  vista previa de 20 filas; por columna: tipo detectado, % de nulos, 10 valores de muestra y
  **candidatos de formato de fecha** probados en orden (`dd/mm/aaaa`, `aaaa-mm-dd`, `mm/dd/aaaa`,
  con y sin hora) con el % de valores que parsea cada uno; decimales con coma o punto.
- `api/datasets.py`: `POST /proyectos/{id}/datasets` (multipart) → dataset en estado `subido`
  con la detección; `GET /proyectos/{id}/datasets`, `GET /datasets/{id}`,
  `DELETE /datasets/{id}` (borra archivos y filas).

Done when: tests con fixtures (UTF-8, latin-1 con acentos, `;` como separador, decimales con
coma, fechas `dd/mm/aaaa`, gzip, zip, archivo vacío, CSV sin encabezado, archivo binario
disfrazado) verifican la detección, el límite de tamaño y el aislamiento por empresa; la subida
de un CSV de 300 MB generado en el test (marcado `lento`, fuera de la CI) no supera 200 MB de RSS.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 3h
- **Razón**: E/S y casos de formato bien enumerados.
- **Dependencies**: F2.2.T1, F1.1.T1
- **Files**:
  - `api/src/predicts/datos/subida.py`
  - `api/src/predicts/datos/deteccion.py`
  - `api/src/predicts/api/datasets.py`
  - `api/tests/test_subida.py`
  - `api/tests/test_deteccion.py`
  - `api/tests/fixtures/csv/`

## F3.2 — Package: mapeo

### F3.2.T1 — Mapeo de campos con sugerencias de Jev y plantillas

- `datos/mapeo.py`:
  - `sugerir(deteccion) -> Sugerencias`: **una sola llamada** `decidir_lote` de `ia.py` con una
    pregunta `Choice` por columna; opciones = campos del esquema interno (`cliente_id`, `fecha`,
    `producto_id`, `producto_nombre`, `pedido_id`, `cantidad`, `precio_unitario`, `valor_total`,
    `categoria`, `marca`) + `ignorar`, con descripción de cada opción en el prompt. Contexto: nombre
    de la columna, tipo detectado y 10 valores de muestra **enmascarados** si parecen email,
    teléfono o CPF (regex documentadas). Para la columna elegida como producto, otra pregunta:
    `sku` o `ean` (EAN = 8/12/13/14 dígitos con dígito verificador válido; si la regla ya lo
    decide, no se pregunta a Jev).
  - Confianza ≥ `CONFIANZA_MAPEO` → `prellenado`; menor → `revisar`. Cada decisión se guarda en
    `decisiones_jev` (tipo `mapeo_columna`).
  - `validar(mapeo, deteccion)`: obligatorios presentes y únicos, formato de fecha elegido,
    tipo de identificador de producto; errores con códigos.
  - Plantillas: firma = SHA-256 de los encabezados normalizados (minúsculas, sin acentos ni
    espacios, ordenados). Si existe plantilla de la empresa con esa firma, se devuelve como
    sugerencia con confianza 1 y origen `plantilla`, sin llamar a Jev.
- `api/datasets_mapeo.py`: `GET /datasets/{id}/mapeo` (sugerencias), `PUT /datasets/{id}/mapeo`
  (confirma; opción `guardar_como_plantilla`), `GET/DELETE /plantillas-mapeo`. Al confirmar,
  se registran las correcciones de la persona en `decisiones_jev` (`corregida_a`).

Done when: tests con un Jev falso cubren prellenado vs. revisar, enmascaramiento, regla de EAN,
validación, uso de plantilla sin llamar a Jev, registro de correcciones y aislamiento.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 4h
- **Razón**: Lógica de decisión con Jev siguiendo un patrón ya definido.
- **Dependencies**: F3.1.T1, F0.2.T3
- **Files**:
  - `api/src/predicts/datos/mapeo.py`
  - `api/src/predicts/api/datasets_mapeo.py`
  - `api/tests/test_mapeo.py`

### F3.2.T2 — Set de CSVs desordenados y medición del mapeo con Jev real

- Generar (script con semilla, a partir del sintético y de Online Retail II) **al menos 25 CSVs
  desordenados** en `api/tests/fixtures/desordenados/`, cada uno con su mapeo correcto en
  `esperado.json`: encabezados en pt-BR, español e inglés, abreviados ("Cód. Prod.", "Dt Venda",
  "cli"), en mayúsculas, con columnas extra (sucursal, vendedor, forma de pago), columnas sin
  nombre, IDs de cliente numéricos y alfanuméricos, EAN y SKU, fechas en distintos formatos.
  Mantener cada CSV chico (≤ 200 filas).
- Comando `predicts medir-mapeo` (en `comandos/medir_mapeo.py`) que corre `sugerir` con **Jev
  real** sobre el set y reporta acierto por columna y por campo, acierto del prellenado (solo lo
  que quedó con confianza alta) y costo.
- `docs/notas/mapeo.md` con la medición real (acierto total, por campo, errores típicos, y si
  `CONFIANZA_MAPEO` = 0,8 es buen umbral: qué % queda prellenado y con qué acierto). Objetivo del
  PRD: ≥ 90 %. No inventar cifras.

Done when: el set existe con su verdad, el comando tiene tests con Jev falso, y el informe trae
los números de una corrida real.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 3h
- **Razón**: Construcción de un set de evaluación y medición.
- **Dependencies**: F3.2.T1, F1.1.T2
- **Files**:
  - `api/tests/fixtures/desordenados/`
  - `scripts/generar_desordenados.py`
  - `api/src/predicts/comandos/medir_mapeo.py`
  - `api/tests/test_medir_mapeo.py`
  - `docs/notas/mapeo.md`

## F3.3 — Package: ingesta y calidad

### F3.3.T1 — Ingesta CSV → Parquet e informe de calidad

- `datos/ingesta.py`: `ingerir(dataset, mapeo, progreso=callback) -> ResumenIngesta` con DuckDB
  (`read_csv` con codificación, separador y formato de fecha del mapeo, `all_varchar` y casteo
  explícito para no perder filas por tipos), normalización (trim, `producto_nombre` y `marca`
  sin espacios dobles, `cliente_id` como texto), descarte de filas inválidas **contadas por
  motivo** (fecha que no parsea, cliente o producto vacío), y escritura de
  `compras.parquet` validado con `validar_parquet`. Llama `progreso(etapa, contadores)` cada
  ~1 M de filas.
- `datos/calidad.py`: `calcular(compras.parquet) -> InformeCalidad` (FR-6): filas, clientes,
  productos, rango de fechas, duplicados exactos, filas descartadas por motivo (de la ingesta),
  distribución de compras por cliente, pares con ≥ `MIN_COMPRAS` días distintos y % de la base
  que representan, y **viabilidad por análisis** (recompra, riesgo, ofertas) con el motivo si no
  alcanza (FR-7).
- Comando `predicts ingerir <csv> --mapeo mapeo.json --salida <dir>` (en
  `comandos/ingerir.py`) que ejecuta ambos sin base de datos, para pruebas y medición.

Done when: tests con los fixtures de F3.1 y F3.2 verifican conteos exactos, descartes por
motivo, la viabilidad, y que el Parquet pasa `validar_parquet`; medición (fuera de la CI) con un
CSV sintético de 5 M de filas: tiempo y memoria pico con `DUCKDB_MEMORY_LIMIT=3GB`, anotados en
el PR.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 3h
- **Razón**: SQL de DuckDB con conteos verificables.
- **Dependencies**: F3.2.T1
- **Files**:
  - `api/src/predicts/datos/ingesta.py`
  - `api/src/predicts/datos/calidad.py`
  - `api/src/predicts/comandos/ingerir.py`
  - `api/tests/test_ingesta.py`
  - `api/tests/test_calidad.py`
