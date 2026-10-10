import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { useEventosTrabajo } from '@/hooks/useEventosTrabajo'
import { useAnalisis, useCancelarTrabajo, useTrabajo } from './hooks'
import { ERRORES_TRABAJO } from './tipos'
import { VistaProcesamiento } from './VistaProcesamiento'

interface Props {
  analisisId: string
  onCompletado: (analisisId: string) => void
}

/** Sigue un análisis ya lanzado: progreso 2D (`VistaProcesamiento`), cancelar y el error
 * traducido del trabajo cuando termina mal. Pasa solo a resultados cuando el análisis queda
 * `listo` (por el SSE o, si se perdió la conexión, por el sondeo de `useAnalisis`). */
export function ProgresoAnalisis({ analisisId, onCompletado }: Props) {
  const { t } = useTranslation('analisis')
  const analisis = useAnalisis(analisisId)
  const trabajoId = analisis.data?.trabajo_id ?? null
  const [cancelado, setCancelado] = useState(false)
  const { eventos, conexion } = useEventosTrabajo(cancelado ? null : trabajoId)
  const ultimo = eventos[eventos.length - 1]
  const etapaError = ultimo?.etapa === 'error'
  const listo = ultimo?.etapa === 'listo' || analisis.data?.estado === 'listo'
  const terminado = cancelado || etapaError || listo

  const trabajo = useTrabajo(trabajoId, etapaError)
  const cancelar = useCancelarTrabajo()

  const yaCompletado = useRef(false)
  useEffect(() => {
    if (listo && !yaCompletado.current) {
      yaCompletado.current = true
      onCompletado(analisisId)
    }
  }, [listo, analisisId, onCompletado])

  const codigoError = trabajo.data?.error_codigo
  const claveTraduccionError =
    codigoError && (ERRORES_TRABAJO as readonly string[]).includes(codigoError)
      ? codigoError
      : 'error_interno'

  return (
    <div className="space-y-4">
      <VistaProcesamiento eventos={eventos} conexion={conexion} />

      {etapaError && (
        <p role="alert" className="text-sm text-destructive">
          {t(`progreso.errores.${claveTraduccionError}`)}
        </p>
      )}
      {cancelado && <p>{t('progreso.cancelado')}</p>}

      <Button
        variant="outline"
        disabled={!trabajoId || terminado}
        onClick={() => trabajoId && cancelar.mutate(trabajoId, { onSuccess: () => setCancelado(true) })}
      >
        {t('progreso.acciones.cancelar')}
      </Button>
    </div>
  )
}
