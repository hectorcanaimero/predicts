import { createFileRoute } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { ChatAgente } from '@/features/agente/ChatAgente'

export const Route = createFileRoute('/_autenticado/datasets/$datasetId/agente')({
  component: AgenteDatasetRuta,
})

function AgenteDatasetRuta() {
  const { datasetId } = Route.useParams()
  const { t } = useTranslation('agente')

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">{t('titulo')}</h1>
      <ChatAgente datasetId={datasetId} />
    </div>
  )
}
