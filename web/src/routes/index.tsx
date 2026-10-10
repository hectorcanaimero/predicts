import { createFileRoute } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

export const Route = createFileRoute('/')({ component: Inicio })

function Inicio() {
  const { t } = useTranslation()

  return (
    <div>
      <h1 className="text-2xl font-semibold">{t('bienvenida')}</h1>
    </div>
  )
}
