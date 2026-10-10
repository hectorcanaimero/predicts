---
type: arch
project_id: predicts
version: 0.1
status: borrador para revisión de Héctor
depends_on:
  - docs/prd/001-predicts.md
  - CONTEXTO.md
generated_by: orch-arch
generated_at: 2026-10-09
title: predicts — arquitectura
---

# predicts — arquitectura

## Contexto

El repo solo tiene `CONTEXTO.md`, el PRD y la configuración de orch. Se construye desde cero con
orch (4 agentes Claude en paralelo, rama `master`). El servidor de desarrollo es el homelab
(Ryzen 7 5700G, 14 GB de RAM compartidos): **todo proceso pesado tiene techo de memoria**. La
demo pública irá probablemente a un VPS con el mismo `docker compose`.

Referencias de patrón: `/mnt/storage/agent-langchain` (FastAPI, LangGraph, `ChatOpenAI` contra
9router, `typesafe-sdk`) y `/mnt/storage/project/apolicies` (Jev con `Choice`/`Noul`, salida
estructurada con `json_schema`, worker en subproceso con tope de memoria). Gotchas de 9router en
`/mnt/storage/project/agndaZAP/docs/notas/2026-09-23-9router-gotchas.md`.

## Vista general

```
navegador ── web (React, nginx) ──HTTP/SSE──► api (FastAPI) ──► postgres (+pgvector)
                                               │   ▲                ▲
                                               │   │ eventos         │ estado, trabajos,
                                               ▼   │                 │ decisiones de Jev
                                          disco DATA_DIR ◄──── worker (análisis en subproceso)
                                       (CSV, Parquet, salidas)        │  DuckDB (memory_limit)
                                                                       ├─► Jev (decisiones)
                                                                       └─► 9router (texto, agente)
```

## Estructura del repo

```
api/                      paquete Python `predicts` (uv, Python 3.13)
  src/predicts/
    config.py             Settings (pydantic-settings)
    db/                   SQLAlchemy 2 + psycopg 3, modelos ORM, Alembic (migraciones)
    auth/                 registro, login, sesiones, recuperación de contraseña
    tenancy.py            empresa actual por request; todo query filtra por empresa_id
    datos/                subida, detección de formato, mapeo, ingesta a Parquet, calidad
    productos/            clasificación (Jev), categoría (Jev), equivalentes (pgvector)
    modelo/               ciclos, probabilidad, línea base, backtesting
    analisis/             recompra, ciclos, riesgo, ofertas, orquestación del trabajo
    mensajes/             generación (LLM) y revisión (Jev)
    agente/               agente analista (LangGraph) y servidor MCP
    trabajos/             cola en Postgres, worker, eventos de progreso
    exportar.py           CSV de salida
    retencion.py          borrado de archivos vencidos
    ia.py                 clientes Jev y 9router, contador de tokens y costo
    api/                  routers FastAPI (auth, proyectos, datasets, analisis, agente)
  tests/                  sin red; fixtures CSV chicos versionados
web/                      Vite + React + TypeScript
  src/
    api/                  cliente generado desde OpenAPI + hooks TanStack Query
    i18n/                 react-i18next: pt-BR.json, es.json, en.json
    paginas/              login, proyectos, subir, mapear, calidad, analisis, resultados, agente
    componentes/          shadcn/ui + gráficos (Recharts)
    tres/                 React Three Fiber (procesamiento en vivo, universo de clientes), lazy
scripts/                  descarga y preparación de datasets públicos
deploy/                   docker-compose.yml, nginx.conf, .env.example
docs/                     prd/, arch/, notas/
```

## Componentes

### config (`api/src/predicts/config.py`)
`Settings` con pydantic-settings; lee `.env` del cwd o `PREDICTS_ENV_FILE` (los worktrees de orch
no tienen `.env`: apuntan a `/mnt/storage/project/predicts/.env`). Claves: `DATABASE_URL`,
`DATA_DIR`, `SECRET_KEY`, `ROUTER_BASE_URL`, `ROUTER_API_KEY`, `ROUTER_MODEL`,
`TYPESAFE_API_KEY`, `TYPESAFE_MODEL` (`jev-latest`), `SMTP_*` (si falta, el email se escribe en el
log), `MAX_CSV_MB` (500), `MIN_COMPRAS` (3), `HORIZONTE_DIAS` (7), `VENTANA_VALIDACION_SEMANAS`
(4), `CONFIANZA_MAPEO` (0.8), `CONFIANZA_JEV` (0.7), `RETENCION_DIAS` (7),
`DUCKDB_MEMORY_LIMIT` (`3GB`), `DUCKDB_THREADS` (4), `MAX_MEMORIA_TRABAJO_MB` (4096),
`TIMEOUT_TRABAJO_S` (1800).

