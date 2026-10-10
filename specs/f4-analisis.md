---
type: spec
project_id: predicts
phase: 4
version: 0.1
depends_on:
  - docs/arch/001-predicts.md
  - docs/notas/spike-modelo.md
consumed_by:
  - orch-atomizer
generated_by: orch-spec
generated_at: 2026-10-09
title: Trabajos, productos y análisis
---

# F4 — Trabajos, productos y análisis

La cola de trabajos en segundo plano con tope de memoria, el enriquecimiento de productos con Jev
y los cuatro análisis del PRD (recompra, ciclos, riesgo de abandono, ofertas) sobre el modelo
validado en F1. Contratos: *Componentes → Trabajos y eventos, Productos, Análisis*,
*Interfaces → Eventos de trabajo* y *Interfaces → API HTTP*.

Contexto común: el de `specs/f0-base.md`. **Leer `docs/notas/spike-modelo.md`** (conclusiones de
F1) antes de tocar el análisis: si recomienda ajustes al modelo, se aplican aquí. Las llamadas a
Jev y al LLM van **por producto o por lote, nunca por fila ni por cliente** (D5), con caché en
Postgres.

## F4.1 — Package: trabajos y eventos

### F4.1.T1 — Cola en Postgres, worker y ejecución en subproceso con tope de memoria

- `trabajos/cola.py`: `encolar(db, empresa_id, tipo, parametros) -> Trabajo`,
  `tomar_siguiente(db)` con `SELECT … FOR UPDATE SKIP LOCKED`, estados
  `en_cola → corriendo → listo | error | cancelado`, `cancelar(id)`.
- `trabajos/registro.py`: registro de tipos de trabajo (`@tipo_trabajo("ingesta")`) para que cada
  fase agregue el suyo en su archivo.
- `trabajos/worker.py` y comando `predicts worker` (en `comandos/worker.py`): bucle que toma
  trabajos y ejecuta **cada uno en un subproceso** (`multiprocessing` con contexto `spawn`) con
  `RLIMIT_AS` o `RLIMIT_DATA` = `MAX_MEMORIA_TRABAJO_MB` (documentar cuál y por qué; DuckDB y
  NumPy reservan memoria virtual) y `TIMEOUT_TRABAJO_S`. Si el hijo muere por memoria, señal o
  timeout, el trabajo queda en `error` con `codigo` (`memoria_excedida`, `tiempo_excedido`,
  `error_interno`) y el worker sigue con el siguiente. Al arrancar, los trabajos que quedaron
  `corriendo` de una caída anterior pasan a `error` (`interrumpido`).
- `trabajos/eventos.py`: `emitir(trabajo_id, etapa, contadores, progreso)` desde el subproceso
  (con su propia conexión) en `eventos_trabajo`, con el formato de *Interfaces → Eventos*; se
  emite como máximo un evento por segundo por trabajo.
- El pico de memoria del hijo (`ru_maxrss`) y la duración se guardan en el trabajo.

Done when: tests con tipos de trabajo falsos cubren éxito, excepción, hijo que reserva memoria por
encima del tope (→ `memoria_excedida` y el worker sigue), timeout, cancelación, recuperación al
reiniciar, dos workers sin tomar el mismo trabajo, y la limitación de frecuencia de eventos.

- **Modelo**: claude/claude-opus-5-5
- **Estimación**: 4h
- **Razón**: Concurrencia, procesos y límites de memoria; ya causó caídas en otro proyecto.
- **Dependencies**: F0.2.T2, F0.2.T4
- **Files**:
  - `api/src/predicts/trabajos/__init__.py`
  - `api/src/predicts/trabajos/cola.py`
  - `api/src/predicts/trabajos/registro.py`
  - `api/src/predicts/trabajos/worker.py`
  - `api/src/predicts/trabajos/eventos.py`
  - `api/src/predicts/comandos/worker.py`
  - `api/tests/test_trabajos.py`

### F4.1.T2 — SSE de progreso y trabajos de ingesta y calidad

- `api/trabajos.py`: `GET /trabajos/{id}` (estado, error, duración, memoria) y
  `GET /trabajos/{id}/eventos` (SSE con `sse-starlette`): envía los eventos guardados y los nuevos
  hasta `listo`/`error`, con `Last-Event-ID` para reconectar; `POST /trabajos/{id}/cancelar`.
- `trabajos/tipos_datos.py`: tipos `ingesta` (llama `datos.ingesta.ingerir` con el mapeo
  confirmado y emite eventos `leyendo`) y `calidad` (llama `datos.calidad.calcular`, guarda el
  informe en `datasets.calidad` y emite `calidad`). Al terminar la ingesta se encola la calidad.
- `api/datasets_ingesta.py`: `POST /datasets/{id}/ingesta` (requiere mapeo confirmado; →
  trabajo) y `GET /datasets/{id}/calidad`. Estados del dataset: `subido → mapeado → ingiriendo →
  listo | error`.

