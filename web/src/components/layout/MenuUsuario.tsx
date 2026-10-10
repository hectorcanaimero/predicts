import { useNavigate } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { cliente } from '@/api/cliente'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { CLAVE_SESION, useSesion } from '@/hooks/useSesion'

/** Menú del usuario autenticado: email y cerrar sesión. `null` sin sesión. */
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
      <DropdownMenuTrigger className="text-sm font-medium">
        {sesion.usuario.email}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onSelect={() => void cerrarSesion()}>
          {t('menu.cerrar_sesion')}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
