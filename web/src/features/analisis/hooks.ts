import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { aErrorApi, cliente, type ErrorApi } from '@/api/cliente'
import type { components } from '@/api/schema'
import type { ParametrosFormulario } from './tipos'

export type AnalisisSalida = components['schemas']['AnalisisSalida']
export type TrabajoSalida = components['schemas']['TrabajoSalida']

const INTERVALO_SONDEO_ANALISIS_MS = 2000

export const claveAnalisis = (analisisId: string) => ['analisis', analisisId] as const
export const claveTrabajo = (trabajoId: string) => ['trabajos', trabajoId] as const

function parametrosEntrada(parametros: ParametrosFormulario) {
  return {
    desde: parametros.desde || null,
    hasta: parametros.hasta || null,
    min_compras: parametros.minCompras,
    horizonte: parametros.horizonte,
    umbral: parametros.umbral,
  }
}

export function useLanzarAnalisis(datasetId: string) {
  return useMutation<AnalisisSalida, ErrorApi, { tipos: string[]; parametros: ParametrosFormulario }>({
    mutationFn: async ({ tipos, parametros }) => {
      const { data, error } = await cliente.POST('/datasets/{dataset_id}/analisis', {
        params: { path: { dataset_id: datasetId } },
        body: { tipos, parametros: parametrosEntrada(parametros) },
      })
      if (error) throw aErrorApi(error)
      return data
    },
  })
}

export function useSubirListaOfertas(datasetId: string) {
  return useMutation<{ productos: number }, ErrorApi, File>({
    mutationFn: async (archivo) => {
      const formData = new FormData()
      formData.append('archivo', archivo)
      const { data, error } = await cliente.POST('/datasets/{dataset_id}/ofertas', {
        params: { path: { dataset_id: datasetId } },
        body: formData as unknown as { archivo: string },
      })
      if (error) throw aErrorApi(error)
      return data
    },
  })
}

/** Estado del análisis; se sondea mientras esté en curso para saber cuándo pasar a resultados
 * incluso si la conexión SSE del progreso se perdió. */
export function useAnalisis(analisisId: string) {
  return useQuery<AnalisisSalida, ErrorApi>({
    queryKey: claveAnalisis(analisisId),
    queryFn: async () => {
      const { data, error } = await cliente.GET('/analisis/{analisis_id}', {
        params: { path: { analisis_id: analisisId } },
      })
      if (error) throw aErrorApi(error)
      return data
    },
    retry: false,
    refetchInterval: (query) =>
      query.state.data && ['en_cola', 'corriendo'].includes(query.state.data.estado)
        ? INTERVALO_SONDEO_ANALISIS_MS
        : false,
  })
}

/** Solo para leer `error_codigo` una vez que el SSE del trabajo informó la etapa `error`. */
export function useTrabajo(trabajoId: string | null, habilitado: boolean) {
  return useQuery<TrabajoSalida, ErrorApi>({
    queryKey: claveTrabajo(trabajoId ?? ''),
    queryFn: async () => {
      const { data, error } = await cliente.GET('/trabajos/{trabajo_id}', {
        params: { path: { trabajo_id: trabajoId as string } },
      })
      if (error) throw aErrorApi(error)
      return data
    },
    enabled: habilitado && !!trabajoId,
    retry: false,
  })
}

export function useCancelarTrabajo() {
  const queryClient = useQueryClient()
  return useMutation<void, ErrorApi, string>({
    mutationFn: async (trabajoId) => {
      const { error } = await cliente.POST('/trabajos/{trabajo_id}/cancelar', {
        params: { path: { trabajo_id: trabajoId } },
      })
      if (error) throw aErrorApi(error)
    },
    onSuccess: (_datos, trabajoId) =>
      void queryClient.invalidateQueries({ queryKey: claveTrabajo(trabajoId) }),
  })
}
