---
type: arch
project_id: predicts
version: 0.1
status: borrador para revisión de Héctor
depends_on:
  - docs/prd/001-predicts.md
  - CONTEXTO.md
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
- **React Three Fiber** solo en `tres/`, con carga diferida: (1) procesamiento en vivo alimentado
  por SSE; (2) universo de clientes (puntos por frecuencia × valor, detalle al tocar). Respeta
  `prefers-reduced-motion` con una versión 2D.

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

**Postgres (principales):** `empresas`, `usuarios`, `sesiones`, `tokens_recuperacion`,
`proyectos` (idioma de mensajes, tono), `datasets` (estado, rutas, firma de encabezados, calidad),
`plantillas_mapeo`, `productos` (nombre normalizado, recompra, categoría, embedding `vector`),
`grupos_producto`, `analisis` (tipo, parámetros, versión del modelo, métricas de backtest,
resumen, costo), `trabajos`, `eventos_trabajo`, `decisiones_jev` (tipo, entrada resumida, salida,
confianza, corregida_por, corregida_a), `plantillas_mensaje`, `api_keys`.

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
  Ciclo contraído + log-normal + backtesting contra línea base. Si en el backtest no supera a la
  línea base, se itera antes de construir pantallas encima (gate en F1).
- **D4 — Jev para decisiones, LLM para texto, código para números.**
- **D5 — Llamadas a modelos por producto, plantilla o lote, nunca por fila o cliente.**
- **D6 — Trabajos en subproceso con tope de memoria.**
- **D7 — Login propio** (Argon2id, sesiones en Postgres).
- **D8 — i18n desde el día 1** en web y en los errores de la API.
- **D9 — React Three Fiber solo en dos vistas, con carga diferida.**

## Fases propuestas (para las specs)

| Fase | Contenido | Gate |
|---|---|---|
| F0 | Monorepo, `docker compose`, CI, config, Postgres + Alembic, `ia.py` | `docker compose up` y tests en verde |
| F1 | **Spike del modelo:** scripts de datasets, ingesta mínima a Parquet, modelo de recompra, línea base y backtesting por CLI sobre Online Retail II e Instacart; informe | el modelo supera a la línea base (si no, se ajusta antes de seguir) |
| F2 | Auth, empresas, proyectos | — |
| F3 | Subida, detección, mapeo con Jev, plantillas, ingesta, calidad | acierto del mapeo medido en CSVs desordenados |
| F4 | Productos (recompra/durable, categoría, equivalentes) y análisis completos (recompra, ciclos, riesgo, ofertas), trabajos en subproceso, eventos SSE | 1 M de filas < 5 min y dentro del límite de memoria |
| F5 | Mensajes (plantillas + revisión Jev) y exportación CSV | — |
| F6 | Frontend: login, proyectos, subir, mapear, calidad, análisis, resultados, i18n pt-BR/es/en | flujo completo de punta a punta |
| F7 | Agente analista + servidor MCP | — |
| F8 | React Three Fiber (procesamiento en vivo, universo de clientes), demo con datos de ejemplo, retención, despliegue en VPS | demo pública |

## Riesgos

- **El modelo no supera a la línea base** en algún dataset → por eso el spike va en F1, antes de
  la interfaz.
- **Instacart sin fechas reales** → las fechas sintéticas sirven para medir intervalos, no
  estacionalidad; se dice así en el contenido.
- **Memoria en el homelab** → límites en compose, subproceso con tope y DuckDB con
  `memory_limit`; medir con el dataset completo en F4.
- **Costo de Jev/LLM con muchos productos distintos** → caché por empresa y lotes; reportar costo
  por análisis.
