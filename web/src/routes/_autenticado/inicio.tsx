import { createFileRoute, Navigate } from '@tanstack/react-router'

/** Destino histórico tras login/registro: hoy la pantalla principal es la lista de proyectos
 * (con el botón de demo en su estado vacío), así que solo redirige para no romper enlaces. */
export const Route = createFileRoute('/_autenticado/inicio')({ component: Inicio })

function Inicio() {
  return <Navigate to="/proyectos" replace />
}
