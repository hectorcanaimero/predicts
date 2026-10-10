---
type: spec
project_id: predicts
phase: 5
version: 0.1
depends_on:
  - docs/arch/001-predicts.md
consumed_by:
  - orch-atomizer
generated_by: orch-spec
generated_at: 2026-10-09
title: Mensajes y exportación
---

# F5 — Mensajes y exportación

Mensajes sugeridos para recordatorios, ofertas y reactivación, escritos por el LLM como
**plantillas** y revisados por Jev, y la exportación a CSV para cualquier CRM o herramienta de
envío. Contratos: *Componentes → Mensajes*, FR-19 y FR-21.

Contexto común: el de `specs/f0-base.md`. **El sistema no envía nada** (fuera de alcance del MVP):
genera y exporta.

## F5.1 — Package: mensajes

### F5.1.T1 — Plantillas de mensaje con el LLM y revisión con Jev

- `mensajes/plantillas.py`: para cada combinación (producto o grupo, o categoría si el producto
  tiene pocos clientes) × tipo (`recordatorio`, `oferta`, `reactivacion`) × idioma del proyecto ×
  tono, genera con `ia.generar` un `PlantillaMensaje` (Pydantic: `texto` ≤ 300 caracteres, con
  marcadores `{producto}`, `{dias}`, `{oferta}`, `{nombre_tienda}` cuando corresponda), en
  **lotes** de hasta 20 combinaciones por llamada. Prompt en el idioma del proyecto, con ejemplos
  de tono y reglas: sin inventar descuentos, sin urgencia falsa, sin datos personales.
- `mensajes/revision.py`: Jev revisa cada plantilla en lote (sí/no con motivo): promesas que el
  sistema no garantiza, datos sensibles, tono distinto del pedido, marcadores mal usados.
  Rechazada → se regenera **una vez** con el motivo; si vuelve a fallar queda `revisar`.
- Caché en `plantillas_mensaje` por (empresa, clave de la combinación, idioma, tono); editar una
  plantilla desde la API la marca `editada` y no se regenera.
- `mensajes/render.py`: completa la plantilla por fila de resultado (en código, nunca con el LLM)
  y valida que no queden marcadores sin reemplazar.
- Tipo de trabajo `mensajes` y paso opcional al final del orquestador de análisis.
- `api/mensajes.py`: `GET /analisis/{id}/plantillas`, `PATCH /plantillas-mensaje/{id}`,
  `POST /analisis/{id}/plantillas/regenerar`.

Done when: tests con LLM y Jev falsos cubren lotes, caché, regeneración única, render sin
marcadores sueltos y edición; medición real (fuera de la CI) sobre Online Retail II: número de
llamadas, costo y 15 plantillas revisadas a mano en los tres idiomas, anotado en el PR.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 4h
- **Razón**: Generación con LLM + revisión con Jev siguiendo patrones definidos.
- **Dependencies**: F4.3.T2
- **Files**:
  - `api/src/predicts/mensajes/__init__.py`
  - `api/src/predicts/mensajes/plantillas.py`
  - `api/src/predicts/mensajes/revision.py`
  - `api/src/predicts/mensajes/render.py`
  - `api/src/predicts/trabajos/tipos_mensajes.py`
  - `api/src/predicts/api/mensajes.py`
  - `api/tests/test_mensajes.py`

## F5.2 — Package: exportación

### F5.2.T1 — Exportación a CSV de recordatorios, ofertas y riesgo

- `exportar.py`: `GET /analisis/{id}/exportar?tipo=recordatorios|ofertas|riesgo&separador=,|;`
  con streaming desde el Parquet (DuckDB `COPY` a un archivo temporal o generador por bloques):
  `cliente_id`, `producto_id`, `producto_nombre`, `fecha_sugerida`, `fecha_min`, `fecha_max`,
  `probabilidad`, `motivo`, `mensaje` (render de F5.1), `contactar` (sí/no/revisar). UTF-8 con BOM
  (abre bien en Excel), encabezados en el idioma del proyecto, nombre de archivo con proyecto,
  tipo y fecha.
- Solo filas con `contactar = sí` por defecto; `incluir_revisar=true` para incluir las dudosas.

Done when: tests verifican columnas, separador, BOM, encabezados en los tres idiomas, filtros,
streaming (memoria acotada con 1 M de filas en un test marcado `lento`) y aislamiento.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 2h
- **Razón**: Exportación acotada.
- **Dependencies**: F5.1.T1, F4.3.T3
- **Files**:
  - `api/src/predicts/exportar.py`
  - `api/src/predicts/api/exportar.py`
  - `api/tests/test_exportar.py`
