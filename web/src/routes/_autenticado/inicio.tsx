import { createFileRoute } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { useSesion } from '@/hooks/useSesion'

/** Landing tras login/registro. Las pantallas de proyectos (F6.1.T2) reemplazarán este destino. */
export const Route = createFileRoute('/_autenticado/inicio')({ component: Inicio })

function Inicio() {
  const { data: sesion } = useSesion()
  const { t } = useTranslation('auth')

  return <h1 className="text-xl font-semibold">{t('inicio.bienvenida', { email: sesion?.usuario.email })}</h1>
}
