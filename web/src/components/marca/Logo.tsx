import { cn } from '@/lib/utils'

interface PropsMarca {
  className?: string
}

/** Isotipo: tres barras crecientes (el histórico de compras) y un punto adelantado (la
 * predicción). Usa `currentColor` para el fondo, así sirve sobre claro y sobre oscuro. */
export function Isotipo({ className }: PropsMarca) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={cn('size-8 shrink-0', className)}>
      <rect width="32" height="32" rx="8" fill="currentColor" />
      <rect x="7" y="17" width="3.5" height="8" rx="1.75" fill="white" opacity="0.55" />
      <rect x="12.5" y="13" width="3.5" height="12" rx="1.75" fill="white" opacity="0.75" />
      <rect x="18" y="9" width="3.5" height="16" rx="1.75" fill="white" />
      <circle cx="25.25" cy="7.75" r="2.25" fill="hsl(42 92% 62%)" />
    </svg>
  )
}

interface PropsLogo extends PropsMarca {
  /** Color del texto del wordmark; el isotipo siempre va en el primario de la marca. */
  tono?: 'claro' | 'oscuro'
}

export function Logo({ className, tono = 'oscuro' }: PropsLogo) {
  return (
    <span className={cn('inline-flex items-center gap-2.5', className)}>
      <Isotipo className={tono === 'claro' ? 'text-sidebar-primary/90' : 'text-primary'} />
      <span
        className={cn(
          'text-lg font-semibold tracking-tight',
          tono === 'claro' ? 'text-sidebar-foreground' : 'text-foreground',
        )}
      >
        predicts
      </span>
    </span>
  )
}
