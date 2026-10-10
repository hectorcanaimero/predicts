/** Espejo de `predicts.datos.calidad.InformeCalidad`: `GET /datasets/{id}/calidad` devuelve un
 * `dict` suelto en el OpenAPI (no un schema propio), así que el tipo se mantiene a mano acá. */
export interface DistribucionComprasCliente {
  minimo: number
  maximo: number
  promedio: number
  mediana: number
}

export interface ParesConHistoria {
  total_pares: number
  con_historia_suficiente: number
  porcentaje: number
}

export interface Viabilidad {
  viable: boolean
  motivo: string | null
}

export interface InformeCalidad {
  filas: number
  clientes: number
  productos: number
  fecha_min: string | null
  fecha_max: string | null
  duplicados_exactos: number
  descartadas: Record<string, number>
  distribucion_compras_cliente: DistribucionComprasCliente
  pares: ParesConHistoria
  viabilidad: Record<string, Viabilidad>
}
