import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { aErrorApi, claveError, cliente, type ErrorApi } from '@/api/cliente'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { CLAVE_SESION } from '@/hooks/useSesion'

export const Route = createFileRoute('/login')({ component: Login })

export function Login() {
  const { t } = useTranslation('auth')
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [email, setEmail] = useState('')
  const [contrasena, setContrasena] = useState('')
  const [error, setError] = useState<ErrorApi | null>(null)
  const [enviando, setEnviando] = useState(false)

  async function enviar(evento: FormEvent) {
    evento.preventDefault()
    setError(null)
    setEnviando(true)
    const { data, error: errorApi } = await cliente.POST('/auth/login', {
      body: { email, contrasena },
    })
    setEnviando(false)
    if (errorApi) {
      setError(aErrorApi(errorApi))
      return
    }
    queryClient.setQueryData(CLAVE_SESION, data)
    void navigate({ to: '/inicio' })
  }

  return (
    <form onSubmit={enviar} className="mx-auto max-w-sm space-y-4">
      <h1 className="text-xl font-semibold">{t('login.titulo')}</h1>
      <div className="space-y-1">
        <Label htmlFor="email">{t('login.email')}</Label>
        <Input
          id="email"
          type="email"
          required
          value={email}
          onChange={(evento) => setEmail(evento.target.value)}
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor="contrasena">{t('login.contrasena')}</Label>
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
        {enviando ? t('login.enviando') : t('login.enviar')}
      </Button>
      <div className="flex justify-between text-sm">
        <Link to="/recuperar">{t('login.olvidaste')}</Link>
        <Link to="/registro">{t('login.crear_cuenta')}</Link>
      </div>
    </form>
  )
}
