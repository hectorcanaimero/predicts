import { createFileRoute } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { EncabezadoPagina } from '@/components/layout/EncabezadoPagina'
import { ProgresoAnalisis } from '@/features/analisis/ProgresoAnalisis'

export const Route = createFileRoute('/_autenticado/analisis/$analisisId/progreso')({
  component: ProgresoAnalisisRuta,
})

function ProgresoAnalisisRuta() {
  const { analisisId } = Route.useParams()
  const { t } = useTranslation('panel')

  return (
    <div className="space-y-8">
      <EncabezadoPagina titulo={t('progreso.titulo')} descripcion={t('progreso.descripcion')} />
      <ProgresoAnalisis
        analisisId={analisisId}
        // La ruta de resultados (`/analisis/$analisisId`) la crea F6.3.T2; navegación dura hasta
        // que exista como ruta tipada.
        onCompletado={(id) => window.location.assign(`/analisis/${id}`)}
      />
    </div>
  )
}
