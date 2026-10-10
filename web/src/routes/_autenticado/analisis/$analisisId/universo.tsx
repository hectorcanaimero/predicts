import { createFileRoute, Link } from '@tanstack/react-router'
import { ArrowLeft } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { EncabezadoPagina } from '@/components/layout/EncabezadoPagina'
import { Button } from '@/components/ui/button'
import { VistaUniverso } from '@/tres/universo/VistaUniverso'

export const Route = createFileRoute('/_autenticado/analisis/$analisisId/universo')({
  component: UniversoRuta,
})

function UniversoRuta() {
  const { analisisId } = Route.useParams()
  const { t } = useTranslation('universo')

  return (
    <div className="space-y-8">
      <EncabezadoPagina
        titulo={t('titulo')}
        descripcion={t('descripcion')}
        acciones={
          <Button asChild variant="outline">
            <Link to="/analisis/$analisisId" params={{ analisisId }}>
              <ArrowLeft aria-hidden="true" />
              {t('layout:nav.resultados')}
            </Link>
          </Button>
        }
      />
      <VistaUniverso analisisId={analisisId} />
    </div>
  )
}
