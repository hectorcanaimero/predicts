# Spike del modelo de recompra — informe (F1.3.T2)

Medido el 2026-10-09 con `VERSION_MODELO = 0.1.0` y `ParamsModelo()` por defecto (k = 2,
`min_compras` = 3). Todas las cifras de este documento salen de las corridas listadas abajo; los
JSON completos quedaron en `DATA_DIR/spike/*.json` (fuera del repo).

## Cómo se midió

```bash
predicts sintetico --clientes 4100 --semilla 0 --salida $DATA_DIR/spike/sintetico_1m.parquet
predicts preparar-dataset online-retail --salida $DATA_DIR/spike/online_retail.parquet

# por cada dataset y H ∈ {7, 14}:
systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 \
  /usr/bin/time -v predicts backtest <compras.parquet> \
  --semanas 8 --horizonte H --repeticiones 4 --salida <dataset>_hH.json
```

- Corte = última fecha − 8 semanas; 4 ventanas consecutivas hacia atrás separadas por H días
  (no se solapan). "media ± desvío" = media y desvío muestral entre esas 4 ventanas.
- K = compradores reales de cada ventana (por eso precisión@K = cobertura@K).
- Población: los pares con ≥ 3 días de compra al corte (los que el modelo ajusta); la línea base
  se evalúa sobre los mismos pares. Detalle del método en `api/src/predicts/modelo/backtest.py`.
- DuckDB con la configuración por defecto (`memory_limit = 3GB`, `threads = 4`).

## Datos usados

| Dataset | Filas | Clientes | Productos | Fechas | Pares evaluados por ventana |
|---|---|---|---|---|---|
| Sintético (semilla 0) | 1.008.243 | 4.100 | 10 | 2022-01-01 .. 2025-01-01 | 20.227 |
| Online Retail II (completo) | 805.620 | 5.881 | 4.631 | 2009-12-01 .. 2011-12-09 | 41.994 – 46.338 |
| Instacart | — | — | — | — | **no medido** (ver Limitaciones) |

Recompra disponible: en el sintético el 69,7 % de los 29.006 pares tiene ≥ 3 días de compra; en
Online Retail II, solo el 11,3 % de 481.947 pares (54.695).

## Resultados

Tasa de compra = compradores / pares de la ventana. "Brier constante" = el Brier de predecir
siempre la tasa de la ventana (`tasa·(1 − tasa)`, media entre ventanas): la referencia mínima que
cualquier probabilidad debería batir.

### Sintético, 1 M de filas (cortes 2024-11-06 hacia atrás)

| H | Métrica | Modelo | Línea base |
|---|---|---|---|
| 7 | precisión@K = cobertura@K | 0,7333 ± 0,0038 | 0,5733 ± 0,0017 |
| 7 | Brier | 0,1021 ± 0,0010 | 0,1945 ± 0,0024 |
| 7 | error en días (compradores) | 2,68 ± 0,04 | 4,01 ± 0,05 |
| 14 | precisión@K = cobertura@K | 0,8704 ± 0,0016 | 0,7798 ± 0,0023 |
| 14 | Brier | 0,0907 ± 0,0004 | 0,1928 ± 0,0008 |
| 14 | error en días (compradores) | 3,02 ± 0,03 | 4,10 ± 0,06 |

Tasa de compra: 0,28 (H = 7) y 0,51 (H = 14); Brier constante 0,2025 y 0,2499.

### Online Retail II completo (cortes 2011-10-14 hacia atrás)

| H | Métrica | Modelo | Línea base |
|---|---|---|---|
| 7 | precisión@K = cobertura@K | 0,1526 ± 0,0139 | 0,1088 ± 0,0350 |
| 7 | Brier | 0,0354 ± 0,0013 | 0,0539 ± 0,0017 |
| 7 | error en días (compradores) | 38,8 ± 1,6 | 66,9 ± 5,6 |
| 14 | precisión@K = cobertura@K | 0,2238 ± 0,0111 | 0,1531 ± 0,0212 |
| 14 | Brier | 0,0677 ± 0,0022 | 0,1006 ± 0,0039 |
| 14 | error en días (compradores) | 37,3 ± 1,6 | 69,1 ± 1,2 |

Tasa de compra: 0,034–0,037 (H = 7) y 0,064–0,071 (H = 14); Brier constante 0,0336 y 0,0627.
**El Brier del modelo (0,0354 / 0,0677) es peor que el de la constante**: ordena bien, pero sus
probabilidades están infladas (ver calibración).

### Tiempo y memoria pico

Cada corrida = 4 ventanas (4 ajustes + predicción + línea base), medido con `/usr/bin/time -v`
bajo `MemoryMax=4G`, incluye el arranque de Python.

