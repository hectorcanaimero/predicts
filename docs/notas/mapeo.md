# Medición del mapeo (`sugerir()`) con Jev real

Corrida real de `predicts medir-mapeo` (`api/src/predicts/comandos/medir_mapeo.py`) sobre el
set de 32 CSVs desordenados de `api/tests/fixtures/desordenados/` (generados con
`scripts/generar_desordenados.py`, semilla `20261009`), contra **Jev real**
(`TYPESAFE_MODEL=jev-latest`). No son cifras inventadas: quedan reproducibles corriendo el
mismo comando contra una base Postgres migrada (`alembic upgrade head`) y el `.env` con las
claves reales.

- **Fecha de la corrida:** 2026-10-09.
- **`CONFIANZA_MAPEO`:** 0.8 (el valor por defecto de `Settings`, sin overrides).
- **Comando exacto:**
  ```bash
  DATABASE_URL=postgresql+psycopg://predicts:predicts@127.0.0.1:54329/<db_temporal> \
  PREDICTS_ENV_FILE=/mnt/storage/project/predicts/.env \
  uv run predicts medir-mapeo
  ```
  (`<db_temporal>` migrada con `alembic upgrade head` y borrada después, para no tocar la base
  de desarrollo compartida — `sugerir()` persiste `decisiones_jev` y la corrida no hace
  `commit`, pero igual conviene una base descartable).

## Resultado

| Métrica | Valor |
|---|---|
| Archivos evaluados | 32 |
| Columnas evaluadas | 329 |
| **Acierto total** (todas las columnas, prellenadas o no) | **100,0 %** |
| % de columnas que quedó **prellenado** (confianza ≥ 0,8) | 97,6 % (321/329) |
| Acierto **del prellenado** (solo esas 321 columnas) | 100,0 % |
| Acierto de `producto_id_tipo` (32 datasets) | 100,0 % |
| Llamadas a Jev | 32 (una por dataset, `decidir_lote`) |
| Tokens Jev (entrada / salida) | 238.581 / 45.089 |
| Costo estimado | USD 0,00 — `PRECIOS_USD_POR_1K_TOKENS["jev"]` en `predicts/ia.py` es un placeholder en 0 porque TypeSafe todavía no publica precio por token; el costo real no es cero, solo no está modelado. Lo único medido con precisión acá es el conteo de tokens. |

Acierto por campo (las 329 columnas, incluyendo `ignorar`): **100,0 % en los 10 campos del
esquema interno y en `ignorar`** — ningún campo individual quedó por debajo del acierto total.

## Las columnas que no quedaron prellenadas

Las 8 columnas con confianza < 0,8 (2,4 % del total) son, las ocho, la **columna sin nombre**
(`con_columna_sin_nombre` del generador) de los 8 datasets con fuente `sintetico` que la tienen
(duckdb la nombra `columnN` al no tener encabezado). Jev la mandó a `ignorar` en las 8 — es
decir, **acertó igual, solo con menos confianza** (0,64–0,72): sin un encabezado que la
describa, y con valores de muestra que son solo un índice de fila (`0,1,2,...`), tiene menos
señal para decidir con seguridad que no es ningún campo del esquema. Es el comportamiento
esperado: pedirle a la persona que revise justo las columnas sin nombre, que son las más
ambiguas.

## Errores típicos

**No hubo ningún error en esta corrida** (0 columnas con `campo_sugerido != campo_esperado`,
sobre 329). Con un set de 32 CSVs cubriendo pt-BR/español/inglés/abreviado, mayúsculas,
columnas extra (sucursal, vendedor, forma de pago), columna sin nombre, IDs numéricos y
alfanuméricos, SKU y EAN válido, y los cuatro formatos de fecha de `deteccion.py`, Jev no se
confundió en ningún campo ni en `producto_id_tipo`. No hay "errores típicos" reales que
reportar todavía — si aparecen en corridas futuras con headers más ambiguos o dominios nuevos,
van acá.

## ¿`CONFIANZA_MAPEO = 0,8` es un buen umbral?

Con esta corrida, sí cumple el objetivo del PRD (**≥ 90 % de acierto**) con margen: el acierto
del prellenado es 100 % y el acierto total (incluyendo lo que queda en revisión) también es
100 %. El umbral de 0,8 no está dejando pasar ningún error al prellenado, pero tampoco está
siendo exigente de más: solo manda a revisar el 2,4 % de las columnas, y son exactamente las
que tiene sentido que una persona revise (las sin encabezado).

**Limitación de esta medición:** el set de 32 CSVs, aunque variado en formato (idioma,
mayúsculas, columnas extra, tipos de ID, formatos de fecha), tiene encabezados que —aun
abreviados o en otro idioma— siguen describiendo razonablemente el campo real (p. ej. "cli"
para cliente, "Cód. Prod." para producto). No incluye encabezados genuinamente ambiguos entre
dos campos del esquema (p. ej. una columna de texto libre que podría ser `producto_nombre` o
`categoria`) ni datos de dominios de negocio muy distintos al de compras retail. El 100 % de
acierto de esta corrida es real, pero probablemente optimista frente a CSVs de clientes reales
con encabezados más ambiguos o datos más sucios; vale la pena volver a correr
`predicts medir-mapeo` con mapeos corregidos por usuarios reales (ver `corregida_a` en
`decisiones_jev`) cuando haya un volumen razonable, para confirmar si 0,8 sigue siendo
suficiente fuera de este set sintético.

## Cómo reproducir

```bash
cd api
uv run python ../scripts/generar_desordenados.py   # regenera los 32 CSV + esperado.json

# base descartable, no la de desarrollo compartida:
uv run python -c "
import psycopg
c = psycopg.connect('postgresql://predicts:predicts@127.0.0.1:54329/postgres', autocommit=True)
c.execute('CREATE DATABASE predicts_medir_mapeo')
"
DATABASE_URL=postgresql+psycopg://predicts:predicts@127.0.0.1:54329/predicts_medir_mapeo \
  PREDICTS_ENV_FILE=/mnt/storage/project/predicts/.env uv run alembic upgrade head
DATABASE_URL=postgresql+psycopg://predicts:predicts@127.0.0.1:54329/predicts_medir_mapeo \
  PREDICTS_ENV_FILE=/mnt/storage/project/predicts/.env uv run predicts medir-mapeo

uv run python -c "
import psycopg
c = psycopg.connect('postgresql://predicts:predicts@127.0.0.1:54329/postgres', autocommit=True)
c.execute('DROP DATABASE predicts_medir_mapeo')
"
```