### Autenticación y empresas (`auth/`, `tenancy.py`)
- Registro con email y contraseña; hash **Argon2id** (`argon2-cffi`).
- Sesión en tabla `sesiones` (token aleatorio, guardado como hash), cookie `httpOnly`, `Secure` en
  producción, `SameSite=Lax`, 30 días deslizantes. Protección CSRF con token doble (cookie +
  header) en métodos que cambian estado.
- Recuperación de contraseña: token de un solo uso, 1 hora, enviado por SMTP.
- Límite de intentos de login por IP y por email.
- Cada usuario pertenece a una empresa; cada tabla de negocio tiene `empresa_id` y una dependencia
  FastAPI (`empresa_actual`) lo inyecta en todas las consultas. RLS de Postgres queda para después.

### Datos de entrada (`datos/`)
1. **Subida:** `POST /proyectos/{id}/datasets` recibe el CSV por streaming a disco
   (`DATA_DIR/<empresa>/<dataset>/original.csv`), con tope `MAX_CSV_MB`.
2. **Detección:** codificación (`charset-normalizer` sobre los primeros MB), separador y tipos con
   `duckdb.sniff_csv`; vista previa de 20 filas. Formatos de fecha probados en orden:
   `dd/mm/aaaa`, `aaaa-mm-dd`, `mm/dd/aaaa`, con y sin hora; decimales con coma o punto.
3. **Sugerencia de mapeo (Jev):** por columna, un `Choice` entre los campos del esquema interno +
   `ignorar`, con el encabezado y 10 valores de muestra (enmascarados si parecen email o teléfono).
   Confianza ≥ `CONFIANZA_MAPEO` → prellenado; menor → marcado para revisión. Decisiones en
   `decisiones_jev`.
4. **Plantillas:** el mapeo confirmado se guarda por empresa con la firma de encabezados (hash del
   conjunto normalizado); al subir un CSV con la misma firma se aplica directo.
5. **Ingesta:** DuckDB lee el CSV con el mapeo y escribe `compras.parquet` con el **esquema interno
   único** (ver *Modelo de datos*). Los conectores futuros escriben este mismo Parquet.
6. **Calidad:** consultas DuckDB sobre el Parquet: filas, clientes, productos, rango de fechas,
   fechas inválidas, duplicados exactos, filas sin cliente o producto, pares con ≥ `MIN_COMPRAS`
   días de compra distintos. Se guarda en `datasets.calidad` (JSON).

### Productos (`productos/`)
- **Recompra o durable (Jev `Noul`):** una pregunta por producto distinto (no por fila), con
  nombre, categoría si existe, y estadísticas del dataset (cuántos clientes lo compraron más de una
  vez, mediana del intervalo). Cacheado por empresa y nombre normalizado. Durable → sin
  recordatorio.
- **Categoría (Jev `Choice`):** solo si el CSV no la trae; taxonomía fija versionada en
  `api/src/predicts/productos/taxonomia.json` (pt-BR/es/en).
- **Equivalentes:** embeddings del nombre normalizado (vía 9router, modelo de embeddings
  configurable) en pgvector; pares con similitud ≥ umbral se proponen como "mismo producto" en el
  panel. El análisis usa el grupo confirmado.
- Las llamadas van **en lotes y con caché**: el costo crece con productos distintos, no con filas
  (NFR-5).

### Modelo de recompra (`modelo/`) — el núcleo
Unidad: par (cliente, producto o grupo). Trabaja sobre **días de compra distintos** del par.

1. **Intervalos:** diferencias en días entre compras consecutivas.
2. **Ciclo del par:** mediana de sus intervalos, contraída hacia la mediana del producto según
   cuántos intervalos tiene: `ciclo = (n·med_cliente + k·med_producto) / (n + k)`, con `k`
   configurable (default 2). Dispersión: MAD del par combinada con la del producto.
