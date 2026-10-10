import { Check, CircleAlert, LoaderCircle } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type { EventoTrabajo } from '@/hooks/useEventosTrabajo'
import { cn } from '@/lib/utils'

/** Orden de las etapas que emite `api/src/predicts/analisis/orquestador.py`. */
const ORDEN_ETAPAS = ['leyendo', 'ciclos', 'prediccion', 'riesgo', 'ofertas', 'contactar', 'backtest', 'mensajes', 'listo']

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

type EstadoPaso = 'completada' | 'en_curso' | 'pendiente' | 'error'

interface Props {
  etapas: string[]
  /** Última etapa recibida (`undefined` si todavía no llegó ningún evento). */
  actual: string | undefined
  /** La etapa en curso falló (evento `error`). */
  fallo: boolean
}

/** Stepper vertical con el estado de cada etapa; el estado también va en texto (no solo color). */
export function PasosAnalisis({ etapas, actual, fallo }: Props) {
  const { t } = useTranslation('panel')
  const indiceActual = actual ? etapas.indexOf(actual) : -1
  const terminado = actual === 'listo'

  function estado(i: number): EstadoPaso {
    if (terminado || i < indiceActual) return 'completada'
    if (i === Math.max(indiceActual, 0) && (actual || i === 0)) return fallo ? 'error' : 'en_curso'
    return 'pendiente'
  }

  return (
    <ol aria-label={t('progreso.pasos_aria')} className="space-y-0">
      {etapas.map((etapa, i) => {
        const e = estado(i)
        const ultima = i === etapas.length - 1
        return (
          <li key={etapa} aria-current={e === 'en_curso' ? 'step' : undefined} className="relative flex gap-3 pb-5 last:pb-0">
            {!ultima && (
              <span
                aria-hidden="true"
                className={cn(
                  'absolute left-3 top-7 -ml-px h-[calc(100%-1.75rem)] w-0.5',
                  e === 'completada' ? 'bg-primary' : 'bg-border',
                )}
              />
            )}
            <span
              aria-hidden="true"
              className={cn(
                'relative z-10 inline-flex size-6 shrink-0 items-center justify-center rounded-full border-2 text-xs',
                e === 'completada' && 'border-primary bg-primary text-primary-foreground',
                e === 'en_curso' && 'border-primary bg-card text-primary',
                e === 'pendiente' && 'border-border bg-card text-muted-foreground',
                e === 'error' && 'border-danger bg-danger-soft text-danger',
              )}
            >
              {e === 'completada' && <Check className="size-3.5" strokeWidth={3} />}
              {e === 'en_curso' && <LoaderCircle className="size-3.5 animate-spin motion-reduce:animate-none" />}
              {e === 'error' && <CircleAlert className="size-3.5" />}
              {e === 'pendiente' && <span className="size-1.5 rounded-full bg-border" />}
            </span>
            <div className="min-w-0 pt-0.5">
              <p
                className={cn(
                  'text-sm leading-tight',
                  e === 'pendiente' ? 'text-muted-foreground' : 'font-medium text-foreground',
                  e === 'error' && 'text-danger',
                )}
              >
                {t(`progreso.etapas.${etapa}`, { defaultValue: etapa })}
              </p>
              <p className="sr-only">{t(`progreso.estado_paso.${e === 'error' ? 'en_curso' : e}`)}</p>
            </div>
          </li>
        )
      })}
    </ol>
  )
}
