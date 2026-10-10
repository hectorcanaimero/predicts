import { Check } from 'lucide-react'
import { Fragment } from 'react'
import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'

const PASOS_FLUJO = ['subir', 'mapear', 'calidad', 'analizar'] as const
type PasoFlujo = (typeof PASOS_FLUJO)[number]

/** Indicador horizontal del recorrido de un dataset: subir → mapear → calidad → analizar. */
export function FlujoDatos({ actual }: { actual: PasoFlujo }) {
  const { t } = useTranslation('layout')
  const indiceActual = PASOS_FLUJO.indexOf(actual)

  return (
    <nav aria-label={t('flujo.aria')}>
      <ol className="flex items-center gap-2 overflow-x-auto text-sm [scrollbar-width:none]">
        {PASOS_FLUJO.map((paso, i) => {
          const hecho = i < indiceActual
          const enCurso = i === indiceActual
          return (
            <Fragment key={paso}>
              {i > 0 && (
                <li
                  aria-hidden="true"
                  className={cn('h-px w-6 shrink-0 sm:w-10', hecho || enCurso ? 'bg-primary' : 'bg-border')}
                />
              )}
              <li aria-current={enCurso ? 'step' : undefined} className="flex shrink-0 items-center gap-2">
                <span
                  aria-hidden="true"
                  className={cn(
                    'inline-flex size-6 items-center justify-center rounded-full text-xs font-semibold',
                    hecho && 'bg-primary text-primary-foreground',
                    enCurso && 'bg-primary/10 text-primary ring-2 ring-primary',
                    !hecho && !enCurso && 'bg-muted text-muted-foreground',
                  )}
                >
                  {hecho ? <Check className="size-3.5" strokeWidth={3} /> : i + 1}
                </span>
                <span className={cn(enCurso ? 'font-medium text-foreground' : 'text-muted-foreground')}>
                  {t(`flujo.${paso}`)}
                </span>
              </li>
            </Fragment>
          )
        })}
      </ol>
    </nav>
  )
}
