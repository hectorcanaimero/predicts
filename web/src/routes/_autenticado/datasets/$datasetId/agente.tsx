import { createFileRoute } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { EncabezadoPagina } from '@/components/layout/EncabezadoPagina'
import { ChatAgente } from '@/features/agente/ChatAgente'

export const Route = createFileRoute('/_autenticado/datasets/$datasetId/agente')({
  component: AgenteDatasetRuta,
})

function AgenteDatasetRuta() {
  const { datasetId } = Route.useParams()
  const { t } = useTranslation('agente')

  return (
    <div className="space-y-6">
      <EncabezadoPagina titulo={t('titulo')} descripcion={t('descripcion')} />
      <ChatAgente datasetId={datasetId} />
    </div>
  )
}
