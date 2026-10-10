import { lazy, Suspense, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Progress } from '@/components/ui/progress'
import type { EstadoConexionSSE, EventoTrabajo } from '@/hooks/useEventosTrabajo'

interface Props {
  eventos: EventoTrabajo[]
  conexion: EstadoConexionSSE
}

// Chunk aparte (no se descarga `three`/`@react-three/fiber` salvo cuando realmente se monta la
// escena), ver done-criteria de F8.1.T1 sobre el bundle inicial.
const EscenaProcesamiento = lazy(() => import('@/tres/procesamiento/EscenaProcesamiento'))

const CONSULTA_MOVIMIENTO_REDUCIDO = '(prefers-reduced-motion: reduce)'

/** Si el usuario pidió menos movimiento en el sistema: la escena 3D no se monta y se queda con
 * la vista 2D de siempre. Si el entorno ni siquiera soporta `matchMedia` (no hay forma de saber
 * la preferencia), por las dudas se asume que sí hay que reducir el movimiento. */
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

/** Vista 2D de siempre (última etapa y contadores): respaldo cuando el usuario prefiere menos
 * movimiento, y lo que se ve mientras se descarga el chunk de la escena 3D. */
function Vista2D({ eventos, conexion }: Props) {
  const { t } = useTranslation('analisis')
  const ultimo = eventos[eventos.length - 1]

  return (
    <div className="space-y-2">
      {!ultimo && (
        <p className="text-muted-foreground">
          {conexion === 'conectando' ? t('progreso.conectando') : t('progreso.esperando')}
        </p>
      )}
      {ultimo && (
        <div className="space-y-2">
          <p>{t('progreso.etapa', { etapa: ultimo.etapa })}</p>
          {ultimo.progreso != null && <Progress value={ultimo.progreso * 100} />}
          {Object.entries(ultimo.contadores).length > 0 && (
            <ul className="text-sm text-muted-foreground">
              {Object.entries(ultimo.contadores).map(([clave, valor]) => (
                <li key={clave}>{t('progreso.contador', { clave, valor })}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

/** Contenedor del progreso de un análisis (spec F6.3.T1): la escena 3D de F8.1.T1 montada acá
 * mismo, con la vista 2D como respaldo (tanto con `prefers-reduced-motion` como mientras carga
 * el chunk de la escena), sin tocar el resto de la pantalla. */
export function VistaProcesamiento({ eventos, conexion }: Props) {
  const movimientoReducido = usePrefiereMovimientoReducido()

  return (
    <div className="space-y-2" aria-live="polite">
      {movimientoReducido ? (
        <Vista2D eventos={eventos} conexion={conexion} />
      ) : (
        <Suspense fallback={<Vista2D eventos={eventos} conexion={conexion} />}>
          <EscenaProcesamiento eventos={eventos} conexion={conexion} />
        </Suspense>
      )}
    </div>
  )
}
