import { createFileRoute, Outlet, useNavigate } from '@tanstack/react-router'
import { useEffect } from 'react'

import { ShellApp } from '@/components/layout/ShellApp'
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
    <ShellApp>
      <Outlet />
    </ShellApp>
  )
}
