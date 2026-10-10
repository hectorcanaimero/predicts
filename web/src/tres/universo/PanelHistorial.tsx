import { useTranslation } from 'react-i18next'

import { Skeleton } from '@/components/ui/skeleton'
import { useHistorialCliente } from './hooks'

interface Props {
  analisisId: string
  clienteId: string
  onCerrar: () => void
}

/** Panel lateral abierto por un clic en la nube 3D o en el respaldo 2D: historial resumido del
 * cliente (`GET /analisis/{id}/universo/{cliente_id}`, F8.2.T1). */
export function PanelHistorial({ analisisId, clienteId, onCerrar }: Props) {
  const { t } = useTranslation('universo')
  const historial = useHistorialCliente(analisisId, clienteId)
  const sinHistorial = historial.isError && historial.error.codigo === 'no_encontrado'

  return (
    <aside
      role="complementary"
      aria-label={t('panel.titulo', { cliente: clienteId })}
      className="fixed inset-y-0 right-0 z-20 w-full max-w-sm overflow-y-auto border-l bg-background p-4 shadow-lg sm:w-96"
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="font-medium">{t('panel.titulo', { cliente: clienteId })}</h3>
        <button type="button" onClick={onCerrar} className="text-sm underline">
          {t('panel.cerrar')}
        </button>
      </div>

      {historial.isLoading && <Skeleton className="h-40 w-full" />}
      {historial.isError && !sinHistorial && (
        <p role="alert" className="text-sm text-destructive">
          {t('panel.error')}
        </p>
      )}
      {(sinHistorial || (historial.data && historial.data.productos.length === 0)) && (
        <p className="text-muted-foreground">{t('panel.vacio')}</p>
      )}
      {historial.data && historial.data.productos.length > 0 && (
        <ul className="space-y-3 text-sm">
          {historial.data.productos.map((p) => (
            <li key={p.producto_id} className="border-b pb-2">
              <p className="font-medium">{p.producto_nombre ?? p.producto_id}</p>
              <p className="text-muted-foreground">
                {t('panel.columnas.n_compras')}: {p.n_compras}
              </p>
              {p.valor_total != null && (
                <p className="text-muted-foreground">
                  {t('panel.columnas.valor_total')}: {p.valor_total}
                </p>
              )}
              <p className="text-muted-foreground">
                {t('panel.columnas.ultima_compra')}: {p.ultima_compra}
              </p>
              {p.ciclo != null && (
                <p className="text-muted-foreground">
                  {t('panel.columnas.ciclo')}: {Math.round(p.ciclo)}
                </p>
              )}
              {p.proxima_compra && (
                <p className="text-muted-foreground">
                  {t('panel.columnas.proxima_compra')}: {p.proxima_compra}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </aside>
  )
}
