import { useQuery } from '@tanstack/react-query'

import { aErrorApi, cliente, type ErrorApi } from '@/api/cliente'
import type { components } from '@/api/schema'

export type ClienteUniverso = components['schemas']['ClienteUniverso']
export type HistorialCliente = components['schemas']['HistorialCliente']

/** Tope de la muestra pedida a la API: alcanza para una nube densa sin sobrecargar el
 * `InstancedMesh` ni el `ScatterChart` de respaldo (mismo criterio de "tope de partículas" que
 * `tres/procesamiento/mapeoEventos.ts`). */
const MAX_MUESTRA = 2000

export const claveUniverso = (analisisId: string) => ['analisis', analisisId, 'universo'] as const

export function useUniverso(analisisId: string) {
  return useQuery<ClienteUniverso[], ErrorApi>({
    queryKey: claveUniverso(analisisId),
    queryFn: async () => {
      const { data, error } = await cliente.GET('/analisis/{analisis_id}/universo', {
        params: { path: { analisis_id: analisisId }, query: { max: MAX_MUESTRA } },
      })
      if (error) throw aErrorApi(error)
      return data
    },
    retry: false,
  })
}

export const claveHistorialCliente = (analisisId: string, clienteId: string) =>
  ['analisis', analisisId, 'universo', clienteId] as const

/** Historial resumido de un cliente (F8.2.T1): solo se dispara cuando hay uno seleccionado en el
 * panel lateral. */
export function useHistorialCliente(analisisId: string, clienteId: string | null) {
  return useQuery<HistorialCliente, ErrorApi>({
    queryKey: claveHistorialCliente(analisisId, clienteId ?? ''),
    queryFn: async () => {
      const { data, error } = await cliente.GET('/analisis/{analisis_id}/universo/{cliente_id}', {
        params: { path: { analisis_id: analisisId, cliente_id: clienteId as string } },
      })
      if (error) throw aErrorApi(error)
      return data
    },
    enabled: clienteId != null,
    retry: false,
  })
}
