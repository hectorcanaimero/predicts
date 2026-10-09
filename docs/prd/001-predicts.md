---
type: prd
project_id: predicts
version: 0.1
status: borrador para revisión de Héctor
fecha: 2026-10-09
---

# PRD 001 — predicts: recompra, recordatorios y ofertas a partir de un CSV

## 1. Problema

Los comercios con compra recurrente tienen el historial de ventas pero no saben **cuándo** cada
cliente va a necesitar volver a comprar. Las campañas salen a toda la base el mismo día con la misma
oferta: llegan tarde a quien ya compró en otro lado y temprano a quien todavía tiene producto.
Los motores de predicción existen en suites caras (Emarsys Predict, Salesforce) y requieren
integraciones largas.

## 2. Objetivo

Que cualquier equipo de marketing o CRM, con **solo un CSV de compras**, obtenga en minutos:
- quién debería recomprar qué y cuándo, con su incertidumbre;
- qué oferta tiene sentido para cada cliente;
- quién está dejando de comprar algo habitual;
- mensajes sugeridos y una lista exportable para su herramienta actual;
- **y cuánto acertaría el sistema** con sus propios datos.

## 3. Usuarios

- **Analista de CRM / marketing** (usuario principal): sube datos, mapea, corre análisis, exporta.
- **Responsable de marketing:** mira el panel y pregunta al agente analista.
- **Agencia / consultor:** gestiona proyectos de varios clientes.

## 4. Requisitos funcionales

### Datos de entrada
- **FR-1** Subida de CSV por arrastrar y soltar (hasta `MAX_CSV_MB`, default 500 MB), con detección
  automática de separador (`,` `;` `\t`), codificación (UTF-8, latin-1) y vista previa de las
  primeras filas.
- **FR-2** Mapeo de campos en el panel. Obligatorios: **ID del cliente**, **fecha de compra** (con
  su formato), **identificador del producto (SKU o EAN)**. Recomendado: **nombre del producto**.
  Opcionales: pedido, cantidad, precio unitario, valor total, categoría, marca.
- **FR-3** Jev sugiere el mapeo de cada columna con su confianza; por encima de `CONFIANZA_MAPEO`
  queda prellenado, por debajo queda marcado para revisión. La persona siempre confirma.
- **FR-4** El mapeo confirmado se puede guardar como **plantilla** y aplicar a futuros CSV con los
  mismos encabezados.
- **FR-5** El CSV se convierte a Parquet con el esquema interno único (el mismo que usarán los
  conectores futuros).

### Calidad de datos
- **FR-6** Informe antes de analizar: filas, clientes, productos, período cubierto, fechas
  inválidas, duplicados, filas sin cliente o sin producto, y **cuántos pares cliente–producto tienen
  historia suficiente** para predecir (≥ `MIN_COMPRAS`, default 3).
- **FR-7** Si los datos no alcanzan para un análisis, el sistema lo dice con el motivo y no lo corre.

### Enriquecimiento de productos
- **FR-8** Jev clasifica cada producto como **de recompra** (consumo) o **durable**, con confianza.
  Los durables no reciben recordatorio de recompra. Lo dudoso se muestra para revisión.
- **FR-9** Si el CSV no trae categoría, Jev la propone a partir del nombre.
- **FR-10** Productos equivalentes (variantes de nombre del mismo producto) se agrupan con
  embeddings en pgvector, con revisión opcional en el panel.

### Análisis (la persona elige cuáles correr)
- **FR-11 Recompra:** para cada par cliente–producto de recompra, ciclo estimado, fecha probable de
  la próxima compra con rango, y probabilidad de compra en el horizonte elegido (default 7 días).
- **FR-12 Ciclos por producto:** ciclo típico de recompra de cada producto y su dispersión.
- **FR-13 Riesgo de abandono:** clientes que superaron con margen su ciclo habitual en un producto
  (o en la tienda), ordenados por valor.
- **FR-14 Ofertas personalizadas:** para cada cliente, productos a ofrecer según su recompra
  próxima, lo que compran clientes parecidos y (si se sube) una lista de productos en oferta.
- **FR-15** Parámetros por análisis: período de datos, mínimo de compras, horizonte, umbral de
  probabilidad.

