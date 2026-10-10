import { createFileRoute } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { CalidadDataset } from '@/features/calidad/CalidadDataset'

interface BusquedaCalidad {
  trabajoId?: string
}

export const Route = createFileRoute('/_autenticado/datasets/$datasetId/calidad')({
  component: CalidadDatasetRuta,
  validateSearch: (busqueda: Record<string, unknown>): BusquedaCalidad => ({
    trabajoId: typeof busqueda.trabajoId === 'string' ? busqueda.trabajoId : undefined,
  }),
})

function CalidadDatasetRuta() {
  const { datasetId } = Route.useParams()
  const { trabajoId } = Route.useSearch()
  const { t } = useTranslation('calidad')

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">{t('titulo')}</h1>
      <CalidadDataset
        datasetId={datasetId}
        trabajoId={trabajoId}
        // La ruta de análisis (`/datasets/$datasetId/analisis/nuevo`) la crea F6.3; navegación
        // dura hasta que exista como ruta tipada.
        onContinuarAnalisis={() => window.location.assign(`/datasets/${datasetId}/analisis/nuevo`)}
      />
    </div>
  )
}
