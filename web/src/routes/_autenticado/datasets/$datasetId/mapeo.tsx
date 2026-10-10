import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { MapeoDataset } from '@/features/mapeo/MapeoDataset'

export const Route = createFileRoute('/_autenticado/datasets/$datasetId/mapeo')({
  component: MapeoDatasetRuta,
})

function MapeoDatasetRuta() {
  const { datasetId } = Route.useParams()
  const { t } = useTranslation('mapeo')
  const navigate = useNavigate()

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">{t('titulo')}</h1>
      <MapeoDataset
        datasetId={datasetId}
        onIngestaIniciada={(trabajoId) =>
          void navigate({
            to: '/datasets/$datasetId/calidad',
            params: { datasetId },
            search: { trabajoId },
          })
        }
      />
    </div>
  )
}
