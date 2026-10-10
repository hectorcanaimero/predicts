import { Package, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Avatar } from '@/components/layout/MenuUsuario'
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
      className="fixed inset-y-0 right-0 z-40 flex w-full max-w-sm flex-col border-l bg-card shadow-xl sm:w-96"
    >
      <div className="flex items-center justify-between gap-3 border-b px-5 py-4">
        <div className="flex min-w-0 items-center gap-3">
          <Avatar email={clienteId} />
          <h3 className="truncate font-semibold">{t('panel.titulo', { cliente: clienteId })}</h3>
        </div>
        <button
          type="button"
          onClick={onCerrar}
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <X aria-hidden="true" className="size-4" />
          {t('panel.cerrar')}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-5">
        {historial.isLoading && <Skeleton className="h-40 w-full" />}
        {historial.isError && !sinHistorial && (
          <p role="alert" className="rounded-md bg-danger-soft p-3 text-sm text-danger">
            {t('panel.error')}
          </p>
        )}
        {(sinHistorial || (historial.data && historial.data.productos.length === 0)) && (
          <p className="py-8 text-center text-sm text-muted-foreground">{t('panel.vacio')}</p>
        )}
        {historial.data && historial.data.productos.length > 0 && (
          <ul className="space-y-3 text-sm">
            {historial.data.productos.map((p) => (
              <li key={p.producto_id} className="rounded-lg border bg-background/60 p-3">
                <p className="flex items-start gap-2 font-medium">
                  <Package aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                  {p.producto_nombre ?? p.producto_id}
                </p>
                <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-muted-foreground tabular">
                  <p>
                    {t('panel.columnas.n_compras')}: {p.n_compras}
                  </p>
                  {p.valor_total != null && (
                    <p>
                      {t('panel.columnas.valor_total')}: {p.valor_total}
                    </p>
                  )}
                  <p>
                    {t('panel.columnas.ultima_compra')}: {p.ultima_compra}
                  </p>
                  {p.ciclo != null && (
                    <p>
                      {t('panel.columnas.ciclo')}: {Math.round(p.ciclo)}
                    </p>
                  )}
                  {p.proxima_compra && (
                    <p className="col-span-2 font-medium text-primary">
                      {t('panel.columnas.proxima_compra')}: {p.proxima_compra}
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  )
}
