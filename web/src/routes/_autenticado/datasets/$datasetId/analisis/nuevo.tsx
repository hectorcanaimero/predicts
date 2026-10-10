import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { SeleccionAnalisis } from '@/features/analisis/SeleccionAnalisis'

export const Route = createFileRoute('/_autenticado/datasets/$datasetId/analisis/nuevo')({
  component: NuevoAnalisisRuta,
})

function NuevoAnalisisRuta() {
  const { datasetId } = Route.useParams()
  const { t } = useTranslation('analisis')
  const navigate = useNavigate()

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">{t('nuevo.titulo')}</h1>
      <SeleccionAnalisis
        datasetId={datasetId}
        onLanzado={(analisisId) =>
          void navigate({ to: '/analisis/$analisisId/progreso', params: { analisisId } })
        }
      />
    </div>
  )
}
