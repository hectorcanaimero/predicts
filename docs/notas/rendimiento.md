# Rendimiento: ingesta + calidad + productos + análisis con 1 M y 5 M de filas

Medición real de NFR-1/NFR-2 pedida en specs/f4-analisis.md#F4.3.T3: "< 5 min para 1 M de
filas", con los límites de memoria de la arquitectura (`deploy/docker-compose.yml`) y sin gastar
en Jev real (el catálogo sintético se clasifica entero por regla, sin preguntarle a Jev — ver
abajo).

## Método

- Stack: `docker compose` con los mismos servicios y `mem_limit` de `deploy/docker-compose.yml`
  (`postgres` 1 GiB, `api` 1 GiB, `worker` 5 GiB), en un proyecto compose separado
  (`predicts-bench`, puertos y `.env` propios, borrado al terminar) para no tocar ningún stack
  de desarrollo que ya estuviera corriendo en la máquina.
- Datos: CSV sintético generado con `predicts sintetico` (mismo generador de
  `datos/sintetico.py` que usan los tests de F4.3.T1/T2) y exportado a CSV con DuckDB:
  - **1 M filas**: `--clientes 2950 --productos 15` → 1 003 410 filas, 31 046 pares con verdad.
  - **5 M filas**: `--clientes 14750 --productos 15` → 5 018 976 filas, 155 104 pares con verdad.
- Pipeline real de punta a punta por la API (sin atajos): registro → crear proyecto → subir el
  CSV → confirmar un mapeo manual 1:1 (nombres de columna ya iguales a los del esquema interno,
  así que no hace falta `GET /mapeo`, que sí llamaría a Jev) → `POST /datasets/{id}/ingesta` →
  esperar `calidad` (la encola la propia ingesta) → esperar `productos` (la encola la calidad) →
  `POST /datasets/{id}/analisis` con `tipos=[recompra, ciclos, riesgo, ofertas]` (sin
  `contactar`: es el único análisis que llama a Jev, y no lo pide esta medición). Driver:
  `httpx` + `psycopg` consultando `trabajos`/`analisis` directo en Postgres (script de un solo
  uso, no versionado).
- Tiempo por etapa: `trabajos.duracion_s` (lo mide el propio worker alrededor de
  `multiprocessing.Process.run`, es el tiempo real del subproceso, no el *polling* del driver).
- Memoria del subproceso: `trabajos.memoria_pico_mb` (`ru_maxrss` del hijo, ya lo guarda
  F4.1.T1). Memoria del contenedor: `cat /sys/fs/cgroup/memory.peak` dentro de cada contenedor
  (cgroup v2), leído una vez al final de cada corrida — es el pico de esa corrida completa, no
  de una sola etapa.
- **"Jev falso, para no gastar"**: no fue necesario simularlo. El catálogo sintético (15
  productos, miles de clientes) cae entero en la regla previa de `clasificacion.py` (≥ 30 % de
  recompra con mediana < 120 días, o ≥ 50 clientes sin ninguna recompra): confirmado con
  `decisiones_jev` en 0 filas en ambas corridas. El único paso que de verdad llama a un servicio
  externo es `equivalentes.generar_embeddings` (9router, F4.2.T2) dentro del trabajo
  `productos`; con `ROUTER_BASE_URL` apuntando a un host que no resuelve (`.invalid`, RFC 2606)
  falla rápido con `ConnectError` y el trabajo queda en `error` — ver más abajo por qué no afecta
  el número que importa para esta medición.

## Resultados — 1 000 000 de filas

| Etapa      | `duracion_s` | memoria subproceso | nota |
|---|---|---|---|
| ingesta    | 5,0 s  | 440 MB | |
| calidad    | 2,8 s  | 517 MB | |
| productos  | 3,1 s  | 620 MB | `error_interno`: falla en `generar_embeddings` (sin credenciales reales en el banco de pruebas) **después** de que catálogo + clasificación por regla ya habían hecho commit — el catálogo quedó clasificado igual (15/15 por regla, 0 llamadas a Jev) |
| análisis (recompra+ciclos+riesgo+ofertas) | 3,9 s | 680 MB | `995 091` filas de compra tras filtrar durables, `22 658` pares evaluados en recompra |
| **Total** | **≈ 14,7 s** | | **muy por debajo de 5 min** |

Memoria pico de contenedor (toda la corrida): `api` 455 MiB / 1 GiB, `worker` 827 MiB / 5 GiB,
`postgres` 111 MiB / 1 GiB.

