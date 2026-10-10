import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { aErrorApi, claveError, cliente, type ErrorApi } from '@/api/cliente'
import { AlertaFormulario, EncabezadoAuth, LayoutPublico } from '@/components/layout/LayoutPublico'
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
    try {
      const { data, error: errorApi } = await cliente.POST('/auth/login', {
        body: { email, contrasena },
      })
      if (errorApi) {
        setError(aErrorApi(errorApi))
        return
      }
      queryClient.setQueryData(CLAVE_SESION, data)
      void navigate({ to: '/proyectos' })
    } catch {
      // `fetch` rechazó (API caída, sin red): sin esto el botón quedaba en "Iniciando sesión…".
      setError(aErrorApi(null))
    } finally {
      setEnviando(false)
    }
  }

  return (
    <LayoutPublico>
      <EncabezadoAuth titulo={t('login.titulo')} subtitulo={t('login.subtitulo')} />
      <form onSubmit={enviar} className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="email">{t('login.email')}</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(evento) => setEmail(evento.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <div className="flex items-center justify-between gap-2">
            <Label htmlFor="contrasena">{t('login.contrasena')}</Label>
            <Link to="/recuperar" className="rounded-sm text-xs font-medium text-primary hover:underline">
              {t('login.olvidaste')}
            </Link>
          </div>
          <Input
            id="contrasena"
            type="password"
            autoComplete="current-password"
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
          {enviando ? t('login.enviando') : t('login.enviar')}
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-muted-foreground">
        {t('login.sin_cuenta')}{' '}
        <Link to="/registro" className="rounded-sm font-medium text-primary hover:underline">
          {t('login.crear_cuenta')}
        </Link>
      </p>
    </LayoutPublico>
  )
}
