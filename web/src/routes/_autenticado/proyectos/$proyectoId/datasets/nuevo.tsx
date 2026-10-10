import { createFileRoute, Link } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { ZonaSubida } from '@/features/subir/ZonaSubida'

export const Route = createFileRoute('/_autenticado/proyectos/$proyectoId/datasets/nuevo')({
  component: NuevoDataset,
})

function NuevoDataset() {
  const { proyectoId } = Route.useParams()
  const { t } = useTranslation('subir')

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-semibold tracking-tight">{t('titulo')}</h1>
      <ZonaSubida
        proyectoId={proyectoId}
        // La ruta de mapeo (`/datasets/$datasetId/mapeo`) la crea F6.2.T2; navegación dura hasta
        // que exista como ruta tipada.
        onSubido={(datasetId) => window.location.assign(`/datasets/${datasetId}/mapeo`)}
      />
      <Link to="/proyectos/$proyectoId" params={{ proyectoId }} className="rounded-sm text-sm font-medium text-primary hover:underline">
        {t('volver')}
      </Link>
    </div>
  )
}
