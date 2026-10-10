import { CAMPOS_OBLIGATORIOS, IGNORAR } from './tipos'

export interface ErrorValidacionMapeo {
  codigo: 'campo_duplicado' | 'campo_obligatorio_faltante'
  parametros: Record<string, unknown>
}

interface ColumnaMapeada {
  columna: string
  campo: string
}

/** Validación en vivo del mapeo (obligatorios, duplicados), espejo de la parte relevante de
 * `validar()` en `predicts.datos.mapeo`: lo que se puede comprobar sin ir al servidor mientras
 * la persona todavía está eligiendo. El resto (formato de fecha, tipo de identificador) ya está
 * acotado por las opciones que ofrecen los selectores. */
export function validarMapeoLocal(columnas: ColumnaMapeada[]): ErrorValidacionMapeo[] {
  const errores: ErrorValidacionMapeo[] = []
  const columnasPorCampo = new Map<string, string[]>()

  for (const { columna, campo } of columnas) {
    if (campo === IGNORAR) continue
    const lista = columnasPorCampo.get(campo) ?? []
    lista.push(columna)
    columnasPorCampo.set(campo, lista)
  }

  for (const [campo, cols] of columnasPorCampo) {
    if (cols.length > 1) errores.push({ codigo: 'campo_duplicado', parametros: { campo, columnas: cols } })
  }

  for (const campo of CAMPOS_OBLIGATORIOS) {
    if (!columnasPorCampo.has(campo)) {
      errores.push({ codigo: 'campo_obligatorio_faltante', parametros: { campo } })
    }
  }

  return errores
}
