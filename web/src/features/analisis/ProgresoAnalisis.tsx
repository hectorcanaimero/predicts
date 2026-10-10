import { CircleAlert, CircleCheck, LoaderCircle } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { useEventosTrabajo } from '@/hooks/useEventosTrabajo'
import { useAnalisis, useCancelarTrabajo, useTrabajo } from './hooks'
import { etapasDelAnalisis } from './etapas'
import { PasosAnalisis } from './PasosAnalisis'
import { ERRORES_TRABAJO } from './tipos'
import { VistaProcesamiento } from './VistaProcesamiento'

interface Props {
  analisisId: string
  onCompletado: (analisisId: string) => void
}

/** Sigue un análisis ya lanzado: etapas (stepper), barra de avance, contadores de la última
 * etapa, la escena 3D si el usuario no pidió menos movimiento, cancelar y el error traducido del
 * trabajo cuando termina mal. Pasa solo a resultados cuando el análisis queda `listo` (por el SSE
 * o, si se perdió la conexión, por el sondeo de `useAnalisis`). */
export function ProgresoAnalisis({ analisisId, onCompletado }: Props) {
  const { t, i18n } = useTranslation('analisis')
  const analisis = useAnalisis(analisisId)
  const trabajoId = analisis.data?.trabajo_id ?? null
  const [cancelado, setCancelado] = useState(false)
  const { eventos, conexion } = useEventosTrabajo(cancelado ? null : trabajoId)
  const ultimo = eventos[eventos.length - 1]
  const etapaError = ultimo?.etapa === 'error'
  const listo = ultimo?.etapa === 'listo' || analisis.data?.estado === 'listo'
  const terminado = cancelado || etapaError || listo

  const trabajo = useTrabajo(trabajoId, etapaError)
  const cancelar = useCancelarTrabajo()

  const yaCompletado = useRef(false)
  useEffect(() => {
    if (listo && !yaCompletado.current) {
      yaCompletado.current = true
      onCompletado(analisisId)
    }
  }, [listo, analisisId, onCompletado])

  const codigoError = trabajo.data?.error_codigo
  const claveTraduccionError =
    codigoError && (ERRORES_TRABAJO as readonly string[]).includes(codigoError) ? codigoError : 'error_interno'

  const eventosEtapa = eventos.filter((evento) => evento.etapa !== 'error')
  const etapaActual = listo ? 'listo' : eventosEtapa[eventosEtapa.length - 1]?.etapa
  const etapas = etapasDelAnalisis(analisis.data?.tipos, eventosEtapa)
  const indice = etapaActual ? etapas.indexOf(etapaActual) : -1
  const avance = listo ? 1 : (ultimo?.progreso ?? (indice >= 0 ? indice / Math.max(1, etapas.length - 1) : 0))
  const porcentaje = Math.round(Math.min(1, Math.max(0, avance)) * 100)
  const contadores = Object.entries(eventosEtapa[eventosEtapa.length - 1]?.contadores ?? {})
  const numero = new Intl.NumberFormat(i18n.language)

  let estadoTexto: string
  if (listo) estadoTexto = t('panel:progreso.listo')
  else if (cancelado) estadoTexto = t('progreso.cancelado')
  else if (etapaActual)
    estadoTexto = t('panel:progreso.en_curso', {
      etapa: t(`panel:progreso.etapas.${etapaActual}`, { defaultValue: etapaActual }),
    })
  else estadoTexto = conexion === 'conectando' ? t('progreso.conectando') : t('panel:progreso.esperando')

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_18rem]">
      <section className="space-y-6 rounded-xl border bg-card p-5 shadow-xs sm:p-6">
        <div className="flex items-start justify-between gap-4">
          <p aria-live="polite" className="flex items-center gap-2 text-sm font-medium">
            {listo ? (
              <CircleCheck aria-hidden="true" className="size-4 text-success" />
            ) : etapaError ? (
              <CircleAlert aria-hidden="true" className="size-4 text-danger" />
            ) : (
              !cancelado && (
                <LoaderCircle
                  aria-hidden="true"
                  className="size-4 animate-spin text-primary motion-reduce:animate-none"
                />
              )
            )}
            {estadoTexto}
          </p>
          <span className="whitespace-nowrap text-2xl font-semibold tracking-tight tabular">
            {t('panel:progreso.porcentaje', { valor: porcentaje })}
          </span>
        </div>

        <Progress value={porcentaje} aria-label={t('panel:progreso.avance')} className="h-2.5" />

        {contadores.length > 0 && (
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {contadores.map(([clave, valor]) => (
              <div key={clave} className="rounded-lg bg-muted/60 px-3 py-2.5">
                <dt className="text-xs text-muted-foreground">
                  {t(`panel:progreso.contadores.${clave}`, { defaultValue: clave })}
                </dt>
                <dd className="mt-0.5 text-lg font-semibold tabular">{numero.format(valor)}</dd>
              </div>
            ))}
          </dl>
        )}

        <div className="overflow-hidden rounded-lg empty:hidden">
          <VistaProcesamiento eventos={eventos} conexion={conexion} soloEscena />
        </div>

        {etapaError && (
          <p
            role="alert"
            className="flex items-start gap-2 rounded-md border border-danger/20 bg-danger-soft px-3 py-2.5 text-sm text-danger"
          >
            <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
            {t(`progreso.errores.${claveTraduccionError}`)}
          </p>
        )}

        <div className="flex justify-end border-t pt-4">
          <Button
            variant="outline"
            disabled={!trabajoId || terminado}
            onClick={() => trabajoId && cancelar.mutate(trabajoId, { onSuccess: () => setCancelado(true) })}
          >
            {t('progreso.acciones.cancelar')}
          </Button>
        </div>
      </section>

      <aside className="rounded-xl border bg-card p-5 shadow-xs">
        <h2 className="mb-4 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {t('panel:progreso.pasos_aria')}
        </h2>
        <PasosAnalisis etapas={etapas} actual={etapaActual} fallo={etapaError} />
      </aside>
    </div>
  )
}
