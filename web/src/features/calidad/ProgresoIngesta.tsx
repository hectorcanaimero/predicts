import { useTranslation } from 'react-i18next'

import type { EstadoConexionSSE, EventoTrabajo } from '@/hooks/useEventosTrabajo'

interface Props {
  eventos: EventoTrabajo[]
  conexion: EstadoConexionSSE
}

/** Progreso 2D simple (spec F6.2.T2): la última etapa recibida y sus contadores, nada de
 * animaciones ni gráficos — eso lo cubre el informe de calidad una vez termina. */
export function ProgresoIngesta({ eventos, conexion }: Props) {
  const { t } = useTranslation('calidad')
  const ultimo = eventos[eventos.length - 1]

  return (
    <div className="space-y-2" aria-live="polite">
      <h2 className="text-lg font-medium">{t('progreso.titulo')}</h2>
      {!ultimo && (
        <p className="text-muted-foreground">
          {conexion === 'conectando' ? t('progreso.conectando') : t('progreso.esperando')}
        </p>
      )}
      {ultimo && (
        <div className="space-y-1">
          <p>{t('progreso.etapa', { etapa: ultimo.etapa })}</p>
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
