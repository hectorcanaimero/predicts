import { createFileRoute, Link } from '@tanstack/react-router'
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
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">{t('titulo')}</h1>
        {/* Pestaña "Universo" (F8.2.T2): `ResultadosAnalisis` (F6.3.T2) no tiene un punto de
         * extensión para pestañas externas, así que el enlace vive en el detalle del análisis. */}
        <Link to="/analisis/$analisisId/universo" params={{ analisisId }} className="text-sm underline">
          {t('universo:enlace')}
        </Link>
      </div>
      <ResultadosAnalisis analisisId={analisisId} />
    </div>
  )
}
