import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { aErrorApi, cliente, type ErrorApi } from '@/api/cliente'
import type { components } from '@/api/schema'

export type Proyecto = components['schemas']['ProyectoSalida']
export type DemoSalida = components['schemas']['DemoSalida']
export type Dataset = components['schemas']['DatasetSalida']
export type Analisis = components['schemas']['AnalisisSalida']
export type ProyectoEntrada = components['schemas']['ProyectoEntrada']
export type ProyectoActualizar = components['schemas']['ProyectoActualizar']

export const CLAVE_PROYECTOS = ['proyectos'] as const
export const claveProyecto = (proyectoId: string) => ['proyectos', proyectoId] as const
export const claveDatasets = (proyectoId: string) => ['proyectos', proyectoId, 'datasets'] as const
export const claveAnalisis = (datasetId: string) => ['datasets', datasetId, 'analisis'] as const

export function useProyectos() {
  return useQuery<Proyecto[], ErrorApi>({
    queryKey: CLAVE_PROYECTOS,
    queryFn: async () => {
      const { data, error } = await cliente.GET('/proyectos')
      if (error) throw aErrorApi(error)
      return data
    },
    retry: false,
  })
}

export function useProyecto(proyectoId: string) {
  return useQuery<Proyecto, ErrorApi>({
    queryKey: claveProyecto(proyectoId),
    queryFn: async () => {
      const { data, error } = await cliente.GET('/proyectos/{proyecto_id}', {
        params: { path: { proyecto_id: proyectoId } },
      })
      if (error) throw aErrorApi(error)
      return data
    },
    retry: false,
  })
}

export function useDatasetsProyecto(proyectoId: string) {
  return useQuery<Dataset[], ErrorApi>({
    queryKey: claveDatasets(proyectoId),
    queryFn: async () => {
      const { data, error } = await cliente.GET('/proyectos/{proyecto_id}/datasets', {
        params: { path: { proyecto_id: proyectoId } },
      })
      if (error) throw aErrorApi(error)
      return data
    },
    retry: false,
  })
}

export function useAnalisisDataset(datasetId: string) {
  return useQuery<Analisis[], ErrorApi>({
    queryKey: claveAnalisis(datasetId),
    queryFn: async () => {
      const { data, error } = await cliente.GET('/datasets/{dataset_id}/analisis', {
        params: { path: { dataset_id: datasetId } },
      })
      if (error) throw aErrorApi(error)
      return data
    },
    retry: false,
  })
}

export function useCrearProyecto() {
  const queryClient = useQueryClient()
  return useMutation<Proyecto, ErrorApi, ProyectoEntrada>({
    mutationFn: async (datos) => {
      const { data, error } = await cliente.POST('/proyectos', { body: datos })
      if (error) throw aErrorApi(error)
      return data
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: CLAVE_PROYECTOS }),
  })
}

export function useCrearDemo() {
  const queryClient = useQueryClient()
  return useMutation<DemoSalida, ErrorApi, void>({
    mutationFn: async () => {
      const { data, error } = await cliente.POST('/demo')
      if (error) throw aErrorApi(error)
      return data
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: CLAVE_PROYECTOS }),
  })
}

export function useActualizarProyecto(proyectoId: string) {
  const queryClient = useQueryClient()
  return useMutation<Proyecto, ErrorApi, ProyectoActualizar>({
    mutationFn: async (datos) => {
      const { data, error } = await cliente.PATCH('/proyectos/{proyecto_id}', {
        params: { path: { proyecto_id: proyectoId } },
        body: datos,
      })
      if (error) throw aErrorApi(error)
      return data
    },
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PROYECTOS })
      queryClient.setQueryData(claveProyecto(proyectoId), data)
    },
  })
}

export function useBorrarProyecto() {
  const queryClient = useQueryClient()
  return useMutation<void, ErrorApi, string>({
    mutationFn: async (proyectoId) => {
      const { error } = await cliente.DELETE('/proyectos/{proyecto_id}', {
        params: { path: { proyecto_id: proyectoId } },
      })
      if (error) throw aErrorApi(error)
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: CLAVE_PROYECTOS }),
  })
}
