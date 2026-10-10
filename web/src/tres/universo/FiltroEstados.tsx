import { useTranslation } from 'react-i18next'

import { COLOR_ESTADO, ESTADOS, type Estado } from './transformaciones'

interface Props {
  visibles: Set<Estado>
  onCambiar: (estado: Estado, visible: boolean) => void
}

/** Leyenda (color por estado) y filtro (ocultar/mostrar estado) en un solo control: ambos
 * muestran la misma información, separarlos solo duplicaría el recorrido de `ESTADOS`. Comparten
 * la nube 3D y el respaldo 2D. Cada estado es un "chip" con su checkbox nativo. */
export function FiltroEstados({ visibles, onCambiar }: Props) {
  const { t } = useTranslation('universo')

  return (
    <fieldset className="flex flex-wrap gap-2 text-sm">
      <legend className="sr-only">{t('filtros.titulo')}</legend>
      {ESTADOS.map((estado) => {
        const activo = visibles.has(estado)
        return (
          <label
            key={estado}
            className={
              activo
                ? 'flex cursor-pointer items-center gap-2 rounded-full border bg-card px-3 py-1.5 font-medium shadow-xs has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring'
                : 'flex cursor-pointer items-center gap-2 rounded-full border border-dashed bg-muted/50 px-3 py-1.5 text-muted-foreground has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring'
            }
          >
            <input
              type="checkbox"
              className="sr-only"
              checked={activo}
              onChange={(e) => onCambiar(estado, e.target.checked)}
            />
            <span
              className="inline-block size-2.5 rounded-full"
              style={{ backgroundColor: COLOR_ESTADO[estado], opacity: activo ? 1 : 0.35 }}
              aria-hidden="true"
            />
            {t(`estados.${estado}`)}
          </label>
        )
      })}
    </fieldset>
  )
}
