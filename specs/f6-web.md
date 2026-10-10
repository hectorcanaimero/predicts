---
type: spec
project_id: predicts
phase: 6
version: 0.1
depends_on:
  - docs/arch/001-predicts.md
consumed_by:
  - orch-atomizer
generated_by: orch-spec
generated_at: 2026-10-09
title: Interfaz web
---

# F6 — Interfaz web

El panel en React: login, proyectos, subir CSV, mapear campos con las sugerencias de Jev, calidad
de datos, elegir análisis, seguir el trabajo y ver y exportar resultados. Multiidioma (pt-BR, es,
en). Contratos: *Componentes → Frontend*, FR-1 a FR-21, FR-26.

Contexto común: el de `specs/f0-base.md`. Además:
- **Tipos de la API:** `web/src/api/openapi.json` se exporta con `uv run predicts openapi
  --salida ../web/src/api/openapi.json` (desde `api/`) y `npm run gen:api` genera
  `web/src/api/schema.ts`. Solo F6.1.T1 los genera; las demás tareas de esta fase los usan sin
  regenerarlos.
- **Textos:** cada página tiene su namespace i18n propio (`web/src/i18n/locales/<idioma>/
  <namespace>.json`, en los tres idiomas). Los códigos de error de la API se traducen en el
  namespace de la pantalla que los muestra; los genéricos están en `comun`.
- **Rutas por archivos** en `web/src/routes/`; cada tarea crea solo sus archivos de ruta.
- Diseño sobrio con shadcn/ui; tablas grandes paginadas desde la API; estados de carga, vacío y
  error en cada pantalla; accesible con teclado.
- Tests con Vitest + Testing Library y la API simulada (MSW o fetch falso).

## F6.1 — Package: base de la aplicación

### F6.1.T1 — Cliente de API, sesión y pantallas de cuenta

- Exportar el OpenAPI y generar `schema.ts`; cliente `openapi-fetch` en `web/src/api/cliente.ts`
  con `credentials: "include"` y el header `X-CSRF-Token` leído de la cookie `predicts_csrf` en
  métodos que cambian estado; manejo central de `401` (redirige a login) y de errores
  `{codigo, parametros}`.
- Hooks de TanStack Query base y `useSesion()` (`GET /auth/yo`).
- Rutas `login`, `registro`, `recuperar`, `restablecer` (namespace `auth`), guarda de rutas
  autenticadas, menú de usuario con cerrar sesión, y selector de idioma que además guarda la
  preferencia con `PATCH /auth/yo`.

Done when: tests cubren login correcto y con error traducido en los tres idiomas, redirección por
`401`, envío del header CSRF y el cambio de idioma persistido; `npm run build` pasa.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 4h
- **Razón**: Integración frontend–API con sesión y CSRF.
- **Dependencies**: F0.1.T2, F2.1.T2, F2.2.T2, F4.2.T2, F5.2.T1
- **Files**:
  - `web/src/api/`
  - `web/src/hooks/useSesion.ts`
  - `web/src/routes/login.tsx`
  - `web/src/routes/registro.tsx`
  - `web/src/routes/recuperar.tsx`
  - `web/src/routes/restablecer.tsx`
  - `web/src/routes/_autenticado.tsx`
  - `web/src/components/layout/`
  - `web/src/i18n/locales/pt-BR/auth.json`
  - `web/src/i18n/locales/es/auth.json`
  - `web/src/i18n/locales/en/auth.json`
  - `web/src/__tests__/auth.test.tsx`

### F6.1.T2 — Proyectos

- Rutas `_autenticado/proyectos/index.tsx` (lista, vacío con llamado a crear el primero) y
  `_autenticado/proyectos/$proyectoId.tsx` (detalle con sus datasets y análisis), diálogo de
  crear/editar (nombre, idioma de los mensajes, tono, descripción) y borrar con confirmación.
- Namespace `proyectos`.

Done when: tests cubren lista, crear, editar, borrar y estados de carga/vacío/error.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 2.5h
- **Razón**: CRUD de interfaz estándar.
- **Dependencies**: F6.1.T1
- **Files**:
  - `web/src/routes/_autenticado/proyectos/`
  - `web/src/features/proyectos/`
  - `web/src/i18n/locales/pt-BR/proyectos.json`
  - `web/src/i18n/locales/es/proyectos.json`
  - `web/src/i18n/locales/en/proyectos.json`
  - `web/src/__tests__/proyectos.test.tsx`

