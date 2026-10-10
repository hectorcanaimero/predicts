import { CircleAlert, Sparkles, TriangleAlert } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { claveError } from '@/api/cliente'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useConfirmarMapeo, useDataset, useIniciarIngesta, useSugerenciasMapeo } from './hooks'
import { CAMPOS_ESQUEMA, IGNORAR, UMBRAL_CONFIANZA_MAPEO } from './tipos'
import { validarMapeoLocal } from './validacion'

interface Props {
  datasetId: string
  onIngestaIniciada?: (trabajoId: string) => void
}

type Estado = 'prellenado' | 'revisar'

const CLASE_SELECT =
  'flex h-9 w-full rounded-md border border-input bg-card px-3 py-1 text-sm shadow-xs focus-visible:border-ring'

function Insignia({ estado }: { estado: Estado }) {
  const { t } = useTranslation('mapeo')
  return (
    <Badge variant={estado === 'prellenado' ? 'success' : 'warning'}>
      {estado === 'prellenado' ? <Sparkles aria-hidden="true" /> : <TriangleAlert aria-hidden="true" />}
      {t(`insignias.${estado}`)}
    </Badge>
  )
}

export function MapeoDataset({ datasetId, onIngestaIniciada }: Props) {
  const { t } = useTranslation('mapeo')
  const dataset = useDataset(datasetId)
  const sugerencias = useSugerenciasMapeo(datasetId)
  const confirmarMapeo = useConfirmarMapeo(datasetId)
  const iniciarIngesta = useIniciarIngesta(datasetId)

  const [campos, setCampos] = useState<Record<string, string>>({})
  const [productoIdTipo, setProductoIdTipo] = useState<string>('sku')
  const [formatoFecha, setFormatoFecha] = useState('')
  const [guardarPlantilla, setGuardarPlantilla] = useState(false)
  const [nombrePlantilla, setNombrePlantilla] = useState('')
  const [inicializado, setInicializado] = useState(false)

  // Ajuste de estado durante el render (no en un efecto): deriva de `sugerencias.data`, que ya
  // llega prellenado desde el servidor; `inicializado` evita pisar los cambios de la persona en
  // refetches posteriores (ver "You Might Not Need an Effect" de React).
  if (!inicializado && sugerencias.data) {
    setCampos(Object.fromEntries(sugerencias.data.columnas.map((c) => [c.columna, c.campo])))
    if (sugerencias.data.producto_id_tipo) setProductoIdTipo(sugerencias.data.producto_id_tipo.tipo)
    setInicializado(true)
  }

  const columnaFecha = useMemo(() => {
    const nombre = Object.entries(campos).find(([, campo]) => campo === 'fecha')?.[0]
    return dataset.data?.deteccion?.columnas.find((c) => c.nombre === nombre) ?? null
  }, [campos, dataset.data])

  const candidatosFecha = columnaFecha?.candidatos_fecha ?? []
  if (!candidatosFecha.some((c) => c.formato === formatoFecha)) {
    const mejor = [...candidatosFecha].sort((a, b) => b.porcentaje - a.porcentaje)[0]
    const nuevoFormato = mejor?.formato ?? ''
    if (nuevoFormato !== formatoFecha) setFormatoFecha(nuevoFormato)
  }

  if (dataset.isLoading || sugerencias.isLoading) {
    return (
      <div className="space-y-3" aria-busy="true">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    )
  }

  if (dataset.isError || sugerencias.isError || !dataset.data?.deteccion) {
    return (
      <div
        role="alert"
        className="flex flex-col items-start gap-3 rounded-xl border border-danger/20 bg-danger-soft p-5 sm:flex-row sm:items-center"
      >
        <CircleAlert aria-hidden="true" className="size-5 shrink-0 text-danger" />
        <p className="flex-1 text-sm font-medium text-danger">
          {sugerencias.error?.codigo === 'dataset_sin_deteccion'
            ? t('errores.dataset_sin_deteccion')
            : t('error.titulo')}
        </p>
        <Button
          variant="outline"
          size="sm"
          onClick={() => void (dataset.isError ? dataset.refetch() : sugerencias.refetch())}
        >
          {t('error.reintentar')}
        </Button>
      </div>
    )
  }

  const deteccion = dataset.data.deteccion
  const sugerenciasPorColumna = new Map(sugerencias.data?.columnas.map((s) => [s.columna, s]))
  const sugerenciaProductoIdTipo = sugerencias.data?.producto_id_tipo ?? null
  const estadoProductoIdTipo: Estado | null = sugerenciaProductoIdTipo
    ? sugerenciaProductoIdTipo.origen !== 'jev' || sugerenciaProductoIdTipo.confianza >= UMBRAL_CONFIANZA_MAPEO
      ? 'prellenado'
      : 'revisar'
    : null

  const errores = validarMapeoLocal(
    deteccion.columnas.map((c) => ({ columna: c.nombre, campo: campos[c.nombre] ?? IGNORAR })),
  )
  const necesitaFormatoFecha = columnaFecha !== null
  const puedeConfirmar =
    errores.length === 0 &&
    (!necesitaFormatoFecha || formatoFecha !== '') &&
    !confirmarMapeo.isPending &&
    !iniciarIngesta.isPending

  const errorEnvio = confirmarMapeo.error ?? iniciarIngesta.error

  async function confirmarEIniciar() {
    try {
      await confirmarMapeo.mutateAsync({
        columnas: deteccion.columnas.map((c) => ({
          columna: c.nombre,
          campo: campos[c.nombre] ?? IGNORAR,
        })),
        producto_id_tipo: productoIdTipo,
        formato_fecha: formatoFecha,
        guardar_como_plantilla: guardarPlantilla,
        nombre_plantilla: guardarPlantilla && nombrePlantilla ? nombrePlantilla : null,
      })
      const ingesta = await iniciarIngesta.mutateAsync()
      onIngestaIniciada?.(ingesta.trabajo_id)
    } catch {
      // el error queda en `confirmarMapeo.error` / `iniciarIngesta.error` y se muestra abajo
    }
  }

  return (
    <div className="space-y-6">
      <section aria-labelledby="titulo-columnas" className="overflow-hidden rounded-xl border bg-card shadow-xs">
        <h2 id="titulo-columnas" className="border-b px-5 py-4 font-semibold">
          {t('columnas_titulo')}
        </h2>
        <Table className="min-w-[40rem]">
          <TableHeader>
            <TableRow>
              <TableHead>{t('tabla.columna')}</TableHead>
              <TableHead>{t('tabla.valores_muestra')}</TableHead>
              <TableHead className="w-56">{t('tabla.campo')}</TableHead>
              <TableHead className="w-32">{t('tabla.confianza')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {deteccion.columnas.map((columna) => {
              const sugerencia = sugerenciasPorColumna.get(columna.nombre)
              const ignorada = (campos[columna.nombre] ?? IGNORAR) === IGNORAR
              return (
                <TableRow key={columna.nombre}>
                  <TableCell>
                    <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">{columna.nombre}</code>
                  </TableCell>
                  <TableCell className="max-w-64 truncate text-muted-foreground">
                    {columna.valores_muestra.slice(0, 3).join(', ')}
                  </TableCell>
                  <TableCell>
                    <select
                      aria-label={columna.nombre}
                      value={campos[columna.nombre] ?? IGNORAR}
                      onChange={(evento) =>
                        setCampos((anteriores) => ({
                          ...anteriores,
                          [columna.nombre]: evento.target.value,
                        }))
                      }
                      className={ignorada ? `${CLASE_SELECT} text-muted-foreground` : CLASE_SELECT}
                    >
                      <option value={IGNORAR}>{t('campos.ignorar')}</option>
                      {CAMPOS_ESQUEMA.map((campo) => (
                        <option key={campo} value={campo}>
                          {t(`campos.${campo}`)}
                        </option>
                      ))}
                    </select>
                  </TableCell>
                  <TableCell>{sugerencia && <Insignia estado={sugerencia.estado as Estado} />}</TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </section>

      {errores.length > 0 && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-xl border border-danger/20 bg-danger-soft p-4 text-sm text-danger"
        >
          <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          <ul className="space-y-1">
            {errores.map((error, indice) => (
              <li key={indice}>{t(`validacion.${error.codigo}`, error.parametros)}</li>
            ))}
          </ul>
        </div>
      )}

      <section aria-labelledby="titulo-opciones" className="rounded-xl border bg-card p-5 shadow-xs">
        <h2 id="titulo-opciones" className="font-semibold">
          {t('opciones.titulo')}
        </h2>
        <div className="mt-4 grid gap-5 sm:grid-cols-2">
          {columnaFecha && (
            <div className="space-y-1.5">
              <Label htmlFor="formato_fecha">{t('formato_fecha.titulo')}</Label>
              <select
                id="formato_fecha"
                value={formatoFecha}
                onChange={(evento) => setFormatoFecha(evento.target.value)}
                className={`${CLASE_SELECT} h-10`}
              >
                {columnaFecha.candidatos_fecha.map((candidato) => (
                  <option key={candidato.formato} value={candidato.formato}>
                    {t('formato_fecha.opcion', {
                      formato: candidato.formato,
                      porcentaje: Math.round(candidato.porcentaje * 100),
                    })}
                  </option>
                ))}
              </select>
            </div>
          )}

          {sugerenciaProductoIdTipo && (
            <div className="space-y-1.5">
              <div className="flex items-center gap-2">
                <Label htmlFor="producto_id_tipo">{t('producto_id_tipo.titulo')}</Label>
                {estadoProductoIdTipo && <Insignia estado={estadoProductoIdTipo} />}
              </div>
              <select
                id="producto_id_tipo"
                value={productoIdTipo}
                onChange={(evento) => setProductoIdTipo(evento.target.value)}
                className={`${CLASE_SELECT} h-10`}
              >
                <option value="sku">{t('producto_id_tipo.sku')}</option>
                <option value="ean">{t('producto_id_tipo.ean')}</option>
              </select>
            </div>
          )}
        </div>

        <div className="mt-5 space-y-3 border-t pt-5">
          <div className="flex items-center gap-2">
            <input
              id="guardar_plantilla"
              type="checkbox"
              checked={guardarPlantilla}
              onChange={(evento) => setGuardarPlantilla(evento.target.checked)}
              className="size-4 rounded accent-[hsl(var(--primary))]"
            />
            <Label htmlFor="guardar_plantilla">{t('plantilla.guardar')}</Label>
          </div>
          {guardarPlantilla && (
            <div className="max-w-sm space-y-1.5">
              <Label htmlFor="nombre_plantilla">{t('plantilla.nombre')}</Label>
              <Input
                id="nombre_plantilla"
                value={nombrePlantilla}
                onChange={(evento) => setNombrePlantilla(evento.target.value)}
              />
            </div>
          )}
        </div>
      </section>

      {errorEnvio && (
        <p
          role="alert"
          className="flex items-start gap-2 rounded-xl border border-danger/20 bg-danger-soft p-4 text-sm text-danger"
        >
          <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          {t(`errores.${claveError(errorEnvio)}`, {
            ...errorEnvio.parametros,
            defaultValue: t('comun:error_generico'),
          })}
        </p>
      )}

      <div className="flex justify-end">
        <Button size="lg" onClick={() => void confirmarEIniciar()} disabled={!puedeConfirmar}>
          {confirmarMapeo.isPending || iniciarIngesta.isPending ? t('acciones.confirmando') : t('acciones.confirmar')}
        </Button>
      </div>
    </div>
  )
}
