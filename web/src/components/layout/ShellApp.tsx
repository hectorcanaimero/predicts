import * as DialogPrimitive from '@radix-ui/react-dialog'
import { Menu, X } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { MenuUsuario } from './MenuUsuario'
import { Migas } from './Migas'
import { NavLateral } from './NavLateral'
import { SelectorIdioma } from './SelectorIdioma'

/** Estructura de la app autenticada: barra lateral fija en desktop (cajón en móvil), encabezado
 * con migas, idioma y menú de usuario, y el contenido con ancho máximo y espaciado consistente. */
export function ShellApp({ children }: { children: ReactNode }) {
  const { t } = useTranslation('layout')
  const [menuAbierto, setMenuAbierto] = useState(false)

  return (
    <div className="min-h-screen bg-background">
      <a
        href="#contenido"
        className="sr-only z-50 rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground focus:not-sr-only focus:fixed focus:left-3 focus:top-3"
      >
        {t('saltar')}
      </a>

      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r border-sidebar-border lg:block">
        <NavLateral />
      </aside>

      <DialogPrimitive.Root open={menuAbierto} onOpenChange={setMenuAbierto}>
        <DialogPrimitive.Portal>
          <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/45 lg:hidden" />
          <DialogPrimitive.Content
            className="fixed inset-y-0 left-0 z-50 w-72 max-w-[85vw] shadow-xl focus:outline-none lg:hidden"
            aria-describedby={undefined}
          >
            <DialogPrimitive.Title className="sr-only">{t('nav.principal')}</DialogPrimitive.Title>
            <NavLateral alNavegar={() => setMenuAbierto(false)} />
            <DialogPrimitive.Close
              className="absolute right-3 top-4 rounded-md p-1.5 text-sidebar-muted hover:bg-sidebar-accent hover:text-sidebar-foreground"
              aria-label={t('nav.cerrar_menu')}
            >
              <X className="size-5" aria-hidden="true" />
            </DialogPrimitive.Close>
          </DialogPrimitive.Content>
        </DialogPrimitive.Portal>
      </DialogPrimitive.Root>

      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b bg-background/90 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/75 sm:px-6 lg:px-8">
          <Button
            variant="ghost"
            size="icon"
            className="-ml-2 lg:hidden"
            onClick={() => setMenuAbierto(true)}
            aria-label={t('nav.abrir_menu')}
          >
            <Menu className="size-5" aria-hidden="true" />
          </Button>
          <div className="min-w-0 flex-1">
            <Migas />
          </div>
          <div className="flex shrink-0 items-center gap-2 sm:gap-3">
            <SelectorIdioma className="hidden sm:inline-flex" />
            <MenuUsuario />
          </div>
        </header>

        <main
          id="contenido"
          tabIndex={-1}
          className="mx-auto w-full max-w-7xl px-4 py-6 focus:outline-none sm:px-6 lg:px-8 lg:py-8"
        >
          {children}
        </main>
      </div>
    </div>
  )
}
