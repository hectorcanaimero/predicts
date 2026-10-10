import { CircleAlert, Plus } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'

/** Ilustración del estado vacío: un CSV que se convierte en barras de recompra. */
function IlustracionVacio() {
  return (
    <svg viewBox="0 0 160 112" aria-hidden="true" className="h-28 w-40">
      <rect x="10" y="14" width="58" height="76" rx="8" className="fill-card stroke-border" strokeWidth="2" />
      <rect x="20" y="28" width="38" height="5" rx="2.5" className="fill-muted-foreground/30" />
      <rect x="20" y="40" width="30" height="5" rx="2.5" className="fill-muted-foreground/20" />
      <rect x="20" y="52" width="34" height="5" rx="2.5" className="fill-muted-foreground/20" />
      <rect x="20" y="64" width="24" height="5" rx="2.5" className="fill-muted-foreground/20" />
      <path d="M76 52h14" className="stroke-primary/50" strokeWidth="2" strokeLinecap="round" strokeDasharray="2 5" />
      <rect x="96" y="20" width="56" height="72" rx="10" className="fill-accent" />
      <rect x="106" y="62" width="8" height="20" rx="4" className="fill-primary/45" />
      <rect x="119" y="50" width="8" height="32" rx="4" className="fill-primary/70" />
      <rect x="132" y="38" width="8" height="44" rx="4" className="fill-primary" />
      <circle cx="144" cy="28" r="5" fill="hsl(42 92% 58%)" />
    </svg>
  )
}

const PASOS = ['subir', 'analizar', 'actuar'] as const

export function ProyectosVacio({ onCrear, demo }: { onCrear: () => void; demo: ReactNode }) {
  const { t } = useTranslation('proyectos')

  return (
    <section className="rounded-xl border border-dashed bg-card px-6 py-12 text-center sm:px-12">
      <div className="mx-auto flex max-w-xl flex-col items-center">
        <IlustracionVacio />
        <h2 className="mt-6 text-xl font-semibold tracking-tight">{t('vacio.titulo')}</h2>
        <p className="mt-2 text-sm text-muted-foreground">{t('vacio.descripcion')}</p>
        <ol className="mt-8 grid w-full gap-3 text-left sm:grid-cols-3">
          {PASOS.map((paso, i) => (
            <li key={paso} className="flex items-start gap-2.5 rounded-lg bg-muted/60 p-3 text-sm">
              <span className="inline-flex size-6 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
                {i + 1}
              </span>
              <span className="pt-0.5">{t(`vacio.pasos.${paso}`)}</span>
            </li>
          ))}
        </ol>
        <div className="mt-8 flex flex-col items-stretch gap-3 sm:flex-row sm:items-center">
          <Button onClick={onCrear}>
            <Plus aria-hidden="true" />
            {t('vacio.crear')}
          </Button>
          {demo}
        </div>
        <p className="mt-4 text-xs text-muted-foreground">{t('vacio.demo_ayuda')}</p>
      </div>
    </section>
  )
}

export function EstadoErrorCarga({ onReintentar }: { onReintentar: () => void }) {
  const { t } = useTranslation('proyectos')

  return (
    <div
      role="alert"
      className="flex flex-col items-start gap-3 rounded-xl border border-danger/20 bg-danger-soft p-5 sm:flex-row sm:items-center"
    >
      <CircleAlert aria-hidden="true" className="size-5 shrink-0 text-danger" />
      <p className="flex-1 text-sm font-medium text-danger">{t('error.titulo')}</p>
      <Button variant="outline" size="sm" onClick={onReintentar}>
        {t('error.reintentar')}
      </Button>
    </div>
  )
}
