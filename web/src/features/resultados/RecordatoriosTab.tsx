import { useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ExportarBoton } from './ExportarBoton'
import { Paginador } from './Paginador'
import { SelectorOrden } from './SelectorOrden'
import { useResultados } from './hooks'
import { varianteProbabilidad } from './formato'
import { COLUMNAS_ORDEN, ORDEN_DEFECTO, TAM_PAGINA_DEFECTO, type FilaRecompra } from './tipos'

interface Props {
  analisisId: string
}

export function RecordatoriosTab({ analisisId }: Props) {
  const { t } = useTranslation('resultados')
  const [pagina, setPagina] = useState(1)
  const [orden, setOrden] = useState(ORDEN_DEFECTO.recompra)
  const resultados = useResultados<FilaRecompra>(analisisId, 'recompra', pagina, TAM_PAGINA_DEFECTO, orden)

  // ponytail: el calendario agrega solo la página cargada (hasta TAM_PAGINA_DEFECTO filas), no
  // el total del análisis; si hace falta el horizonte completo, agregar un endpoint dedicado.
  const datosCalendario = useMemo(() => {
    const porDia = new Map<string, number>()
    for (const fila of resultados.data?.resultados ?? []) {
      porDia.set(fila.fecha_probable, (porDia.get(fila.fecha_probable) ?? 0) + 1)
    }
    return [...porDia.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([fecha, cantidad]) => ({ fecha, cantidad }))
  }, [resultados.data])

  if (resultados.isLoading) return <Skeleton className="h-40 w-full" />
  if (resultados.isError) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {t('error_generico')}
      </p>
    )
  }
  if (!resultados.data) return null

  const columnasOrden = COLUMNAS_ORDEN.recompra.map((clave) => ({
    clave,
    etiqueta: t(`recordatorios.columnas.${clave}`),
  }))

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <SelectorOrden
          columnas={columnasOrden}
          valor={orden}
          onCambiar={(v) => {
            setOrden(v)
            setPagina(1)
          }}
          nombreAccesible={t('ordenar_por')}
          etiquetaAscendente={t('orden.ascendente')}
          etiquetaDescendente={t('orden.descendente')}
        />
        <ExportarBoton analisisId={analisisId} tipo="recordatorios" />
      </div>

      {datosCalendario.length > 0 && (
        <div className="space-y-3 rounded-xl border bg-card p-4 shadow-xs sm:p-5">
          <h3 className="text-sm font-semibold">{t('recordatorios.calendario.titulo')}</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={datosCalendario} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(36, 15%, 87%)" />
              <XAxis dataKey="fecha" tick={{ fontSize: 12 }} tickLine={false} axisLine={false} />
              <YAxis allowDecimals={false} tick={{ fontSize: 12 }} tickLine={false} axisLine={false} />
              <Tooltip cursor={{ fill: 'hsl(168, 32%, 92%)' }} />
              <Bar
                dataKey="cantidad"
                fill="hsl(173, 68%, 30%)"
                radius={[4, 4, 0, 0]}
                maxBarSize={48}
                name={t('recordatorios.calendario.titulo')}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {resultados.data.resultados.length === 0 ? (
        <p className="rounded-xl border border-dashed bg-card p-8 text-center text-sm text-muted-foreground">
          {t('vacio')}
        </p>
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card shadow-xs">
          <Table className="min-w-[52rem]">
            <TableHeader>
              <TableRow>
                <TableHead>{t('recordatorios.columnas.cliente_id')}</TableHead>
                <TableHead className="min-w-44">{t('recordatorios.columnas.producto_nombre')}</TableHead>
                <TableHead>{t('recordatorios.columnas.fecha_probable')}</TableHead>
                <TableHead>{t('recordatorios.columnas.p')}</TableHead>
                <TableHead>{t('recordatorios.columnas.motivo')}</TableHead>
                <TableHead>{t('recordatorios.columnas.mensaje')}</TableHead>
                <TableHead>{t('recordatorios.columnas.contactar')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {resultados.data.resultados.map((fila) => (
                <TableRow key={`${fila.cliente_id}-${fila.producto_id}`}>
                  <TableCell className="font-medium">{fila.cliente_id}</TableCell>
                  <TableCell>{fila.producto_nombre ?? fila.producto_id}</TableCell>
                  <TableCell className="whitespace-nowrap">
                    <span className="font-medium">{fila.fecha_probable}</span>
                    <span className="block text-xs text-muted-foreground">
                      {fila.fecha_min} – {fila.fecha_max}
                    </span>
                  </TableCell>
                  <TableCell>
                    <Badge variant={varianteProbabilidad(fila.p)} className="tabular">
                      {Math.round(fila.p * 100)}%
                    </Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{fila.motivo}</TableCell>
                  <TableCell className="text-muted-foreground">{fila.mensaje ?? '—'}</TableCell>
                  <TableCell>{fila.contactar ?? '—'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <Paginador pagina={pagina} tamPagina={TAM_PAGINA_DEFECTO} total={resultados.data.total} onCambiar={setPagina} />
    </section>
  )
}
