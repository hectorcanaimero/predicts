import { createFileRoute, Link } from '@tanstack/react-router'
import { Bot } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { EncabezadoPagina } from '@/components/layout/EncabezadoPagina'
import { FlujoDatos } from '@/components/layout/FlujoDatos'
import { Button } from '@/components/ui/button'
import { CalidadDataset } from '@/features/calidad/CalidadDataset'

interface BusquedaCalidad {
  trabajoId?: string
}

export const Route = createFileRoute('/_autenticado/datasets/$datasetId/calidad')({
  component: CalidadDatasetRuta,
  validateSearch: (busqueda: Record<string, unknown>): BusquedaCalidad => ({
    trabajoId: typeof busqueda.trabajoId === 'string' ? busqueda.trabajoId : undefined,
  }),
})

function CalidadDatasetRuta() {
  const { datasetId } = Route.useParams()
  const { trabajoId } = Route.useSearch()
  const { t } = useTranslation('calidad')

  return (
    <div className="space-y-8">
      <FlujoDatos actual="calidad" />
      <EncabezadoPagina
        titulo={t('titulo')}
        descripcion={t('descripcion')}
        acciones={
          <Button asChild variant="outline">
            <Link to="/datasets/$datasetId/agente" params={{ datasetId }}>
              <Bot aria-hidden="true" />
              {t('agente:enlace')}
            </Link>
          </Button>
        }
      />
      <CalidadDataset
        datasetId={datasetId}
        trabajoId={trabajoId}
        // La ruta de análisis (`/datasets/$datasetId/analisis/nuevo`) la crea F6.3; navegación
        // dura hasta que exista como ruta tipada.
        onContinuarAnalisis={() => window.location.assign(`/datasets/${datasetId}/analisis/nuevo`)}
      />
    </div>
  )
}
