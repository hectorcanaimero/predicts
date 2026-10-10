import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ExportarBoton } from './ExportarBoton'
import { Paginador } from './Paginador'
import { SelectorOrden } from './SelectorOrden'
import { useResultados } from './hooks'
import { COLUMNAS_ORDEN, ORDEN_DEFECTO, TAM_PAGINA_DEFECTO, type FilaOfertas } from './tipos'

interface Props {
  analisisId: string
}

/** "Ofertas por cliente" (spec): el orden inicial agrupa por `cliente_id` (ver `ORDEN_DEFECTO`),
 * aunque se puede reordenar por cualquier columna válida de la API. */
export function OfertasTab({ analisisId }: Props) {
  const { t } = useTranslation('resultados')
  const [pagina, setPagina] = useState(1)
  const [orden, setOrden] = useState(ORDEN_DEFECTO.ofertas)
  const resultados = useResultados<FilaOfertas>(analisisId, 'ofertas', pagina, TAM_PAGINA_DEFECTO, orden)

  if (resultados.isLoading) return <Skeleton className="h-40 w-full" />
  if (resultados.isError) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {t('error_generico')}
      </p>
    )
  }
  if (!resultados.data) return null

  const columnasOrden = COLUMNAS_ORDEN.ofertas.map((clave) => ({
    clave,
    etiqueta: t(`ofertas.columnas.${clave}`),
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
        <ExportarBoton analisisId={analisisId} tipo="ofertas" />
      </div>

      {resultados.data.resultados.length === 0 ? (
        <p className="rounded-xl border border-dashed bg-card p-8 text-center text-sm text-muted-foreground">
          {t('vacio')}
        </p>
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card shadow-xs">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('ofertas.columnas.cliente_id')}</TableHead>
                <TableHead>{t('ofertas.columnas.producto_nombre')}</TableHead>
                <TableHead>{t('ofertas.columnas.puntaje')}</TableHead>
                <TableHead>{t('ofertas.columnas.descuento')}</TableHead>
                <TableHead>{t('ofertas.columnas.motivo')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {resultados.data.resultados.map((fila) => (
                <TableRow key={`${fila.cliente_id}-${fila.producto_id}`}>
                  <TableCell className="font-medium">{fila.cliente_id}</TableCell>
                  <TableCell>{fila.producto_nombre ?? fila.producto_id}</TableCell>
                  <TableCell>
                    <span className="flex items-center gap-2 tabular">
                      <span aria-hidden="true" className="h-1.5 w-12 overflow-hidden rounded-full bg-muted">
                        <span
                          className="block h-full rounded-full bg-primary"
                          style={{
                            width: `${Math.min(100, Math.max(0, fila.puntaje * 100))}%`,
                          }}
                        />
                      </span>
                      {fila.puntaje.toFixed(2)}
                    </span>
                  </TableCell>
                  <TableCell>{fila.descuento > 0 ? `${Math.round(fila.descuento * 100)}%` : '—'}</TableCell>
                  <TableCell className="text-muted-foreground">{fila.motivo}</TableCell>
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
