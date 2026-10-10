import { createFileRoute, Outlet, useNavigate } from '@tanstack/react-router'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'

import { ShellApp } from '@/components/layout/ShellApp'
import { Isotipo } from '@/components/marca/Logo'
import { useSesion } from '@/hooks/useSesion'

export const Route = createFileRoute('/_autenticado')({ component: LayoutAutenticado })

/** Mientras se resuelve la sesión: la marca con un pulso suave, en vez de una pantalla en blanco. */
function CargandoSesion() {
  const { t } = useTranslation('layout')
  return (
    <div role="status" className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background">
      <Isotipo className="size-12 animate-pulse text-primary motion-reduce:animate-none" />
      <p className="text-sm text-muted-foreground">{t('cargando_sesion')}</p>
    </div>
  )
}

export function LayoutAutenticado() {
  const sesion = useSesion()
  const navigate = useNavigate()

  useEffect(() => {
    if (!sesion.isLoading && !sesion.data) void navigate({ to: '/login' })
  }, [sesion.isLoading, sesion.data, navigate])

  if (sesion.isLoading) return <CargandoSesion />
  if (!sesion.data) return null

  return (
    <ShellApp>
      <Outlet />
    </ShellApp>
  )
}
