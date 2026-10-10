import { CircleAlert, CircleCheck, Info, LoaderCircle } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { useEventosTrabajo } from '@/hooks/useEventosTrabajo'
import { GruposEquivalentes } from './GruposEquivalentes'
import { useCalidad } from './hooks'
import { InformeCalidadVista } from './InformeCalidadVista'
import { ProductosARevisar } from './ProductosARevisar'
import { ProgresoIngesta } from './ProgresoIngesta'

interface Props {
  datasetId: string
  trabajoId?: string
  onContinuarAnalisis?: () => void
}

function Alerta({ children }: { children: string }) {
  return (
    <p
      role="alert"
      className="flex items-start gap-2 rounded-xl border border-danger/20 bg-danger-soft p-4 text-sm font-medium text-danger"
    >
      <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
      {children}
    </p>
  )
}

/** Orquesta el progreso de la ingesta (SSE del `trabajoId` que devolvió `POST
 * /datasets/{id}/ingesta`, ver mapeo.tsx) y, una vez termina, el informe de calidad. Si no hay
 * `trabajoId` (se volvió a esta ruta directamente) se asume que la ingesta ya terminó y se va
 * directo a pedir el informe. */
export function CalidadDataset({ datasetId, trabajoId, onContinuarAnalisis }: Props) {
  const { t } = useTranslation('calidad')
  const { eventos, conexion } = useEventosTrabajo(trabajoId ?? null)
  const ultimoEvento = eventos[eventos.length - 1]
  const ingestaFallo = ultimoEvento?.etapa === 'error'
  const ingestaTerminada = !trabajoId || ultimoEvento?.etapa === 'listo'

  const calidad = useCalidad(datasetId, ingestaTerminada)
  const calidadNoDisponible = calidad.isError && calidad.error.codigo === 'calidad_no_disponible'
  // Dataset ya `listo` sin informe (p. ej. la demo, que se carga procesada): no va a llegar nunca.
  const sinInforme = calidadNoDisponible && calidad.error.parametros.estado === 'listo'
  const calidadNoDisponibleAun = calidadNoDisponible && !sinInforme
  const calidadOtroError = calidad.isError && !calidadNoDisponible

  return (
    <div className="space-y-8">
      {trabajoId && !ingestaTerminada && !ingestaFallo && <ProgresoIngesta eventos={eventos} conexion={conexion} />}

      {ingestaFallo && <Alerta>{t('progreso.error')}</Alerta>}

      {ingestaTerminada && !calidad.data && (calidad.isLoading || calidadNoDisponibleAun) && (
        <p
          aria-live="polite"
          className="flex items-center gap-2 rounded-xl border bg-card p-5 text-sm text-muted-foreground shadow-xs"
        >
          <LoaderCircle aria-hidden="true" className="size-4 animate-spin text-primary motion-reduce:animate-none" />
          {t('informe.procesando')}
        </p>
      )}

      {calidadOtroError && <Alerta>{t('error.titulo')}</Alerta>}

      {sinInforme && !calidad.data && (
        <div className="flex flex-col gap-4 rounded-xl border bg-card p-5 shadow-xs sm:flex-row sm:items-center">
          <p className="flex flex-1 items-start gap-2 text-sm text-muted-foreground">
            <Info aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-info" />
            {t('informe.sin_informe')}
          </p>
          <Button onClick={onContinuarAnalisis}>{t('acciones.continuar_analisis')}</Button>
        </div>
      )}

      {calidad.data && (
        <>
          <InformeCalidadVista informe={calidad.data} />
          <ProductosARevisar datasetId={datasetId} />
          <GruposEquivalentes />
          <div className="flex flex-col gap-4 rounded-xl border bg-accent/50 p-5 sm:flex-row sm:items-center">
            <p className="flex flex-1 items-center gap-2 text-sm font-medium text-accent-foreground">
              <CircleCheck aria-hidden="true" className="size-5 shrink-0" />
              {t('acciones.listo')}
            </p>
            <Button size="lg" onClick={onContinuarAnalisis}>
              {t('acciones.continuar_analisis')}
            </Button>
          </div>
        </>
      )}
    </div>
  )
}