## F6.2 — Package: datos

### F6.2.T1 — Subir CSV

- Ruta `_autenticado/proyectos/$proyectoId/datasets/nuevo.tsx`: zona de arrastrar y soltar
  (CSV, `.csv.gz`, `.zip`), vista previa de las primeras filas leída **en el navegador** antes de
  subir (primer bloque del archivo), subida con barra de progreso real (XHR/fetch con progreso) y
  cancelación, errores traducidos (`archivo_muy_grande`, formato no soportado). Al terminar,
  pasa a la pantalla de mapeo.
- Namespace `subir`.

Done when: tests cubren selección por arrastre y por botón, vista previa, progreso, cancelación y
errores.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 2.5h
- **Razón**: Componente de subida con estados definidos.
- **Dependencies**: F6.1.T2
- **Files**:
  - `web/src/routes/_autenticado/proyectos/$proyectoId/datasets/nuevo.tsx`
  - `web/src/features/subir/`
  - `web/src/i18n/locales/pt-BR/subir.json`
  - `web/src/i18n/locales/es/subir.json`
  - `web/src/i18n/locales/en/subir.json`
  - `web/src/__tests__/subir.test.tsx`

### F6.2.T2 — Mapear campos, ingesta y calidad de datos

- Ruta `_autenticado/datasets/$datasetId/mapeo.tsx`: tabla con cada columna del CSV, sus valores
  de muestra y un selector del campo interno, **prellenado con la sugerencia de Jev** y una
  insignia de confianza (alta → verde "sugerido", baja → ámbar "revisar"); selector de formato de
  fecha con el % que parsea cada uno; SKU o EAN; validación en vivo (obligatorios, duplicados);
  casilla "guardar como plantilla"; botón confirmar e iniciar ingesta.
- Ruta `_autenticado/datasets/$datasetId/calidad.tsx`: progreso de la ingesta (SSE de
  `/trabajos/{id}/eventos`, versión 2D simple: etapas y contadores) y luego el informe de calidad
  (FR-6) con tarjetas y un gráfico de compras por cliente; viabilidad por análisis con el motivo
  cuando no alcanza (FR-7); botón para continuar a análisis.
- Lista de productos a revisar (recompra/durable y categoría con confianza baja) con corrección en
  línea (`PATCH /productos/{id}`), y propuestas de productos equivalentes para confirmar o
  rechazar.
- Hook `useEventosTrabajo(trabajoId)` (SSE con reconexión) en `web/src/hooks/`, reutilizable.
- Namespaces `mapeo` y `calidad`.

Done when: tests cubren prellenado e insignias, validación, plantilla, el hook SSE con un stream
falso (incluida la reconexión), el informe de calidad y la corrección de productos.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 4h
- **Razón**: Pantallas con varios estados y streaming.
- **Dependencies**: F6.2.T1
- **Files**:
  - `web/src/routes/_autenticado/datasets/$datasetId/mapeo.tsx`
  - `web/src/routes/_autenticado/datasets/$datasetId/calidad.tsx`
  - `web/src/features/mapeo/`
  - `web/src/features/calidad/`
  - `web/src/hooks/useEventosTrabajo.ts`
  - `web/src/i18n/locales/pt-BR/mapeo.json`
  - `web/src/i18n/locales/es/mapeo.json`
  - `web/src/i18n/locales/en/mapeo.json`
  - `web/src/i18n/locales/pt-BR/calidad.json`
  - `web/src/i18n/locales/es/calidad.json`
  - `web/src/i18n/locales/en/calidad.json`
  - `web/src/__tests__/mapeo.test.tsx`
  - `web/src/__tests__/calidad.test.tsx`

## F6.3 — Package: análisis y resultados

### F6.3.T1 — Elegir análisis y seguir su ejecución

