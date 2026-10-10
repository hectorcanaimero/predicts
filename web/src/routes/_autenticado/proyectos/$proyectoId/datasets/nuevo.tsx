import { createFileRoute, Link } from '@tanstack/react-router'
import { ArrowLeft, Check } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { EncabezadoPagina } from '@/components/layout/EncabezadoPagina'
import { FlujoDatos } from '@/components/layout/FlujoDatos'
import { ZonaSubida } from '@/features/subir/ZonaSubida'

export const Route = createFileRoute('/_autenticado/proyectos/$proyectoId/datasets/nuevo')({
  component: NuevoDataset,
})

const REQUISITOS = ['cliente', 'fecha', 'producto', 'opcional'] as const

function NuevoDataset() {
  const { proyectoId } = Route.useParams()
  const { t } = useTranslation('subir')

  return (
    <div className="space-y-8">
      <FlujoDatos actual="subir" />
      <EncabezadoPagina titulo={t('titulo')} descripcion={t('descripcion')} />
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <ZonaSubida
          proyectoId={proyectoId}
          // La ruta de mapeo (`/datasets/$datasetId/mapeo`) la crea F6.2.T2; navegación dura hasta
          // que exista como ruta tipada.
          onSubido={(datasetId) => window.location.assign(`/datasets/${datasetId}/mapeo`)}
        />
        <aside className="rounded-xl border bg-card p-5 shadow-xs">
          <h2 className="text-sm font-semibold">{t('requisitos.titulo')}</h2>
          <ul className="mt-3 space-y-2.5 text-sm">
            {REQUISITOS.map((clave) => {
              const opcional = clave === 'opcional'
              return (
                <li key={clave} className="flex items-start gap-2">
                  <Check
                    aria-hidden="true"
                    className={
                      opcional ? 'mt-0.5 size-4 shrink-0 text-muted-foreground' : 'mt-0.5 size-4 shrink-0 text-primary'
                    }
                  />
                  <span className={opcional ? 'text-muted-foreground' : undefined}>{t(`requisitos.${clave}`)}</span>
                </li>
              )
            })}
          </ul>
        </aside>
      </div>
      <Link
        to="/proyectos/$proyectoId"
        params={{ proyectoId }}
        className="inline-flex items-center gap-1.5 rounded-sm text-sm font-medium text-primary hover:underline"
      >
        <ArrowLeft aria-hidden="true" className="size-4" />
        {t('volver')}
      </Link>
    </div>
  )
}
