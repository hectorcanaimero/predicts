import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { EncabezadoPagina } from '@/components/layout/EncabezadoPagina'
import { FlujoDatos } from '@/components/layout/FlujoDatos'
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
      <FlujoDatos actual="analizar" />
      <EncabezadoPagina titulo={t('nuevo.titulo')} descripcion={t('nuevo.descripcion')} />
      <SeleccionAnalisis
        datasetId={datasetId}
        onLanzado={(analisisId) => void navigate({ to: '/analisis/$analisisId/progreso', params: { analisisId } })}
      />
    </div>
  )
}
