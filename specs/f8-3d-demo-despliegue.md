---
type: spec
project_id: predicts
phase: 8
version: 0.1
depends_on:
  - docs/arch/001-predicts.md
consumed_by:
  - orch-atomizer
generated_by: orch-spec
generated_at: 2026-10-09
title: 3D, demo y despliegue
---

# F8 — 3D, demo y despliegue

Las dos vistas con React Three Fiber, la demo con datos de ejemplo, la retención de archivos y el
despliegue en un VPS. Contratos: *Componentes → Frontend (R3F)*, *Despliegue*, FR-23 a FR-25 y
NFR-3, NFR-6.

Contexto común: el de `specs/f0-base.md` y el de `specs/f6-web.md` (tipos de la API, i18n por
namespace, rutas por archivos). React Three Fiber **solo** en `web/src/tres/`, cargado con
`React.lazy` para que no pese en el resto del panel; siempre con versión 2D cuando el usuario
tiene `prefers-reduced-motion` o el dispositivo no soporta WebGL.

## F8.1 — Package: procesamiento en vivo

### F8.1.T1 — Escena 3D del procesamiento alimentada por los eventos reales

- `web/src/tres/procesamiento/`: escena con `@react-three/fiber` + `drei` que representa el flujo
  real del trabajo por etapas: las filas entran como partículas desde un "archivo", se agrupan en
  nodos de clientes y productos, se forman los ciclos y salen los recordatorios. **La cantidad y
  el ritmo de las partículas salen de los contadores de los eventos SSE** (`useEventosTrabajo`),
  con escala logarítmica para millones de filas; nada es decorativo ni inventado.
- Rendimiento: instancias (`InstancedMesh`), tope de partículas en pantalla, 60 fps en una
  laptop común, pausa cuando la pestaña no está visible.
- Se monta en el `<VistaProcesamiento>` de F6.3.T1 (y en la calidad de F6.2.T2 si aplica) con la
  versión 2D como respaldo; textos superpuestos con i18n (namespace `tres`).
- Captura: script `npm run captura:procesamiento` (Playwright) que graba un GIF/MP4 corto con un
  stream falso, para el contenido de la serie.

Done when: tests de la lógica de mapeo eventos → parámetros de la escena (pura, sin WebGL), test de
que se usa la versión 2D con `prefers-reduced-motion`, build sin aumentar el bundle inicial (la
escena en un chunk aparte, verificado en el análisis del build) y la captura generada.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 4h
- **Razón**: Visualización 3D con datos reales y restricciones de rendimiento.
- **Dependencies**: F6.3.T1
- **Files**:
  - `web/src/tres/procesamiento/`
  - `web/src/features/analisis/VistaProcesamiento.tsx`
  - `web/src/i18n/locales/pt-BR/tres.json`
  - `web/src/i18n/locales/es/tres.json`
  - `web/src/i18n/locales/en/tres.json`
  - `web/src/__tests__/tres-procesamiento.test.tsx`
  - `web/scripts/captura-procesamiento.ts`

## F8.2 — Package: universo de clientes

### F8.2.T1 — Endpoint del universo de clientes

- `api/universo.py`: `GET /analisis/{id}/universo?max=5000` que devuelve una muestra
  estratificada de clientes con: frecuencia (compras por mes), valor (si hay precio, si no número
  de compras), recencia, estado (`activo`, `en_recompra`, `en_riesgo`) y un grupo calculado con
  k-means simple sobre esas variables normalizadas (NumPy, k configurable). Desde los Parquet con
  DuckDB, sin cargar todo en memoria. `GET /analisis/{id}/universo/{cliente_id}`: historial
  resumido del cliente (productos, ciclos, próximas compras).

Done when: tests sobre el sintético cubren el tamaño de la muestra, la estratificación por estado,
los grupos y el aislamiento.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 2.5h
- **Razón**: Agregaciones con DuckDB y un clustering simple.
- **Dependencies**: F4.3.T3
- **Files**:
  - `api/src/predicts/api/universo.py`
  - `api/src/predicts/analisis/universo.py`
  - `api/tests/test_universo.py`

### F8.2.T2 — Vista 3D del universo de clientes

- Regenerar `web/src/api/openapi.json` y `schema.ts`.
- `web/src/tres/universo/`: nube de puntos (`InstancedMesh`) con ejes frecuencia × valor ×
  recencia, color por estado, controles de órbita y zoom, hover con tooltip y clic que abre el
  historial del cliente en un panel lateral; leyenda y filtros por estado.
- Pestaña "Universo" en resultados (enlazada desde F6.3.T2 sin modificar sus archivos: ruta propia
  `_autenticado/analisis/$analisisId/universo.tsx` y enlace en el layout de resultados si existe
  un punto de extensión; si no, enlace desde el detalle del análisis).
