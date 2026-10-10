import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { claveError } from '@/api/cliente'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useConfirmarMapeo, useDataset, useIniciarIngesta, useSugerenciasMapeo } from './hooks'
import { CAMPOS_ESQUEMA, IGNORAR, UMBRAL_CONFIANZA_MAPEO } from './tipos'
import { validarMapeoLocal } from './validacion'

interface Props {
  datasetId: string
  onIngestaIniciada?: (trabajoId: string) => void
}

type Estado = 'prellenado' | 'revisar'

function Insignia({ estado }: { estado: Estado }) {
  const { t } = useTranslation('mapeo')
  return (
    <Badge
      variant="outline"
      className={
        estado === 'prellenado'
          ? 'border-green-600 text-green-700'
          : 'border-amber-600 text-amber-700'
      }
    >
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

  if (dataset.isLoading || sugerencias.isLoading) return <Skeleton className="h-10 w-full" />

  if (dataset.isError || sugerencias.isError || !dataset.data?.deteccion) {
    return (
      <div role="alert" className="space-y-2">
        <p>{t('error.titulo')}</p>
        <Button onClick={() => void (dataset.isError ? dataset.refetch() : sugerencias.refetch())}>
          {t('error.reintentar')}
        </Button>
      </div>
    )
  }

  const deteccion = dataset.data.deteccion
  const sugerenciasPorColumna = new Map(sugerencias.data?.columnas.map((s) => [s.columna, s]))
  const sugerenciaProductoIdTipo = sugerencias.data?.producto_id_tipo ?? null
  const estadoProductoIdTipo: Estado | null = sugerenciaProductoIdTipo
    ? sugerenciaProductoIdTipo.origen !== 'jev' ||
      sugerenciaProductoIdTipo.confianza >= UMBRAL_CONFIANZA_MAPEO
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
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t('tabla.columna')}</TableHead>
            <TableHead>{t('tabla.valores_muestra')}</TableHead>
            <TableHead>{t('tabla.campo')}</TableHead>
            <TableHead>{t('tabla.confianza')}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {deteccion.columnas.map((columna) => {
            const sugerencia = sugerenciasPorColumna.get(columna.nombre)
            return (
              <TableRow key={columna.nombre}>
                <TableCell>{columna.nombre}</TableCell>
                <TableCell className="text-muted-foreground">
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
                    className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
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

      {columnaFecha && (
        <div className="space-y-1">
          <Label htmlFor="formato_fecha">{t('formato_fecha.titulo')}</Label>
          <select
            id="formato_fecha"
            value={formatoFecha}
            onChange={(evento) => setFormatoFecha(evento.target.value)}
            className="flex h-9 w-full max-w-sm rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
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
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Label htmlFor="producto_id_tipo">{t('producto_id_tipo.titulo')}</Label>
            {estadoProductoIdTipo && <Insignia estado={estadoProductoIdTipo} />}
          </div>
          <select
            id="producto_id_tipo"
            value={productoIdTipo}
            onChange={(evento) => setProductoIdTipo(evento.target.value)}
            className="flex h-9 w-full max-w-sm rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
          >
            <option value="sku">{t('producto_id_tipo.sku')}</option>
            <option value="ean">{t('producto_id_tipo.ean')}</option>
          </select>
        </div>
      )}

      {errores.length > 0 && (
        <div role="alert" className="space-y-1 text-sm text-destructive">
          <ul className="list-inside list-disc">
            {errores.map((error, indice) => (
              <li key={indice}>{t(`validacion.${error.codigo}`, error.parametros)}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <input
            id="guardar_plantilla"
            type="checkbox"
            checked={guardarPlantilla}
            onChange={(evento) => setGuardarPlantilla(evento.target.checked)}
          />
          <Label htmlFor="guardar_plantilla">{t('plantilla.guardar')}</Label>
        </div>
        {guardarPlantilla && (
          <div className="max-w-sm space-y-1">
            <Label htmlFor="nombre_plantilla">{t('plantilla.nombre')}</Label>
            <Input
              id="nombre_plantilla"
              value={nombrePlantilla}
              onChange={(evento) => setNombrePlantilla(evento.target.value)}
            />
          </div>
        )}
      </div>

      {errorEnvio && (
        <p role="alert" className="text-sm text-destructive">
          {t(`errores.${claveError(errorEnvio)}`, {
            ...errorEnvio.parametros,
            defaultValue: t('comun:error_generico'),
          })}
        </p>
      )}

      <Button onClick={() => void confirmarEIniciar()} disabled={!puedeConfirmar}>
        {confirmarMapeo.isPending || iniciarIngesta.isPending
          ? t('acciones.confirmando')
          : t('acciones.confirmar')}
      </Button>
    </div>
  )
}
