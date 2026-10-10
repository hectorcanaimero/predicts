import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { aErrorApi, cliente, type ErrorApi } from '@/api/cliente'
import type { components } from '@/api/schema'
import type { ResultadosPagina, Separador, TipoExportar, TipoResultado } from './tipos'

export type AnalisisSalida = components['schemas']['AnalisisSalida']
export type PlantillaSalida = components['schemas']['PlantillaSalida']

export const claveAnalisis = (analisisId: string) => ['analisis', analisisId] as const

/** Estado, `resumen` y `metricas` (backtest FR-16) de un análisis ya lanzado; en esta pantalla
 * siempre está `listo`, así que una sola consulta alcanza (sin `refetchInterval`). */
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
  })
}

export const claveResultados = (
  analisisId: string,
  tipo: TipoResultado,
  pagina: number,
  orden: string,
) => ['analisis', analisisId, 'resultados', tipo, pagina, orden] as const

export function useResultados<T>(
  analisisId: string,
  tipo: TipoResultado,
  pagina: number,
  tamPagina: number,
  orden: string,
) {
  return useQuery<ResultadosPagina<T>, ErrorApi>({
    queryKey: claveResultados(analisisId, tipo, pagina, orden),
    queryFn: async () => {
      const { data, error } = await cliente.GET('/analisis/{analisis_id}/resultados', {
        params: {
          path: { analisis_id: analisisId },
          query: { tipo, pagina, tam_pagina: tamPagina, orden },
        },
      })
      if (error) throw aErrorApi(error)
      return data as unknown as ResultadosPagina<T>
    },
    retry: false,
  })
}

export const clavePlantillas = (analisisId: string) => ['analisis', analisisId, 'plantillas'] as const

export function usePlantillas(analisisId: string) {
  return useQuery<PlantillaSalida[], ErrorApi>({
    queryKey: clavePlantillas(analisisId),
    queryFn: async () => {
      const { data, error } = await cliente.GET('/analisis/{analisis_id}/plantillas', {
        params: { path: { analisis_id: analisisId } },
      })
      if (error) throw aErrorApi(error)
      return data
    },
    retry: false,
  })
}

export function useEditarPlantilla(analisisId: string) {
  const queryClient = useQueryClient()
  return useMutation<PlantillaSalida, ErrorApi, { plantillaId: string; texto: string }>({
    mutationFn: async ({ plantillaId, texto }) => {
      const { data, error } = await cliente.PATCH('/plantillas-mensaje/{plantilla_id}', {
        params: { path: { plantilla_id: plantillaId } },
        body: { texto },
      })
      if (error) throw aErrorApi(error)
      return data
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: clavePlantillas(analisisId) }),
  })
}

export function useRegenerarPlantillas(analisisId: string) {
  const queryClient = useQueryClient()
  return useMutation<void, ErrorApi, void>({
    mutationFn: async () => {
      const { error } = await cliente.POST('/analisis/{analisis_id}/plantillas/regenerar', {
        params: { path: { analisis_id: analisisId } },
      })
      if (error) throw aErrorApi(error)
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: clavePlantillas(analisisId) }),
  })
}

function nombreDesdeCabecera(valor: string | null): string | null {
  return valor?.match(/filename="?([^";]+)"?/)?.[1] ?? null
}

/** Descarga el CSV del tipo pedido (ver `api/src/predicts/api/exportar.py`): usa el mismo
 * cliente que el resto de la app (CSRF/credenciales/401 ya resueltos por su middleware), solo
 * que con `parseAs: 'blob'`, y dispara la descarga del navegador con el nombre de archivo que
 * manda `Content-Disposition`. */
export function useExportar(analisisId: string) {
  return useMutation<void, ErrorApi, { tipo: TipoExportar; separador: Separador }>({
    mutationFn: async ({ tipo, separador }) => {
      const { data, error, response } = await cliente.GET('/analisis/{analisis_id}/exportar', {
        params: { path: { analisis_id: analisisId }, query: { tipo, separador } },
        parseAs: 'blob',
      })
      if (error) throw aErrorApi(error)
      const nombre = nombreDesdeCabecera(response.headers.get('content-disposition')) ?? `${tipo}.csv`
      const url = URL.createObjectURL(data as unknown as Blob)
      const enlace = document.createElement('a')
      enlace.href = url
      enlace.download = nombre
      document.body.appendChild(enlace)
      enlace.click()
      enlace.remove()
      URL.revokeObjectURL(url)
    },
  })
}
