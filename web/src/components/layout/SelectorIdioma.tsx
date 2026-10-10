import { useQueryClient } from '@tanstack/react-query'
import { Languages } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { cliente } from '@/api/cliente'
import { cn } from '@/lib/utils'
import { IDIOMAS, type Idioma } from '@/i18n'
import { CLAVE_SESION, useSesion } from '@/hooks/useSesion'

const NOMBRE_IDIOMA: Record<Idioma, string> = {
  'pt-BR': 'Português',
  es: 'Español',
  en: 'English',
}

const CODIGO_IDIOMA: Record<Idioma, string> = {
  'pt-BR': 'PT',
  es: 'ES',
  en: 'EN',
}

interface PropsControl {
  alElegir?: (idioma: Idioma) => void | Promise<void>
  className?: string
  /** Para fondos oscuros (barra lateral). */
  oscuro?: boolean
}

/** Control segmentado compacto (PT · ES · EN). El nombre accesible de cada botón es el nombre
 * completo del idioma; sin `alElegir` solo cambia el idioma de la interfaz. */
export function ControlIdioma({ alElegir, className, oscuro = false }: PropsControl) {
  const { i18n } = useTranslation()
  const elegir = alElegir ?? ((idioma: Idioma) => i18n.changeLanguage(idioma))

  return (
    <div
      role="group"
      aria-label="idioma"
      className={cn(
        'inline-flex items-center gap-0.5 rounded-lg border p-0.5',
        oscuro ? 'border-sidebar-border bg-sidebar-accent' : 'bg-card shadow-xs',
        className,
      )}
    >
      <Languages
        aria-hidden="true"
        className={cn('mx-1.5 size-3.5', oscuro ? 'text-sidebar-muted' : 'text-muted-foreground')}
      />
      {IDIOMAS.map((idioma) => {
        const activo = i18n.resolvedLanguage === idioma
        return (
          <button
            key={idioma}
            type="button"
            onClick={() => void elegir(idioma)}
            aria-pressed={activo}
            aria-label={NOMBRE_IDIOMA[idioma]}
            title={NOMBRE_IDIOMA[idioma]}
            className={cn(
              'rounded-md px-2 py-1 text-xs font-semibold tracking-wide transition-colors',
              activo && (oscuro ? 'bg-sidebar-primary text-sidebar' : 'bg-primary text-primary-foreground'),
              !activo &&
                (oscuro
                  ? 'text-sidebar-muted hover:text-sidebar-foreground'
                  : 'text-muted-foreground hover:bg-muted hover:text-foreground'),
            )}
          >
            {CODIGO_IDIOMA[idioma]}
          </button>
        )
      })}
    </div>
  )
}

/** `ControlIdioma` que además guarda la preferencia con `PATCH /auth/yo` cuando hay sesión. */
export function SelectorIdioma({ className, oscuro }: { className?: string; oscuro?: boolean }) {
  const { i18n } = useTranslation()
  const { data: sesion } = useSesion()
  const queryClient = useQueryClient()

  async function elegir(idioma: Idioma) {
    await i18n.changeLanguage(idioma)
    if (!sesion) return
    const { data } = await cliente.PATCH('/auth/yo', { body: { idioma } })
    if (data) queryClient.setQueryData(CLAVE_SESION, data)
  }

  return <ControlIdioma alElegir={elegir} className={className} oscuro={oscuro} />
}
