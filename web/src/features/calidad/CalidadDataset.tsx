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
  const calidadNoDisponibleAun = calidad.isError && calidad.error.codigo === 'calidad_no_disponible'
  const calidadOtroError = calidad.isError && !calidadNoDisponibleAun

  return (
    <div className="space-y-8">
      {trabajoId && !ingestaTerminada && <ProgresoIngesta eventos={eventos} conexion={conexion} />}

      {ingestaFallo && (
        <p role="alert" className="text-sm text-destructive">
          {t('progreso.error')}
        </p>
      )}

      {ingestaTerminada && !calidad.data && (calidad.isLoading || calidadNoDisponibleAun) && (
        <p className="text-muted-foreground">{t('informe.procesando')}</p>
      )}

      {calidadOtroError && (
        <p role="alert" className="text-sm text-destructive">
          {t('error.titulo')}
        </p>
      )}

      {calidad.data && (
        <>
          <InformeCalidadVista informe={calidad.data} />
          <ProductosARevisar datasetId={datasetId} />
          <GruposEquivalentes />
          <Button onClick={onContinuarAnalisis}>{t('acciones.continuar_analisis')}</Button>
        </>
      )}
    </div>
  )
}
