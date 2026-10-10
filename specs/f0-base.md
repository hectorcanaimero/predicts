---
type: spec
project_id: predicts
phase: 0
version: 0.1
depends_on:
  - docs/arch/001-predicts.md
  - docs/prd/001-predicts.md
consumed_by:
  - orch-atomizer
generated_by: orch-spec
generated_at: 2026-10-09
title: Base del proyecto
---

# F0 — Base del proyecto

Esqueleto del monorepo sobre el que trabajan todas las fases: `api/` (Python), `web/` (React),
CI, configuración, base de datos con el esquema completo, clientes de IA y Docker Compose.

**Contexto común (vale para todas las tareas de esta fase y las siguientes):**

- Leer antes que nada `CONTEXTO.md` y `docs/arch/001-predicts.md` (secciones *Estructura del repo*,
  *Componentes*, *Modelo de datos*, *Interfaces* y *Decisiones*). El PRD está en
  `docs/prd/001-predicts.md`.
- Los worktrees de orch no tienen `.env`: el código lee `PREDICTS_ENV_FILE`; para pruebas reales
  apuntar a `/mnt/storage/project/predicts/.env` (claves de 9router y Jev, `DATABASE_URL`,
  `TEST_DATABASE_URL`). **Nunca** copiar ni imprimir sus valores.
- Postgres de desarrollo ya corriendo en el homelab: contenedor `predicts-pg-dev`
  (`pgvector/pgvector:pg17`) en `127.0.0.1:54329`, usuario y contraseña `predicts`. Los tests que
  usan base **crean su propia base temporal** (`predicts_test_<uuid>`) a partir de
  `TEST_DATABASE_URL` y la borran al terminar, para que varios worktrees corran en paralelo.
- Patrones de referencia (leer, no copiar a ciegas): `/mnt/storage/project/apolicies`
  (`src/apolicies/llm.py`: `ChatOpenAI` contra 9router con salida JSON validada por Pydantic y
  reintento; `src/apolicies/juez_jev.py`: `TypeSafeClient.system_one` con `Choice`; worker en
  subproceso con tope de memoria) y `/mnt/storage/agent-langchain`. Gotchas de 9router:
  `/mnt/storage/project/agndaZAP/docs/notas/2026-09-23-9router-gotchas.md` (`stream` explícito en
  falso, `reasoning_effort: "none"` en razonadores, embeddings solo con ids directos).
- Herramientas del homelab: `uv` (Python 3.13), `node`/`npm` (no hay pnpm: usar **npm** con
  `package-lock.json`), Docker Compose v5.
- Código, comentarios y docs en **español**; textos de interfaz en archivos i18n; nombres de
  columnas del esquema interno según la arquitectura.
- Tests sin red: Jev y 9router siempre falsos en tests (inyectados), salvo en tareas que pidan una
  medición real.

## F0.1 — Package: monorepo y CI

### F0.1.T1 — Proyecto Python `api/` con todas las dependencias del MVP

Crear el paquete `predicts` en `api/` con `uv` (Python 3.13, layout `src/`):

- `api/pyproject.toml` con **todas las dependencias previstas del MVP** para que las tareas
  siguientes no tengan que tocar este archivo en paralelo: fastapi, uvicorn[standard],
  pydantic, pydantic-settings, sqlalchemy>=2, psycopg[binary]>=3, alembic, pgvector, duckdb,
  pyarrow, numpy, scipy, argon2-cffi, itsdangerous, python-multipart, charset-normalizer,
  sse-starlette, typer, httpx, langchain-core, langchain-openai, langgraph, typesafe-sdk>=0.7,
  mcp, email-validator, openpyxl (lectura del Excel de Online Retail II); dev: pytest, pytest-asyncio, ruff, mypy (opcional).
- `api/uv.lock` generado y versionado.
- `api/src/predicts/__init__.py` con `__version__`, `api/src/predicts/cli.py` con la app Typer
  `predicts` y el script `predicts` en `pyproject`. `cli.py` **descubre** los módulos de
  `predicts.comandos` y registra cada función decorada con `@comando` (helper en
  `predicts/comandos/__init__.py`), así cada fase agrega su comando en un archivo propio sin tocar
  `cli.py`. Primer comando: `comandos/version.py`.
- Ruff configurado (line-length 100, reglas E, F, I, B, UP) y pytest con `tests/` y marcador
  `db` para tests que necesitan Postgres.
- `api/tests/test_smoke.py` que importa el paquete y corre el CLI.
- `Makefile` en la raíz con `api-test`, `api-lint`, `web-test`, `web-lint`, `test`, `lint`.

