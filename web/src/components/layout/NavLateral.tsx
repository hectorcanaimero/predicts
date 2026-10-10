import { Link, type LinkProps } from '@tanstack/react-router'
import {
  Bot,
  ChartColumn,
  ClipboardCheck,
  FolderKanban,
  FolderOpen,
  Orbit,
  Plus,
  Upload,
  type LucideIcon,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { Logo } from '@/components/marca/Logo'
import { useContextoRuta } from '@/hooks/useContextoRuta'
import { useSesion } from '@/hooks/useSesion'
import { SelectorIdioma } from './SelectorIdioma'

interface PropsEnlace {
  enlace: LinkProps
  icono: LucideIcon
  children: ReactNode
  alNavegar?: () => void
}

function EnlaceNav({ enlace, icono: Icono, children, alNavegar }: PropsEnlace) {
  return (
    <Link
      {...enlace}
      activeOptions={{ exact: true }}
      onClick={alNavegar}
      className="group flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-sidebar-muted transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground focus-visible:outline-sidebar-primary data-[status=active]:bg-sidebar-accent data-[status=active]:text-sidebar-foreground"
    >
      <Icono
        aria-hidden="true"
        className="size-4 shrink-0 group-data-[status=active]:text-sidebar-primary"
      />
      <span className="truncate">{children}</span>
    </Link>
  )
}

function Seccion({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <p className="truncate px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-sidebar-muted/80">
        {titulo}
      </p>
      {children}
    </div>
  )
}

/** Contenido de la barra lateral (se reutiliza en el cajón móvil). Las secciones de proyecto,
 * datos y análisis aparecen solo cuando la ruta actual las tiene en contexto. */
export function NavLateral({ alNavegar }: { alNavegar?: () => void }) {
  const { t } = useTranslation('layout')
  const { data: sesion } = useSesion()
  const { proyectoId, datasetId, analisisId, nombreProyecto, estadoAnalisis } = useContextoRuta()

  return (
    <div className="flex h-full flex-col bg-sidebar text-sidebar-foreground">
      <div className="flex h-16 shrink-0 items-center px-5">
        <Link to="/proyectos" onClick={alNavegar} aria-label="predicts" className="rounded-md">
          <Logo tono="claro" />
        </Link>
      </div>

      <nav aria-label={t('nav.principal')} className="flex-1 space-y-6 overflow-y-auto px-3 py-4">
        <Seccion titulo={t('nav.espacio')}>
          <EnlaceNav enlace={{ to: '/proyectos' }} icono={FolderKanban} alNavegar={alNavegar}>
            {t('nav.proyectos')}
          </EnlaceNav>
        </Seccion>

        {proyectoId && (
          <Seccion titulo={nombreProyecto ?? t('nav.proyecto')}>
            <EnlaceNav
              enlace={{ to: '/proyectos/$proyectoId', params: { proyectoId } }}
              icono={FolderOpen}
              alNavegar={alNavegar}
            >
              {t('nav.resumen_proyecto')}
            </EnlaceNav>
            <EnlaceNav
              enlace={{ to: '/proyectos/$proyectoId/datasets/nuevo', params: { proyectoId } }}
              icono={Upload}
              alNavegar={alNavegar}
            >
              {t('nav.subir_datos')}
            </EnlaceNav>
          </Seccion>
        )}

        {datasetId && (
          <Seccion titulo={t('nav.datos')}>
            <EnlaceNav
              enlace={{ to: '/datasets/$datasetId/calidad', params: { datasetId } }}
              icono={ClipboardCheck}
              alNavegar={alNavegar}
            >
              {t('nav.calidad')}
            </EnlaceNav>
            <EnlaceNav
              enlace={{ to: '/datasets/$datasetId/analisis/nuevo', params: { datasetId } }}
              icono={Plus}
              alNavegar={alNavegar}
            >
              {t('nav.nuevo_analisis')}
            </EnlaceNav>
            <EnlaceNav
              enlace={{ to: '/datasets/$datasetId/agente', params: { datasetId } }}
              icono={Bot}
              alNavegar={alNavegar}
            >
              {t('nav.agente')}
            </EnlaceNav>
          </Seccion>
        )}

        {analisisId && (
          <Seccion titulo={t('nav.analisis')}>
            <EnlaceNav
              enlace={
                estadoAnalisis && estadoAnalisis !== 'listo'
                  ? { to: '/analisis/$analisisId/progreso', params: { analisisId } }
                  : { to: '/analisis/$analisisId', params: { analisisId } }
              }
              icono={ChartColumn}
              alNavegar={alNavegar}
            >
              {estadoAnalisis && estadoAnalisis !== 'listo' ? t('nav.progreso') : t('nav.resultados')}
            </EnlaceNav>
            <EnlaceNav
              enlace={{ to: '/analisis/$analisisId/universo', params: { analisisId } }}
              icono={Orbit}
              alNavegar={alNavegar}
            >
              {t('nav.universo')}
            </EnlaceNav>
          </Seccion>
        )}
      </nav>

      <div className="space-y-3 border-t border-sidebar-border p-4">
        <SelectorIdioma oscuro className="flex w-full justify-between sm:hidden" />
        {sesion && (
          <div className="flex items-center gap-3">
            <span
              aria-hidden="true"
              className="inline-flex size-9 shrink-0 items-center justify-center rounded-md bg-sidebar-accent text-sm font-semibold text-sidebar-primary"
            >
              {sesion.empresa.nombre.slice(0, 1).toUpperCase()}
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{sesion.empresa.nombre}</p>
              <p className="truncate text-xs text-sidebar-muted">{sesion.usuario.email}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
