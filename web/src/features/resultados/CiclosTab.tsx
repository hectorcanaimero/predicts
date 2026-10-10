import { useState } from 'react'
import { CartesianGrid, Scatter, ScatterChart, XAxis, YAxis, ResponsiveContainer } from 'recharts'
import { useTranslation } from 'react-i18next'

import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Paginador } from './Paginador'
import { SelectorOrden } from './SelectorOrden'
import { useResultados } from './hooks'
import { COLUMNAS_ORDEN, ORDEN_DEFECTO, TAM_PAGINA_DEFECTO, type FilaCiclos } from './tipos'

interface Props {
  analisisId: string
}

export function CiclosTab({ analisisId }: Props) {
  const { t } = useTranslation('resultados')
  const [pagina, setPagina] = useState(1)
  const [orden, setOrden] = useState(ORDEN_DEFECTO.ciclos)
  const resultados = useResultados<FilaCiclos>(analisisId, 'ciclos', pagina, TAM_PAGINA_DEFECTO, orden)

  if (resultados.isLoading) return <Skeleton className="h-40 w-full" />
  if (resultados.isError) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {t('error_generico')}
      </p>
    )
  }
  if (!resultados.data) return null

  const columnasOrden = COLUMNAS_ORDEN.ciclos.map((clave) => ({
    clave,
    etiqueta: t(`ciclos.columnas.${clave}`),
  }))

  return (
    <section className="space-y-4">
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

      {resultados.data.resultados.length > 0 && (
        <div className="space-y-3 rounded-xl border bg-card p-4 shadow-xs sm:p-5">
          <h3 className="text-sm font-semibold">{t('ciclos.dispersion.titulo')}</h3>
          {/* ponytail: dispersión de la página cargada, no de todo el análisis (ver RecordatoriosTab). */}
          <ResponsiveContainer width="100%" height={240}>
            <ScatterChart margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(36, 15%, 87%)" />
              <XAxis type="number" dataKey="ciclo_mediano" name={t('ciclos.columnas.ciclo_mediano')} />
              <YAxis type="number" dataKey="clientes_recurrentes" name={t('ciclos.columnas.clientes_recurrentes')} />
              <Scatter data={resultados.data.resultados} fill="hsl(173, 68%, 30%)" fillOpacity={0.75} />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      )}

      {resultados.data.resultados.length === 0 ? (
        <p className="rounded-xl border border-dashed bg-card p-8 text-center text-sm text-muted-foreground">
          {t('vacio')}
        </p>
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card shadow-xs">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('ciclos.columnas.producto_nombre')}</TableHead>
                <TableHead>{t('ciclos.columnas.ciclo_mediano')}</TableHead>
                <TableHead>{t('ciclos.columnas.dispersion')}</TableHead>
                <TableHead>{t('ciclos.columnas.clientes_recurrentes')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {resultados.data.resultados.map((fila) => (
                <TableRow key={fila.producto_id}>
                  <TableCell>{fila.producto_nombre ?? fila.producto_id}</TableCell>
                  <TableCell>{fila.ciclo_mediano}</TableCell>
                  <TableCell>{fila.dispersion}</TableCell>
                  <TableCell>{fila.clientes_recurrentes}</TableCell>
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
