import { lazy, Suspense, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Skeleton } from '@/components/ui/skeleton'
import { Dispersion2D } from './Dispersion2D'
import { FiltroEstados } from './FiltroEstados'
import { useUniverso } from './hooks'
import { PanelHistorial } from './PanelHistorial'
import { clientesAPuntos, ESTADOS, type Estado } from './transformaciones'

// Chunk aparte (no se descarga `three`/`@react-three/fiber` salvo cuando realmente se monta la
// escena), igual que `EscenaProcesamiento` en F8.1.T1.
const EscenaUniverso = lazy(() => import('./EscenaUniverso'))

const CONSULTA_MOVIMIENTO_REDUCIDO = '(prefers-reduced-motion: reduce)'

/** Igual que `VistaProcesamiento` (F8.1.T1): si no se puede saber la preferencia, se asume que
 * sí hay que reducir el movimiento. Vive acá (no se reutiliza la de `VistaProcesamiento`) porque
 * ese archivo es de F6.3.T1/F8.1.T1 y esta tarea no debe modificarlo. */
function usePrefiereMovimientoReducido(): boolean {
  const [reducido, setReducido] = useState(() =>
    typeof matchMedia === 'function' ? matchMedia(CONSULTA_MOVIMIENTO_REDUCIDO).matches : true,
  )

  useEffect(() => {
    if (typeof matchMedia !== 'function') return undefined
    const consulta = matchMedia(CONSULTA_MOVIMIENTO_REDUCIDO)
    const actualizar = () => setReducido(consulta.matches)
    actualizar()
    consulta.addEventListener('change', actualizar)
    return () => consulta.removeEventListener('change', actualizar)
  }, [])

  return reducido
}

interface Props {
  analisisId: string
}

/** Pantalla "Universo" de resultados (spec F8.2.T2): nube 3D con respaldo 2D (Recharts) cuando el
 * usuario prefiere menos movimiento o mientras se descarga el chunk de la escena, filtro/leyenda
 * por estado compartidos entre ambas vistas, y panel lateral con el historial del cliente
 * seleccionado. */
export function VistaUniverso({ analisisId }: Props) {
  const { t } = useTranslation('universo')
  const universo = useUniverso(analisisId)
  const [visibles, setVisibles] = useState<Set<Estado>>(() => new Set(ESTADOS))
  const [seleccionado, setSeleccionado] = useState<string | null>(null)
  const movimientoReducido = usePrefiereMovimientoReducido()

  if (universo.isLoading) return <Skeleton className="h-96 w-full" />
  if (universo.isError) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {t('error_generico')}
      </p>
    )
  }
  if (!universo.data || universo.data.length === 0) {
    return <p className="text-muted-foreground">{t('vacio')}</p>
  }

  const puntos = clientesAPuntos(universo.data).filter((p) => visibles.has(p.estado))

  function alternarEstado(estado: Estado, visible: boolean) {
    setVisibles((actual) => {
      const copia = new Set(actual)
      if (visible) copia.add(estado)
      else copia.delete(estado)
      return copia
    })
  }

  return (
    <div className="space-y-3">
      <FiltroEstados visibles={visibles} onCambiar={alternarEstado} />
      {movimientoReducido ? (
        <Dispersion2D puntos={puntos} onSeleccionar={setSeleccionado} />
      ) : (
        <Suspense fallback={<Dispersion2D puntos={puntos} onSeleccionar={setSeleccionado} />}>
          <EscenaUniverso puntos={puntos} onSeleccionar={setSeleccionado} />
        </Suspense>
      )}
      {seleccionado && (
        <PanelHistorial
          analisisId={analisisId}
          clienteId={seleccionado}
          onCerrar={() => setSeleccionado(null)}
        />
      )}
    </div>
  )
}
