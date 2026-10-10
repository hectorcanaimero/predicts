import { Bot, CircleAlert, MessageSquareText, SendHorizontal, TriangleAlert, UserRound } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { claveError } from '@/api/cliente'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ComoLoCalcule } from './ComoLoCalcule'
import { usePreguntarAgente, type ConsultaAgente, type MensajeHistorial } from './hooks'

interface MensajeChat {
  id: string
  rol: 'usuario' | 'agente'
  contenido: string
  consultas?: ConsultaAgente[]
  advertencias?: string[]
  codigoError?: string
}

// El backend trunca a 20 (`MensajeHistorial`, ver `api/src/predicts/api/agente.py`).
const MAX_HISTORIAL = 20

interface Props {
  datasetId: string
}

function AvatarAgente() {
  return (
    <span
      aria-hidden="true"
      className="inline-flex size-8 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground"
    >
      <Bot className="size-4" />
    </span>
  )
}

export function ChatAgente({ datasetId }: Props) {
  const { t } = useTranslation('agente')
  const [mensajes, setMensajes] = useState<MensajeChat[]>([])
  const [pregunta, setPregunta] = useState('')
  const preguntar = usePreguntarAgente(datasetId)
  const idEntrada = useId()
  const finRef = useRef<HTMLDivElement>(null)

  const sugerencias = t('sugerencias', { returnObjects: true }) as string[]

  useEffect(() => {
    finRef.current?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' })
  }, [mensajes.length, preguntar.isPending])

  function enviar(texto: string) {
    const limpio = texto.trim()
    if (!limpio || preguntar.isPending) return

    const historial: MensajeHistorial[] = mensajes
      .filter((m) => !m.codigoError)
      .slice(-MAX_HISTORIAL)
      .map((m) => ({ rol: m.rol, contenido: m.contenido }))

    setMensajes((actuales) => [...actuales, { id: crypto.randomUUID(), rol: 'usuario', contenido: limpio }])
    setPregunta('')

    preguntar.mutate(
      { pregunta: limpio, historial },
      {
        onSuccess: (respuesta) => {
          setMensajes((actuales) => [
            ...actuales,
            {
              id: crypto.randomUUID(),
              rol: 'agente',
              contenido: respuesta.respuesta,
              consultas: respuesta.consultas,
              advertencias: respuesta.advertencias,
            },
          ])
        },
        onError: (error) => {
          setMensajes((actuales) => [
            ...actuales,
            { id: crypto.randomUUID(), rol: 'agente', contenido: '', codigoError: claveError(error) },
          ])
        },
      },
    )
  }

  return (
    <div className="flex h-[min(44rem,calc(100dvh-16rem))] min-h-[28rem] flex-col overflow-hidden rounded-xl border bg-card shadow-xs">
      <div className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        {mensajes.length === 0 && (
          <div className="mx-auto flex max-w-xl flex-col items-center py-6 text-center">
            <span className="inline-flex size-12 items-center justify-center rounded-full bg-accent text-accent-foreground">
              <MessageSquareText aria-hidden="true" className="size-5" />
            </span>
            <h2 className="mt-4 text-lg font-semibold tracking-tight">{t('vacio_titulo')}</h2>
            <p className="mt-1 text-sm text-muted-foreground">{t('sugerencias_titulo')}</p>
            <div className="mt-5 grid w-full gap-2 sm:grid-cols-2">
              {sugerencias.map((texto) => (
                <Button
                  key={texto}
                  variant="outline"
                  className="h-auto justify-start whitespace-normal px-3 py-2.5 text-left font-normal"
                  onClick={() => enviar(texto)}
                >
                  {texto}
                </Button>
              ))}
            </div>
          </div>
        )}

        <ul className="space-y-5">
          {mensajes.map((mensaje) =>
            mensaje.rol === 'usuario' ? (
              <li key={mensaje.id} className="flex items-start justify-end gap-3">
                <div className="max-w-[85%] rounded-2xl rounded-tr-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground">
                  <p className="whitespace-pre-wrap">{mensaje.contenido}</p>
                </div>
                <span
                  aria-hidden="true"
                  className="hidden size-8 shrink-0 items-center justify-center rounded-full bg-accent text-accent-foreground sm:inline-flex"
                >
                  <UserRound className="size-4" />
                </span>
              </li>
            ) : (
              <li key={mensaje.id} className="flex items-start gap-3">
                <AvatarAgente />
                <div className="min-w-0 max-w-[85%] space-y-2 rounded-2xl rounded-tl-sm border bg-background px-4 py-2.5 text-sm">
                  {mensaje.codigoError ? (
                    <p role="alert" className="flex items-start gap-2 text-danger">
                      <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
                      {t(`errores.${mensaje.codigoError}`, { defaultValue: t('comun:error_generico') })}
                    </p>
                  ) : (
                    <>
                      <p className="whitespace-pre-wrap leading-relaxed">{mensaje.contenido}</p>
                      {mensaje.advertencias && mensaje.advertencias.length > 0 && (
                        <ul
                          role="alert"
                          className="space-y-1 rounded-md bg-warning-soft px-3 py-2 text-xs text-warning"
                        >
                          {mensaje.advertencias.map((advertencia, indice) => (
                            <li key={indice} className="flex items-start gap-1.5">
                              <TriangleAlert aria-hidden="true" className="mt-px size-3.5 shrink-0" />
                              <span>{advertencia}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                      {mensaje.consultas && <ComoLoCalcule consultas={mensaje.consultas} />}
                    </>
                  )}
                </div>
              </li>
            ),
          )}
          {preguntar.isPending && (
            <li className="flex items-center gap-3">
              <AvatarAgente />
              <span className="flex items-center gap-2 rounded-2xl rounded-tl-sm border bg-background px-4 py-3 text-sm text-muted-foreground">
                <span aria-hidden="true" className="flex gap-1">
                  <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground/60 motion-reduce:animate-none" />
                  <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground/60 [animation-delay:150ms] motion-reduce:animate-none" />
                  <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground/60 [animation-delay:300ms] motion-reduce:animate-none" />
                </span>
                {t('pensando')}
              </span>
            </li>
          )}
        </ul>
        <div ref={finRef} />
      </div>

      <form
        className="flex gap-2 border-t bg-background/60 p-3 sm:p-4"
        onSubmit={(e) => {
          e.preventDefault()
          enviar(pregunta)
        }}
      >
        <label htmlFor={idEntrada} className="sr-only">
          {t('entrada_etiqueta')}
        </label>
        <Input
          id={idEntrada}
          value={pregunta}
          onChange={(e) => setPregunta(e.target.value)}
          placeholder={t('entrada_placeholder')}
          disabled={preguntar.isPending}
          className="h-11"
        />
        <Button
          type="submit"
          size="lg"
          className="h-11 px-4"
          aria-label={t('enviar')}
          disabled={preguntar.isPending || !pregunta.trim()}
        >
          <SendHorizontal aria-hidden="true" />
          <span aria-hidden="true" className="hidden sm:inline">
            {t('enviar')}
          </span>
        </Button>
      </form>
    </div>
  )
}
