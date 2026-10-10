import { Link } from '@tanstack/react-router'
import { BellRing, ChartColumn, CircleAlert, MessageSquareText, RefreshCw, Tag, TriangleAlert, type LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { CiclosTab } from './CiclosTab'
import { useAnalisis } from './hooks'
import { KpisAnalisis } from './KpisAnalisis'
import { MensajesTab } from './MensajesTab'
import { OfertasTab } from './OfertasTab'
import { PrecisionTab } from './PrecisionTab'
import { RecordatoriosTab } from './RecordatoriosTab'
import { RiesgoTab } from './RiesgoTab'
import type { MetricasBacktest } from './tipos'

interface Props {
  analisisId: string
}

interface Pestana {
  clave: string
  icono: LucideIcon
  elemento: ReactNode
}

export function ResultadosAnalisis({ analisisId }: Props) {
  const { t } = useTranslation('resultados')
  const analisis = useAnalisis(analisisId)

  if (analisis.isLoading) {
    return (
      <div className="space-y-6" aria-busy="true">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-28 rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    )
  }
  if (analisis.isError) {
    return (
      <p role="alert" className="flex items-center gap-2 rounded-xl border border-danger/20 bg-danger-soft p-4 text-sm text-danger">
        <CircleAlert aria-hidden="true" className="size-4 shrink-0" />
        {t('error_generico')}
      </p>
    )
  }
  if (!analisis.data) return null
  if (analisis.data.estado !== 'listo') {
    return (
      <div className="rounded-xl border border-dashed bg-card p-8 text-center text-sm text-muted-foreground">
        <p>{t('no_listo')}</p>
        <Link
          to="/analisis/$analisisId/progreso"
          params={{ analisisId }}
          className="mt-3 inline-block font-medium text-primary hover:underline"
        >
          {t('layout:nav.progreso')}
        </Link>
      </div>
    )
  }

  const tipos = new Set(analisis.data.tipos)
  const metricas = analisis.data.metricas as unknown as MetricasBacktest | null
  const candidatas: (Pestana | null)[] = [
    tipos.has('recompra')
      ? { clave: 'recordatorios', icono: BellRing, elemento: <RecordatoriosTab analisisId={analisisId} /> }
      : null,
    tipos.has('ciclos') ? { clave: 'ciclos', icono: RefreshCw, elemento: <CiclosTab analisisId={analisisId} /> } : null,
    tipos.has('riesgo')
      ? { clave: 'riesgo', icono: TriangleAlert, elemento: <RiesgoTab analisisId={analisisId} /> }
      : null,
    tipos.has('ofertas') ? { clave: 'ofertas', icono: Tag, elemento: <OfertasTab analisisId={analisisId} /> } : null,
    { clave: 'mensajes', icono: MessageSquareText, elemento: <MensajesTab analisisId={analisisId} /> },
    metricas ? { clave: 'precision', icono: ChartColumn, elemento: <PrecisionTab metricas={metricas} /> } : null,
  ]
  const pestanas = candidatas.filter((p): p is Pestana => p !== null)

  return (
    <div className="space-y-8">
      <KpisAnalisis resumen={analisis.data.resumen} metricas={metricas} />
      {pestanas.length > 0 && (
        <Tabs defaultValue={pestanas[0].clave}>
          <TabsList>
            {pestanas.map(({ clave, icono: Icono }) => (
              <TabsTrigger key={clave} value={clave}>
                <Icono aria-hidden="true" />
                {t(`pestanas.${clave}`)}
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
