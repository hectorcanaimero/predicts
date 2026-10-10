import { createRootRoute, Outlet } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { IDIOMAS, type Idioma } from '@/i18n'
import { cn } from '@/lib/utils'

const NOMBRE_IDIOMA: Record<Idioma, string> = {
  'pt-BR': 'Português',
  es: 'Español',
  en: 'English',
}

export function LanguageSwitcher() {
  const { i18n } = useTranslation()

  return (
    <div role="group" aria-label="idioma" className="flex gap-2">
      {IDIOMAS.map((idioma) => (
        <button
          key={idioma}
          type="button"
          onClick={() => void i18n.changeLanguage(idioma)}
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

function RootComponent() {
  return (
    <div className="min-h-screen">
      <header className="flex items-center justify-end border-b p-4">
        <LanguageSwitcher />
      </header>
      <main className="p-4">
        <Outlet />
      </main>
    </div>
  )
}

export const Route = createRootRoute({ component: RootComponent })
