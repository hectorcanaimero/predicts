import { BellRing, ChartColumn, CircleAlert, MessageSquareText, TriangleAlert, type LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { Logo } from '@/components/marca/Logo'
import { SelectorIdioma } from './SelectorIdioma'

const PUNTOS: { clave: string; icono: LucideIcon }[] = [
  { clave: 'recompra', icono: BellRing },
  { clave: 'riesgo', icono: TriangleAlert },
  { clave: 'mensajes', icono: MessageSquareText },
  { clave: 'precision', icono: ChartColumn },
]

/** Fondo decorativo del panel de marca: una grilla de puntos que se desvanece. */
function TramaPuntos() {
  return (
    <svg aria-hidden="true" className="pointer-events-none absolute inset-0 size-full opacity-[0.15]">
      <defs>
        <pattern id="trama-puntos" width="22" height="22" patternUnits="userSpaceOnUse">
          <circle cx="1.5" cy="1.5" r="1.5" fill="currentColor" />
        </pattern>
        <linearGradient id="trama-desvanecer" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="white" stopOpacity="0" />
          <stop offset="1" stopColor="white" stopOpacity="1" />
        </linearGradient>
        <mask id="trama-mascara">
          <rect width="100%" height="100%" fill="url(#trama-desvanecer)" />
        </mask>
      </defs>
      <rect width="100%" height="100%" fill="url(#trama-puntos)" mask="url(#trama-mascara)" />
    </svg>
  )
}

/** Layout de las pantallas públicas (login, registro, recuperar, restablecer): panel de marca
 * con la propuesta de valor en desktop y el formulario centrado en una tarjeta. */
export function LayoutPublico({ children }: { children: ReactNode }) {
  const { t } = useTranslation('layout')

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      <aside className="relative hidden overflow-hidden bg-sidebar p-10 text-sidebar-foreground lg:flex lg:flex-col lg:justify-between xl:p-14">
        <TramaPuntos />
        <Logo tono="claro" className="relative" />
        <div className="relative max-w-md space-y-8">
          <div className="space-y-4">
            <h2 className="text-3xl font-semibold leading-tight tracking-tight xl:text-4xl">{t('publico.titular')}</h2>
            <p className="text-base leading-relaxed text-sidebar-muted">{t('publico.subtitulo')}</p>
          </div>
          <ul className="space-y-4">
            {PUNTOS.map(({ clave, icono: Icono }) => (
              <li key={clave} className="flex items-start gap-3">
                <span className="mt-0.5 inline-flex size-8 shrink-0 items-center justify-center rounded-md bg-sidebar-accent text-sidebar-primary">
                  <Icono aria-hidden="true" className="size-4" />
                </span>
                <span className="pt-1 text-sm leading-relaxed">{t(`publico.puntos.${clave}`)}</span>
              </li>
            ))}
          </ul>
        </div>
        <p className="relative text-xs text-sidebar-muted">{t('publico.pie')}</p>
      </aside>

      <div className="flex min-h-screen flex-col">
        <div className="flex items-center justify-between gap-4 px-4 py-4 sm:px-8 sm:py-6">
          <Logo className="lg:invisible" />
          <SelectorIdioma />
        </div>
        <main className="flex flex-1 items-start justify-center px-4 pb-12 pt-4 sm:items-center sm:px-8 sm:pt-0">
          <div className="w-full max-w-md rounded-xl border bg-card p-6 shadow-sm sm:p-8">{children}</div>
        </main>
      </div>
    </div>
  )
}

export function EncabezadoAuth({ titulo, subtitulo }: { titulo: string; subtitulo?: string }) {
  return (
    <div className="mb-6 space-y-1.5">
      <h1 className="text-2xl font-semibold tracking-tight">{titulo}</h1>
      {subtitulo && <p className="text-sm text-muted-foreground">{subtitulo}</p>}
    </div>
  )
}

export function AlertaFormulario({ children }: { children: ReactNode }) {
  return (
    <p
      role="alert"
      className="flex items-start gap-2 rounded-md border border-danger/20 bg-danger-soft px-3 py-2.5 text-sm text-danger"
    >
      <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
      <span>{children}</span>
    </p>
  )
}
