import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { EncabezadoPagina } from '@/components/layout/EncabezadoPagina'
import { FlujoDatos } from '@/components/layout/FlujoDatos'
import { MapeoDataset } from '@/features/mapeo/MapeoDataset'

export const Route = createFileRoute('/_autenticado/datasets/$datasetId/mapeo')({
  component: MapeoDatasetRuta,
})

function MapeoDatasetRuta() {
  const { datasetId } = Route.useParams()
  const { t } = useTranslation('mapeo')
  const navigate = useNavigate()

  return (
    <div className="space-y-8">
      <FlujoDatos actual="mapear" />
      <EncabezadoPagina titulo={t('titulo')} descripcion={t('descripcion')} />
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
