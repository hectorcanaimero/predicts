import { createFileRoute, Link } from '@tanstack/react-router'
import { type FormEvent, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { aErrorApi, claveError, cliente, type ErrorApi } from '@/api/cliente'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

export const Route = createFileRoute('/recuperar')({ component: Recuperar })

export function Recuperar() {
  const { t } = useTranslation('auth')
  const [email, setEmail] = useState('')
  const [error, setError] = useState<ErrorApi | null>(null)
  const [enviando, setEnviando] = useState(false)
  const [enviado, setEnviado] = useState(false)

  async function enviar(evento: FormEvent) {
    evento.preventDefault()
    setError(null)
    setEnviando(true)
    const { error: errorApi } = await cliente.POST('/auth/recuperar', { body: { email } })
    setEnviando(false)
    if (errorApi) {
      setError(aErrorApi(errorApi))
      return
    }
    setEnviado(true)
  }

  if (enviado) {
    return (
      <div className="mx-auto max-w-sm space-y-4">
        <p>{t('recuperar.enviado')}</p>
        <Link to="/login">{t('recuperar.volver')}</Link>
      </div>
    )
  }

  return (
    <form onSubmit={enviar} className="mx-auto max-w-sm space-y-4">
      <h1 className="text-xl font-semibold">{t('recuperar.titulo')}</h1>
      <div className="space-y-1">
        <Label htmlFor="email">{t('recuperar.email')}</Label>
        <Input
          id="email"
          type="email"
          required
          value={email}
          onChange={(evento) => setEmail(evento.target.value)}
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
        {enviando ? t('recuperar.enviando') : t('recuperar.enviar')}
      </Button>
      <Link to="/login" className="text-sm">
        {t('recuperar.volver')}
      </Link>
    </form>
  )
}
