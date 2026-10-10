import { Link, useMatches } from '@tanstack/react-router'
import { ChevronRight } from 'lucide-react'
import { Fragment } from 'react'
import { useTranslation } from 'react-i18next'

import { useContextoRuta } from '@/hooks/useContextoRuta'

/** Sección de cada ruta autenticada para la última miga (clave en `layout:migas`). */
const SECCION_POR_RUTA: Record<string, string> = {
  '/_autenticado/proyectos/$proyectoId/datasets/nuevo': 'subir',
  '/_autenticado/datasets/$datasetId/mapeo': 'mapeo',
  '/_autenticado/datasets/$datasetId/calidad': 'calidad',
  '/_autenticado/datasets/$datasetId/agente': 'agente',
  '/_autenticado/datasets/$datasetId/analisis/nuevo': 'nuevo_analisis',
  '/_autenticado/analisis/$analisisId/': 'resultados',
  '/_autenticado/analisis/$analisisId/progreso': 'progreso',
  '/_autenticado/analisis/$analisisId/universo': 'universo',
  '/_autenticado/demo': 'demo',
}

interface Miga {
  clave: string
  etiqueta: string
  enlace?: { to: '/proyectos' } | { to: '/proyectos/$proyectoId'; params: { proyectoId: string } }
}

/** Migas de pan del encabezado: Proyectos › {proyecto} › {sección}. En móvil solo se ve la
 * última (el resto queda accesible desde la barra lateral). */
export function Migas() {
  const { t } = useTranslation('layout')
  const matches = useMatches()
  const { proyectoId, nombreProyecto } = useContextoRuta()
  const rutaActual = matches[matches.length - 1]?.routeId ?? ''
  const seccion = SECCION_POR_RUTA[rutaActual]
  const esDetalleProyecto = rutaActual === '/_autenticado/proyectos/$proyectoId/'

  const migas: Miga[] = [{ clave: 'proyectos', etiqueta: t('migas.proyectos'), enlace: { to: '/proyectos' } }]
  if (proyectoId) {
    migas.push({
      clave: 'proyecto',
      etiqueta: nombreProyecto ?? '…',
      enlace: { to: '/proyectos/$proyectoId', params: { proyectoId } },
    })
  }
  if (seccion) migas.push({ clave: seccion, etiqueta: t(`migas.${seccion}`) })
  else if (esDetalleProyecto) delete migas[migas.length - 1].enlace

  if (migas.length === 1) delete migas[0].enlace

  return (
    <nav aria-label={t('migas.aria')} className="min-w-0">
      <ol className="flex min-w-0 items-center gap-1.5 text-sm">
        {migas.map((miga, i) => {
          const ultima = i === migas.length - 1
          return (
            <Fragment key={miga.clave}>
              {i > 0 && (
                <li aria-hidden="true" className="hidden text-muted-foreground/60 sm:block">
                  <ChevronRight className="size-4" />
                </li>
              )}
              <li className={ultima ? 'min-w-0' : 'hidden min-w-0 sm:block'}>
                {miga.enlace && !ultima ? (
                  <Link
                    {...miga.enlace}
                    className="block truncate rounded-sm text-muted-foreground transition-colors hover:text-foreground"
                  >
                    {miga.etiqueta}
                  </Link>
                ) : (
                  <span aria-current={ultima ? 'page' : undefined} className="block truncate font-medium text-foreground">
                    {miga.etiqueta}
                  </span>
                )}
              </li>
            </Fragment>
          )
        })}
      </ol>
    </nav>
  )
}
