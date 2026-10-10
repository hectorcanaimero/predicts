import { createFileRoute, Link } from '@tanstack/react-router'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { DialogoBorrarProyecto } from '@/features/proyectos/DialogoBorrarProyecto'
import { DialogoProyecto } from '@/features/proyectos/DialogoProyecto'
import { useProyectos, type Proyecto } from '@/features/proyectos/hooks'

export const Route = createFileRoute('/_autenticado/proyectos/')({ component: Proyectos })

type Dialogo = { tipo: 'crear' } | { tipo: 'editar' | 'borrar'; proyecto: Proyecto }

export function Proyectos() {
  const { t } = useTranslation('proyectos')
  const proyectos = useProyectos()
  const [dialogo, setDialogo] = useState<Dialogo | null>(null)

  if (proyectos.isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    )
  }

  if (proyectos.isError) {
    return (
      <div role="alert" className="space-y-2">
        <p>{t('error.titulo')}</p>
        <Button onClick={() => void proyectos.refetch()}>{t('error.reintentar')}</Button>
      </div>
    )
  }

  const lista = proyectos.data ?? []

  if (lista.length === 0) {
    return (
      <div className="space-y-4 text-center">
        <h1 className="text-xl font-semibold">{t('vacio.titulo')}</h1>
        <p className="text-muted-foreground">{t('vacio.descripcion')}</p>
        <Button onClick={() => setDialogo({ tipo: 'crear' })}>{t('vacio.crear')}</Button>
        {dialogo?.tipo === 'crear' && (
          <DialogoProyecto open onOpenChange={(open) => !open && setDialogo(null)} />
        )}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t('titulo')}</h1>
        <Button onClick={() => setDialogo({ tipo: 'crear' })}>{t('nuevo')}</Button>
      </div>
      <ul className="space-y-2">
        {lista.map((proyecto) => (
          <li key={proyecto.id} className="flex items-center justify-between rounded-md border p-3">
            <Link to="/proyectos/$proyectoId" params={{ proyectoId: proyecto.id }} className="font-medium">
              {proyecto.nombre}
            </Link>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setDialogo({ tipo: 'editar', proyecto })}>
                {t('acciones.editar')}
              </Button>
              <Button variant="destructive" size="sm" onClick={() => setDialogo({ tipo: 'borrar', proyecto })}>
                {t('acciones.eliminar')}
              </Button>
            </div>
          </li>
        ))}
      </ul>
      {(dialogo?.tipo === 'crear' || dialogo?.tipo === 'editar') && (
        <DialogoProyecto
          open
          proyecto={dialogo.tipo === 'editar' ? dialogo.proyecto : undefined}
          onOpenChange={(open) => !open && setDialogo(null)}
        />
      )}
      {dialogo?.tipo === 'borrar' && (
        <DialogoBorrarProyecto
          open
          proyecto={dialogo.proyecto}
          onOpenChange={(open) => !open && setDialogo(null)}
        />
      )}
    </div>
  )
}
