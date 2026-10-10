import type { BadgeProps } from '@/components/ui/badge'

/** Umbrales de probabilidad para colorear (el número siempre se muestra: el color no es la única
 * señal). */
export function varianteProbabilidad(p: number): BadgeProps['variant'] {
  if (p >= 0.7) return 'success'
  if (p >= 0.4) return 'warning'
  return 'neutral'
}
