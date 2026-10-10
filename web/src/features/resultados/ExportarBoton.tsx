import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { claveError } from '@/api/cliente'
import { Button } from '@/components/ui/button'
import { useExportar } from './hooks'
import { SEPARADORES, type Separador, type TipoExportar } from './tipos'

interface Props {
  analisisId: string
  tipo: TipoExportar
}

export function ExportarBoton({ analisisId, tipo }: Props) {
  const { t } = useTranslation('resultados')
  const [separador, setSeparador] = useState<Separador>(',')
  const exportar = useExportar(analisisId)

  return (
    <div className="flex items-center gap-2">
      <select
        aria-label={t('exportar.separador')}
        value={separador}
        onChange={(evento) => setSeparador(evento.target.value as Separador)}
        className="flex h-8 rounded-md border border-input bg-card px-2 text-xs shadow-xs"
      >
        {SEPARADORES.map((s) => (
          <option key={s} value={s}>
            {t(`exportar.separadores.${s === ',' ? 'coma' : 'punto_y_coma'}`)}
          </option>
        ))}
      </select>
      <Button
        variant="outline"
        size="sm"
        disabled={exportar.isPending}
        onClick={() => exportar.mutate({ tipo, separador })}
      >
        {exportar.isPending ? t('exportar.exportando') : t('exportar.boton')}
      </Button>
      {exportar.error && (
        <p role="alert" className="text-sm text-danger">
          {t(`exportar.errores.${claveError(exportar.error)}`, {
            defaultValue: t('comun:error_generico'),
          })}
        </p>
      )}
    </div>
  )
}
