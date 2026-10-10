import type { EventoTrabajo } from '@/hooks/useEventosTrabajo'

/** Orden de las etapas que emite `api/src/predicts/analisis/orquestador.py`. */
const ORDEN_ETAPAS = [
  'leyendo',
  'ciclos',
  'prediccion',
  'riesgo',
  'ofertas',
  'contactar',
  'backtest',
  'mensajes',
  'listo',
]

/** Etapas esperables para los tipos pedidos (más cualquiera que ya haya llegado por SSE, por
 * si el orquestador agrega una que acá no se previó). */
export function etapasDelAnalisis(tipos: readonly string[] | undefined, eventos: EventoTrabajo[]): string[] {
  const vistas = new Set(eventos.map((evento) => evento.etapa))
  const pedidos = new Set(tipos ?? [])
  return ORDEN_ETAPAS.filter((etapa) => {
    if (etapa === 'leyendo' || etapa === 'listo' || vistas.has(etapa)) return true
    if (!tipos) return false
    if (etapa === 'prediccion' || etapa === 'backtest') return pedidos.has('recompra')
    return pedidos.has(etapa)
  })
}
