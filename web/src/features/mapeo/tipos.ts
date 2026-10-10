/** Espejo de `predicts.datos.deteccion` (API): `DatasetSalida.deteccion` es un `dict` suelto
 * en el OpenAPI (no un schema propio), así que el tipo se mantiene a mano acá. */
export interface CandidatoFecha {
  formato: string
  porcentaje: number
}

export interface ColumnaDeteccion {
  nombre: string
  tipo: string
  porcentaje_nulos: number
  valores_muestra: string[]
  candidatos_fecha: CandidatoFecha[]
  separador_decimal: 'coma' | 'punto' | null
}

export interface Deteccion {
  codificacion: string
  separador: string
  encabezado: boolean
  columnas: ColumnaDeteccion[]
  vista_previa: Record<string, string | null>[]
}

/** Campos del esquema interno elegibles para una columna (espejo de `CAMPOS_ESQUEMA` en
 * `predicts.datos.mapeo`); cada uno tiene su etiqueta en `mapeo:campos.<campo>`. */
export const CAMPOS_ESQUEMA = [
  'cliente_id',
  'fecha',
  'producto_id',
  'producto_nombre',
  'pedido_id',
  'cantidad',
  'precio_unitario',
  'valor_total',
  'categoria',
  'marca',
] as const

export type CampoEsquema = (typeof CAMPOS_ESQUEMA)[number]

export const IGNORAR = 'ignorar'

/** Campos obligatorios del mapeo (espejo de `_CAMPOS_OBLIGATORIOS` en `predicts.datos.mapeo`,
 * sin `producto_id_tipo`: ese se valida aparte). */
export const CAMPOS_OBLIGATORIOS: readonly CampoEsquema[] = ['cliente_id', 'fecha', 'producto_id']

/** Umbral de confianza para la insignia "sugerido"/"revisar" del tipo de identificador de
 * producto (espejo de `Settings.CONFIANZA_MAPEO`, default `0.8`; no viene por la API). */
export const UMBRAL_CONFIANZA_MAPEO = 0.8