Done when: tests de punta a punta con el worker real en un hilo de prueba: subir el fixture,
confirmar mapeo, ingerir, recibir los eventos por SSE (cliente de prueba) y leer la calidad;
reconexión con `Last-Event-ID`; aislamiento por empresa.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 3h
- **Razón**: Integración de piezas ya definidas.
- **Dependencies**: F4.1.T1, F3.3.T1
- **Files**:
  - `api/src/predicts/api/trabajos.py`
  - `api/src/predicts/trabajos/tipos_datos.py`
  - `api/src/predicts/api/datasets_ingesta.py`
  - `api/tests/test_trabajos_api.py`

## F4.2 — Package: productos

### F4.2.T1 — Catálogo de productos, recompra o durable y categoría con Jev

- `productos/catalogo.py`: a partir del Parquet, `actualizar_catalogo(dataset)` hace upsert en
  `productos` (por empresa y nombre normalizado) con estadísticas del dataset: clientes, clientes
  que lo compraron más de una vez, mediana del intervalo, precio medio.
- `productos/clasificacion.py`:
  - **Recompra o durable** (`decidir_lote`, `Noul`-equivalente sí/no, en lotes de 50 productos
    por llamada): pregunta y criterios en el código, con nombre, categoría si existe y las
    estadísticas. Regla previa sin Jev: si ≥ 30 % de sus clientes lo recompraron con mediana
    < 120 días → recompra; si nadie lo recompró y tiene ≥ 50 clientes → durable. Solo lo ambiguo va
    a Jev. Confianza < `CONFIANZA_JEV` → `revisar`.
  - **Categoría** (`Choice` sobre `productos/taxonomia.json`, ~40 categorías de consumo y
    durables con nombre en pt-BR/es/en) solo si el CSV no trae categoría.
  - Caché: un producto ya clasificado para la empresa no se vuelve a preguntar salvo que la
    persona lo pida.
- Tipo de trabajo `productos` (en `trabajos/tipos_productos.py`) encolado al terminar la calidad.
- `api/productos.py`: `GET /datasets/{id}/productos?estado=revisar`, `PATCH /productos/{id}`
  (corregir recompra/durable o categoría; se registra en `decisiones_jev`).

Done when: tests con Jev falso cubren la regla previa, el lote, el umbral, la caché, la
corrección y el aislamiento; medición real (fuera de la CI) sobre Online Retail II: cuántos
productos van a Jev, costo y 30 clasificaciones revisadas a mano, anotado en el PR.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 4h
- **Razón**: Reglas + Jev por lotes siguiendo un patrón definido.
- **Dependencies**: F4.1.T2, F0.2.T3
- **Files**:
  - `api/src/predicts/productos/__init__.py`
  - `api/src/predicts/productos/catalogo.py`
  - `api/src/predicts/productos/clasificacion.py`
  - `api/src/predicts/productos/taxonomia.json`
  - `api/src/predicts/trabajos/tipos_productos.py`
  - `api/src/predicts/api/productos.py`
  - `api/tests/test_productos.py`

### F4.2.T2 — Productos equivalentes con embeddings en pgvector

- `productos/equivalentes.py`: embeddings del nombre normalizado (`ia.embeddings`, lotes de 100,
  solo productos sin embedding), búsqueda de vecinos con pgvector (coseno, índice HNSW) dentro de
  la empresa, y propuestas de grupo cuando similitud ≥ umbral configurable **y** coinciden marca
  o categoría si existen. Las propuestas no se aplican solas: quedan en `grupos_producto` con
  estado `propuesto`.
- El análisis (F4.3) usa los grupos `confirmado`; un producto sin grupo es su propio grupo.
- Rutas en `api/productos_grupos.py`: listar propuestas, confirmar, rechazar, separar.

Done when: tests con embeddings falsos deterministas cubren propuestas, umbral, la condición de
marca/categoría, confirmar/rechazar y aislamiento; el índice existe en la migración inicial
(si falta, agregarlo con una migración nueva en esta tarea).

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 3h
- **Razón**: pgvector con reglas acotadas.
- **Dependencies**: F4.2.T1
- **Files**:
  - `api/src/predicts/productos/equivalentes.py`
  - `api/src/predicts/api/productos_grupos.py`
  - `api/alembic/versions/`
  - `api/tests/test_equivalentes.py`

## F4.3 — Package: análisis

### F4.3.T1 — Análisis de recompra y ciclos por producto con backtesting

- `analisis/orquestador.py`: tipo de trabajo `analisis` que recibe los tipos pedidos y sus
  parámetros (FR-15), aplica grupos de productos y excluye durables, y ejecuta cada análisis
  emitiendo eventos (`ciclos`, `prediccion`, `backtest`, …) con contadores reales.
