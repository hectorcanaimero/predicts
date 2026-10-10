import { createFileRoute } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { ResultadosAnalisis } from '@/features/resultados/ResultadosAnalisis'

export const Route = createFileRoute('/_autenticado/analisis/$analisisId/')({
  component: ResultadosAnalisisRuta,
})

function ResultadosAnalisisRuta() {
  const { analisisId } = Route.useParams()
  const { t } = useTranslation('resultados')

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">{t('titulo')}</h1>
      <ResultadosAnalisis analisisId={analisisId} />
    </div>
  )
}