| Dataset | H | Tiempo (wall) | Memoria pico (RSS) |
|---|---|---|---|
| Sintético 1 M | 7 | 3,38 s | 595 MB |
| Sintético 1 M | 14 | 3,38 s | 549 MB |
| Online Retail II | 7 | 2,99 s | 434 MB |
| Online Retail II | 14 | 2,96 s | 450 MB |

Ninguna corrida se acercó al límite de 4 GB.

## Calibración (tramos fijos de `p`, las 4 ventanas agrupadas)

`n` = pares; `pred` = `p` medio; `obs` = fracción que compró. La línea base solo tiene dos tramos
(p = 0 y p = 1).

### Sintético

| Tramo | H=7 n | pred | obs | H=14 n | pred | obs |
|---|---|---|---|---|---|---|
| [0,0, 0,1) | 41.010 | 0,011 | 0,018 | 26.362 | 0,009 | 0,015 |
| [0,1, 0,2) | 5.166 | 0,147 | 0,193 | 3.092 | 0,150 | 0,196 |
| [0,2, 0,3) | 4.728 | 0,247 | 0,292 | 2.660 | 0,251 | 0,294 |
| [0,3, 0,4) | 4.686 | 0,353 | 0,394 | 2.850 | 0,351 | 0,403 |
| [0,4, 0,5) | 5.090 | 0,464 | 0,492 | 3.157 | 0,456 | 0,491 |
| [0,5, 0,6) | 3.410 | 0,556 | 0,567 | 3.473 | 0,558 | 0,592 |
| [0,6, 0,7) | 4.237 | 0,646 | 0,668 | 4.179 | 0,656 | 0,658 |
| [0,7, 0,8) | 5.127 | 0,751 | 0,775 | 5.712 | 0,753 | 0,765 |
| [0,8, 0,9) | 5.395 | 0,848 | 0,865 | 8.327 | 0,854 | 0,864 |
| [0,9, 1,0] | 2.059 | 0,924 | 0,949 | 21.096 | 0,957 | 0,966 |
| línea base p=0 | 63.714 | 0 | 0,168 | 44.401 | 0 | 0,229 |
| línea base p=1 | 17.194 | 1 | 0,706 | 36.507 | 1 | 0,851 |

Bien calibrado; levemente conservador en los tramos bajos (predice 0,15, ocurre 0,19).

### Online Retail II

| Tramo | H=7 n | pred | obs | H=14 n | pred | obs |
|---|---|---|---|---|---|---|
| [0,0, 0,1) | 145.699 | 0,039 | 0,025 | 86.311 | 0,040 | 0,037 |
| [0,1, 0,2) | 27.923 | 0,134 | 0,060 | 57.308 | 0,142 | 0,064 |
| [0,2, 0,3) | 4.778 | 0,240 | 0,126 | 20.371 | 0,241 | 0,111 |
| [0,3, 0,4) | 1.404 | 0,342 | 0,179 | 7.068 | 0,342 | 0,173 |
| [0,4, 0,5) | 466 | 0,442 | 0,185 | 2.829 | 0,443 | 0,241 |
| [0,5, 0,6) | 200 | 0,549 | 0,205 | 1.268 | 0,545 | 0,289 |
| [0,6, 0,7) | 111 | 0,642 | 0,216 | 673 | 0,644 | 0,324 |
| [0,7, 0,8) | 47 | 0,748 | 0,447 | 326 | 0,744 | 0,387 |
| [0,8, 0,9) | 37 | 0,843 | 0,297 | 184 | 0,843 | 0,364 |
| [0,9, 1,0] | 29 | 0,963 | 0,483 | 118 | 0,955 | 0,475 |
| línea base p=0 | 175.971 | 0 | 0,032 | 167.275 | 0 | 0,061 |
| línea base p=1 | 4.723 | 1 | 0,136 | 9.181 | 1 | 0,179 |

Monótono (más `p` → más compra) pero **sobreconfiado ≈ 2×** de 0,1 para arriba: lo que el modelo
llama 0,44 ocurre 0,19–0,24 veces.

## Ejemplos concretos (ventana más reciente, H = 14)

Columnas: par, días de compra al corte, ciclo estimado (días), `p` modelo, fecha probable,
predicción de la línea base (0/1), primera compra real en la ventana.

**Sintético** (corte 2024-11-06, ventana hasta 2024-11-20):

- Bien: `cliente-03071 / producto-003` — 147 compras, ciclo 7,1, p = 0,99, probable 11-09; compró
  el 11-09 (base también acierta: 1).
- Bien donde la base falla: `cliente-03360 / producto-008` — 64 compras, ciclo 17,1, p = 0,37; la
  base dice 1 (próxima compra 11-20) y no compró. En los 1.365 pares donde la base dijo 1 y no
  hubo compra, el modelo dio p medio 0,706: también ahí se equivoca, pero con menos confianza.
- Mal (falso positivo confiado): `cliente-01188 / producto-003` — 110 compras, ciclo 9,0,
  p = 0,988; no compró en la ventana. La verdad del generador: ciclo real 9,9 y sin abandono, o sea
  un intervalo largo por azar (cola de la log-normal), no un error de método.