3. **Distribución del intervalo:** log-normal con media `log(ciclo)` y desvío estimado por
   producto (agrupado entre clientes, más estable que por par).
4. **Probabilidad en el horizonte:** con `t` = días desde la última compra y `H` el horizonte,
   `P = (F(t+H) − F(t)) / (1 − F(t))` (condicional a no haber comprado todavía). Fecha probable =
   mediana condicional; rango = percentiles 25–75.
5. **Sin historia suficiente** (< `MIN_COMPRAS`): no se predice; el par aparece como "historia
   insuficiente" con su conteo.
6. **Línea base:** próxima compra = última + promedio de intervalos; "compra en el horizonte" si
   cae dentro.
7. **Backtesting:** corte en `fecha_max − VENTANA_VALIDACION_SEMANAS`; se ajusta con datos
   anteriores y se evalúa en `(corte, corte + H]`: precisión y cobertura en el top-K por
   probabilidad, Brier y calibración por deciles, error absoluto en días para quienes compraron.
   Siempre modelo **y** línea base, lado a lado.

Todo en SQL de DuckDB + NumPy/SciPy; nada de esto pasa por un LLM. Versión del modelo en
`modelo/__init__.py` (`VERSION_MODELO`), guardada en cada resultado.

### Análisis (`analisis/`)
- **Recompra:** pares de productos de recompra con `P ≥ umbral` en el horizonte, ordenados por `P`.
- **Ciclos por producto:** mediana, dispersión, clientes recurrentes.
- **Riesgo de abandono:** pares con `t > ciclo + 2·dispersión` (configurable) y compras regulares
  previas, ordenados por valor histórico del par (si hay precio) o por número de compras.
- **Ofertas:** candidatos = recompra próxima + productos con alta co-compra con lo que el cliente
  ya compra (matriz ítem–ítem en DuckDB) + intersección con la lista de ofertas si se sube; puntaje
  combinado documentado; tope de N ofertas por cliente.
- **¿Contactar? (Jev `Noul`):** solo para casos límite (probabilidad cerca del umbral, contacto
  reciente, varias recompras simultáneas); el resto lo decide una regla en código. Debajo de
  `CONFIANZA_JEV` → marcado para la persona.
- Resultados en Parquet (`DATA_DIR/.../resultados/*.parquet`) + resumen en `analisis.resumen`.

### Mensajes (`mensajes/`)
- El LLM (9router) genera **plantillas** por (producto o categoría, tipo de mensaje, idioma, tono)
  con marcadores (`{nombre_producto}`, `{dias}`, `{oferta}`); el código las completa por cliente.
  Así el costo no crece con la cantidad de clientes.
- Jev revisa cada plantilla (`Noul`: sin promesas que el sistema no puede garantizar, sin datos
  sensibles, tono de la marca). Rechazada → se regenera una vez con el motivo; si vuelve a fallar,
  queda marcada.

### Agente analista (`agente/`)
- LangGraph con una herramienta `consultar_sql`: conexión DuckDB **de solo lectura** a vistas
  fijas (`compras`, `predicciones`, `ciclos`, `riesgo`, `ofertas`) del dataset activo; solo
  `SELECT`, tope de filas (1.000) y de tiempo (10 s), `memory_limit` propio.
- La respuesta incluye la consulta y los números en que se basa (FR-22).
- Mismo núcleo expuesto como **servidor MCP** (`predicts mcp`), autenticado con una API key por
  empresa, para usarlo desde Claude u otros clientes.

### Trabajos y eventos (`trabajos/`)
- Cola en Postgres (`trabajos`, `SELECT … FOR UPDATE SKIP LOCKED`); el worker es un proceso aparte
  (`predicts worker`).
- **Cada trabajo corre en un subproceso** con `RLIMIT_AS`/`RLIMIT_DATA` = `MAX_MEMORIA_TRABAJO_MB`
  y `TIMEOUT_TRABAJO_S`; si muere, el trabajo queda en `error` con mensaje traducible y el worker
  sigue (lección de apolicies). DuckDB con `memory_limit`, `threads` y `temp_directory` en
  `DATA_DIR/tmp`.
- El subproceso escribe **eventos de progreso** en `eventos_trabajo` (etapa, contadores: filas,
  clientes, pares, ciclos, recordatorios). La API los transmite por **SSE**
  (`GET /trabajos/{id}/eventos`); la pantalla de React Three Fiber se alimenta de ese stream.