- Ruta `_autenticado/datasets/$datasetId/analisis/nuevo.tsx`: tarjetas para recompra, ciclos,
  riesgo de abandono y ofertas (deshabilitadas con el motivo si la calidad dice que no hay datos
  suficientes), parámetros con valores por defecto y ayuda (período, mínimo de compras,
  horizonte, umbral), subida opcional de la lista de ofertas.
- Ruta `_autenticado/analisis/$analisisId/progreso.tsx`: progreso con `useEventosTrabajo` en una
  vista 2D (etapas y contadores; la escena 3D llega en F8.1 y se monta en un contenedor
  `<VistaProcesamiento>` que esta tarea deja con la versión 2D por defecto), cancelar, error
  traducido (`memoria_excedida`, `tiempo_excedido`, …) y paso automático a resultados.
- Namespace `analisis`.

Done when: tests cubren la selección, los deshabilitados por viabilidad, parámetros, el progreso
con un stream falso, cancelar y los errores.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 3h
- **Razón**: Formulario y progreso con hook ya existente.
- **Dependencies**: F6.2.T2
- **Files**:
  - `web/src/routes/_autenticado/datasets/$datasetId/analisis/nuevo.tsx`
  - `web/src/routes/_autenticado/analisis/$analisisId/progreso.tsx`
  - `web/src/features/analisis/`
  - `web/src/i18n/locales/pt-BR/analisis.json`
  - `web/src/i18n/locales/es/analisis.json`
  - `web/src/i18n/locales/en/analisis.json`
  - `web/src/__tests__/analisis.test.tsx`

### F6.3.T2 — Resultados, precisión, mensajes y exportación

- Ruta `_autenticado/analisis/$analisisId/index.tsx` con pestañas:
  - **Recordatorios:** tabla paginada (cliente, producto, fecha probable con rango, probabilidad,
    motivo, mensaje, contactar), filtros y orden desde la API; calendario de recordatorios por día
    del horizonte (gráfico de barras).
  - **Ciclos por producto:** tabla y gráfico de dispersión ciclo vs. clientes recurrentes.
  - **Riesgo:** tabla con motivo y valor.
  - **Ofertas:** por cliente.
  - **Precisión:** métricas del backtest **modelo vs. línea base** lado a lado, gráfico de
    calibración por deciles y una explicación corta de qué significa cada número (FR-16).
  - **Mensajes:** plantillas por producto y tipo, editar y regenerar.
- Botones de exportar (recordatorios, ofertas, riesgo; separador `,` o `;`).
- Namespace `resultados`.

Done when: tests cubren cada pestaña con datos falsos, paginación y orden, edición de plantilla y
la descarga del CSV.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 4h
- **Razón**: Pantalla rica pero con datos ya resueltos por la API.
- **Dependencies**: F6.3.T1
- **Files**:
  - `web/src/routes/_autenticado/analisis/$analisisId/index.tsx`
  - `web/src/features/resultados/`
  - `web/src/i18n/locales/pt-BR/resultados.json`
  - `web/src/i18n/locales/es/resultados.json`
  - `web/src/i18n/locales/en/resultados.json`
  - `web/src/__tests__/resultados.test.tsx`

### F6.3.T3 — Prueba de punta a punta con Playwright

- `web/e2e/flujo-completo.spec.ts`: con `docker compose` levantado (Jev y 9router reemplazados
  por servidores falsos deterministas que la tarea crea en `api/tests/e2e/` y que se activan con
  una variable de entorno), registrar usuario, crear proyecto, subir el CSV de fixture, confirmar
  el mapeo, esperar la calidad, correr los cuatro análisis, ver resultados y exportar; repetir el
  login y una pantalla en es y en.
- Script `npm run e2e` y un job opcional en la CI (manual, `workflow_dispatch`) en un workflow
  aparte.
- Medir y anotar en el PR el tiempo del flujo (objetivo del PRD: ≤ 10 min para un usuario nuevo).

Done when: `npm run e2e` pasa localmente contra el compose y el informe del PR trae el tiempo.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 4h
- **Razón**: E2E con dobles de servicios externos.
- **Dependencies**: F6.3.T2
- **Files**:
  - `web/e2e/`
  - `web/playwright.config.ts`
  - `api/tests/e2e/`
  - `.github/workflows/e2e.yml`