### Medición
- **FR-16** Cada análisis de recompra se valida con **backtesting sobre los datos del propio
  cliente**: se esconden las últimas `VENTANA_VALIDACION` semanas, se predicen, y se informa
  precisión, cobertura y error de fecha frente a una línea base simple (promedio del intervalo).
- **FR-17** Las decisiones de Jev corregidas por la persona quedan registradas y alimentan la
  medición de acierto de Jev (mapeo y clasificación).

### Resultados
- **FR-18** Panel con: lista de recordatorios del horizonte, ciclos por producto, clientes en riesgo,
  ofertas, métricas de precisión y gráficos.
- **FR-19** Mensajes sugeridos por cliente (pt-BR o español), escritos por el LLM a partir de datos
  del sistema, con tono configurable; Jev los revisa (sin promesas falsas ni datos sensibles)
  antes de exportar.
- **FR-20** Jev decide si vale la pena contactar a cada cliente (contactado hace poco, ya compró,
  baja probabilidad), con confianza.
- **FR-21** Exportación a CSV de recordatorios y ofertas: cliente, producto, fecha sugerida,
  probabilidad, motivo y mensaje.
- **FR-22** **Agente analista:** chat en el panel que responde preguntas sobre los datos
  ("¿por qué cayó la recompra de pañales?") ejecutando consultas SQL de solo lectura sobre DuckDB,
  mostrando la consulta y los números en que se basa.

### Experiencia
- **FR-23** Pantalla de **procesamiento en vivo** con React Three Fiber que muestra el avance real
  del análisis (filas leídas, clientes, pares, ciclos, recordatorios) vía eventos del backend.
- **FR-24** Vista 3D opcional del **universo de clientes** (agrupados por frecuencia y valor), con
  detalle al tocar un punto.
- **FR-25** Botón **"probar con datos de ejemplo"** (muestra de Instacart) sin subir nada.
- **FR-26** Interfaz en **pt-BR y español**.

### Cuentas
- **FR-27** Empresas (multi-tenant), usuarios con login, proyectos por empresa.

## 5. Requisitos no funcionales

- **NFR-1 Rendimiento:** un CSV de 1 millón de filas se analiza (recompra + ciclos + riesgo +
  backtesting) en menos de 5 minutos en el homelab.
- **NFR-2 Memoria:** ningún contenedor supera su límite; DuckDB con `memory_limit` (default 3 GB) y
  temporales en disco. Medido con la muestra completa de Instacart.
- **NFR-3 Privacidad:** archivos borrados a los `RETENCION_DIAS` (default 7); ningún dato de
  contacto requerido; aislamiento por empresa en Postgres.
- **NFR-4 Trazabilidad:** cada resultado guarda la versión del modelo, los parámetros, las
  decisiones de Jev con su confianza y el costo en tokens.
- **NFR-5 Costo:** costo de IA por análisis reportado; objetivo < 1 USD para 1 millón de filas
  (las llamadas a LLM se hacen por producto o por lote, nunca por fila).
- **NFR-6 Despliegue:** `docker compose up` levanta todo; mismas imágenes para homelab y VPS.
- **NFR-7 Calidad:** tests sin red para la lógica; CI en cada PR; datasets de prueba versionados
  y chicos.

## 6. Métricas de éxito

- Precisión de recompra en backtesting **por encima de la línea base** (promedio del intervalo) en
  Instacart, reportada en cada episodio.
- Acierto del mapeo automático de Jev ≥ 90 % sobre un set de CSVs reales y desordenados.
- Tiempo desde subir el CSV hasta exportar ≤ 10 minutos para un usuario nuevo.
- Serie publicada: al menos un episodio por semana (ver `build-in-public/ESTRATEGIA.md`).

## 7. Fuera de alcance del MVP

Conectores directos, envío de mensajes, integración con open-emarsys, deep learning, pagos.

## 8. Preguntas abiertas

1. ¿Repo público en GitHub desde el día 1 (recomendado para la serie) y bajo qué licencia (MIT o
   Apache-2.0)?
2. ¿Login propio simple (email + contraseña) o un proveedor (Clerk, Supabase Auth) para el MVP?
3. ¿La demo pública corre en el homelab vía Cloudflare Tunnel o directamente en un VPS?
