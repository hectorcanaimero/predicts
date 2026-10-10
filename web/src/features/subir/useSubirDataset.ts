import { useCallback, useRef, useState } from 'react'

import { aErrorApi, ErrorApi } from '@/api/cliente'
import {
  type ControladorSubida,
  type Dataset,
  type ProgresoSubida,
  SubidaCancelada,
  subirDataset,
} from './subida'

export type EstadoSubida = 'inicial' | 'subiendo' | 'error' | 'listo'

export function useSubirDataset(proyectoId: string) {
  const [estado, setEstado] = useState<EstadoSubida>('inicial')
  const [progreso, setProgreso] = useState<ProgresoSubida>({ cargado: 0, total: 0 })
  const [error, setError] = useState<ErrorApi | null>(null)
  const [dataset, setDataset] = useState<Dataset | null>(null)
  const controladorRef = useRef<ControladorSubida | null>(null)

  const iniciar = useCallback(
    (archivo: File) => {
      setError(null)
      setEstado('subiendo')
      setProgreso({ cargado: 0, total: archivo.size })
      const controlador = subirDataset(proyectoId, archivo, setProgreso)
      controladorRef.current = controlador
      controlador.promesa
        .then((resultado) => {
          setDataset(resultado)
          setEstado('listo')
        })
        .catch((err: unknown) => {
          if (err instanceof SubidaCancelada) {
            setEstado('inicial')
            return
          }
          setError(err instanceof ErrorApi ? err : aErrorApi(err))
          setEstado('error')
        })
    },
    [proyectoId],
  )

  const cancelar = useCallback(() => controladorRef.current?.cancelar(), [])

  const reiniciar = useCallback(() => {
    setEstado('inicial')
    setError(null)
    setDataset(null)
  }, [])

  return { estado, progreso, error, dataset, iniciar, cancelar, reiniciar }
}
