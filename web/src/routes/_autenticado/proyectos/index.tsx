import { createFileRoute, Link } from '@tanstack/react-router'
import { ArrowRight, Pencil, Plus, Trash } from 'lucide-react'
import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { EncabezadoPagina } from '@/components/layout/EncabezadoPagina'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { BotonProbarDemo } from '@/features/proyectos/BotonProbarDemo'
import { DialogoBorrarProyecto } from '@/features/proyectos/DialogoBorrarProyecto'
import { DialogoProyecto } from '@/features/proyectos/DialogoProyecto'
import { EstadoErrorCarga, ProyectosVacio } from '@/features/proyectos/EstadosLista'
import { useProyectos, type Proyecto } from '@/features/proyectos/hooks'

export const Route = createFileRoute('/_autenticado/proyectos/')({ component: Proyectos })

type Dialogo = { tipo: 'crear' } | { tipo: 'editar' | 'borrar'; proyecto: Proyecto }

function TarjetaProyecto({
  proyecto,
  onEditar,
  onBorrar,
}: {
  proyecto: Proyecto
  onEditar: () => void
  onBorrar: () => void
}) {
  const { t } = useTranslation('proyectos')
  const idTitulo = useId()
  const tono = t(`dialogo.tonos.${proyecto.tono}`).toLowerCase()

  return (
    <li className="min-w-0">
      <article
        aria-labelledby={idTitulo}
        className="group relative flex h-full flex-col rounded-xl border bg-card p-5 shadow-xs transition-[border-color,box-shadow] focus-within:border-primary/50 hover:border-primary/40 hover:shadow-sm"
      >
        <div className="flex items-start gap-3">
          <span
            aria-hidden="true"
            className="inline-flex size-10 shrink-0 items-center justify-center rounded-lg bg-accent text-base font-semibold text-accent-foreground"
          >
            {proyecto.nombre.slice(0, 1).toUpperCase()}
          </span>
          <div className="min-w-0 flex-1">
            <h2 id={idTitulo} className="truncate font-semibold leading-tight">
              <Link
                to="/proyectos/$proyectoId"
                params={{ proyectoId: proyecto.id }}
                className="rounded-sm after:absolute after:inset-0 after:rounded-xl focus-visible:outline-none"
              >
                {proyecto.nombre}
              </Link>
            </h2>
            <p className="mt-1 line-clamp-2 text-sm text-muted-foreground [overflow-wrap:anywhere]">
              {proyecto.descripcion || t('tarjeta.sin_descripcion')}
            </p>
          </div>
          <div className="relative z-10 -mr-2 -mt-1 flex shrink-0">
            <Button
              variant="ghost"
              size="icon"
              className="size-8"
              aria-label={t('acciones.editar')}
              title={t('acciones.editar')}
              onClick={onEditar}
            >
              <Pencil aria-hidden="true" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="size-8 text-muted-foreground hover:bg-danger-soft hover:text-danger"
              aria-label={t('acciones.eliminar')}
              title={t('acciones.eliminar')}
              onClick={onBorrar}
            >
              <Trash aria-hidden="true" />
            </Button>
          </div>
        </div>
        <div className="mt-5 flex flex-wrap items-center gap-2 border-t pt-4">
          <Badge variant="neutral">{t('tarjeta.mensajes', { idioma: t(`idiomas.${proyecto.idioma_mensajes}`) })}</Badge>
          <Badge variant="neutral">{t('tarjeta.tono', { tono })}</Badge>
          <ArrowRight
            aria-hidden="true"
            className="ml-auto size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary"
          />
        </div>
      </article>
    </li>
  )
}

export function Proyectos() {
  const { t } = useTranslation('proyectos')
  const proyectos = useProyectos()
  const [dialogo, setDialogo] = useState<Dialogo | null>(null)

  if (proyectos.isLoading) {
    return (
      <div className="space-y-8" aria-busy="true">
        <div className="space-y-2">
          <Skeleton className="h-7 w-40" />
          <Skeleton className="h-4 w-80 max-w-full" />
        </div>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <Skeleton className="h-40 w-full rounded-xl" />
          <Skeleton className="h-40 w-full rounded-xl" />
          <Skeleton className="h-40 w-full rounded-xl" />
        </div>
      </div>
    )
  }

  if (proyectos.isError) {
    return <EstadoErrorCarga onReintentar={() => void proyectos.refetch()} />
  }

  const lista = proyectos.data ?? []

  if (lista.length === 0) {
    return (
      <div className="space-y-8">
        <EncabezadoPagina titulo={t('titulo')} descripcion={t('descripcion')} />
        <ProyectosVacio onCrear={() => setDialogo({ tipo: 'crear' })} demo={<BotonProbarDemo />} />
        {dialogo?.tipo === 'crear' && <DialogoProyecto open onOpenChange={(open) => !open && setDialogo(null)} />}
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <EncabezadoPagina
        titulo={t('titulo')}
        descripcion={t('descripcion')}
        acciones={
          <Button onClick={() => setDialogo({ tipo: 'crear' })}>
            <Plus aria-hidden="true" />
            {t('nuevo')}
          </Button>
        }
      />
      <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {lista.map((proyecto) => (
          <TarjetaProyecto
            key={proyecto.id}
            proyecto={proyecto}
            onEditar={() => setDialogo({ tipo: 'editar', proyecto })}
            onBorrar={() => setDialogo({ tipo: 'borrar', proyecto })}
          />
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
        <DialogoBorrarProyecto open proyecto={dialogo.proyecto} onOpenChange={(open) => !open && setDialogo(null)} />
      )}
    </div>
  )
}
