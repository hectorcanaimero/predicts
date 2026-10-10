import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { varianteProbabilidad } from '@/features/resultados/formato'
import { useCorregirProducto, useProductosARevisar, type Producto } from './hooks'

function FilaProducto({ datasetId, producto }: { datasetId: string; producto: Producto }) {
  const { t } = useTranslation('calidad')
  const corregir = useCorregirProducto(datasetId)
  const [categoria, setCategoria] = useState(producto.categoria ?? '')

  function guardarCategoria() {
    if (categoria !== (producto.categoria ?? '')) {
      corregir.mutate({ productoId: producto.id, datos: { categoria } })
    }
  }

  return (
    <TableRow>
      <TableCell className="font-medium">{producto.nombre}</TableCell>
      <TableCell>
        <select
          aria-label={t('productos.tipo_de', { nombre: producto.nombre })}
          value={producto.tipo}
          onChange={(evento) => corregir.mutate({ productoId: producto.id, datos: { tipo: evento.target.value } })}
          className="flex h-9 w-full rounded-md border border-input bg-card px-3 py-1 text-sm shadow-xs"
        >
          <option value="recompra">{t('productos.tipos.recompra')}</option>
          <option value="durable">{t('productos.tipos.durable')}</option>
        </select>
      </TableCell>
      <TableCell>
        <Input
          aria-label={t('productos.categoria_de', { nombre: producto.nombre })}
          value={categoria}
          onChange={(evento) => setCategoria(evento.target.value)}
          onBlur={guardarCategoria}
          className="h-9"
        />
      </TableCell>
      <TableCell>
        {producto.confianza != null ? (
          <Badge variant={varianteProbabilidad(producto.confianza)} className="tabular">
            {Math.round(producto.confianza * 100)}%
          </Badge>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </TableCell>
    </TableRow>
  )
}

export function ProductosARevisar({ datasetId }: { datasetId: string }) {
  const { t } = useTranslation('calidad')
  const productos = useProductosARevisar(datasetId)

  if (productos.isLoading) return <Skeleton className="h-40 w-full rounded-xl" />
  if (productos.isError) {
    return (
      <p role="alert" className="rounded-xl border border-danger/20 bg-danger-soft p-4 text-sm text-danger">
        {t('error.titulo')}
      </p>
    )
  }
  if (!productos.data) return null

  return (
    <section aria-labelledby="titulo-productos" className="overflow-hidden rounded-xl border bg-card shadow-xs">
      <div className="border-b px-5 py-4">
        <h2 id="titulo-productos" className="font-semibold">
          {t('productos.titulo')}
        </h2>
        <p className="mt-0.5 text-sm text-muted-foreground">{t('productos.descripcion')}</p>
      </div>
      {productos.data.length === 0 ? (
        <p className="px-5 py-8 text-center text-sm text-muted-foreground">{t('productos.vacio')}</p>
      ) : (
        <Table className="min-w-[40rem]">
          <TableHeader>
            <TableRow>
              <TableHead>{t('productos.columnas.nombre')}</TableHead>
              <TableHead className="w-40">{t('productos.columnas.tipo')}</TableHead>
              <TableHead className="w-56">{t('productos.columnas.categoria')}</TableHead>
              <TableHead className="w-28">{t('productos.columnas.confianza')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {productos.data.map((producto) => (
              <FilaProducto key={producto.id} datasetId={datasetId} producto={producto} />
            ))}
          </TableBody>
        </Table>
      )}
    </section>
  )
}
