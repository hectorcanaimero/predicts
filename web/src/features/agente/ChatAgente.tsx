import { useId, useState } from 'react'
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

export function ChatAgente({ datasetId }: Props) {
  const { t } = useTranslation('agente')
  const [mensajes, setMensajes] = useState<MensajeChat[]>([])
  const [pregunta, setPregunta] = useState('')
  const preguntar = usePreguntarAgente(datasetId)
  const idEntrada = useId()

  const sugerencias = t('sugerencias', { returnObjects: true }) as string[]

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
    <div className="space-y-4">
      {mensajes.length === 0 && (
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">{t('sugerencias_titulo')}</p>
          <div className="flex flex-wrap gap-2">
            {sugerencias.map((texto) => (
              <Button key={texto} variant="outline" size="sm" onClick={() => enviar(texto)}>
                {texto}
              </Button>
            ))}
          </div>
        </div>
      )}

      <ul className="space-y-3">
        {mensajes.map((mensaje) => (
          <li
            key={mensaje.id}
            className={mensaje.rol === 'usuario' ? 'flex justify-end' : 'flex justify-start'}
          >
            <div
              className={
                mensaje.rol === 'usuario'
                  ? 'max-w-[85%] rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground'
                  : 'max-w-[85%] space-y-2 rounded-md bg-muted px-3 py-2 text-sm'
              }
            >
              {mensaje.codigoError ? (
                <p role="alert" className="text-destructive">
                  {t(`errores.${mensaje.codigoError}`, { defaultValue: t('comun:error_generico') })}
                </p>
              ) : (
                <>
                  <p className="whitespace-pre-wrap">{mensaje.contenido}</p>
                  {mensaje.advertencias && mensaje.advertencias.length > 0 && (
                    <ul role="alert" className="space-y-1 text-xs text-destructive">
                      {mensaje.advertencias.map((advertencia, indice) => (
                        <li key={indice}>
                          <span aria-hidden="true">⚠ </span>
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
        ))}
        {preguntar.isPending && <p className="text-sm text-muted-foreground">{t('pensando')}</p>}
      </ul>

      <form
        className="flex gap-2"
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
        />
        <Button type="submit" disabled={preguntar.isPending || !pregunta.trim()}>
          {t('enviar')}
        </Button>
      </form>
    </div>
  )
}
