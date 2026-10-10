import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { ArrowRight, ClipboardCheck, FileSpreadsheet, Pencil, Plus, Trash, Upload } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { EncabezadoPagina } from '@/components/layout/EncabezadoPagina'
import { Badge, type BadgeProps } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { DialogoBorrarProyecto } from '@/features/proyectos/DialogoBorrarProyecto'
import { DialogoProyecto } from '@/features/proyectos/DialogoProyecto'
import { EstadoErrorCarga } from '@/features/proyectos/EstadosLista'
import { useAnalisisDataset, useDatasetsProyecto, useProyecto, type Dataset } from '@/features/proyectos/hooks'

export const Route = createFileRoute('/_autenticado/proyectos/$proyectoId/')({
  component: ProyectoDetalle,
})

const VARIANTE_ESTADO: Record<string, BadgeProps['variant']> = {
  listo: 'success',
  error: 'danger',
  cancelado: 'neutral',
  archivado: 'neutral',
  corriendo: 'info',
  en_cola: 'info',
  ingiriendo: 'info',
  subido: 'warning',
  mapeado: 'info',
}

function formatoBytes(bytes: number, idioma: string): string {
  const unidades = ['B', 'KB', 'MB', 'GB']
  let valor = bytes
  let i = 0
  while (valor >= 1024 && i < unidades.length - 1) {
    valor /= 1024
    i += 1
  }
  return `${new Intl.NumberFormat(idioma, { maximumFractionDigits: i === 0 ? 0 : 1 }).format(valor)} ${unidades[i]}`
}

function AccionesDataset({ dataset }: { dataset: Dataset }) {
  const { t } = useTranslation('proyectos')
  const params = { datasetId: dataset.id }

  if (dataset.estado === 'subido') {
    return (
      <Button asChild size="sm">
        <Link to="/datasets/$datasetId/mapeo" params={params}>
          {t('detalle.mapear')}
        </Link>
      </Button>
    )
  }
  return (
    <>
      <Button asChild variant="outline" size="sm">
        <Link to="/datasets/$datasetId/calidad" params={params}>
          <ClipboardCheck aria-hidden="true" />
          {t('detalle.calidad')}
        </Link>
      </Button>
      {dataset.estado === 'listo' && (
        <Button asChild size="sm">
          <Link to="/datasets/$datasetId/analisis/nuevo" params={params}>
            <Plus aria-hidden="true" />
            {t('detalle.nuevo_analisis')}
          </Link>
        </Button>
      )}
    </>
  )
}

