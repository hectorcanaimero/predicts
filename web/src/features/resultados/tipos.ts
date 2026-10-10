/** Tipos de la pestaña "Recordatorios/Ciclos/Riesgo/Ofertas": coinciden con las claves de
 * `_RESULTADOS` en `api/src/predicts/api/analisis.py`. */
export const TIPOS_RESULTADO = ['recompra', 'ciclos', 'riesgo', 'ofertas'] as const
export type TipoResultado = (typeof TIPOS_RESULTADO)[number]

/** Tipos válidos para `GET /analisis/{id}/exportar` (`predicts.exportar.TIPOS`). */
export const TIPOS_EXPORTAR = ['recordatorios', 'ofertas', 'riesgo'] as const
export type TipoExportar = (typeof TIPOS_EXPORTAR)[number]

export const SEPARADORES = [',', ';'] as const
export type Separador = (typeof SEPARADORES)[number]

export const TAM_PAGINA_DEFECTO = 20

/** Columnas válidas para `orden` en cada tipo (mismo orden que documenta
 * `api/src/predicts/api/analisis.py`); el selector de orden de cada pestaña solo ofrece estas,
 * así nunca se manda un `orden_invalido`. */
export const COLUMNAS_ORDEN: Record<TipoResultado, readonly string[]> = {
  recompra: [
    'cliente_id', 'producto_id', 'producto_nombre', 'ciclo', 'p', 'fecha_probable',
    'fecha_min', 'fecha_max', 'n_compras', 'dias_desde_ultima', 'posible_abandono', 'motivo',
  ], // fmt: skip
  ciclos: ['producto_id', 'producto_nombre', 'ciclo_mediano', 'dispersion', 'desvio_log', 'clientes_recurrentes'],
  riesgo: [
    'nivel', 'cliente_id', 'producto_id', 'producto_nombre', 'n_compras', 'ciclo',
    'dispersion', 'dias_desde_ultima', 'atraso', 'valor', 'motivo',
  ], // fmt: skip
  ofertas: [
    'cliente_id', 'producto_id', 'producto_nombre', 'puntaje', 'p_recompra', 'lift',
    'por_producto', 'descuento', 'fuentes', 'motivo',
  ], // fmt: skip
}

export const ORDEN_DEFECTO: Record<TipoResultado, string> = {
  recompra: '-p',
  ciclos: '-clientes_recurrentes',
  riesgo: '-valor',
  // "por cliente" (spec): a diferencia del resto, el orden inicial de esta pestaña agrupa por
  // cliente en vez del `-puntaje` que usa la API cuando no se manda `orden`.
  ofertas: 'cliente_id',
}

/** Filas de `resultados/*.parquet` (columnas documentadas en `analisis/recompra.py` et al.).
 * `mensaje`/`contactar` son opcionales: hoy la API de resultados no los incluye por fila (solo
 * el CSV exportado los junta desde `contactar.parquet` y las plantillas), pero la respuesta es
 * `additionalProperties: true` a propósito para poder agregarlos más adelante sin tocar el
 * front. */
export interface FilaRecompra {
  cliente_id: string
  producto_id: string
  producto_nombre: string | null
  ciclo: number
  p: number
  fecha_probable: string
  fecha_min: string
  fecha_max: string
  n_compras: number
  dias_desde_ultima: number
  posible_abandono: boolean
  motivo: string
  mensaje?: string | null
  contactar?: string | null
}

export interface FilaCiclos {
  producto_id: string
  producto_nombre: string | null
  ciclo_mediano: number
  dispersion: number
  desvio_log: number
  clientes_recurrentes: number
}

export interface FilaRiesgo {
  nivel: string
  cliente_id: string
  producto_id: string | null
  producto_nombre: string | null
  n_compras: number
  ciclo: number
  dispersion: number
  dias_desde_ultima: number
  atraso: number
  valor: number | null
  motivo: string
}

export interface FilaOfertas {
  cliente_id: string
  producto_id: string
  producto_nombre: string | null
  puntaje: number
  p_recompra: number | null
  lift: number | null
  por_producto: string | null
  descuento: number
  fuentes: string[]
  motivo: string
}

export interface ResultadosPagina<T> {
  pagina: number
  tam_pagina: number
  total: number
  resultados: T[]
}

/** `MetricasBacktest` de `api/src/predicts/modelo/backtest.py` (FR-16): modelo vs. línea base. */
export interface Tramo {
  desde: number
  hasta: number
  n: number
  predicho: number | null
  observado: number | null
}

export interface Estadistico {
  media: number | null
  desvio: number | null
}

export interface ResumenMetodo {
  precision_at_k: Estadistico
  cobertura_at_k: Estadistico
  brier: Estadistico
  mae_dias: Estadistico
  calibracion: Tramo[]
}

export interface MetricasBacktest {
  version_modelo: string
  semanas: number
  horizonte: number
  n_pares: number
  k: number | null
  modelo: ResumenMetodo
  linea_base: ResumenMetodo
}

export const METRICAS = ['precision_at_k', 'cobertura_at_k', 'brier', 'mae_dias'] as const
export type Metrica = (typeof METRICAS)[number]
