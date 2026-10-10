import { useTranslation } from 'react-i18next'

import { COLOR_ESTADO, ESTADOS, type Estado } from './transformaciones'

interface Props {
  visibles: Set<Estado>
  onCambiar: (estado: Estado, visible: boolean) => void
}

/** Leyenda (color por estado) y filtro (ocultar/mostrar estado) en un solo control: ambos
 * muestran la misma información, separarlos solo duplicaría el recorrido de `ESTADOS`. Comparten
 * la nube 3D y el respaldo 2D. */
export function FiltroEstados({ visibles, onCambiar }: Props) {
  const { t } = useTranslation('universo')

  return (
    <fieldset className="flex flex-wrap gap-4 text-sm">
      <legend className="sr-only">{t('filtros.titulo')}</legend>
      {ESTADOS.map((estado) => (
        <label key={estado} className="flex items-center gap-1.5">
          <input
            type="checkbox"
            checked={visibles.has(estado)}
            onChange={(e) => onCambiar(estado, e.target.checked)}
          />
          <span
            className="inline-block h-2.5 w-2.5 rounded-full"
            style={{ backgroundColor: COLOR_ESTADO[estado] }}
            aria-hidden="true"
          />
          {t(`estados.${estado}`)}
        </label>
      ))}
    </fieldset>
  )
}