Done when: `cd api && uv sync --frozen && uv run pytest -q && uv run ruff check .` pasa y
`uv run predicts version` imprime la versión.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 1.5h
- **Razón**: Scaffolding estándar con lista de dependencias definida.
- **Dependencies**:
- **Files**:
  - `api/pyproject.toml`
  - `api/uv.lock`
  - `api/src/predicts/__init__.py`
  - `api/src/predicts/cli.py`
  - `api/src/predicts/comandos/__init__.py`
  - `api/src/predicts/comandos/version.py`
  - `api/tests/test_smoke.py`
  - `api/tests/conftest.py`
  - `Makefile`
  - `.gitignore`

### F0.1.T2 — Proyecto web `web/` con todas las dependencias del MVP

Crear `web/` con Vite + React + TypeScript (npm, `package-lock.json` versionado):

- Dependencias previstas del MVP (para no tocar `package.json` en paralelo después): react,
  react-dom, @tanstack/react-query, @tanstack/react-router (+ plugin de rutas por archivos),
  i18next, react-i18next, i18next-browser-languagedetector, tailwindcss (v4 con su plugin de
  Vite), clsx, tailwind-merge, class-variance-authority, lucide-react, @radix-ui/* necesarios para
  shadcn/ui, recharts, framer-motion, reactflow, three, @react-three/fiber, @react-three/drei,
  openapi-typescript, openapi-fetch; dev: vitest, @testing-library/react, jsdom, eslint con
  typescript-eslint, prettier.
- Rutas por archivos (`web/src/routes/`) para que cada página viva en su propio archivo y las
  tareas de pantallas no compartan un archivo de rutas.
- **i18n por namespaces:** `web/src/i18n/index.ts` carga con `import.meta.glob` todos los
  archivos `web/src/i18n/locales/<idioma>/<namespace>.json` para `pt-BR`, `es` y `en`, con
  detección del navegador y `pt-BR` por defecto. Cada feature tendrá su propio namespace, así dos
  tareas nunca editan el mismo JSON. Crear el namespace `comun` (botones, errores genéricos) en los
  tres idiomas.
- Componentes base de shadcn/ui en `web/src/components/ui/` (button, input, label, card, dialog,
  dropdown-menu, select, table, tabs, toast, badge, progress, skeleton) y `web/src/lib/utils.ts`.
- Layout raíz con selector de idioma y una página de inicio de prueba.
- Scripts: `dev`, `build`, `test`, `lint`, `gen:api` (genera `web/src/api/schema.ts` a partir de
  `web/src/api/openapi.json`, que se exporta con `predicts openapi`).

Done when: `cd web && npm ci && npm run lint && npm test -- --run && npm run build` pasa, y un test
de Vitest verifica que el selector de idioma cambia un texto entre pt-BR, es y en.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 3h
- **Razón**: Scaffolding de frontend con varias piezas a integrar (router, i18n, shadcn).
- **Dependencies**:
- **Files**:
  - `web/package.json`
  - `web/package-lock.json`
  - `web/vite.config.ts`
  - `web/tsconfig.json`
  - `web/index.html`
  - `web/eslint.config.js`
  - `web/src/main.tsx`
  - `web/src/routes/__root.tsx`
  - `web/src/routes/index.tsx`
  - `web/src/i18n/index.ts`
  - `web/src/i18n/locales/pt-BR/comun.json`
  - `web/src/i18n/locales/es/comun.json`
  - `web/src/i18n/locales/en/comun.json`
  - `web/src/components/ui/`
  - `web/src/lib/utils.ts`
  - `web/src/styles.css`
  - `web/src/__tests__/i18n.test.tsx`
  - `web/.gitignore`

### F0.1.T3 — CI de GitHub para api y web

Reemplazar `.github/workflows/orch-ci.yml` (el que generó `orch init` usa pip y Python 3.11, y no
sirve) por un workflow con dos jobs que corren en cada PR y en push a `master`:

- `api`: `astral-sh/setup-uv`, Python 3.13, servicio `pgvector/pgvector:pg17` con
  `TEST_DATABASE_URL` apuntando a él, `uv sync --frozen`, `uv run ruff check .`,
  `uv run pytest -q`. Si `api/` no existe todavía, el job termina en verde sin hacer nada.
- `web`: Node 22, `npm ci`, `npm run lint`, `npm test -- --run`, `npm run build`. Si `web/` no
  existe, termina en verde.
- El nombre del check que orch espera es `test`: crear un job final `test` que dependa de `api`
  y `web` y solo pase si ambos pasan.

Done when: el workflow es YAML válido (`python -c "import yaml,sys;yaml.safe_load(open(...))"`),
los pasos condicionales están probados leyendo el archivo, y el PR de esta tarea muestra el
check `test` en verde.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 1h
- **Razón**: Configuración de CI acotada.
- **Dependencies**:
- **Files**:
  - `.github/workflows/orch-ci.yml`

## F0.2 — Package: configuración, base de datos e IA

### F0.2.T1 — Configuración (`config.py`)

`Settings` con pydantic-settings exactamente con las claves y defaults de la sección *config* de
la arquitectura, más `ROUTER_EMBEDDINGS_MODEL` (default `openai/text-embedding-3-small`) y
`TEST_DATABASE_URL`. Lee `.env` del cwd o el archivo de `PREDICTS_ENV_FILE`. Función
`settings()` cacheada y `settings_para_tests(**overrides)`. Validaciones: `DUCKDB_MEMORY_LIMIT`
con formato `<n>GB|MB`, `MAX_MEMORIA_TRABAJO_MB` > 512, `CONFIANZA_*` entre 0 y 1. `SECRET_KEY`
obligatoria fuera de `ENTORNO=dev`.

Done when: tests cubren defaults, lectura desde `PREDICTS_ENV_FILE`, overrides por entorno y cada
validación.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 1h
- **Razón**: Configuración tipada estándar.
- **Dependencies**: F0.1.T1
- **Files**:
  - `api/src/predicts/config.py`
  - `api/tests/test_config.py`

### F0.2.T2 — Esquema completo de Postgres con SQLAlchemy y Alembic

Modelos ORM (SQLAlchemy 2, tipado con `Mapped`) de **todas** las tablas de *Modelo de datos →
Postgres* de la arquitectura, **con exactamente las columnas que allí se listan**, con `empresa_id` en cada tabla de negocio, timestamps, índices y FKs con
`ON DELETE` coherente: `empresas`, `usuarios`, `sesiones`, `tokens_recuperacion`,
`intentos_login`, `proyectos`, `datasets`, `plantillas_mapeo`, `productos` (con
`embedding vector(1536)`), `grupos_producto`, `analisis`, `trabajos`, `eventos_trabajo`,
`decisiones_jev`, `plantillas_mensaje`, `api_keys`. Campos JSON como `JSONB`.

- `api/src/predicts/db/` con `base.py`, `modelos.py`, `sesion.py` (engine y `SessionLocal` desde
  `DATABASE_URL`, dependencia FastAPI `get_db`).
- Alembic en `api/alembic/` con **una sola migración inicial** que crea la extensión `vector` y
  todo el esquema. Las fases siguientes no cambian el esquema salvo que su tarea lo diga.
- Fixture de pytest `db` (en `api/tests/conftest_db.py`, registrada en `api/tests/conftest.py`
  con `pytest_plugins`) que crea una base temporal única desde `TEST_DATABASE_URL`, corre
  `alembic upgrade head` y la borra al final.
- `docs/notas/esquema.md` con el diagrama de tablas (Mermaid) y el porqué de cada índice.

Done when: `uv run pytest -q -m db` crea la base, migra, inserta y lee una fila de cada tabla, y
`alembic downgrade base` deja la base vacía; `alembic check` no detecta diferencias con los
modelos.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 3h
- **Razón**: Esquema amplio pero especificado; volumen más que dificultad.
- **Dependencies**: F0.1.T1, F0.2.T1
- **Files**:
  - `api/src/predicts/db/`
  - `api/alembic.ini`
  - `api/alembic/`
  - `api/tests/conftest.py`
  - `api/tests/conftest_db.py`
  - `api/tests/test_db_esquema.py`
  - `docs/notas/esquema.md`

### F0.2.T3 — Clientes de IA (`ia.py`): Jev, 9router y contador de costo

Implementar las funciones de *Interfaces → Jev* de la arquitectura:

- `cliente_jev()` (`TypeSafeClient` con `TYPESAFE_API_KEY`/`TYPESAFE_MODEL`) y
  `decidir_choice(pregunta, opciones, contexto)` / `decidir_si_no(pregunta, contexto)` sobre
  `system_one` (ver el patrón de `juez_jev.py` de apolicies), que devuelven
  `Decision(opcion, confianza, crudo)`. Variante en lote: `decidir_lote(contexto, preguntas)` que
  hace una sola llamada con varias preguntas.
- `registrar_decision(db, empresa_id, tipo, entrada_resumida, decision)` que guarda en
  `decisiones_jev`.
- `llm_texto()` (`ChatOpenAI` contra 9router, `streaming=False`, `timeout=120`, `max_retries=2`)
  y `generar(prompt, esquema)` con salida JSON validada por Pydantic y hasta 2 reintentos con el
  error de validación (patrón `estruturar` de apolicies; **no** usar `tool_choice` forzado).
- `embeddings(textos)` contra `/v1/embeddings` de 9router con `ROUTER_EMBEDDINGS_MODEL`, en lotes.
- `Contador` (thread-safe) de llamadas, tokens de entrada/salida por proveedor y costo estimado
  con precios configurables en un dict documentado.
- Todas las funciones aceptan un cliente inyectado para tests.

Done when: tests sin red con clientes falsos cubren cada función, el reintento por JSON inválido,
el registro en `decisiones_jev` (marcador `db`) y el contador; y un script
`api/scripts_dev/probar_ia.py` (no lo corre la CI) hace una llamada real a cada servicio con
`PREDICTS_ENV_FILE` y el resultado de esa corrida queda en el PR.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 3h
- **Razón**: Integración con dos SDKs conocidos y patrón existente en apolicies.
- **Dependencies**: F0.2.T1, F0.2.T2
- **Files**:
  - `api/src/predicts/ia.py`
  - `api/tests/test_ia.py`
  - `api/scripts_dev/probar_ia.py`

### F0.2.T4 — App FastAPI con descubrimiento de routers y salud

`api/src/predicts/app.py` con `crear_app()`:

- Descubre automáticamente todos los módulos de `predicts.api` que exponen `router` y los
  incluye, para que cada fase agregue su archivo sin tocar `app.py`.
- Manejador de errores con el formato `{"codigo": str, "parametros": dict}` de la arquitectura;
  clase `ErrorApi(codigo, status, **parametros)` para usar en todo el proyecto.
- `GET /salud` (incluye chequeo de Postgres y de `DATA_DIR`), CORS configurable para el
  frontend en dev, OpenAPI con títulos en español.
- Comandos `predicts api` (uvicorn) y `predicts openapi --salida <archivo>` (escribe el
  OpenAPI sin levantar el servidor; lo usa el frontend para generar sus tipos) en
  `comandos/api.py`.

Done when: tests con `TestClient` verifican el descubrimiento (un router de prueba en un paquete
temporal), el formato de error y `/salud`.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 1.5h
- **Razón**: Infraestructura de API acotada.
- **Dependencies**: F0.2.T1, F0.2.T2
- **Files**:
  - `api/src/predicts/app.py`
  - `api/src/predicts/api/__init__.py`
  - `api/src/predicts/api/salud.py`
  - `api/src/predicts/errores.py`
  - `api/src/predicts/comandos/api.py`
  - `api/tests/test_app.py`

## F0.3 — Package: Docker

### F0.3.T1 — Dockerfiles y docker compose con límites de memoria

- `api/Dockerfile` multi-stage con `uv` (imagen final slim, usuario no root) que sirve para
  `api` y `worker`.
- `web/Dockerfile`: build con Node 22 y nginx que sirve el build y hace proxy de `/api` a la API
  (`deploy/nginx.conf`), con soporte de SSE (`proxy_buffering off` en `/api/trabajos/`).
- `deploy/docker-compose.yml` con `postgres` (pgvector/pg17), `migrar` (one-shot
  `alembic upgrade head`), `api`, `worker` (comando `predicts worker`; si todavía no existe, que el
  servicio quede definido y documentado) y `web`, con los **límites de memoria** de la
  arquitectura (`mem_limit`), healthchecks, volúmenes para Postgres y `DATA_DIR`.
- `deploy/.env.example` con todas las claves de `config.py` sin valores secretos.
- `docs/notas/desarrollo.md`: cómo levantar todo, cómo correr tests contra `predicts-pg-dev`, y
  dónde mirar los logs.

Done when: `docker compose -f deploy/docker-compose.yml config` valida; `docker compose build`
termina; `docker compose up -d postgres migrar api web` deja `/salud` respondiendo a través de
nginx; se anota en el PR la memoria de cada contenedor en reposo (`docker stats --no-stream`).
Bajar los contenedores al terminar.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 2.5h
- **Razón**: Docker estándar con verificación real.
- **Dependencies**: F0.1.T1, F0.1.T2, F0.2.T4
- **Files**:
  - `api/Dockerfile`
  - `api/.dockerignore`
  - `web/Dockerfile`
  - `web/.dockerignore`
  - `deploy/docker-compose.yml`
  - `deploy/nginx.conf`
  - `deploy/.env.example`
  - `docs/notas/desarrollo.md`
