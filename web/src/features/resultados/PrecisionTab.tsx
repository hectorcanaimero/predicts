import { CartesianGrid, Line, LineChart, Tooltip, XAxis, YAxis } from 'recharts'
import { useTranslation } from 'react-i18next'

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { METRICAS, type Estadistico, type MetricasBacktest, type Metrica } from './tipos'

interface Props {
  metricas: MetricasBacktest
}

function formato(metrica: Metrica, valor: number | null): string {
  if (valor == null) return '—'
  if (metrica === 'precision_at_k' || metrica === 'cobertura_at_k') return `${Math.round(valor * 100)}%`
  if (metrica === 'mae_dias') return valor.toFixed(1)
  return valor.toFixed(3)
}

function celda(metrica: Metrica, estadistico: Estadistico): string {
  const media = formato(metrica, estadistico.media)
  if (estadistico.desvio == null) return media
  return `${media} (± ${formato(metrica, estadistico.desvio)})`
}

/** FR-16: métricas del backtest modelo vs. línea base lado a lado, calibración por deciles y la
 * explicación corta de cada número (ver docstring de `api/src/predicts/modelo/backtest.py`). */
export function PrecisionTab({ metricas }: Props) {
  const { t } = useTranslation('resultados')

  const datosCalibracion = metricas.modelo.calibracion.map((tramo, i) => ({
    tramo: `${Math.round(tramo.desde * 100)}–${Math.round(tramo.hasta * 100)}%`,
    modelo: tramo.observado,
    linea_base: metricas.linea_base.calibracion[i]?.observado ?? null,
  }))

  return (
    <section className="space-y-4">
      <p className="text-sm text-muted-foreground">
        {t('precision.resumen', {
          semanas: metricas.semanas,
          horizonte: metricas.horizonte,
          n_pares: metricas.n_pares,
        })}
      </p>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t('precision.columnas.metrica')}</TableHead>
            <TableHead>{t('precision.columnas.modelo')}</TableHead>
            <TableHead>{t('precision.columnas.linea_base')}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {METRICAS.map((metrica) => (
            <TableRow key={metrica}>
              <TableCell>
                <div>{t(`precision.metricas.${metrica}`)}</div>
                <div className="text-xs text-muted-foreground">{t(`precision.explicaciones.${metrica}`)}</div>
              </TableCell>
              <TableCell>{celda(metrica, metricas.modelo[metrica])}</TableCell>
              <TableCell>{celda(metrica, metricas.linea_base[metrica])}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <div className="space-y-1">
        <h3 className="text-sm font-medium">{t('precision.calibracion.titulo')}</h3>
        <p className="text-xs text-muted-foreground">{t('precision.calibracion.explicacion')}</p>
        <LineChart width={500} height={240} data={datosCalibracion}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="tramo" />
          <YAxis domain={[0, 1]} />
          <Tooltip />
          <Line type="monotone" dataKey="modelo" name={t('precision.columnas.modelo')} stroke="#2563eb" />
          <Line
            type="monotone"
            dataKey="linea_base"
            name={t('precision.columnas.linea_base')}
            stroke="#9ca3af"
          />
        </LineChart>
      </div>
    </section>
  )
}
