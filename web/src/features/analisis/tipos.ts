/** Las 4 tarjetas de la pantalla "Elegir análisis" (spec F6.3.T1): `contactar` y `mensajes`
 * también son tipos válidos en la API, pero el backend los calcula o deriva solo, no se eligen
 * aquí. */
export const TARJETAS = ['recompra', 'ciclos', 'riesgo', 'ofertas'] as const
export type TipoTarjeta = (typeof TARJETAS)[number]

/** Mismos defaults que `ParametrosAnalisis` en `api/src/predicts/analisis/orquestador.py`: si el
 * campo queda en su default, se podría omitir y el backend los completa igual, pero mostrarlos
 * ya llenos es lo que pide la spec ("parámetros con valores por defecto"). */
export const PARAMETROS_DEFECTO = {
  minCompras: 3,
  horizonte: 7,
  umbral: 0.5,
}

export interface ParametrosFormulario {
  desde: string
  hasta: string
  minCompras: number
  horizonte: number
  umbral: number
}

export const PARAMETROS_FORM_INICIAL: ParametrosFormulario = {
  desde: '',
  hasta: '',
  minCompras: PARAMETROS_DEFECTO.minCompras,
  horizonte: PARAMETROS_DEFECTO.horizonte,
  umbral: PARAMETROS_DEFECTO.umbral,
}

/** Códigos de error de trabajo traducidos en esta pantalla (ver `trabajos/worker.py`). */
export const ERRORES_TRABAJO = ['memoria_excedida', 'tiempo_excedido', 'error_interno'] as const
