import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { aErrorApi, claveError, cliente, type ErrorApi } from '@/api/cliente'
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
    const { data, error: errorApi } = await cliente.POST('/auth/registro', {
      body: { email, contrasena, nombre_empresa: nombreEmpresa, idioma },
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
      <h1 className="text-xl font-semibold">{t('registro.titulo')}</h1>
      <div className="space-y-1">
        <Label htmlFor="nombre_empresa">{t('registro.nombre_empresa')}</Label>
        <Input
          id="nombre_empresa"
          required
          value={nombreEmpresa}
          onChange={(evento) => setNombreEmpresa(evento.target.value)}
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor="email">{t('registro.email')}</Label>
        <Input
          id="email"
          type="email"
          required
          value={email}
          onChange={(evento) => setEmail(evento.target.value)}
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor="contrasena">{t('registro.contrasena')}</Label>
        <Input
          id="contrasena"
          type="password"
          required
          value={contrasena}
          onChange={(evento) => setContrasena(evento.target.value)}
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor="idioma">{t('registro.idioma')}</Label>
        <select
          id="idioma"
          value={idioma}
          onChange={(evento) => setIdioma(evento.target.value as Idioma)}
          className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
        >
          {IDIOMAS.map((opcion) => (
            <option key={opcion} value={opcion}>
              {NOMBRE_IDIOMA[opcion]}
            </option>
          ))}
        </select>
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
        {enviando ? t('registro.enviando') : t('registro.enviar')}
      </Button>
      <div className="text-sm">
        <Link to="/login">{t('registro.ya_tengo_cuenta')}</Link>
      </div>
    </form>
  )
}
