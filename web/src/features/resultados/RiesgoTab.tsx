import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ExportarBoton } from './ExportarBoton'
import { Paginador } from './Paginador'
import { SelectorOrden } from './SelectorOrden'
import { useResultados } from './hooks'
import { COLUMNAS_ORDEN, ORDEN_DEFECTO, TAM_PAGINA_DEFECTO, type FilaRiesgo } from './tipos'

interface Props {
  analisisId: string
}

export function RiesgoTab({ analisisId }: Props) {
  const { t } = useTranslation('resultados')
  const [pagina, setPagina] = useState(1)
  const [orden, setOrden] = useState(ORDEN_DEFECTO.riesgo)
  const resultados = useResultados<FilaRiesgo>(analisisId, 'riesgo', pagina, TAM_PAGINA_DEFECTO, orden)

  if (resultados.isLoading) return <Skeleton className="h-40 w-full" />
  if (resultados.isError) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {t('error_generico')}
      </p>
    )
  }
  if (!resultados.data) return null

  const columnasOrden = COLUMNAS_ORDEN.riesgo.map((clave) => ({
    clave,
    etiqueta: t(`riesgo.columnas.${clave}`),
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
        <ExportarBoton analisisId={analisisId} tipo="riesgo" />
      </div>

      {resultados.data.resultados.length === 0 ? (
        <p className="text-muted-foreground">{t('vacio')}</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t('riesgo.columnas.cliente_id')}</TableHead>
              <TableHead>{t('riesgo.columnas.producto_nombre')}</TableHead>
              <TableHead>{t('riesgo.columnas.nivel')}</TableHead>
              <TableHead>{t('riesgo.columnas.motivo')}</TableHead>
              <TableHead>{t('riesgo.columnas.valor')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {resultados.data.resultados.map((fila, i) => (
              <TableRow key={`${fila.cliente_id}-${fila.producto_id ?? 'tienda'}-${i}`}>
                <TableCell>{fila.cliente_id}</TableCell>
                <TableCell>{fila.producto_nombre ?? '—'}</TableCell>
                <TableCell>{t(`riesgo.niveles.${fila.nivel}`, { defaultValue: fila.nivel })}</TableCell>
                <TableCell className="text-muted-foreground">{fila.motivo}</TableCell>
                <TableCell>{fila.valor ?? '—'}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <Paginador pagina={pagina} tamPagina={TAM_PAGINA_DEFECTO} total={resultados.data.total} onCambiar={setPagina} />
    </section>
  )
}
