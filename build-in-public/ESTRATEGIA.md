# Estrategia de publicación — predicts (build in public)

## Objetivo

Mostrar **cómo construye Héctor productos de IA con un equipo de agentes** (Hermes + orch +
agentes de código + supervisor + evals), usando predicts como caso real. Es la vitrina para la
búsqueda de trabajo como **AI Engineer** (remoto, Brasil, Latam y España).

El protagonista es **el método**; predicts es la historia que lo demuestra.

## Reglas

- **Nunca se publica nada automáticamente.** Todo es borrador; Héctor revisa y publica a mano.
- **Números reales o nada.** Cada cifra sale de orch (tareas, costo, reintentos), de las evals o
  de una medición anotada en el diario. Si falta un dato, el borrador lo marca con `[DATO: …]`.
- **Lo que salió mal se cuenta.** Los errores y cómo se resolvieron son el mejor contenido.
- **Confidencialidad:** no se nombra al empleador de Héctor, sus marcas ni sus clientes; no se usa
  el encuadre "supermercado". Antes de entregar un borrador se revisa contra esa lista.
- **Héctor no aparece en cámara.** Formatos escritos y visuales; video solo más adelante, sin cara.
- **Idiomas:** pt-BR primero (audiencia principal), español después. Inglés solo si Héctor decide
  responder comentarios con traducción.

## Canales y formato

La serie es **diaria**: cada día de trabajo deja una pieza corta, y los hitos se cuentan en largo.

| Canal | Qué va | Frecuencia |
|---|---|---|
| X / Twitter (pt-BR) | "Dia N" del predicts: 1 post (≤ 280 caracteres) o un hilo corto de 3–6 posts, con una imagen o GIF real (captura, diagrama, gráfico de métrica) | **diario** (días con trabajo) |
| Instagram (pt-BR) | **Carrusel** de 5–7 láminas 1080×1350 generado con datos reales ("o que fiz hoje", "o erro do dia", "o número do dia") + caption; **stories** con el avance | **diario** el carrusel o una lámina; stories cuando haya algo visual |
| LinkedIn (pt-BR, luego es) | Resumen de la semana: la decisión o el problema más importante, o carrusel PDF de 8–10 láminas | **semanal** (más en semanas con hito) |
| Reddit (r/brdev en pt-BR; comunidades dev en español) | Post largo y técnico en los hitos, con lo que se midió y lo que se rompió, link al repo, sin vender | cada 2–3 semanas |
| Blog (tryorch.us o guria.lat) | Artículo largo por episodio, con diagramas, código y métricas. Es lo que se enlaza en el CV | por episodio |
| GitHub (repo público) | Código, README y `build-in-public/diario/` | continuo |

### Formatos diarios

- **X:** `Dia N do predicts:` + qué se hizo, un número o un error, y la imagen. Hilo solo cuando la
  historia lo pide (una decisión con su porqué, un bug con su causa).
- **Instagram:** plantilla fija para que se reconozca la serie (portada "DIA N", 3–5 láminas de
  contenido, cierre "amanhã: …"). Las láminas se generan desde el diario y los datos reales con el
  mismo generador de slides del proyecto; Héctor no aparece.
- **Material visual del día:** capturas del panel, del dashboard de orch, gráficos de métricas,
  diagramas de arquitectura, fragmentos de código cortos.

## Calendario de episodios (borrador)

Cada episodio se publica cuando su hito está hecho, no por fecha. El orden sigue al desarrollo.

| # | Título de trabajo | Hito que lo dispara | Ángulo |
|---|---|---|---|
| 0 | O método: um time de agentes para construir um produto | PRD aprobado | quién hace qué: Héctor, Hermes, orch, agentes, supervisor |
| 1 | Por que um CSV (e não integrações) | diseño del flujo de entrada | producto: empezar por la entrada universal |
| 2 | Duas bases de dados, não uma | arquitectura aprobada | DuckDB para analizar, Postgres para la app |
| 3 | Onde o LLM entra e onde não entra | primer modelo de recompra | estadística decide "cuándo", Jev decide "qué", el LLM escribe |
| 4 | O primeiro backtest (e como ele foi mal) | primera medición contra la línea base | evals honestas |
| 5 | Jev mapeando CSVs bagunçados | mapeo automático medido | decisiones con confianza y humano en el medio |
| 6 | O bug da semana | el primer incidente serio | operación real |
| 7 | Vendo o processo andar (React Three Fiber) | pantalla de procesamiento | producto visual |
| 8 | Um agente analista com SQL | agente analista | agentes con herramientas, MCP |
| 9 | Quanto custa analisar 1 milhão de linhas | medición de costo | costo por análisis |
| 10 | O que aprendi | demo pública | retrospectiva con todos los números |

## Flujo de producción

### Diario (cada día de trabajo)

1. Durante el día, Hermes anota en `diario/AAAA-MM-DD.md`: decisiones, mediciones, errores,
   capturas y números de orch.
2. Al cierre del día, Hermes arma `dias/AAAA-MM-DD/` con `x.md` (post o hilo), `instagram.md`
   (caption + guion de láminas) y las imágenes en `dias/AAAA-MM-DD/img/`, y avisa a Héctor por
   Slack para que revise y publique.

### Episodio (cada hito)

1. El material sale del diario de los días del hito.
2. Al cerrar el hito, Hermes arma en `episodios/NN-slug/`:
   - `linkedin-pt.md` y `linkedin-es.md` (post + notas de horario, imagen y datos faltantes);
   - `carrusel/` (fuente y PDF generado con datos reales), cuando el episodio lo amerita;
   - `reddit-pt.md` (y `reddit-es.md`) en episodios de hito;
   - `articulo.md` (blog).
3. Héctor revisa, corrige y publica (en todos los canales, a mano). Anota en `publicaciones.md` la fecha, el link y las métricas
   que quiera seguir (impresiones, comentarios, estrellas del repo).
4. Los comentarios que traigan ideas o preguntas buenas pasan al diario y pueden ser un episodio.

## Horarios sugeridos (LinkedIn Brasil)

Martes a jueves, entre 8:00 y 9:30 o entre 12:00 y 13:00 (hora de Brasília). Es una referencia
para empezar; se ajusta con lo que muestren las métricas propias.

## Métricas a seguir

- LinkedIn: impresiones, comentarios, nuevos seguidores, mensajes de reclutadores.
- Reddit: upvotes, comentarios, visitas al repo.
- GitHub: estrellas, forks, issues de terceros.
- El objetivo real: **entrevistas de AI Engineer**. Se anota cuando una conversación venga del
  contenido.