### API (`api/`)
FastAPI con OpenAPI completo (de ahí se generan los tipos del frontend). Errores como
`{"codigo": "...", "parametros": {...}}`; el frontend los traduce (i18n). Rutas principales:
`/auth/*`, `/proyectos`, `/proyectos/{id}/datasets`, `/datasets/{id}/mapeo`,
`/datasets/{id}/calidad`, `/datasets/{id}/analisis`, `/analisis/{id}` (+ `/resultados`,
`/exportar`), `/trabajos/{id}/eventos`, `/agente/preguntas`, `/demo` (dataset de ejemplo).

### Frontend (`web/`)
- Vite + React + TypeScript, Tailwind + shadcn/ui, TanStack Query y Router, `openapi-typescript`
  para los tipos, Recharts para gráficos, Framer Motion para transiciones.
- **i18n:** `react-i18next` con `pt-BR`, `es`, `en`; idioma por usuario, detectado del navegador
  la primera vez. Ningún texto de interfaz fuera de los archivos de traducción.
- **Sala pixel art en React Three Fiber** (`tres/`, carga diferida), la identidad visual del
  producto: una sala isométrica estilo pixel art (cámara ortográfica, render a baja resolución
  escalado con filtro `nearest`, paleta limitada, sprites/voxels low-poly; `@react-three/drei` y
  `postprocessing` para el pixelado). En la sala:
  1. **Procesamiento en vivo:** personajes/estaciones que representan las etapas del trabajo
     (subida → mapeo Jev → ingesta → productos → análisis → mensajes), animados con los eventos
     SSE; el progreso y los avisos aparecen como globos o pantallas dentro de la sala.
  2. **Universo de clientes:** vista de la sala (o una ventana dentro de ella) con los clientes
     como puntos/píxeles por frecuencia × valor; detalle al tocar.
  - Formularios, tablas y resultados siguen en UI convencional (shadcn/ui) con un tema que
    combina con la sala (tipografía pixel en títulos, misma paleta), para que sea usable y
    accesible.
  - Respeta `prefers-reduced-motion` y equipos débiles con una versión 2D estática; presupuesto
    de rendimiento: 60 fps en notebook común, bundle 3D separado del inicial.
  - Assets propios o con licencia abierta (CC0), registrados en `web/ASSETS.md`.

### Despliegue (`deploy/`)
`docker-compose.yml` con:

| Servicio | Imagen | Límite de memoria |
|---|---|---|
| `postgres` | `pgvector/pgvector:pg17` | 1 GB |
| `api` | `api/Dockerfile` (uvicorn) | 1 GB |
| `worker` | misma imagen, `predicts worker` | 5 GB (subproceso con tope 4 GB) |
| `web` | `web/Dockerfile` (build + nginx) | 256 MB |

Volúmenes para `DATA_DIR` y Postgres; `.env.example` sin secretos. Mismo compose en homelab y VPS
(en el VPS, nginx con TLS delante).

## Modelo de datos

**Esquema interno de compras (Parquet):**

| Columna | Tipo | Obligatoria |
|---|---|---|
| `cliente_id` | VARCHAR | sí |
| `fecha` | TIMESTAMP | sí |
| `producto_id` | VARCHAR | sí |
| `producto_id_tipo` | VARCHAR (`sku` \| `ean`) | sí |
| `producto_nombre` | VARCHAR | recomendada |
| `pedido_id`, `categoria`, `marca` | VARCHAR | no |
| `cantidad`, `precio_unitario`, `valor_total` | DOUBLE | no |

**Postgres.** Todas las tablas de negocio llevan `id` (UUID v7), `empresa_id` (FK), `creado_en` y
`actualizado_en`; las que no, se indican. Columnas mínimas (F0.2.T2 las crea todas; las fases
siguientes no cambian el esquema salvo que su tarea lo diga):

- `empresas`: `id`, `nombre`, `creado_en`. (sin `empresa_id`)
- `usuarios`: `email` (único, minúsculas), `hash_contrasena`, `idioma` (`pt-BR|es|en`), `rol`
  (`dueno|miembro`), `ultimo_login_en`.
