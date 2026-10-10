import { Link } from '@tanstack/react-router'
import { CirclePlay } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button, type ButtonProps } from '@/components/ui/button'

/** Botón "probar con datos de ejemplo": solo navega a `/demo`, que es la ruta que llama la
 * API y redirige al progreso (ver `routes/_autenticado/demo.tsx`). Se usa en el estado vacío de
 * la lista de proyectos. */
export function BotonProbarDemo({
  variant = 'outline',
  className,
}: {
  variant?: ButtonProps['variant']
  className?: string
}) {
  const { t } = useTranslation('demo')
  return (
    <Button asChild variant={variant} className={className}>
      <Link to="/demo">
        <CirclePlay aria-hidden="true" />
        {t('boton')}
      </Link>
    </Button>
  )
}