- Versión 2D (gráfico de dispersión con Recharts) como respaldo.

Done when: tests de la transformación de datos a posiciones/colores, del respaldo 2D y del panel
de historial; build con la escena en un chunk aparte.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 4h
- **Razón**: Visualización interactiva sobre un endpoint ya definido.
- **Dependencies**: F8.2.T1, F8.1.T1, F7.2.T1
- **Files**:
  - `web/src/api/openapi.json`
  - `web/src/api/schema.ts`
  - `web/src/tres/universo/`
  - `web/src/routes/_autenticado/analisis/$analisisId/universo.tsx`
  - `web/src/__tests__/tres-universo.test.tsx`

## F8.3 — Package: demo, retención y despliegue

### F8.3.T1 — Demo con datos de ejemplo

- `api/demo.py`: `POST /demo` crea, en la empresa del usuario, un proyecto "Demo" con una muestra
  de Online Retail II (CC BY 4.0, con la atribución visible en la interfaz y en el README),
  mapeo ya confirmado y el análisis completo encolado. La muestra se prepara al construir la
  imagen o al primer uso con `predicts preparar-dataset online-retail --muestra` y se cachea en
  `DATA_DIR/demo/`.
- Botón "probar con datos de ejemplo" en la lista de proyectos vacía y en la página de inicio
  (ruta `web/src/routes/_autenticado/demo.tsx` que llama la API y redirige al progreso), con
  namespace `demo`.

Done when: tests de la ruta (marcador `db`, con el dataset de fixture en lugar de la descarga) y
del botón; desde cero, la demo llega a resultados con el compose local (anotado en el PR con el
tiempo).

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 2.5h
- **Razón**: Ensamble de piezas existentes.
- **Dependencies**: F6.3.T2, F1.1.T2
- **Files**:
  - `api/src/predicts/api/demo.py`
  - `api/tests/test_demo.py`
  - `web/src/routes/_autenticado/demo.tsx`
  - `web/src/features/proyectos/`
  - `web/src/i18n/locales/pt-BR/demo.json`
  - `web/src/i18n/locales/es/demo.json`
  - `web/src/i18n/locales/en/demo.json`
  - `web/src/__tests__/demo.test.tsx`

### F8.3.T2 — Retención de archivos

- `retencion.py`: borra `original.csv`, `compras.parquet` y `resultados/` de datasets con más de
  `RETENCION_DIAS` desde la subida (los resultados resumidos, métricas y plantillas en Postgres se
  conservan); marca el dataset como `archivado` y la API responde `410 archivo_vencido` al pedir
  resultados detallados o exportar. Limpia `DATA_DIR/tmp` de restos de más de 1 día.
- Tipo de trabajo `retencion` encolado por el worker una vez por hora (sin cron externo).
- Comando `predicts limpiar --dry-run`.

Done when: tests con fechas simuladas cubren qué se borra y qué no, el `410`, la limpieza de
temporales y el dry-run.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 2h
- **Razón**: Tarea periódica acotada.
- **Dependencies**: F5.2.T1, F4.1.T1
- **Files**:
  - `api/src/predicts/retencion.py`
  - `api/src/predicts/trabajos/tipos_retencion.py`
  - `api/src/predicts/comandos/limpiar.py`
  - `api/tests/test_retencion.py`

### F8.3.T3 — Despliegue en VPS y README final

- `deploy/vps/`: override de compose para producción con **Caddy** como proxy con TLS automático
  delante de `web`, variables obligatorias (`SECRET_KEY`, `ENTORNO=prod`, SMTP), backups diarios
  de Postgres con retención de 7 días a un volumen, y un `instalar.sh` idempotente para un VPS
  Ubuntu limpio (Docker, firewall con 80/443/22, usuario sin root).
- `docs/notas/despliegue.md`: requisitos mínimos del VPS (RAM según `docs/notas/rendimiento.md`),
  pasos, actualización, restauración de backup y monitoreo básico (`/salud`).
- `README.md` final en pt-BR (principal) con secciones en español e inglés: qué es, capturas,
  demo, cómo correrlo local, arquitectura en una imagen, licencias de los datasets.

Done when: `docker compose -f deploy/docker-compose.yml -f deploy/vps/docker-compose.prod.yml
config` valida, `instalar.sh` pasa `shellcheck`, y un ensayo en local con un dominio de prueba
(o `localhost` con certificado interno de Caddy) levanta todo con TLS.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 3h
- **Razón**: Infraestructura y documentación estándar.
- **Dependencies**: F8.3.T1, F8.3.T2
- **Files**:
  - `deploy/vps/`
  - `docs/notas/despliegue.md`
  - `README.md`