- `sesiones`: `usuario_id`, `token_hash` (único), `expira_en`, `ip`, `user_agent`.
- `tokens_recuperacion`: `usuario_id`, `token_hash`, `expira_en`, `usado_en`.
- `intentos_login`: `email`, `ip`, `exitoso`, `creado_en`. (sin `empresa_id`)
- `api_keys`: `nombre`, `prefijo`, `key_hash` (único), `ultimo_uso_en`, `revocada_en`.
- `proyectos`: `nombre`, `descripcion`, `idioma_mensajes` (`pt-BR|es|en`), `tono`
  (`cercano|neutro|formal`).
- `datasets`: `proyecto_id`, `nombre_archivo`, `tamano_bytes`, `sha256`, `estado`
  (`subido|mapeado|ingiriendo|listo|error|archivado`), `deteccion` (JSONB), `mapeo` (JSONB),
  `firma_encabezados`, `calidad` (JSONB), `resumen_ingesta` (JSONB), `ruta_original`,
  `ruta_parquet`, `subido_en`, `archivado_en`.
- `plantillas_mapeo`: `firma_encabezados` (único por empresa), `nombre`, `mapeo` (JSONB).
- `productos`: `nombre_normalizado` (único por empresa), `nombre`, `producto_id_origen`,
  `categoria`, `categoria_origen` (`csv|jev|persona`), `tipo` (`recompra|durable|desconocido`),
  `tipo_origen` (`regla|jev|persona`), `confianza`, `estado_revision` (`ok|revisar`),
  `estadisticas` (JSONB), `embedding` (`vector(1536)`, índice HNSW coseno), `grupo_id`.
- `grupos_producto`: `nombre`, `estado` (`propuesto|confirmado|rechazado`), `similitud`.
- `analisis`: `dataset_id`, `tipos` (array), `parametros` (JSONB), `estado`, `version_modelo`,
  `metricas` (JSONB), `resumen` (JSONB), `ruta_resultados`, `costo_ia` (JSONB), `trabajo_id`.
- `trabajos`: `tipo`, `parametros` (JSONB), `estado` (`en_cola|corriendo|listo|error|cancelado`),
  `error_codigo`, `error_detalle`, `iniciado_en`, `terminado_en`, `duracion_s`,
  `memoria_pico_mb`, `intentos`.
- `eventos_trabajo`: `trabajo_id`, `secuencia`, `etapa`, `contadores` (JSONB), `progreso`, `ts`.
- `decisiones_jev`: `tipo` (`mapeo_columna|tipo_producto|categoria|contactar|revision_mensaje`),
  `referencia` (id del objeto decidido), `entrada_resumida` (JSONB), `opcion`, `confianza`,
  `corregida_a`, `corregida_por`, `corregida_en`.
- `plantillas_mensaje`: `clave` (producto/grupo/categoría + tipo), `tipo`
  (`recordatorio|oferta|reactivacion`), `idioma`, `tono`, `texto`, `estado`
  (`ok|revisar|editada`), `motivo_revision`; único por (empresa, clave, idioma, tono).

## Datasets públicos

- **Online Retail II (UCI, CC BY 4.0):** transacciones reales con fecha, cliente, código y
  descripción del producto, cantidad y precio. Es el **CSV de demo** (formato realista, licencia
  abierta).
- **Instacart Market Basket:** pedidos de consumo recurrente, ideal para medir recompra. No trae
  fechas absolutas (trae `days_since_prior_order`): el script de preparación construye fechas
  sintéticas acumulando días desde una fecha base, y eso se documenta. **Revisar su licencia**
  antes de redistribuir muestras; si no lo permite, el script lo descarga y lo prepara localmente.
- **Tests:** CSVs chicos versionados en `api/tests/fixtures/` (generados o derivados de Online
  Retail II), incluidos CSVs "desordenados" para medir el mapeo.
- Los datos completos viven en `data/` (fuera de git).

## Decisiones

- **D1 — CSV como entrada universal.** Los conectores llegan después escribiendo el mismo Parquet.
- **D2 — DuckDB + Parquet para analizar, Postgres para la aplicación.** Postgres solo no alcanza
  para millones de filas en el homelab; ClickHouse es un servidor más que operar.
