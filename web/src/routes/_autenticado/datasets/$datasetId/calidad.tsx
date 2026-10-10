import { createFileRoute, Link } from '@tanstack/react-router'
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
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">{t('titulo')}</h1>
        <Link to="/datasets/$datasetId/agente" params={{ datasetId }} className="rounded-sm text-sm font-medium text-primary hover:underline">
          {t('agente:enlace')}
        </Link>
      </div>
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
