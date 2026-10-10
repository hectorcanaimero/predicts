import { createFileRoute } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { ProgresoAnalisis } from '@/features/analisis/ProgresoAnalisis'

export const Route = createFileRoute('/_autenticado/analisis/$analisisId/progreso')({
  component: ProgresoAnalisisRuta,
})

function ProgresoAnalisisRuta() {
  const { analisisId } = Route.useParams()
  const { t } = useTranslation('analisis')

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">{t('progreso.titulo')}</h1>
      <ProgresoAnalisis
        analisisId={analisisId}
        // La ruta de resultados (`/analisis/$analisisId`) la crea F6.3.T2; navegación dura hasta
        // que exista como ruta tipada.
        onCompletado={(id) => window.location.assign(`/analisis/${id}`)}
      />
    </div>
  )
}
