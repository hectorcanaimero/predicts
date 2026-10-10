import { createFileRoute, Link } from '@tanstack/react-router'
import { ArrowLeft, MailCheck } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { aErrorApi, claveError, cliente, type ErrorApi } from '@/api/cliente'
import { AlertaFormulario, EncabezadoAuth, LayoutPublico } from '@/components/layout/LayoutPublico'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

export const Route = createFileRoute('/recuperar')({ component: Recuperar })

function VolverALogin({ texto }: { texto: string }) {
  return (
    <Link
      to="/login"
      className="mt-6 inline-flex items-center gap-1.5 rounded-sm text-sm font-medium text-primary hover:underline"
    >
      <ArrowLeft aria-hidden="true" className="size-4" />
      {texto}
    </Link>
  )
}

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
    try {
      const { error: errorApi } = await cliente.POST('/auth/recuperar', { body: { email } })
      if (errorApi) {
        setError(aErrorApi(errorApi))
        return
      }
      setEnviado(true)
    } catch {
      setError(aErrorApi(null))
    } finally {
      setEnviando(false)
    }
  }

  if (enviado) {
    return (
      <LayoutPublico>
        <div className="space-y-4">
          <span className="inline-flex size-11 items-center justify-center rounded-full bg-success-soft text-success">
            <MailCheck aria-hidden="true" className="size-5" />
          </span>
          <h1 className="text-2xl font-semibold tracking-tight">{t('recuperar.titulo')}</h1>
          <p role="status" className="text-sm text-muted-foreground">
            {t('recuperar.enviado')}
          </p>
        </div>
        <VolverALogin texto={t('recuperar.volver')} />
      </LayoutPublico>
    )
  }

  return (
    <LayoutPublico>
      <EncabezadoAuth titulo={t('recuperar.titulo')} subtitulo={t('recuperar.subtitulo')} />
      <form onSubmit={enviar} className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="email">{t('recuperar.email')}</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(evento) => setEmail(evento.target.value)}
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
          {enviando ? t('recuperar.enviando') : t('recuperar.enviar')}
        </Button>
      </form>
      <VolverALogin texto={t('recuperar.volver')} />
    </LayoutPublico>
  )
}
