# predicts: contexto del proyecto

Lectura obligatoria para cualquier agente antes de tocar código o specs.

## Qué es

Herramienta web que **predice cuándo cada cliente va a volver a comprar cada producto** a partir
de su historial de compras, y propone **recordatorios y ofertas** en el momento justo.

Ejemplo: María compra detergente cada ~21 días y su última compra fue hace 18 → el sistema sugiere
un recordatorio ("seu detergente deve estar acabando — hoje está em oferta") para los próximos días.

Cualquier empresa entra con **un CSV de compras** exportado de su ERP, tienda online o planilla;
mapea sus columnas en el panel, elige qué análisis correr y obtiene un panel con los resultados y
un **CSV de salida** listo para importar en su CRM, herramienta de email o WhatsApp.

Es open source y se construye **en público**: la carpeta `build-in-public/` guarda el diario y el
contenido que se publica (LinkedIn, Reddit, artículos, carruseles).

## Para quién

- **Primero:** equipos de marketing y CRM de negocios con compra recurrente (farmacias, pet shops,
  cosméticos, café, suplementos, e-commerce de consumo, clubes de suscripción) en Brasil y Latam
  que tienen datos de ventas pero no un motor de predicción.
- **En el contenido público** no se usa el encuadre "supermercado" ni se menciona el empleador de
  Héctor ni sus marcas (regla de confidencialidad). El dataset de Instacart se presenta como
  "dataset público de pedidos".
- **También:** agencias y consultores de CRM que analizan datos de varios clientes.

## Qué hace (MVP)

1. **Subir datos:** CSV por arrastrar y soltar, con detección de separador, codificación y formato
   de fecha, y vista previa.
2. **Mapear campos:** la persona define en el panel qué columna es el **ID del cliente**, la
   **fecha de compra**, el **identificador del producto (SKU o EAN)** y el **nombre del producto**
   (más los opcionales: pedido, cantidad, precio, categoría, marca). Jev sugiere el mapeo con su
   confianza; la persona confirma. El mapeo se guarda como plantilla.
3. **Informe de calidad de datos** antes de analizar.
4. **Elegir análisis:** recompra (quién y cuándo), ofertas personalizadas, riesgo de abandono y
   ciclos por producto, con parámetros (período, mínimo de compras, horizonte).
5. **Resultados:** panel, precisión medida sobre la propia historia (backtesting), mensajes
   sugeridos, exportación a CSV y un agente analista para preguntar a los datos.

## Reglas que no se negocian

- **Cada herramienta hace lo que mejor sabe hacer.**
  - **Estadística / ML** decide *cuándo* (ciclos de recompra, probabilidad de compra en una
    ventana). Nunca un LLM inventa una fecha o un número.
  - **Jev (TypeSafe, `system_one`)** toma las **decisiones** con probabilidad y confianza: mapeo
    de columnas, si un producto es de recompra o durable, categoría de producto, si vale la pena
    contactar a un cliente, y la revisión del mensaje antes de exportarlo.
  - **El LLM generativo vía 9router** (`ChatOpenAI`, `ROUTER_BASE_URL`/`ROUTER_API_KEY`/
    `ROUTER_MODEL`) escribe: mensajes, explicaciones y el agente analista.
- **Toda predicción viene con su evidencia y su incertidumbre** (rango de fechas, número de compras
  en que se basa). Si no hay historia suficiente, se dice, no se predice.
- **Toda decisión de Jev guarda su confianza.** Debajo del umbral, la decide una persona en el panel.
- **El sistema se mide:** cada análisis reporta su precisión sobre los datos del propio cliente
  (se esconden las últimas semanas y se predicen). Sin métrica no hay feature.
- **Privacidad (LGPD):** se recomiendan IDs anónimos; el sistema no necesita nombre, teléfono ni
  email. Los archivos subidos se borran a los `RETENCION_DIAS` días; quedan los resultados.
- **El sistema sugiere, no envía.** En el MVP no manda mensajes: los genera y los exporta.
- **Todo con techo de memoria.** El homelab tiene 14 GB de RAM compartidos: DuckDB con
  `memory_limit` y `threads` configurados y temporales en disco; cada contenedor con límite de
  memoria. Ningún proceso puede tumbar el servidor.

## Stack

- **Backend:** Python 3.13 con `uv`, FastAPI, Pydantic. Worker de análisis aparte.
- **Datos:** **DuckDB** sobre **Parquet** para el análisis (cada CSV se convierte a Parquet);
  **PostgreSQL** (con **pgvector**) para el estado de la aplicación: empresas, usuarios,
  proyectos, plantillas de mapeo, trabajos, resultados resumidos, decisiones de Jev, y la cola de
  trabajos. Archivos en disco local en desarrollo y almacenamiento compatible con S3 en producción.
- **IA:** Jev (`typesafe-sdk`, `TYPESAFE_API_KEY`, `TYPESAFE_MODEL=jev-latest`) para decisiones;
  LangChain/LangGraph + `ChatOpenAI` contra 9router para generación y el agente analista.
  Patrón de referencia: `/mnt/storage/agent-langchain` (guria-intake) y `/mnt/storage/project/apolicies`.
  Gotchas de 9router: `/mnt/storage/project/agndaZAP/docs/notas/2026-09-23-9router-gotchas.md`
  (por ejemplo, salida estructurada con `json_schema`, no `tool_choice` forzado).
- **Frontend:** React + TypeScript con Vite, Tailwind + shadcn/ui, TanStack Query, tipos generados
  desde el OpenAPI de FastAPI, Recharts/ECharts para gráficos, **React Three Fiber** solo para la
  pantalla de procesamiento en vivo y la vista 3D de clientes (carga diferida), Framer Motion /
  React Flow para animaciones 2D.
- **Despliegue:** todo en **Docker Compose** (`web`, `api`, `worker`, `postgres`), con límites de
  memoria por servicio. Un solo `docker compose up`.

## Datos de ejemplo (públicos)

Nunca se usan datos de clientes reales en el repo. Para desarrollo, tests y demos:
- **Instacart Market Basket** (pedidos de supermercado con días desde la compra anterior).
- **Dunnhumby "The Complete Journey"** y **Online Retail II (UCI)** como alternativas.
Los datasets completos viven fuera de git (`data/`); los tests usan muestras chicas versionadas.

## Idioma

- Código, specs, docs internas y diario: **español**.
- Interfaz del producto: **pt-BR y español** (i18n desde el inicio).
- Contenido público (`build-in-public/`): **pt-BR y español**.

## Flujo de trabajo

PRD (`docs/prd/`) → arquitectura (`docs/arch/`) → specs (`specs/`) → `orch atomize` → `orch run`.
Héctor revisa cada decisión antes del despacho. Cada fase cerrada deja una entrada en
`build-in-public/diario/` (qué se decidió, qué se midió, qué salió mal).

## Fuera de alcance (por ahora)

Conectores directos (Shopify, VTEX, Nuvemshop, Bling, Tiny, Omie, bases de datos, webhooks),
envío de mensajes (WhatsApp, email, push), integración con open-emarsys, modelos de deep learning,
facturación y planes pagos. El diseño los deja posibles: los conectores entrarán traduciendo al
mismo esquema interno que hoy produce el mapeo del CSV.
