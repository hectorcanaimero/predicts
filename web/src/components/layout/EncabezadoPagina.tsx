import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

interface Props {
  titulo: ReactNode
  descripcion?: ReactNode
  /** Botones/enlaces a la derecha del título (abajo en móvil). */
  acciones?: ReactNode
  /** Línea chica sobre el título (p. ej. el tipo de pantalla). */
  antetitulo?: ReactNode
  className?: string
}

/** Encabezado estándar de página: un único `h1` con descripción y acciones. */
export function EncabezadoPagina({ titulo, descripcion, acciones, antetitulo, className }: Props) {
  return (
    <div className={cn('flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between', className)}>
      <div className="min-w-0 space-y-1">
        {antetitulo && (
          <p className="text-xs font-semibold uppercase tracking-wider text-primary">{antetitulo}</p>
        )}
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">{titulo}</h1>
        {descripcion && <p className="max-w-3xl text-sm text-muted-foreground [overflow-wrap:anywhere]">{descripcion}</p>}
      </div>
      {acciones && <div className="flex shrink-0 flex-wrap items-center gap-2">{acciones}</div>}
    </div>
  )
}