- **D3 — Modelo estadístico simple, explicable y medido antes de cualquier ML pesado.**
  Elegido: ciclo contraído + log-normal + backtesting contra línea base. Rechazado por ahora:
  BG/NBD y gradient boosting, porque explican peor cada predicción y no sabemos aún si hacen falta. Si en el backtest no supera a la
  línea base, se itera antes de construir pantallas encima (gate en F1).
- **D4 — Jev para decisiones, LLM para texto, código para números.** Rechazado: un LLM que
  "analice" el CSV, porque inventa números y no se puede medir.
- **D5 — Llamadas a modelos por producto, plantilla o lote, nunca por fila o cliente.**
  Rechazado: un mensaje generado por cliente, porque el costo crece con la base.
- **D6 — Trabajos en subproceso con tope de memoria.** Rechazado: hilos en el proceso de la API
  (un análisis que se pasa de memoria tumba la API).
- **D7 — Login propio** (Argon2id, sesiones en Postgres). Rechazado: Clerk/Supabase Auth, por
  dependencia externa en un proyecto open source autoalojable.
- **D8 — i18n desde el día 1** en web y en los errores de la API. Rechazado: traducir al final
  (obliga a tocar todas las pantallas).
- **D9 — Sala pixel art en React Three Fiber como identidad visual** (procesamiento en vivo y
  universo de clientes), con carga diferida y versión 2D; el resto de la app en UI convencional.

## Interfaces

Contratos fijados en F0/F1 para que los paquetes paralelos no se pisen.

### Esquema interno (`api/src/predicts/datos/esquema.py`)
`COLUMNAS_COMPRA` (ver *Modelo de datos*) y `validar_parquet(path) -> list[str]`. Todo productor
(ingesta CSV, conectores futuros, scripts de datasets) escribe exactamente este Parquet.

### Modelo (`api/src/predicts/modelo/`)
```python
VERSION_MODELO: str
def intervalos(con: duckdb.DuckDBPyConnection, compras: str) -> str          # nombre de vista
def ajustar(con, compras: str, params: ParamsModelo) -> Ajuste               # ciclos por par y producto
def predecir(ajuste: Ajuste, fecha_ref: date, horizonte: int) -> str         # vista: cliente_id, producto_id, ciclo, p, fecha_probable, fecha_min, fecha_max, n_compras
def linea_base(con, compras: str, fecha_ref: date, horizonte: int) -> str
def backtest(con, compras: str, params: ParamsModelo, semanas: int, horizonte: int) -> MetricasBacktest
```
`MetricasBacktest` (Pydantic): `precision_at_k`, `cobertura_at_k`, `brier`, `calibracion` (deciles),
`mae_dias`, `n_pares`, `k`, y los mismos campos para la línea base.

### Jev (`api/src/predicts/ia.py`)
```python
def decidir_choice(pregunta: str, opciones: dict[str, str], contexto: dict) -> Decision
def decidir_si_no(pregunta: str, contexto: dict) -> Decision
# Decision: opcion, confianza, crudo; se persiste en decisiones_jev con tipo y empresa_id
def generar(llm_prompt: str, esquema: type[BaseModel]) -> BaseModel   # 9router, json_schema
```

### Eventos de trabajo (SSE)
`GET /trabajos/{id}/eventos` → `text/event-stream`, un JSON por evento:
`{"etapa": "leyendo|mapeando|calidad|ciclos|prediccion|backtest|ofertas|mensajes|listo|error",
"contadores": {"filas": int, "clientes": int, "productos": int, "pares": int, "recordatorios": int},
"progreso": float, "ts": iso8601}`.

### API HTTP (resumen; el OpenAPI generado es la fuente de verdad)
| Método y ruta | Entrada | Salida |
|---|---|---|
| `POST /auth/registro`, `/auth/login`, `/auth/logout` | email, contraseña | cookie de sesión |
| `POST /auth/recuperar`, `/auth/restablecer` | email / token + contraseña | 204 |
| `GET/POST /proyectos` | nombre, idioma, tono | proyecto |
| `POST /proyectos/{id}/datasets` | multipart CSV | dataset + vista previa + detección |
| `GET/PUT /datasets/{id}/mapeo` | mapeo confirmado | sugerencias de Jev con confianza |
| `POST /datasets/{id}/ingesta` | — | trabajo |
| `GET /datasets/{id}/calidad` | — | informe |
| `POST /datasets/{id}/analisis` | tipos + parámetros | análisis + trabajo |
| `GET /analisis/{id}`, `/analisis/{id}/resultados?tipo=` | paginación | resumen, métricas, filas |
| `GET /analisis/{id}/exportar?tipo=` | — | CSV |
| `POST /agente/preguntas` | dataset, pregunta | respuesta, sql, filas |
| `POST /demo` | — | proyecto con el dataset de ejemplo |

