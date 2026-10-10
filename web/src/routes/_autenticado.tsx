import { createFileRoute, Outlet, useNavigate } from '@tanstack/react-router'
import { useEffect } from 'react'

import { MenuUsuario } from '@/components/layout/MenuUsuario'
import { SelectorIdioma } from '@/components/layout/SelectorIdioma'
import { useSesion } from '@/hooks/useSesion'

export const Route = createFileRoute('/_autenticado')({ component: LayoutAutenticado })

export function LayoutAutenticado() {
  const sesion = useSesion()
  const navigate = useNavigate()

  useEffect(() => {
    if (!sesion.isLoading && !sesion.data) void navigate({ to: '/login' })
  }, [sesion.isLoading, sesion.data, navigate])

  if (sesion.isLoading || !sesion.data) return null

  return (
    <div>
      <header className="flex items-center justify-between gap-4 border-b pb-4">
        <SelectorIdioma />
        <MenuUsuario />
      </header>
      <Outlet />
    </div>
  )
}
