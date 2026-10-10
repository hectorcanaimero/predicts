import { useQueryClient } from '@tanstack/react-query'
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

/** Como `LanguageSwitcher` de `__root`, pero además guarda la preferencia con `PATCH /auth/yo`
 * cuando hay sesión (se usa dentro del layout autenticado). */
export function SelectorIdioma() {
  const { i18n } = useTranslation()
  const { data: sesion } = useSesion()
  const queryClient = useQueryClient()

  async function elegir(idioma: Idioma) {
    await i18n.changeLanguage(idioma)
    if (!sesion) return
    const { data } = await cliente.PATCH('/auth/yo', { body: { idioma } })
    if (data) queryClient.setQueryData(CLAVE_SESION, data)
  }

  return (
    <div role="group" aria-label="idioma" className="flex gap-2">
      {IDIOMAS.map((idioma) => (
        <button
          key={idioma}
          type="button"
          onClick={() => void elegir(idioma)}
          aria-pressed={i18n.resolvedLanguage === idioma}
          className={cn(
            'rounded-md px-2 py-1 text-sm',
            i18n.resolvedLanguage === idioma
              ? 'bg-primary text-primary-foreground'
              : 'bg-secondary text-secondary-foreground',
          )}
        >
          {NOMBRE_IDIOMA[idioma]}
        </button>
      ))}
    </div>
  )
}