Errores: `{"codigo": str, "parametros": dict}` con status HTTP adecuado.

### CLI (`predicts …`)
`predicts preparar-dataset {online-retail|instacart} --salida data/…` · `predicts backtest
<compras.parquet> [--semanas N --horizonte H]` · `predicts worker` · `predicts mcp`.

## Requirement coverage

| Requisito | Componente(s) |
| --- | --- |
| FR-1 | datos (subida, detección), web (subir) |
| FR-2, FR-3, FR-4 | datos (mapeo, plantillas), ia (Jev), web (mapear) |
| FR-5 | datos (ingesta), esquema interno |
| FR-6, FR-7 | datos (calidad), web (calidad) |
| FR-8, FR-9, FR-10 | productos, ia, pgvector |
| FR-11, FR-12 | modelo, analisis |
| FR-13, FR-14 | analisis (riesgo, ofertas) |
| FR-15 | analisis (parámetros), web |
| FR-16 | modelo (backtest) |
| FR-17 | decisiones_jev, web (correcciones) |
| FR-18 | web (resultados) |
| FR-19 | mensajes |
| FR-20 | analisis (¿contactar?), ia |
| FR-21 | exportar |
| FR-22 | agente |
| FR-23, FR-24 | trabajos (eventos SSE), web/tres |
| FR-25 | scripts de datasets, api `/demo` |
| FR-26 | web/i18n, errores con código |
| FR-27 | auth, tenancy |
| NFR-1, NFR-2 | trabajos (subproceso), DuckDB `memory_limit`, compose |
| NFR-3 | auth, tenancy, retencion |
| NFR-4 | analisis (versión, parámetros), decisiones_jev, ia (contador) |
| NFR-5 | productos y mensajes por lote y caché, ia (costo) |
| NFR-6 | deploy |
| NFR-7 | tests, CI |

## Work breakdown

### F0 — Base del proyecto
- **F0.1 — monorepo y CI**: estructura `api/` (uv, ruff, pytest) y `web/` (Vite, eslint, vitest), Makefile, CI de GitHub para ambos. Files: `api/pyproject.toml`, `api/src/predicts/__init__.py`, `web/package.json`, `Makefile`, `.github/workflows/`.
- **F0.2 — config, base de datos e IA**: `config.py`, SQLAlchemy + Alembic con la migración inicial (todas las tablas de *Modelo de datos*), `ia.py` (Jev y 9router, contador). Files: `api/src/predicts/config.py`, `api/src/predicts/db/`, `api/alembic/`, `api/src/predicts/ia.py`. Depends on: F0.1.
- **F0.3 — docker compose**: Dockerfiles de api y web, compose con límites de memoria, `.env.example`. Files: `api/Dockerfile`, `web/Dockerfile`, `deploy/`. Depends on: F0.1.

### F1 — Spike del modelo (gate)
- **F1.1 — datasets y esquema**: `esquema.py`, scripts para descargar y preparar Online Retail II e Instacart al esquema interno, fixtures chicos. Files: `api/src/predicts/datos/esquema.py`, `api/src/predicts/datos/datasets_publicos.py`, `scripts/`, `api/tests/fixtures/`.
- **F1.2 — modelo y línea base**: intervalos, ciclo contraído, log-normal, predicción y línea base (contratos de *Interfaces*). Files: `api/src/predicts/modelo/`. Depends on: F1.1.
- **F1.3 — backtesting e informe**: `backtest`, CLI `predicts backtest`, medición en ambos datasets con tiempo y memoria, informe `docs/notas/spike-modelo.md` con recomendación. Files: `api/src/predicts/modelo/backtest.py`, `api/src/predicts/cli.py`, `docs/notas/spike-modelo.md`. Depends on: F1.2.

