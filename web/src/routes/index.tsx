import { createFileRoute, Navigate } from '@tanstack/react-router'

import { useSesion } from '@/hooks/useSesion'

export const Route = createFileRoute('/')({ component: Inicio })

/** `/` no tiene contenido propio: con sesión va a la lista de proyectos, sin sesión al login. */
function Inicio() {
  const sesion = useSesion()

  if (sesion.isLoading) return null
  return <Navigate to={sesion.data ? '/proyectos' : '/login'} replace />
}
