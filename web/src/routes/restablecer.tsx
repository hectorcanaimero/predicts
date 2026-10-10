import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { ArrowLeft } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { aErrorApi, claveError, cliente, type ErrorApi } from '@/api/cliente'
import { AlertaFormulario, EncabezadoAuth, LayoutPublico } from '@/components/layout/LayoutPublico'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

export const Route = createFileRoute('/restablecer')({ component: Restablecer })

export function Restablecer() {
  const { t } = useTranslation('auth')
  const navigate = useNavigate()
  const [token] = useState(() => new URLSearchParams(window.location.search).get('token') ?? '')
  const [contrasena, setContrasena] = useState('')
  const [error, setError] = useState<ErrorApi | null>(null)
  const [enviando, setEnviando] = useState(false)

  async function enviar(evento: FormEvent) {
    evento.preventDefault()
    setError(null)
    setEnviando(true)
    try {
      const { error: errorApi } = await cliente.POST('/auth/restablecer', {
        body: { token, contrasena },
      })
      if (errorApi) {
        setError(aErrorApi(errorApi))
        return
      }
      void navigate({ to: '/login' })
    } catch {
      setError(aErrorApi(null))
    } finally {
      setEnviando(false)
    }
  }

  return (
    <LayoutPublico>
      <EncabezadoAuth titulo={t('restablecer.titulo')} subtitulo={t('restablecer.subtitulo')} />
      <form onSubmit={enviar} className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="contrasena">{t('restablecer.contrasena')}</Label>
          <Input
            id="contrasena"
            type="password"
            autoComplete="new-password"
            required
            value={contrasena}
            onChange={(evento) => setContrasena(evento.target.value)}
          />
        </div>
        {error && (
          <AlertaFormulario>
            {t(`errores.${claveError(error)}`, {
              ...error.parametros,
              defaultValue: t('comun:error_generico'),
            })}
          </AlertaFormulario>
        )}
        <Button type="submit" disabled={enviando} className="h-10 w-full">
          {enviando ? t('restablecer.enviando') : t('restablecer.enviar')}
        </Button>
      </form>
      <Link
        to="/login"
        className="mt-6 inline-flex items-center gap-1.5 rounded-sm text-sm font-medium text-primary hover:underline"
      >
        <ArrowLeft aria-hidden="true" className="size-4" />
        {t('restablecer.volver')}
      </Link>
    </LayoutPublico>
  )
}
