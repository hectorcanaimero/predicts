import { Button } from '@/components/ui/button'

interface Props {
  columnas: readonly { clave: string; etiqueta: string }[]
  valor: string
  onCambiar: (orden: string) => void
  nombreAccesible: string
  etiquetaDescendente: string
  etiquetaAscendente: string
}

/** Selector de columna + botón asc/desc; `valor` es el `orden` tal cual lo espera la API
 * (`campo` o `-campo`). Usa un `<select>` nativo (no el Select de Radix) para que los tests no
 * tengan que simular su interacción por puntero. */
export function SelectorOrden({
  columnas,
  valor,
  onCambiar,
  nombreAccesible,
  etiquetaDescendente,
  etiquetaAscendente,
}: Props) {
  const descendente = valor.startsWith('-')
  const campo = descendente ? valor.slice(1) : valor

  return (
    <div className="flex items-center gap-2">
      <select
        aria-label={nombreAccesible}
        value={campo}
        onChange={(evento) => onCambiar((descendente ? '-' : '') + evento.target.value)}
        className="flex h-8 rounded-md border border-input bg-card px-2 text-xs shadow-xs"
      >
        {columnas.map((columna) => (
          <option key={columna.clave} value={columna.clave}>
            {columna.etiqueta}
          </option>
        ))}
      </select>
      <Button variant="outline" size="sm" onClick={() => onCambiar((descendente ? '' : '-') + campo)}>
        {descendente ? etiquetaDescendente : etiquetaAscendente}
      </Button>
    </div>
  )
}
