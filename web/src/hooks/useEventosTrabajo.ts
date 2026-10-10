import { useEffect, useRef, useState } from 'react'

import { URL_BASE_API } from '@/api/cliente'

export interface EventoTrabajo {
  etapa: string
  contadores: Record<string, number>
  progreso: number | null
}

export type EstadoConexionSSE = 'conectando' | 'abierta' | 'cerrada'

const REINTENTO_MS = 1000
const ETAPAS_FINALES = new Set(['listo', 'error'])

// `sse_starlette` (el servidor) termina cada línea y cada bloque en CRLF (`\r\n`, `\r\n\r\n`); un
// bloque separado solo por LF (`\n\n`) también es válido SSE y es lo que usan los tests con un
// stream falso (`calidad.test.tsx`), así que ambos formatos tienen que reconocerse.
const SEPARADOR_BLOQUE = /\r?\n\r?\n/

interface BloqueSSE {
  id?: string
  evento?: string
  datos?: string
}

function parsearBloque(bloque: string): BloqueSSE {
  const resultado: BloqueSSE = {}
  for (const linea of bloque.split(/\r?\n/)) {
    if (linea.startsWith('id:')) resultado.id = linea.slice(3).trim()
    else if (linea.startsWith('event:')) resultado.evento = linea.slice(6).trim()
    else if (linea.startsWith('data:')) resultado.datos = (resultado.datos ?? '') + linea.slice(5).trim()
  }
  return resultado
}

/** Progreso de un trabajo por SSE (`GET /trabajos/{id}/eventos`), con reconexión.
 *
 * No usa el `EventSource` nativo: sus nombres de evento (`etapa`) son dinámicos por tipo de
 * trabajo, y `EventSource` solo permite escuchar nombres conocidos de antemano (no hay
 * wildcard). En cambio, se lee el `ReadableStream` del `fetch` a mano, parseando `text/event-
 * stream` línea a línea, lo que además hace trivial simular la reconexión en los tests (un
 * `fetch` falso que corta el stream y abre uno nuevo).
 */
export function useEventosTrabajo(trabajoId: string | null | undefined) {
  const [eventos, setEventos] = useState<EventoTrabajo[]>([])
  const [conexion, setConexion] = useState<EstadoConexionSSE>('conectando')
  const ultimoIdRef = useRef<string | null>(null)

  useEffect(() => {
    if (!trabajoId) return undefined

    ultimoIdRef.current = null
    let activo = true
    let controlador: AbortController | null = null
    let temporizador: ReturnType<typeof setTimeout> | null = null

    async function conectar(primeraVez: boolean) {
      if (!activo) return
      controlador = new AbortController()
      setConexion('conectando')
      if (primeraVez) setEventos([])
      let terminado = false

      try {
        const cabeceras: Record<string, string> = {}
        if (ultimoIdRef.current) cabeceras['Last-Event-ID'] = ultimoIdRef.current
        const respuesta = await fetch(`${URL_BASE_API}/trabajos/${trabajoId}/eventos`, {
          headers: cabeceras,
          credentials: 'include',
          signal: controlador.signal,
        })
        if (!respuesta.body) throw new Error('sin cuerpo')
        if (!activo) return
        setConexion('abierta')

        const lector = respuesta.body.getReader()
        const decodificador = new TextDecoder()
        let buffer = ''
        while (activo) {
          const { done, value } = await lector.read()
          if (done) break
          buffer += decodificador.decode(value, { stream: true })
          const bloques = buffer.split(SEPARADOR_BLOQUE)
          buffer = bloques.pop() ?? ''
          for (const bloqueTexto of bloques) {
            const bloque = parsearBloque(bloqueTexto)
            if (!bloque.evento) continue
            if (bloque.id) ultimoIdRef.current = bloque.id
            const datos = bloque.datos ? (JSON.parse(bloque.datos) as Record<string, unknown>) : {}
            setEventos((anteriores) => [
              ...anteriores,
              {
                etapa: bloque.evento as string,
                contadores: (datos.contadores as Record<string, number>) ?? {},
                progreso: (datos.progreso as number | null | undefined) ?? null,
              },
            ])
            if (ETAPAS_FINALES.has(bloque.evento)) terminado = true
          }
        }
      } catch {
        // red caída o fetch abortado por el cleanup: cae al reintento de abajo salvo que ya
        // no esté activo
      }

      if (!activo) return
      if (terminado) {
        setConexion('cerrada')
        return
      }
      temporizador = setTimeout(() => void conectar(false), REINTENTO_MS)
    }

    void conectar(true)

    return () => {
      activo = false
      controlador?.abort()
      if (temporizador) clearTimeout(temporizador)
    }
  }, [trabajoId])

  return { eventos, conexion }
}
