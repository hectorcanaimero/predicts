import { useMutation } from '@tanstack/react-query'

import { aErrorApi, cliente, type ErrorApi } from '@/api/cliente'
import type { components } from '@/api/schema'

export type RespuestaAgente = components['schemas']['RespuestaSalida']
export type MensajeHistorial = components['schemas']['MensajeHistorial']
export type ConsultaAgente = components['schemas']['Consulta']

interface EntradaPregunta {
  pregunta: string
  historial: MensajeHistorial[]
}

/** `POST /agente/preguntas` (FR-22): el historial se manda tal cual lo acumula el chat en esta
 * sesión, no se persiste en el backend. */
export function usePreguntarAgente(datasetId: string) {
  return useMutation<RespuestaAgente, ErrorApi, EntradaPregunta>({
    mutationFn: async ({ pregunta, historial }) => {
      const { data, error } = await cliente.POST('/agente/preguntas', {
        body: { dataset_id: datasetId, pregunta, historial },
      })
      if (error) throw aErrorApi(error)
      return data
    },
  })
}
