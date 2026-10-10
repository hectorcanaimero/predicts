import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { DialogoBorrarProyecto } from '@/features/proyectos/DialogoBorrarProyecto'
import { DialogoProyecto } from '@/features/proyectos/DialogoProyecto'
import { useAnalisisDataset, useDatasetsProyecto, useProyecto, type Dataset } from '@/features/proyectos/hooks'

export const Route = createFileRoute('/_autenticado/proyectos/$proyectoId/')({
  component: ProyectoDetalle,
})

function AnalisisDeDataset({ dataset }: { dataset: Dataset }) {
  const { t } = useTranslation('proyectos')
  const analisis = useAnalisisDataset(dataset.id)

  return (
    <li className="rounded-md border p-3">
      <div className="flex items-center justify-between">
        <span className="font-medium">{dataset.nombre_archivo}</span>
        <Badge variant="outline">{dataset.estado}</Badge>
      </div>
      {analisis.isLoading && <Skeleton className="mt-2 h-6 w-full" />}
      {analisis.isError && (
        <p role="alert" className="mt-2 text-sm text-destructive">
          {t('error.titulo')}
        </p>
      )}
      {analisis.data?.length === 0 && (
        <p className="mt-2 text-sm text-muted-foreground">{t('detalle.analisis_vacio')}</p>
      )}
      {analisis.data && analisis.data.length > 0 && (
        <ul className="mt-2 space-y-1">
          {analisis.data.map((item) => (
            <li key={item.id} className="flex items-center justify-between text-sm">
              <span>{item.tipos.join(', ')}</span>
              <Badge variant="outline">{item.estado}</Badge>
            </li>
          ))}
        </ul>
      )}
    </li>
  )
}

export function ProyectoDetalle() {
  const { proyectoId } = Route.useParams()
  const { t } = useTranslation('proyectos')
  const navigate = useNavigate()
  const proyecto = useProyecto(proyectoId)
  const datasets = useDatasetsProyecto(proyectoId)
  const [dialogo, setDialogo] = useState<'editar' | 'borrar' | null>(null)

  if (proyecto.isLoading) return <Skeleton className="h-10 w-full" />

  if (proyecto.isError || !proyecto.data) {
    return (
      <div role="alert" className="space-y-2">
        <p>{t('error.titulo')}</p>
        <Button onClick={() => void proyecto.refetch()}>{t('error.reintentar')}</Button>
      </div>
    )
  }

  const datos = proyecto.data

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold">{datos.nombre}</h1>
          {datos.descripcion && <p className="text-muted-foreground">{datos.descripcion}</p>}
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setDialogo('editar')}>
            {t('acciones.editar')}
          </Button>
          <Button variant="destructive" size="sm" onClick={() => setDialogo('borrar')}>
            {t('acciones.eliminar')}
          </Button>
        </div>
      </div>

      <section className="space-y-2">
        <h2 className="text-lg font-medium">{t('detalle.datasets_titulo')}</h2>
        {datasets.isLoading && <Skeleton className="h-10 w-full" />}
        {datasets.isError && (
          <div role="alert" className="space-y-2">
            <p>{t('error.titulo')}</p>
            <Button onClick={() => void datasets.refetch()}>{t('error.reintentar')}</Button>
          </div>
        )}
        {datasets.data?.length === 0 && (
          <p className="text-muted-foreground">{t('detalle.datasets_vacio')}</p>
        )}
        {datasets.data && datasets.data.length > 0 && (
          <ul className="space-y-2">
            {datasets.data.map((dataset) => (
              <AnalisisDeDataset key={dataset.id} dataset={dataset} />
            ))}
          </ul>
        )}
      </section>

      <Link to="/proyectos" className="text-sm underline">
        {t('detalle.volver')}
      </Link>

      {dialogo === 'editar' && (
        <DialogoProyecto open proyecto={datos} onOpenChange={(open) => !open && setDialogo(null)} />
      )}
      {dialogo === 'borrar' && (
        <DialogoBorrarProyecto
          open
          proyecto={datos}
          onOpenChange={(open) => !open && setDialogo(null)}
          onBorrado={() => void navigate({ to: '/proyectos' })}
        />
      )}
    </div>
  )
}
