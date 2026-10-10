import { Link } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'

/** Botón "probar con datos de ejemplo": solo navega a `/demo`, que es la ruta que llama la
 * API y redirige al progreso (ver `routes/_autenticado/demo.tsx`). Se usa en la lista de
 * proyectos vacía y en la página de inicio. */
export function BotonProbarDemo() {
  const { t } = useTranslation('demo')
  return (
    <Button asChild variant="outline">
      <Link to="/demo">{t('boton')}</Link>
    </Button>
  )
}
