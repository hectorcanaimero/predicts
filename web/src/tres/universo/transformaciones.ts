import type { components } from '@/api/schema'

export type ClienteUniverso = components['schemas']['ClienteUniverso']
export type Estado = ClienteUniverso['estado']

export const ESTADOS: readonly Estado[] = ['activo', 'en_recompra', 'en_riesgo']

/** Color por estado (mismo criterio que `api/src/predicts/analisis/universo.py`): verde = sano,
 * ámbar = se acerca a su próxima compra, rojo = en riesgo de abandono. Hex plano (no `THREE.Color`)
 * para que esta función siga sin depender de three.js y se pueda testear sin WebGL. */
export const COLOR_ESTADO: Record<Estado, string> = {
  activo: '#22c55e',
  en_recompra: '#f59e0b',
  en_riesgo: '#ef4444',
}

/** Media distancia del cubo donde cae la nube de puntos (coordenadas en [-RANGO, RANGO]). */
const RANGO = 5

export interface PuntoUniverso {
  cliente_id: string
  estado: Estado
  grupo: number
  color: string
  /** [x, y, z] = [frecuencia, valor, recencia] normalizados a la propia muestra. */
  posicion: [number, number, number]
  frecuencia: number
  valor: number
  recencia: number
}

function minYMax(valores: number[]): [min: number, max: number] {
  let min = Infinity
  let max = -Infinity
  for (const v of valores) {
    if (v < min) min = v
    if (v > max) max = v
  }
  return [min, max]
}

function normalizar(valor: number, min: number, max: number): number {
  if (max === min) return 0
  return ((valor - min) / (max - min)) * (2 * RANGO) - RANGO
}

/** Mapea la muestra del universo (`GET /analisis/{id}/universo`, F8.2.T1) a posiciones 3D y
 * colores: cada eje se escala con min-max a la propia muestra (no hay un rango universal entre
 * análisis). Pura, sin three.js, para poder testearla sin montar el `Canvas`. */
export function clientesAPuntos(clientes: ClienteUniverso[]): PuntoUniverso[] {
  if (clientes.length === 0) return []

  const [minF, maxF] = minYMax(clientes.map((c) => c.frecuencia))
  const [minV, maxV] = minYMax(clientes.map((c) => c.valor))
  const [minR, maxR] = minYMax(clientes.map((c) => c.recencia))

  return clientes.map((c) => ({
    cliente_id: c.cliente_id,
    estado: c.estado,
    grupo: c.grupo,
    color: COLOR_ESTADO[c.estado],
    posicion: [
      normalizar(c.frecuencia, minF, maxF),
      normalizar(c.valor, minV, maxV),
      normalizar(c.recencia, minR, maxR),
    ],
    frecuencia: c.frecuencia,
    valor: c.valor,
    recencia: c.recencia,
  }))
}
