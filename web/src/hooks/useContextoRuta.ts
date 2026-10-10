import { useQuery } from '@tanstack/react-query'
import { useParams } from '@tanstack/react-router'

import { aErrorApi, cliente } from '@/api/cliente'

interface ParamsRuta {
  proyectoId?: string
  datasetId?: string
  analisisId?: string
}

/** Contexto de la ruta actual para la navegación (barra lateral y migas): resuelve hacia arriba
 * análisis → dataset → proyecto con las mismas claves de caché que usan las pantallas
 * (`['analisis', id]`, `['datasets', id]`, `['proyectos', id]`), así no se repiten pedidos. */
export function useContextoRuta() {
  const params = useParams({ strict: false }) as ParamsRuta
  const analisisId = params.analisisId

  const analisis = useQuery({
    queryKey: ['analisis', analisisId ?? ''],
    queryFn: async () => {
      const { data, error } = await cliente.GET('/analisis/{analisis_id}', {
        params: { path: { analisis_id: analisisId as string } },
      })
      if (error) throw aErrorApi(error)
      return data
    },
    enabled: !!analisisId,
    retry: false,
  })

  const datasetId = params.datasetId ?? analisis.data?.dataset_id
  const dataset = useQuery({
    queryKey: ['datasets', datasetId ?? ''],
    queryFn: async () => {
      const { data, error } = await cliente.GET('/datasets/{dataset_id}', {
        params: { path: { dataset_id: datasetId as string } },
      })
      if (error) throw aErrorApi(error)
      return data
    },
    enabled: !!datasetId,
    retry: false,
  })

  const proyectoId = params.proyectoId ?? dataset.data?.proyecto_id
  const proyecto = useQuery({
    queryKey: ['proyectos', proyectoId ?? ''],
    queryFn: async () => {
      const { data, error } = await cliente.GET('/proyectos/{proyecto_id}', {
        params: { path: { proyecto_id: proyectoId as string } },
      })
      if (error) throw aErrorApi(error)
      return data
    },
    enabled: !!proyectoId,
    retry: false,
  })

  return {
    analisisId,
    datasetId,
    proyectoId,
    nombreProyecto: proyecto.data?.nombre,
    estadoAnalisis: analisis.data?.estado,
  }
}
