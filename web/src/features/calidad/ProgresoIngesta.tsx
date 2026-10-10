import { LoaderCircle } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type { EstadoConexionSSE, EventoTrabajo } from '@/hooks/useEventosTrabajo'

interface Props {
  eventos: EventoTrabajo[]
  conexion: EstadoConexionSSE
}

/** Progreso de la ingesta (spec F6.2.T2): la última etapa recibida y sus contadores; el informe
 * de calidad lo reemplaza una vez termina. */
export function ProgresoIngesta({ eventos, conexion }: Props) {
  const { t, i18n } = useTranslation('calidad')
  const ultimo = eventos[eventos.length - 1]
  const numero = new Intl.NumberFormat(i18n.language)

  return (
    <section aria-live="polite" className="space-y-4 rounded-xl border bg-card p-5 shadow-xs">
      <div className="flex items-center gap-3">
        <LoaderCircle aria-hidden="true" className="size-5 animate-spin text-primary motion-reduce:animate-none" />
        <div>
          <h2 className="font-semibold">{t('progreso.titulo')}</h2>
          <p className="text-sm text-muted-foreground">
            {ultimo
              ? t('progreso.etapa', { etapa: ultimo.etapa })
              : conexion === 'conectando'
                ? t('progreso.conectando')
                : t('progreso.esperando')}
          </p>
        </div>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-muted">
        <div className="h-full w-1/3 animate-pulse rounded-full bg-primary" />
      </div>
      {ultimo && Object.entries(ultimo.contadores).length > 0 && (
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {Object.entries(ultimo.contadores).map(([clave, valor]) => (
            <div key={clave} className="rounded-lg bg-muted/60 px-3 py-2.5">
              <dt className="text-xs text-muted-foreground">
                {t(`panel:progreso.contadores.${clave}`, { defaultValue: clave })}
              </dt>
              <dd className="mt-0.5 text-lg font-semibold tabular">{numero.format(valor)}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  )
}