- Mal (compra sorpresa): `cliente-00538 / producto-004` — ciclo 30,1, última compra 11-04,
  p = 0,006; volvió a comprar el 11-20 (16 días después, la mitad de su ciclo real de 31,4).

**Online Retail II** (corte 2011-10-14, ventana hasta 2011-10-28):

- Bien: cliente `14096`, producto `DOT` — 8 compras, ciclo 7,0, p = 0,99; compró el 10-17.
- Bien donde la base falla: cliente `14096`, producto `21055` — 3 compras, ciclo 45,8, p ≈ 0,
  probable 11-25; la base, con el par "vencido", dice 1 (10-17). No compró. En los 2.079 pares
  donde la base dijo 1 y no hubo compra, el modelo dio p medio 0,247.
- Mal (falso positivo confiado): cliente `17509`, producto `23502` — 3 compras, ciclo 3,0,
  p = 0,985; no compró. Con 3 compras (2 intervalos) y ciclo de 3 días el modelo se juega todo a
  una ráfaga de pedidos que no se repitió.
- Mal (compra sorpresa): cliente `16549`, producto `21733` — 12 compras, ciclo 20,8, p ≈ 0 (la base
  ubicaba la próxima compra en 2010-11-21: el par llevaba ~11 meses dormido); compró el
  2011-10-25. Reactivación estacional (el mismo cliente reactivó otros pares — `21166`, `82583` — el
  mismo día): el modelo lo da por abandonado.

## Limitaciones

- **Instacart no se midió.** El dataset solo se descarga desde Kaggle con cuenta y aceptando las
  reglas de la competencia; F1.1.T2 no encontró un espejo sin login con licencia clara
  (`docs/notas/datasets.md`) y este entorno no tiene credenciales de Kaggle. El preparador
  (`predicts preparar-dataset instacart --desde <carpeta>`) está listo: con los CSV en disco, las
  mismas dos corridas completan la tabla. Aun medido, sus **fechas son sintéticas** (fecha base +
  suma de `days_since_prior_order`, que además está topeado en 30 días): sirve para medir
  intervalos, no estacionalidad ni fechas de calendario.
- **Poca recompra en Online Retail II:** solo el 11,3 % de los pares tiene ≥ 3 días de compra, y
  la tasa de compra en la ventana es 3–7 %. Es un mayorista de regalos: compras por temporada, no
  consumo periódico. Las ventanas medidas (sep–oct 2011) son la previa navideña, donde reactivan
  pares dormidos.
- **El sintético es fácil a propósito:** 10 productos, ciclos log-normales — exactamente la
  familia que el modelo supone. Confirma que el método recupera lo que debe, no que funcione en
  datos reales.
- Un solo juego de parámetros (`ParamsModelo()` por defecto) y `--semanas 8` fijo; no se buscó
  el mejor `k` ni otros cortes.
- El error en días de Online Retail (~38 días) se mide sobre quienes compraron, que incluyen las
  reactivaciones: el modelo había puesto su fecha probable muy lejos.

## Recomendación: **seguir, con un ajuste de calibración antes de mostrar `p` al usuario**

El modelo supera a la línea base en todas las métricas, en ambos datasets y horizontes, con
desvíos entre ventanas mucho menores que las diferencias (p. ej. Online Retail H = 14: precisión
0,224 ± 0,011 vs. 0,153 ± 0,021; Brier 0,068 vs. 0,101). El gate de F1 ("el modelo supera a la
línea base") **se cumple**: no hace falta cambiar de método, y F4+ pueden avanzar.

Ajustar (como tarea propia, sube `VERSION_MODELO`):

1. **Calibrar `p` contra los datos de cada dataset.** En Online Retail las probabilidades están
   ≈ 2× infladas y el Brier no bate a la constante. La log-normal condicional supone que el par
   sigue activo; falta multiplicarla por una probabilidad de "par vivo". Lo más barato: recalibrar
   (isotónica o Platt) con las ventanas de backtest anteriores al corte, que ya se calculan; luego
   reemplazarlo por un término explícito de actividad (recencia del par vs. su historia y tasa
   real de recompra del producto) si la recalibración no generaliza entre ventanas.
2. **Pares con 2 intervalos:** el falso positivo típico en Online Retail tiene 3 compras y un
   ciclo muy corto. Probar `k` más alto (más peso al producto) o `min_compras = 4` y medir con el
   mismo `predicts backtest`.
3. **Reactivación estacional:** hoy un par dormido recibe p ≈ 0. No arreglar en el modelo todavía;
   documentarlo en la UI como "posible reactivación" cuando haya datos de más de un año.

Antes de cerrar el ajuste 1, correr Instacart (con los CSV en `--desde`) para tener un dataset real
de consumo periódico, que es el caso de uso de predicts.
