import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { type FormEvent, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { aErrorApi, claveError, cliente, type ErrorApi } from '@/api/cliente'
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
    const { error: errorApi } = await cliente.POST('/auth/restablecer', {
      body: { token, contrasena },
    })
    setEnviando(false)
    if (errorApi) {
      setError(aErrorApi(errorApi))
      return
    }
    void navigate({ to: '/login' })
  }

  return (
    <form onSubmit={enviar} className="mx-auto max-w-sm space-y-4">
      <h1 className="text-xl font-semibold">{t('restablecer.titulo')}</h1>
      <div className="space-y-1">
        <Label htmlFor="contrasena">{t('restablecer.contrasena')}</Label>
        <Input
          id="contrasena"
          type="password"
          required
          value={contrasena}
          onChange={(evento) => setContrasena(evento.target.value)}
        />
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {t(`errores.${claveError(error)}`, {
            ...error.parametros,
            defaultValue: t('comun:error_generico'),
          })}
        </p>
      )}
      <Button type="submit" disabled={enviando} className="w-full">
        {enviando ? t('restablecer.enviando') : t('restablecer.enviar')}
      </Button>
      <Link to="/login" className="text-sm">
        {t('restablecer.volver')}
      </Link>
    </form>
  )
}
