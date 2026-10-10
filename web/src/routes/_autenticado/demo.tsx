import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useCallback, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'

import { claveError } from '@/api/cliente'
import { Button } from '@/components/ui/button'
import { useCrearDemo } from '@/features/proyectos/hooks'

export const Route = createFileRoute('/_autenticado/demo')({ component: DemoRuta })

/** Crea el proyecto "Demo" al entrar a la ruta y redirige al progreso del análisis; no hay
 * nada que el usuario tenga que completar (el botón que llega acá ya decidió "probar con
 * datos de ejemplo"). */
export function DemoRuta() {
  const { t } = useTranslation('demo')
  const navigate = useNavigate()
  const crear = useCrearDemo()
  const yaLanzado = useRef(false)

  const lanzar = useCallback(() => {
    crear.mutate(undefined, {
      onSuccess: (datos) =>
        void navigate({
          to: '/analisis/$analisisId/progreso',
          params: { analisisId: datos.analisis_id },
        }),
    })
  }, [crear, navigate])

  useEffect(() => {
    if (yaLanzado.current) return
    yaLanzado.current = true
    lanzar()
  }, [lanzar])

  return (
    <div className="space-y-4 text-center">
      <p>{t('creando')}</p>
      <p className="text-sm text-muted-foreground">{t('atribucion')}</p>
      {crear.error && (
        <>
          <p role="alert" className="text-sm text-destructive">
            {t(`errores.${claveError(crear.error)}`, { defaultValue: t('comun:error_generico') })}
          </p>
          <Button onClick={lanzar}>{t('reintentar')}</Button>
        </>
      )}
    </div>
  )
}