- `analisis/recompra.py`: usa `modelo.ajustar/predecir` (F1) con `fecha_ref` = última fecha del
  dataset; resultado en `resultados/recompra.parquet` (columnas de *Interfaces → Modelo* + nombre
  de producto + motivo legible), filtrado por umbral de probabilidad; **backtest** del mismo
  dataset guardado en `analisis.metricas` (modelo y línea base).
- `analisis/ciclos.py`: ciclo típico por producto (mediana, dispersión, clientes recurrentes) en
  `resultados/ciclos.parquet`.
- `analisis.resumen` (JSON): totales por análisis, top productos, costo de IA, versión del
  modelo y parámetros (NFR-4).

Done when: tests sobre el sintético verifican resultados contra la verdad (ciclos ±15 %, los
pares que compran en el horizonte tienen más probabilidad), que los durables quedan fuera, que
los grupos se aplican, y que métricas y resumen se guardan.

- **Modelo**: claude/claude-opus-5-5
- **Estimación**: 4h
- **Razón**: Corazón del producto sobre el modelo de F1.
- **Dependencies**: F1.3.T2, F4.1.T2, F4.2.T1
- **Files**:
  - `api/src/predicts/analisis/__init__.py`
  - `api/src/predicts/analisis/orquestador.py`
  - `api/src/predicts/analisis/recompra.py`
  - `api/src/predicts/analisis/ciclos.py`
  - `api/tests/test_analisis_recompra.py`

### F4.3.T2 — Riesgo de abandono, ofertas y decisión de contactar

- `analisis/riesgo.py` (FR-13): pares con compras regulares previas (≥ `MIN_COMPRAS`) y
  `t > ciclo + 2·dispersión` (factor configurable), y clientes cuya actividad total cayó por
  debajo de su ritmo; ordenados por valor histórico (si hay precio) o número de compras; con el
  motivo legible.
- `analisis/ofertas.py` (FR-14): matriz ítem–ítem de co-compra en DuckDB (lift con soporte
  mínimo) y candidatos por cliente = recompra próxima + productos con alto lift con lo que ya
  compra y todavía no compra + (si se subió) intersección con una lista de ofertas
  (`POST /datasets/{id}/ofertas` con un CSV `producto_id,descuento`). Puntaje combinado
  documentado; tope de N por cliente.
- `analisis/contactar.py` (FR-20): regla en código para los casos claros y `decidir_lote` de Jev
  solo para los límite (probabilidad a ±0,1 del umbral, varios recordatorios el mismo día, cliente
  en riesgo y en recompra a la vez), en lotes; confianza baja → `revisar`.
- Se suman al orquestador de F4.3.T1.

Done when: tests sobre el sintético cubren riesgo contra `abandono_en` (precisión y cobertura
reportadas), ofertas (lift calculado a mano en un caso chico), la lista de ofertas, y que Jev solo
recibe los casos límite.

- **Modelo**: claude/claude-opus-5-5
- **Estimación**: 4h
- **Razón**: Varias heurísticas con decisiones de producto.
- **Dependencies**: F4.3.T1
- **Files**:
  - `api/src/predicts/analisis/riesgo.py`
  - `api/src/predicts/analisis/ofertas.py`
  - `api/src/predicts/analisis/contactar.py`
  - `api/src/predicts/analisis/orquestador.py`
  - `api/src/predicts/api/datasets_ofertas.py`
  - `api/tests/test_analisis_riesgo_ofertas.py`

### F4.3.T3 — Rutas de análisis y medición de rendimiento con 1 M de filas

- `api/analisis.py`: `POST /datasets/{id}/analisis` (tipos + parámetros → análisis + trabajo),
  `GET /datasets/{id}/analisis`, `GET /analisis/{id}` (estado, resumen, métricas),
  `GET /analisis/{id}/resultados?tipo=recompra|ciclos|riesgo|ofertas&pagina=&orden=` (paginado
  desde el Parquet con DuckDB, sin cargar todo en memoria), `DELETE /analisis/{id}`.
- **Medición (NFR-1, NFR-2):** con `docker compose` (límites de la arquitectura), CSV sintético de
  1 M y 5 M de filas: tiempo de ingesta + calidad + productos (Jev falso, para no gastar) +
  análisis completo, y memoria pico de cada contenedor y del subproceso. Escribir
  `docs/notas/rendimiento.md` con los números medidos y si se cumple "< 5 min para 1 M de
  filas".

Done when: tests de las rutas (paginación, orden, tipos inválidos, aislamiento) y el informe de
rendimiento con datos reales.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 3h
- **Razón**: Rutas estándar más una medición guiada.
- **Dependencies**: F4.3.T2, F0.3.T1
- **Files**:
  - `api/src/predicts/api/analisis.py`
  - `api/tests/test_analisis_api.py`
  - `docs/notas/rendimiento.md`
