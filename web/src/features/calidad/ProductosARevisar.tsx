import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
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
      <TableCell>{producto.nombre}</TableCell>
      <TableCell>
        <select
          aria-label={t('productos.tipo_de', { nombre: producto.nombre })}
          value={producto.tipo}
          onChange={(evento) =>
            corregir.mutate({ productoId: producto.id, datos: { tipo: evento.target.value } })
          }
          className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
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
        />
      </TableCell>
      <TableCell className="text-muted-foreground">
        {producto.confianza != null ? `${Math.round(producto.confianza * 100)}%` : '—'}
      </TableCell>
    </TableRow>
  )
}

export function ProductosARevisar({ datasetId }: { datasetId: string }) {
  const { t } = useTranslation('calidad')
  const productos = useProductosARevisar(datasetId)

  if (productos.isLoading) return <Skeleton className="h-10 w-full" />
  if (productos.isError) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {t('error.titulo')}
      </p>
    )
  }
  if (!productos.data) return null

  return (
    <section className="space-y-2">
      <h2 className="text-lg font-medium">{t('productos.titulo')}</h2>
      {productos.data.length === 0 ? (
        <p className="text-muted-foreground">{t('productos.vacio')}</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t('productos.columnas.nombre')}</TableHead>
              <TableHead>{t('productos.columnas.tipo')}</TableHead>
              <TableHead>{t('productos.columnas.categoria')}</TableHead>
              <TableHead>{t('productos.columnas.confianza')}</TableHead>
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
