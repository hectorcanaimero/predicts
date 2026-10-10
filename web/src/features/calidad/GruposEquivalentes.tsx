import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useConfirmarGrupo, useGruposPropuestos, useRechazarGrupo } from './hooks'

export function GruposEquivalentes() {
  const { t } = useTranslation('calidad')
  const grupos = useGruposPropuestos()
  const confirmar = useConfirmarGrupo()
  const rechazar = useRechazarGrupo()

  if (grupos.isLoading) return <Skeleton className="h-10 w-full" />
  if (grupos.isError) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {t('error.titulo')}
      </p>
    )
  }
  if (!grupos.data) return null

  return (
    <section className="space-y-2">
      <h2 className="text-lg font-medium">{t('grupos.titulo')}</h2>
      {grupos.data.length === 0 ? (
        <p className="text-muted-foreground">{t('grupos.vacio')}</p>
      ) : (
        <ul className="space-y-2">
          {grupos.data.map((grupo) => (
            <li key={grupo.id} className="flex items-center justify-between rounded-md border p-3">
              <span className="font-medium">{grupo.productos.map((p) => p.nombre).join(' · ')}</span>
              <div className="flex gap-2">
                <Button size="sm" onClick={() => confirmar.mutate(grupo.id)}>
                  {t('grupos.confirmar')}
                </Button>
                <Button size="sm" variant="outline" onClick={() => rechazar.mutate(grupo.id)}>
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