## Resultados — 5 000 000 de filas

| Etapa      | `duracion_s` | memoria subproceso | nota |
|---|---|---|---|
| ingesta    | 13,3 s | 442 MB | |
| calidad    | 3,9 s  | 1 409 MB | |
| productos  | 4,9 s  | 2 043 MB | mismo `error_interno` de `generar_embeddings`, mismo catálogo (15/15 por regla, 0 Jev) |
| análisis, `MAX_MEMORIA_TRABAJO_MB=4096` (default de la arquitectura) | — | — | **el subproceso aborta**: `terminate called after throwing an instance of 'std::bad_alloc'`, el worker lo reporta como señal (`error_interno`), no como `memoria_excedida` — ver "Hallazgo" abajo |
| análisis, repetido con `MAX_MEMORIA_TRABAJO_MB=4800` (mismo contenedor, mismo límite de 5 GiB) | 9,8 s | 1 917 MB | `listo`: `4 977 455` filas tras filtrar durables |
| **Total con el ajuste** | **≈ 32,0 s** | | **muy por debajo de 5 min** |

Memoria pico de contenedor `worker` con `MAX_MEMORIA_TRABAJO_MB=4800`: 1,94 GiB / 5 GiB (sigue
con margen hasta el límite del contenedor).

## Hallazgo: `MAX_MEMORIA_TRABAJO_MB=4096` no alcanza para el análisis completo a 5 M de filas

Con el default de la arquitectura (4096 MB de `RLIMIT_DATA` por trabajo, ver
`trabajos/worker.py`), el análisis completo (recompra + ciclos + riesgo + ofertas) sobre 5 M de
filas no termina: el subproceso aborta con `std::bad_alloc` sin capturar (probablemente lanzado
en un hilo de DuckDB — corre con `DUCKDB_THREADS=4` — que no pasa por el manejo de excepciones
de Python). El worker lo clasifica como señal genérica (`error_interno`), **no** como
`memoria_excedida`: el camino que sí distingue el tope de memoria
(`MemoryError`/`OutOfMemoryException` atajado en el hijo, o `SIGKILL` del OOM killer del
contenedor) no cubre un `abort()` de una librería C++ en otro hilo. Repetir la misma corrida con
`MAX_MEMORIA_TRABAJO_MB=4800` (todavía por debajo del límite de 5 GiB del contenedor `worker`)
sí completa en 9,8 s con 1,9 GB de pico — o sea que el techo real está en algún punto entre
4096 MB y 4800 MB para este tamaño de dataset y catálogo, no en los 5 GB del contenedor.

Dos consecuencias para decidir fuera de esta tarea (no son parte de los archivos que toca
F4.3.T3):

1. Subir el default de `MAX_MEMORIA_TRABAJO_MB` (p. ej. a 4800) para que datasets de varios
   millones de filas no fallen con el valor de fábrica, dejando margen bajo el límite del
   contenedor `worker` (5 GiB).
2. `worker.py` podría tratar cualquier muerte por señal (no solo `SIGKILL`) como candidato a
   `memoria_excedida` cuando el detalle menciona `bad_alloc`/`OutOfMemoryException`, en vez de
   `error_interno` genérico — ahora mismo ese caso no se distingue de un crash real del código.

## Conclusión sobre NFR-1/NFR-2

- **"< 5 min para 1 M de filas" se cumple con margen amplio**: ingesta + calidad + productos +
  análisis completo tardan ≈ 15 s, no minutos — casi dos órdenes de magnitud por debajo del
  límite.
- **5 M de filas también entra en el margen de 5 minutos** (≈ 32 s) una vez corregido el tope de
  memoria del trabajo de análisis (ver hallazgo arriba); con el default de fábrica el análisis
  no llega a terminar.
- La memoria de los contenedores `api` y `postgres` se mantuvo muy por debajo de sus límites
  (1 GiB) en ambos tamaños; el contenedor que importa vigilar es `worker`, y ahí el límite que
  realmente actúa primero es el tope *por trabajo* (`MAX_MEMORIA_TRABAJO_MB`), no el del
  contenedor completo.
- El catálogo de productos de este sintético (15 productos) se clasifica entero por regla sin
  Jev; el costo de Jev en productos escala con la cantidad de *productos* distintos, no con las
  filas de compra, así que no es sensible al tamaño del dataset medido aquí (ya se midió aparte
  en F4.2.T1 sobre Online Retail II).
