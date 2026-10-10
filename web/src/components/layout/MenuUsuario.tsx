import { useNavigate } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { ChevronDown, LogOut } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { cliente } from '@/api/cliente'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { CLAVE_SESION, useSesion } from '@/hooks/useSesion'
import { cn } from '@/lib/utils'

/** Iniciales para el avatar: primeras letras de las dos primeras "palabras" del email. */
function iniciales(email: string): string {
  const partes = email.split('@')[0].split(/[._-]+/).filter(Boolean)
  const letras = (partes.length > 1 ? partes[0][0] + partes[1][0] : email.slice(0, 2)) ?? ''
  return letras.toUpperCase()
}

export function Avatar({ email, className }: { email: string; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        'inline-flex size-8 shrink-0 items-center justify-center rounded-full bg-accent text-xs font-semibold text-accent-foreground',
        className,
      )}
    >
      {iniciales(email)}
    </span>
  )
}

/** Menú del usuario autenticado: email, empresa y cerrar sesión. `null` sin sesión. */
export function MenuUsuario() {
  const { t } = useTranslation('auth')
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { data: sesion } = useSesion()

  if (!sesion) return null

  async function cerrarSesion() {
    await cliente.POST('/auth/logout')
    queryClient.setQueryData(CLAVE_SESION, null)
    void navigate({ to: '/login' })
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className="flex items-center gap-2 rounded-lg p-1 text-sm font-medium hover:bg-muted md:pr-2"
        aria-label={t('menu.cuenta', { email: sesion.usuario.email })}
      >
        <Avatar email={sesion.usuario.email} />
        <span className="hidden max-w-48 truncate md:inline">{sesion.usuario.email}</span>
        <ChevronDown aria-hidden="true" className="hidden size-4 text-muted-foreground md:inline" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel className="space-y-0.5 font-normal">
          <span className="block truncate text-sm font-medium">{sesion.usuario.email}</span>
          <span className="block truncate text-xs text-muted-foreground">{sesion.empresa.nombre}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => void cerrarSesion()}>
          <LogOut aria-hidden="true" className="size-4" />
          {t('menu.cerrar_sesion')}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
