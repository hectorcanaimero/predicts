import { createFileRoute, Link } from '@tanstack/react-router'
import { Bot, Orbit } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { EncabezadoPagina } from '@/components/layout/EncabezadoPagina'
import { Button } from '@/components/ui/button'
import { useAnalisis } from '@/features/resultados/hooks'
import { ResultadosAnalisis } from '@/features/resultados/ResultadosAnalisis'

export const Route = createFileRoute('/_autenticado/analisis/$analisisId/')({
  component: ResultadosAnalisisRuta,
})

function ResultadosAnalisisRuta() {
  const { analisisId } = Route.useParams()
  const { t } = useTranslation('resultados')
  const analisis = useAnalisis(analisisId)
  const datos = analisis.data
  const fecha = typeof datos?.resumen?.fecha_ref === 'string' ? datos.resumen.fecha_ref : null
  const version = datos?.version_modelo ?? '—'

  return (
    <div className="space-y-8">
      <EncabezadoPagina
        titulo={t('titulo')}
        descripcion={
          datos
            ? fecha
              ? t('panel:resultados.descripcion', { fecha, version })
              : t('panel:resultados.descripcion_sin_fecha', { version })
            : undefined
        }
        acciones={
          <>
            {/* "Universo" (F8.2.T2) vive como pantalla aparte: `ResultadosAnalisis` no tiene
             * punto de extensión para pestañas externas. */}
            <Button asChild variant="outline">
              <Link to="/analisis/$analisisId/universo" params={{ analisisId }}>
                <Orbit aria-hidden="true" />
                {t('panel:resultados.universo')}
              </Link>
            </Button>
            {datos && (
              <Button asChild>
                <Link to="/datasets/$datasetId/agente" params={{ datasetId: datos.dataset_id }}>
                  <Bot aria-hidden="true" />
                  {t('panel:resultados.agente')}
                </Link>
              </Button>
            )}
          </>
        }
      />
      <ResultadosAnalisis analisisId={analisisId} />
    </div>
  )
}
