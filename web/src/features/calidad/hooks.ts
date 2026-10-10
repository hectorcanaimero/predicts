import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { aErrorApi, cliente, type ErrorApi } from '@/api/cliente'
import type { components } from '@/api/schema'
import type { InformeCalidad } from './tipos'

export type Producto = components['schemas']['ProductoSalida']
export type CorregirProductoEntrada = components['schemas']['CorregirProductoEntrada']
export type Grupo = components['schemas']['GrupoSalida']

const INTERVALO_SONDEO_CALIDAD_MS = 2000

export const claveCalidad = (datasetId: string) => ['datasets', datasetId, 'calidad'] as const
export const claveProductosARevisar = (datasetId: string) =>
  ['datasets', datasetId, 'productos', 'revisar'] as const
export const CLAVE_GRUPOS_PROPUESTOS = ['productos', 'grupos', 'propuesto'] as const

/** El informe lo llena un trabajo `calidad` encolado después de la `ingesta` (ver
 * `trabajos/tipos_datos.py`); no hay un segundo `trabajo_id` para seguirlo por SSE, así que
 * mientras no haya informe se sondea cada par de segundos. */
export function useCalidad(datasetId: string, habilitado: boolean) {
  return useQuery<InformeCalidad, ErrorApi>({
    queryKey: claveCalidad(datasetId),
    queryFn: async () => {
      const { data, error } = await cliente.GET('/datasets/{dataset_id}/calidad', {
        params: { path: { dataset_id: datasetId } },
      })
      if (error) throw aErrorApi(error)
      return data as unknown as InformeCalidad
    },
    enabled: habilitado,
    retry: false,
    refetchInterval: (query) => (query.state.data ? false : INTERVALO_SONDEO_CALIDAD_MS),
  })
}

export function useProductosARevisar(datasetId: string) {
  return useQuery<Producto[], ErrorApi>({
    queryKey: claveProductosARevisar(datasetId),
    queryFn: async () => {
      const { data, error } = await cliente.GET('/datasets/{dataset_id}/productos', {
        params: { path: { dataset_id: datasetId }, query: { estado: 'revisar' } },
      })
      if (error) throw aErrorApi(error)
      return data
    },
    retry: false,
  })
}

export function useCorregirProducto(datasetId: string) {
  const queryClient = useQueryClient()
  return useMutation<Producto, ErrorApi, { productoId: string; datos: CorregirProductoEntrada }>({
    mutationFn: async ({ productoId, datos }) => {
      const { data, error } = await cliente.PATCH('/productos/{producto_id}', {
        params: { path: { producto_id: productoId } },
        body: datos,
      })
      if (error) throw aErrorApi(error)
      return data
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: claveProductosARevisar(datasetId) }),
  })
}

export function useGruposPropuestos() {
  return useQuery<Grupo[], ErrorApi>({
    queryKey: CLAVE_GRUPOS_PROPUESTOS,
    queryFn: async () => {
      const { data, error } = await cliente.GET('/productos/grupos', {
        params: { query: { estado: 'propuesto' } },
      })
      if (error) throw aErrorApi(error)
      return data
    },
    retry: false,
  })
}

export function useConfirmarGrupo() {
  const queryClient = useQueryClient()
  return useMutation<Grupo, ErrorApi, string>({
    mutationFn: async (grupoId) => {
      const { data, error } = await cliente.POST('/productos/grupos/{grupo_id}/confirmar', {
        params: { path: { grupo_id: grupoId } },
      })
      if (error) throw aErrorApi(error)
      return data
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: CLAVE_GRUPOS_PROPUESTOS }),
  })
}

export function useRechazarGrupo() {
  const queryClient = useQueryClient()
  return useMutation<Grupo, ErrorApi, string>({
    mutationFn: async (grupoId) => {
      const { data, error } = await cliente.POST('/productos/grupos/{grupo_id}/rechazar', {
        params: { path: { grupo_id: grupoId } },
      })
      if (error) throw aErrorApi(error)
      return data
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: CLAVE_GRUPOS_PROPUESTOS }),
  })
}
