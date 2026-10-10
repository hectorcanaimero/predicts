import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from 'recharts'
import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { InformeCalidad } from './tipos'

interface Props {
  informe: InformeCalidad
}

const ANALISIS: ReadonlyArray<keyof InformeCalidad['viabilidad']> = ['recompra', 'riesgo', 'ofertas']

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
    <section className="space-y-4">
      <h2 className="text-lg font-medium">{t('informe.titulo')}</h2>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Card>
          <CardHeader>
            <CardTitle>{t('informe.tarjetas.filas')}</CardTitle>
          </CardHeader>
          <CardContent data-testid="tarjeta-filas">{informe.filas}</CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{t('informe.tarjetas.clientes')}</CardTitle>
          </CardHeader>
          <CardContent data-testid="tarjeta-clientes">{informe.clientes}</CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{t('informe.tarjetas.productos')}</CardTitle>
          </CardHeader>
          <CardContent data-testid="tarjeta-productos">{informe.productos}</CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{t('informe.tarjetas.duplicados')}</CardTitle>
          </CardHeader>
          <CardContent data-testid="tarjeta-duplicados">{informe.duplicados_exactos}</CardContent>
        </Card>
      </div>

      <div className="space-y-1">
        <h3 className="text-sm font-medium">{t('informe.distribucion.titulo')}</h3>
        <BarChart width={400} height={220} data={datosGrafico}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="nombre" />
          <YAxis />
          <Bar dataKey="valor" fill="#2563eb" name={t('informe.distribucion.titulo')} />
        </BarChart>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {ANALISIS.map((analisis) => {
          const viabilidad = informe.viabilidad[analisis]
          if (!viabilidad) return null
          return (
            <Card key={analisis}>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle>{t(`informe.analisis.${analisis}`)}</CardTitle>
                <Badge variant={viabilidad.viable ? 'outline' : 'destructive'}>
                  {t(viabilidad.viable ? 'informe.viabilidad.viable' : 'informe.viabilidad.no_viable')}
                </Badge>
              </CardHeader>
              {!viabilidad.viable && viabilidad.motivo && (
                <CardContent className="text-sm text-muted-foreground">{viabilidad.motivo}</CardContent>
              )}
            </Card>
          )
        })}
      </div>
    </section>
  )
}
