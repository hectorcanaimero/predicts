import { useTranslation } from 'react-i18next'

import { Progress } from '@/components/ui/progress'
import type { EstadoConexionSSE, EventoTrabajo } from '@/hooks/useEventosTrabajo'

interface Props {
  eventos: EventoTrabajo[]
  conexion: EstadoConexionSSE
}

/** Contenedor del progreso de un análisis (spec F6.3.T1): hoy solo la vista 2D (última etapa y
 * contadores). La escena 3D llega en F8.1 montada acá mismo, sin tocar el resto de la pantalla. */
export function VistaProcesamiento({ eventos, conexion }: Props) {
  const { t } = useTranslation('analisis')
  const ultimo = eventos[eventos.length - 1]

  return (
    <div className="space-y-2" aria-live="polite">
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
