import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { CircleAlert, LoaderCircle } from 'lucide-react'
import { useCallback, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'

import { claveError } from '@/api/cliente'
import { Isotipo } from '@/components/marca/Logo'
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
    <div className="flex min-h-[60vh] items-center justify-center">
      <div className="w-full max-w-md rounded-xl border bg-card p-8 text-center shadow-sm">
        <Isotipo className="mx-auto size-12 text-primary" />
        <h1 className="mt-5 text-xl font-semibold tracking-tight">{t('titulo')}</h1>
        <p className="mt-2 text-sm text-muted-foreground">{t('pasos')}</p>

        {!crear.error && (
          <p aria-live="polite" className="mt-6 flex items-center justify-center gap-2 text-sm font-medium">
            <LoaderCircle aria-hidden="true" className="size-4 animate-spin text-primary motion-reduce:animate-none" />
            {t('creando')}
          </p>
        )}

        {crear.error && (
          <div className="mt-6 space-y-4">
            <p
              role="alert"
              className="flex items-start gap-2 rounded-md border border-danger/20 bg-danger-soft px-3 py-2.5 text-left text-sm text-danger"
            >
              <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
              {t(`errores.${claveError(crear.error)}`, { defaultValue: t('comun:error_generico') })}
            </p>
            <Button onClick={lanzar}>{t('reintentar')}</Button>
          </div>
        )}

        <p className="mt-8 border-t pt-4 text-xs text-muted-foreground">{t('atribucion')}</p>
      </div>
    </div>
  )
}
