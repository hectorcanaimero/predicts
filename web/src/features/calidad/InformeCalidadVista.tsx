import {
  BellRing,
  CircleCheck,
  CircleX,
  Copy,
  Package,
  Rows3,
  Tag,
  TriangleAlert,
  Users,
  type LucideIcon,
} from 'lucide-react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import type { InformeCalidad } from './tipos'

interface Props {
  informe: InformeCalidad
}

const ANALISIS: ReadonlyArray<keyof InformeCalidad['viabilidad']> = ['recompra', 'riesgo', 'ofertas']
const ICONO_ANALISIS: Record<string, LucideIcon> = { recompra: BellRing, riesgo: TriangleAlert, ofertas: Tag }

function Indicador({
  etiqueta,
  valor,
  icono: Icono,
  testId,
}: {
  etiqueta: string
  valor: number
  icono: LucideIcon
  testId: string
}) {
  const { i18n } = useTranslation()
  return (
    <div className="rounded-xl border bg-card p-4 shadow-xs">
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-medium text-muted-foreground">{etiqueta}</p>
        <span className="inline-flex size-7 items-center justify-center rounded-md bg-muted text-muted-foreground">
          <Icono aria-hidden="true" className="size-3.5" />
        </span>
      </div>
      <p data-testid={testId} className="mt-2 text-2xl font-semibold tracking-tight tabular">
        {new Intl.NumberFormat(i18n.language).format(valor)}
      </p>
    </div>
  )
}

export function InformeCalidadVista({ informe }: Props) {
  const { t } = useTranslation('calidad')
  const distribucion = informe.distribucion_compras_cliente

  const datosGrafico = [
    { nombre: t('informe.distribucion.minimo'), valor: distribucion.minimo },
    { nombre: t('informe.distribucion.promedio'), valor: distribucion.promedio },
    { nombre: t('informe.distribucion.mediana'), valor: distribucion.mediana },
    { nombre: t('informe.distribucion.maximo'), valor: distribucion.maximo },
  ]

  return (
    <section aria-labelledby="titulo-informe" className="space-y-6">
      <h2 id="titulo-informe" className="text-lg font-semibold tracking-tight">
        {t('informe.titulo')}
      </h2>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Indicador etiqueta={t('informe.tarjetas.filas')} valor={informe.filas} icono={Rows3} testId="tarjeta-filas" />
        <Indicador
          etiqueta={t('informe.tarjetas.clientes')}
          valor={informe.clientes}
          icono={Users}
          testId="tarjeta-clientes"
        />
        <Indicador
          etiqueta={t('informe.tarjetas.productos')}
          valor={informe.productos}
          icono={Package}
          testId="tarjeta-productos"
        />
        <Indicador
          etiqueta={t('informe.tarjetas.duplicados')}
          valor={informe.duplicados_exactos}
          icono={Copy}
          testId="tarjeta-duplicados"
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="space-y-3 rounded-xl border bg-card p-5 shadow-xs">
          <h3 className="text-sm font-semibold">{t('informe.distribucion.titulo')}</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={datosGrafico} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(36, 15%, 87%)" />
              <XAxis dataKey="nombre" tick={{ fontSize: 12 }} tickLine={false} axisLine={false} />
              <YAxis tick={{ fontSize: 12 }} tickLine={false} axisLine={false} />
              <Tooltip cursor={{ fill: 'hsl(168, 32%, 92%)' }} />
              <Bar
                dataKey="valor"
                fill="hsl(173, 68%, 30%)"
                radius={[4, 4, 0, 0]}
                maxBarSize={56}
                name={t('informe.distribucion.titulo')}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="rounded-xl border bg-card p-5 shadow-xs">
          <h3 className="text-sm font-semibold">{t('informe.viabilidad_titulo')}</h3>
          <ul className="mt-3 divide-y">
            {ANALISIS.map((analisis) => {
              const viabilidad = informe.viabilidad[analisis]
              if (!viabilidad) return null
              const Icono = ICONO_ANALISIS[analisis]
              return (
                <li key={analisis} className="flex items-start gap-3 py-3 first:pt-0 last:pb-0">
                  <span className="mt-0.5 inline-flex size-8 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
                    <Icono aria-hidden="true" className="size-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-sm font-medium">{t(`informe.analisis.${analisis}`)}</p>
                      <Badge variant={viabilidad.viable ? 'success' : 'danger'}>
                        {viabilidad.viable ? <CircleCheck aria-hidden="true" /> : <CircleX aria-hidden="true" />}
                        {t(viabilidad.viable ? 'informe.viabilidad.viable' : 'informe.viabilidad.no_viable')}
                      </Badge>
                    </div>
                    {!viabilidad.viable && viabilidad.motivo && (
                      <p className="mt-1 text-xs text-muted-foreground">{viabilidad.motivo}</p>
                    )}
                  </div>
                </li>
              )
            })}
          </ul>
        </div>
      </div>
    </section>
  )
}
