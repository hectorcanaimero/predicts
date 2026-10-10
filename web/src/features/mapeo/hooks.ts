import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { aErrorApi, cliente, type ErrorApi } from '@/api/cliente'
import type { components } from '@/api/schema'
import type { Deteccion } from './tipos'

export type Dataset = Omit<components['schemas']['DatasetSalida'], 'deteccion'> & {
  deteccion: Deteccion | null
}
export type Sugerencias = components['schemas']['Sugerencias']
export type MapeoEntrada = components['schemas']['MapeoEntrada']
export type ConfirmarMapeoSalida = components['schemas']['ConfirmarMapeoSalida']
export type IngestaSalida = components['schemas']['IngestaSalida']
export type PlantillaMapeoSalida = components['schemas']['PlantillaMapeoSalida']

export const claveDataset = (datasetId: string) => ['datasets', datasetId] as const
export const claveSugerenciasMapeo = (datasetId: string) => ['datasets', datasetId, 'mapeo'] as const

export function useDataset(datasetId: string) {
  return useQuery<Dataset, ErrorApi>({
    queryKey: claveDataset(datasetId),
    queryFn: async () => {
      const { data, error } = await cliente.GET('/datasets/{dataset_id}', {
        params: { path: { dataset_id: datasetId } },
      })
      if (error) throw aErrorApi(error)
      return data as unknown as Dataset
    },
    retry: false,
  })
}

export function useSugerenciasMapeo(datasetId: string) {
  return useQuery<Sugerencias, ErrorApi>({
    queryKey: claveSugerenciasMapeo(datasetId),
    queryFn: async () => {
      const { data, error } = await cliente.GET('/datasets/{dataset_id}/mapeo', {
        params: { path: { dataset_id: datasetId } },
      })
      if (error) throw aErrorApi(error)
      return data
    },
    retry: false,
  })
}

export function useConfirmarMapeo(datasetId: string) {
  const queryClient = useQueryClient()
  return useMutation<ConfirmarMapeoSalida, ErrorApi, MapeoEntrada>({
    mutationFn: async (entrada) => {
      const { data, error } = await cliente.PUT('/datasets/{dataset_id}/mapeo', {
        params: { path: { dataset_id: datasetId } },
        body: entrada,
      })
      if (error) throw aErrorApi(error)
      return data
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: claveDataset(datasetId) }),
  })
}

export function useIniciarIngesta(datasetId: string) {
  return useMutation<IngestaSalida, ErrorApi, void>({
    mutationFn: async () => {
      const { data, error } = await cliente.POST('/datasets/{dataset_id}/ingesta', {
        params: { path: { dataset_id: datasetId } },
      })
      if (error) throw aErrorApi(error)
      return data
    },
  })
}
