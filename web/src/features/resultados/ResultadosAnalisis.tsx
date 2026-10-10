import { Link } from '@tanstack/react-router'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { CiclosTab } from './CiclosTab'
import { useAnalisis } from './hooks'
import { MensajesTab } from './MensajesTab'
import { OfertasTab } from './OfertasTab'
import { PrecisionTab } from './PrecisionTab'
import { RecordatoriosTab } from './RecordatoriosTab'
import { RiesgoTab } from './RiesgoTab'
import type { MetricasBacktest } from './tipos'

interface Props {
  analisisId: string
}

export function ResultadosAnalisis({ analisisId }: Props) {
  const { t } = useTranslation('resultados')
  const analisis = useAnalisis(analisisId)

  if (analisis.isLoading) return <Skeleton className="h-40 w-full" />
  if (analisis.isError) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {t('error_generico')}
      </p>
    )
  }
  if (!analisis.data) return null
  if (analisis.data.estado !== 'listo') {
    return <p className="text-muted-foreground">{t('no_listo')}</p>
  }

  const tipos = new Set(analisis.data.tipos)
  const metricas = analisis.data.metricas as unknown as MetricasBacktest | null
  const candidatas: (({ clave: string; elemento: ReactNode }) | null)[] = [
    tipos.has('recompra') ? { clave: 'recordatorios', elemento: <RecordatoriosTab analisisId={analisisId} /> } : null,
    tipos.has('ciclos') ? { clave: 'ciclos', elemento: <CiclosTab analisisId={analisisId} /> } : null,
    tipos.has('riesgo') ? { clave: 'riesgo', elemento: <RiesgoTab analisisId={analisisId} /> } : null,
    tipos.has('ofertas') ? { clave: 'ofertas', elemento: <OfertasTab analisisId={analisisId} /> } : null,
    metricas ? { clave: 'precision', elemento: <PrecisionTab metricas={metricas} /> } : null,
    { clave: 'mensajes', elemento: <MensajesTab analisisId={analisisId} /> },
  ]
  const pestanas = candidatas.filter((p): p is { clave: string; elemento: ReactNode } => p !== null)

  return (
    <div className="space-y-4">
      <Link
        to="/datasets/$datasetId/agente"
        params={{ datasetId: analisis.data.dataset_id }}
        className="text-sm underline"
      >
        {t('agente:enlace')}
      </Link>
      {pestanas.length > 0 && (
        <Tabs defaultValue={pestanas[0].clave}>
          <TabsList>
            {pestanas.map((pestana) => (
              <TabsTrigger key={pestana.clave} value={pestana.clave}>
                {t(`pestanas.${pestana.clave}`)}
              </TabsTrigger>
            ))}
          </TabsList>
          {pestanas.map((pestana) => (
            <TabsContent key={pestana.clave} value={pestana.clave}>
              {pestana.elemento}
            </TabsContent>
          ))}
        </Tabs>
      )}
    </div>
  )
}
