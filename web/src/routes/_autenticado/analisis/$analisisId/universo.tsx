import { createFileRoute } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { VistaUniverso } from '@/tres/universo/VistaUniverso'

export const Route = createFileRoute('/_autenticado/analisis/$analisisId/universo')({
  component: UniversoRuta,
})

function UniversoRuta() {
  const { analisisId } = Route.useParams()
  const { t } = useTranslation('universo')

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">{t('titulo')}</h1>
      <VistaUniverso analisisId={analisisId} />
    </div>
  )
}
