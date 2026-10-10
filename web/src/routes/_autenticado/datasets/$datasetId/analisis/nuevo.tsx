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
    <div className="space-y-8">
      <h1 className="text-2xl font-semibold tracking-tight">{t('nuevo.titulo')}</h1>
      <SeleccionAnalisis
        datasetId={datasetId}
        onLanzado={(analisisId) =>
          void navigate({ to: '/analisis/$analisisId/progreso', params: { analisisId } })
        }
      />
    </div>
  )
}