### F2 — Cuentas
- **F2.1 — auth**: registro, login, sesiones, CSRF, recuperación, límite de intentos. Files: `api/src/predicts/auth/`, `api/src/predicts/api/auth.py`.
- **F2.2 — empresas y proyectos**: `tenancy.py`, rutas de proyectos. Files: `api/src/predicts/tenancy.py`, `api/src/predicts/api/proyectos.py`. Depends on: F2.1.

### F3 — Entrada de datos
- **F3.1 — subida y detección**: streaming a disco, codificación, `sniff_csv`, vista previa. Files: `api/src/predicts/datos/subida.py`, `api/src/predicts/datos/deteccion.py`.
- **F3.2 — mapeo con Jev y plantillas**: sugerencias con confianza, plantillas por firma de encabezados, set de CSVs desordenados y medición de acierto. Files: `api/src/predicts/datos/mapeo.py`, `api/tests/fixtures/desordenados/`. Depends on: F3.1.
- **F3.3 — ingesta y calidad**: CSV → Parquet con el mapeo, informe de calidad, rutas de datasets. Files: `api/src/predicts/datos/ingesta.py`, `api/src/predicts/datos/calidad.py`, `api/src/predicts/api/datasets.py`. Depends on: F3.2.

### F4 — Productos, análisis y trabajos
- **F4.1 — trabajos y eventos**: cola en Postgres, worker con subproceso y tope de memoria, eventos y SSE. Files: `api/src/predicts/trabajos/`, `api/src/predicts/api/trabajos.py`.
- **F4.2 — productos**: recompra/durable y categoría con Jev (lotes y caché), equivalentes con pgvector. Files: `api/src/predicts/productos/`.
- **F4.3 — análisis**: recompra, ciclos, riesgo, ofertas y ¿contactar?, sobre el modelo de F1; rutas de análisis y resultados; medición con 1 M de filas. Files: `api/src/predicts/analisis/`, `api/src/predicts/api/analisis.py`. Depends on: F4.1, F4.2.

### F5 — Mensajes y exportación
- **F5.1 — mensajes**: plantillas por lote con 9router y revisión con Jev. Files: `api/src/predicts/mensajes/`.
- **F5.2 — exportación**: CSV de recordatorios y ofertas. Files: `api/src/predicts/exportar.py`. Depends on: F5.1.

### F6 — Interfaz web
- **F6.1 — base web**: layout, rutas, i18n (pt-BR/es/en), cliente OpenAPI, login y proyectos. Files: `web/src/api/`, `web/src/i18n/`, `web/src/paginas/login*`, `web/src/paginas/proyectos*`.
- **F6.2 — flujo de datos**: subir, mapear (con confianza de Jev), calidad. Files: `web/src/paginas/datos/`. Depends on: F6.1.
- **F6.3 — análisis y resultados**: elegir análisis, resultados, métricas de backtest, mensajes, exportar. Files: `web/src/paginas/analisis/`. Depends on: F6.1.

### F7 — Agente analista
- **F7.1 — agente y MCP**: LangGraph con `consultar_sql` de solo lectura, ruta `/agente/preguntas`, servidor MCP. Files: `api/src/predicts/agente/`, `api/src/predicts/api/agente.py`.
- **F7.2 — chat en la web**: pantalla del agente con la consulta y los números. Files: `web/src/paginas/agente/`. Depends on: F7.1.

### F8 — 3D, demo y despliegue
- **F8.1 — procesamiento en vivo (R3F)**: escena alimentada por SSE, versión 2D con `prefers-reduced-motion`. Files: `web/src/tres/procesamiento/`.
- **F8.2 — universo de clientes (R3F)**. Files: `web/src/tres/universo/`.
- **F8.3 — demo, retención y VPS**: `/demo` con Online Retail II, `retencion.py`, guía de despliegue con TLS. Files: `api/src/predicts/retencion.py`, `api/src/predicts/api/demo.py`, `deploy/vps/`, `README.md`.

## Riesgos

- **El modelo no supera a la línea base** en algún dataset → por eso el spike va en F1, antes de
  la interfaz.
- **Instacart sin fechas reales** → las fechas sintéticas sirven para medir intervalos, no
  estacionalidad; se dice así en el contenido.
- **Memoria en el homelab** → límites en compose, subproceso con tope y DuckDB con
  `memory_limit`; medir con el dataset completo en F4.
- **Costo de Jev/LLM con muchos productos distintos** → caché por empresa y lotes; reportar costo
  por análisis.
