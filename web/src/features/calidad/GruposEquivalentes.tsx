import { Check, Layers, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useConfirmarGrupo, useGruposPropuestos, useRechazarGrupo } from './hooks'

export function GruposEquivalentes() {
  const { t } = useTranslation('calidad')
  const grupos = useGruposPropuestos()
  const confirmar = useConfirmarGrupo()
  const rechazar = useRechazarGrupo()

  if (grupos.isLoading) return <Skeleton className="h-24 w-full rounded-xl" />
  if (grupos.isError) {
    return (
      <p role="alert" className="rounded-xl border border-danger/20 bg-danger-soft p-4 text-sm text-danger">
        {t('error.titulo')}
      </p>
    )
  }
  if (!grupos.data) return null

  return (
    <section aria-labelledby="titulo-grupos" className="overflow-hidden rounded-xl border bg-card shadow-xs">
      <div className="border-b px-5 py-4">
        <h2 id="titulo-grupos" className="font-semibold">
          {t('grupos.titulo')}
        </h2>
        <p className="mt-0.5 text-sm text-muted-foreground">{t('grupos.descripcion')}</p>
      </div>
      {grupos.data.length === 0 ? (
        <p className="px-5 py-8 text-center text-sm text-muted-foreground">{t('grupos.vacio')}</p>
      ) : (
        <ul className="divide-y">
          {grupos.data.map((grupo) => (
            <li key={grupo.id} className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center">
              <span className="flex min-w-0 flex-1 items-start gap-3">
                <Layers aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                <span className="text-sm font-medium">{grupo.productos.map((p) => p.nombre).join(' · ')}</span>
              </span>
              <div className="flex shrink-0 gap-2">
                <Button size="sm" onClick={() => confirmar.mutate(grupo.id)}>
                  <Check aria-hidden="true" />
                  {t('grupos.confirmar')}
                </Button>
                <Button size="sm" variant="outline" onClick={() => rechazar.mutate(grupo.id)}>
                  <X aria-hidden="true" />
                  {t('grupos.rechazar')}
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
