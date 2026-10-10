---
type: spec
project_id: predicts
phase: 7
version: 0.1
depends_on:
  - docs/arch/001-predicts.md
consumed_by:
  - orch-atomizer
generated_by: orch-spec
generated_at: 2026-10-09
title: Agente analista y MCP
---

# F7 — Agente analista y MCP

Un agente que responde preguntas sobre los datos consultándolos con SQL de solo lectura, siempre
mostrando la consulta y los números en que se basa (FR-22), expuesto en la web y como servidor
MCP. Contratos: *Componentes → Agente analista*.

Contexto común: el de `specs/f0-base.md`. El agente **nunca** inventa un número: todo número de
la respuesta sale de una consulta ejecutada en esa conversación.

## F7.1 — Package: agente

### F7.1.T1 — Agente con LangGraph y herramienta `consultar_sql` de solo lectura

- `agente/sql.py`: conexión DuckDB **de solo lectura** con vistas fijas del dataset y su último
  análisis (`compras`, `predicciones`, `ciclos`, `riesgo`, `ofertas`, `productos` con
  categoría y recompra/durable), y `consultar(sql)`: una sola sentencia, solo `SELECT`/`WITH`
  (validado con `duckdb.extract_statements` y el tipo de sentencia), sin funciones de archivo ni
  de red (`read_csv`, `read_parquet`, `httpfs`, `COPY`, `ATTACH`, `INSTALL`, `LOAD` rechazadas;
  `enable_external_access=false`), tope de 1.000 filas y 10 s, `memory_limit` de 1 GB.
- `agente/grafo.py`: LangGraph con el LLM de 9router, herramienta `consultar_sql` (el LLM recibe
  el esquema de las vistas con descripción de cada columna) y `describir_dataset`; máximo 6
  consultas por pregunta; respuesta estructurada `{respuesta, consultas: [{sql, filas_muestra,
  n_filas}], advertencias}` en el idioma del usuario. Si los datos no alcanzan, lo dice.
- `api/agente.py`: `POST /agente/preguntas` (`dataset_id`, `pregunta`, historial opcional de la
  conversación) con aislamiento por empresa; costo de cada pregunta registrado.

Done when: tests sin red con un LLM falso que emite llamadas a la herramienta cubren el flujo,
el tope de consultas, y que cada sentencia peligrosa listada se rechaza; tests de `consultar` con
el sintético.

- **Modelo**: claude/claude-opus-5-5
- **Estimación**: 4h
- **Razón**: Agente con herramientas y superficie de seguridad (SQL).
- **Dependencies**: F4.3.T2, F0.2.T3
- **Files**:
  - `api/src/predicts/agente/__init__.py`
  - `api/src/predicts/agente/sql.py`
  - `api/src/predicts/agente/grafo.py`
  - `api/src/predicts/api/agente.py`
  - `api/tests/test_agente.py`

### F7.1.T2 — Evaluación del agente con preguntas de respuesta conocida

- `api/tests/evals/agente/preguntas.yaml`: al menos 25 preguntas en pt-BR, es y en sobre el
  sintético (cuyas respuestas se calculan en el script, no a mano): conteos, top productos,
  ciclos, clientes en riesgo, comparación entre períodos, preguntas sin respuesta posible y
  preguntas maliciosas ("borra la tabla", "lee /etc/passwd").
- Comando `predicts evaluar-agente` (en `comandos/evaluar_agente.py`) que corre el agente con el
  LLM real y puntúa: respuesta numérica correcta (tolerancia definida), uso de consultas, no
  inventar cuando no hay dato, rechazo de las maliciosas; reporta acierto, consultas por pregunta
  y costo.
- `docs/notas/agente.md` con la medición real y los errores típicos.

Done when: el set y el comando existen con tests sin red, y el informe trae los números de una
corrida real.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 3h
- **Razón**: Construcción de evals y medición.
- **Dependencies**: F7.1.T1
- **Files**:
  - `api/tests/evals/agente/`
  - `api/src/predicts/comandos/evaluar_agente.py`
  - `api/tests/test_evaluar_agente.py`
  - `docs/notas/agente.md`

### F7.1.T3 — Servidor MCP

- `agente/mcp.py` y comando `predicts mcp` (en `comandos/mcp.py`) con el SDK `mcp`: transporte
  stdio y HTTP streamable, autenticado con API key de empresa (F2.2.T2). Herramientas:
  `listar_proyectos`, `listar_datasets`, `recordatorios(analisis_id, dias, limite)`,
  `ciclos_producto(analisis_id, producto)`, `clientes_en_riesgo(analisis_id, limite)` y
  `preguntar(dataset_id, pregunta)` (usa el agente de F7.1.T1).
- `docs/notas/mcp.md`: cómo conectarlo desde Claude Desktop/Claude Code con un ejemplo de
  configuración.

Done when: tests con el cliente MCP del SDK en memoria cubren cada herramienta, el rechazo sin
API key y el aislamiento entre empresas.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 3h
- **Razón**: Exponer funciones existentes por MCP.
- **Dependencies**: F7.1.T1, F2.2.T2
- **Files**:
  - `api/src/predicts/agente/mcp.py`
  - `api/src/predicts/comandos/mcp.py`
  - `api/tests/test_mcp.py`
  - `docs/notas/mcp.md`

## F7.2 — Package: chat en la web

### F7.2.T1 — Pantalla del agente analista

- Regenerar `web/src/api/openapi.json` y `schema.ts` (incluyen `/agente/preguntas`).
- Ruta `_autenticado/datasets/$datasetId/agente.tsx`: chat con historial de la sesión, sugerencias
  de preguntas, y en cada respuesta un desplegable "cómo lo calculé" con las consultas SQL
  (resaltadas) y la tabla de filas de muestra; advertencias visibles; errores traducidos.
- Enlace al agente desde resultados y desde el detalle del dataset.
- Namespace `agente`.

Done when: tests cubren enviar una pregunta, mostrar consultas y filas, advertencias y errores.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 3h
- **Razón**: Interfaz de chat con datos estructurados.
- **Dependencies**: F7.1.T1, F6.3.T3
- **Files**:
  - `web/src/api/openapi.json`
  - `web/src/api/schema.ts`
  - `web/src/routes/_autenticado/datasets/$datasetId/agente.tsx`
  - `web/src/features/agente/`
  - `web/src/i18n/locales/pt-BR/agente.json`
  - `web/src/i18n/locales/es/agente.json`
  - `web/src/i18n/locales/en/agente.json`
  - `web/src/__tests__/agente.test.tsx`
