import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { aErrorApi, claveError, cliente, type ErrorApi } from '@/api/cliente'
import { AlertaFormulario, EncabezadoAuth, LayoutPublico } from '@/components/layout/LayoutPublico'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { IDIOMAS, type Idioma } from '@/i18n'
import { CLAVE_SESION } from '@/hooks/useSesion'

const NOMBRE_IDIOMA: Record<Idioma, string> = {
  'pt-BR': 'Português',
  es: 'Español',
  en: 'English',
}

export const Route = createFileRoute('/registro')({ component: Registro })

export function Registro() {
  const { t } = useTranslation('auth')
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [email, setEmail] = useState('')
  const [contrasena, setContrasena] = useState('')
  const [nombreEmpresa, setNombreEmpresa] = useState('')
  const [idioma, setIdioma] = useState<Idioma>('pt-BR')
  const [error, setError] = useState<ErrorApi | null>(null)
  const [enviando, setEnviando] = useState(false)

  async function enviar(evento: FormEvent) {
    evento.preventDefault()
    setError(null)
    setEnviando(true)
    try {
      const { data, error: errorApi } = await cliente.POST('/auth/registro', {
        body: { email, contrasena, nombre_empresa: nombreEmpresa, idioma },
      })
      if (errorApi) {
        setError(aErrorApi(errorApi))
        return
      }
      queryClient.setQueryData(CLAVE_SESION, data)
      void navigate({ to: '/proyectos' })
    } catch {
      setError(aErrorApi(null))
    } finally {
      setEnviando(false)
    }
  }

  return (
    <LayoutPublico>
      <EncabezadoAuth titulo={t('registro.titulo')} subtitulo={t('registro.subtitulo')} />
      <form onSubmit={enviar} className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="nombre_empresa">{t('registro.nombre_empresa')}</Label>
          <Input
            id="nombre_empresa"
            autoComplete="organization"
            required
            value={nombreEmpresa}
            onChange={(evento) => setNombreEmpresa(evento.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="email">{t('registro.email')}</Label>
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
          <Label htmlFor="contrasena">{t('registro.contrasena')}</Label>
          <Input
            id="contrasena"
            type="password"
            autoComplete="new-password"
            required
            value={contrasena}
            onChange={(evento) => setContrasena(evento.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="idioma">{t('registro.idioma')}</Label>
          <select
            id="idioma"
            value={idioma}
            onChange={(evento) => setIdioma(evento.target.value as Idioma)}
            className="flex h-10 w-full rounded-md border border-input bg-card px-3 py-1 text-sm shadow-xs"
          >
            {IDIOMAS.map((opcion) => (
              <option key={opcion} value={opcion}>
                {NOMBRE_IDIOMA[opcion]}
              </option>
            ))}
          </select>
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
          {enviando ? t('registro.enviando') : t('registro.enviar')}
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-muted-foreground">
        {t('registro.con_cuenta')}{' '}
        <Link to="/login" className="rounded-sm font-medium text-primary hover:underline">
          {t('registro.iniciar')}
        </Link>
      </p>
    </LayoutPublico>
  )
}