function FilaDataset({ dataset }: { dataset: Dataset }) {
  const { t, i18n } = useTranslation('proyectos')
  const analisis = useAnalisisDataset(dataset.id)

  return (
    <li className="p-4 sm:p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
            <FileSpreadsheet aria-hidden="true" className="size-5" />
          </span>
          <div className="min-w-0">
            <p className="truncate font-medium">{dataset.nombre_archivo}</p>
            <p className="text-xs text-muted-foreground">{formatoBytes(dataset.tamano_bytes, i18n.language)}</p>
          </div>
          <Badge variant={VARIANTE_ESTADO[dataset.estado] ?? 'neutral'} className="ml-1">
            {t(`detalle.estados_dataset.${dataset.estado}`, { defaultValue: dataset.estado })}
          </Badge>
        </div>
        <div className="flex flex-wrap gap-2">
          <AccionesDataset dataset={dataset} />
        </div>
      </div>

      <div className="mt-4 sm:pl-13">
        {analisis.isLoading && <Skeleton className="h-12 w-full" />}
        {analisis.isError && (
          <p role="alert" className="text-sm text-danger">
            {t('error.titulo')}
          </p>
        )}
        {analisis.data?.length === 0 && (
          <p className="text-sm text-muted-foreground">{t('detalle.analisis_vacio')}</p>
        )}
        {analisis.data && analisis.data.length > 0 && (
          <ul className="divide-y rounded-lg border bg-background/60">
            {analisis.data.map((item) => {
              const listo = item.estado === 'listo'
              const enCurso = item.estado === 'en_cola' || item.estado === 'corriendo'
              return (
                <li key={item.id} className="flex flex-col gap-3 px-3 py-3 sm:flex-row sm:items-center">
                  <div className="flex flex-1 flex-wrap items-center gap-1.5">
                    <Badge variant={VARIANTE_ESTADO[item.estado] ?? 'neutral'}>
                      {t(`detalle.estados_analisis.${item.estado}`, { defaultValue: item.estado })}
                    </Badge>
                    <span aria-hidden="true" className="mx-1 h-4 w-px bg-border" />
                    {item.tipos.map((tipo) => (
                      <span key={tipo} className="rounded-md border bg-card px-1.5 py-0.5 text-xs text-muted-foreground">
                        {t(`detalle.tipos.${tipo}`, { defaultValue: tipo })}
                      </span>
                    ))}
                  </div>
                  {(listo || enCurso) && (
                    <Button asChild variant={listo ? 'secondary' : 'ghost'} size="sm" className="self-start sm:self-auto">
                      <Link
                        to={listo ? '/analisis/$analisisId' : '/analisis/$analisisId/progreso'}
                        params={{ analisisId: item.id }}
                      >
                        {listo ? t('detalle.ver_resultados') : t('detalle.ver_progreso')}
                        <ArrowRight aria-hidden="true" />
                      </Link>
                    </Button>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </div>
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

  if (proyecto.isLoading) {
    return (
      <div className="space-y-8" aria-busy="true">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-48 w-full rounded-xl" />
      </div>
    )
  }

  if (proyecto.isError || !proyecto.data) {
    return <EstadoErrorCarga onReintentar={() => void proyecto.refetch()} />
  }

  const datos = proyecto.data
  const subir = (
    <Button asChild>
      <Link to="/proyectos/$proyectoId/datasets/nuevo" params={{ proyectoId }}>
        <Upload aria-hidden="true" />
        {t('detalle.subir')}
      </Link>
    </Button>
  )

  return (
    <div className="space-y-8">
      <EncabezadoPagina
        titulo={datos.nombre}
        descripcion={datos.descripcion}
        acciones={
          <>
            <Button variant="outline" onClick={() => setDialogo('editar')}>
              <Pencil aria-hidden="true" />
              {t('acciones.editar')}
            </Button>
            <Button
              variant="ghost"
              className="text-danger hover:bg-danger-soft hover:text-danger"
              onClick={() => setDialogo('borrar')}
            >
              <Trash aria-hidden="true" />
              {t('acciones.eliminar')}
            </Button>
            {subir}
          </>
        }
      />
      <div className="-mt-4 flex flex-wrap gap-2">
        <Badge variant="neutral">{t('tarjeta.mensajes', { idioma: t(`idiomas.${datos.idioma_mensajes}`) })}</Badge>
        <Badge variant="neutral">
          {t('tarjeta.tono', { tono: t(`dialogo.tonos.${datos.tono}`).toLowerCase() })}
        </Badge>
      </div>

      <section aria-labelledby="titulo-datasets" className="overflow-hidden rounded-xl border bg-card shadow-xs">
        <div className="border-b px-4 py-4 sm:px-5">
          <h2 id="titulo-datasets" className="font-semibold">
            {t('detalle.datasets_titulo')}
          </h2>
          <p className="mt-0.5 text-sm text-muted-foreground">{t('detalle.datasets_descripcion')}</p>
        </div>
        {datasets.isLoading && (
          <div className="p-5">
            <Skeleton className="h-16 w-full" />
          </div>
        )}
        {datasets.isError && (
          <div className="p-5">
            <EstadoErrorCarga onReintentar={() => void datasets.refetch()} />
          </div>
        )}
        {datasets.data?.length === 0 && (
          <div className="flex flex-col items-center gap-4 px-6 py-12 text-center">
            <span className="inline-flex size-12 items-center justify-center rounded-full bg-accent text-accent-foreground">
              <Upload aria-hidden="true" className="size-5" />
            </span>
            <p className="text-sm text-muted-foreground">{t('detalle.datasets_vacio')}</p>
            {subir}
          </div>
        )}
        {datasets.data && datasets.data.length > 0 && (
          <ul className="divide-y">
            {datasets.data.map((dataset) => (
              <FilaDataset key={dataset.id} dataset={dataset} />
            ))}
          </ul>
        )}
      </section>

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
