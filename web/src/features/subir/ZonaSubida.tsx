import { CircleAlert, CircleCheck, FileSpreadsheet, Upload } from 'lucide-react'
import { type ChangeEvent, type DragEvent, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { claveError, ErrorApi } from '@/api/cliente'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'
import { extensionValida, leerPrevia, type Previa } from './subida'
import { useSubirDataset } from './useSubirDataset'

interface Props {
  proyectoId: string
  onSubido?: (datasetId: string) => void
}

export function ZonaSubida({ proyectoId, onSubido }: Props) {
  const { t } = useTranslation('subir')
  const subida = useSubirDataset(proyectoId)
  const [errorFormato, setErrorFormato] = useState<ErrorApi | null>(null)
  const [previa, setPrevia] = useState<Previa | null>(null)
  const [arrastrando, setArrastrando] = useState(false)
  const [nombreArchivo, setNombreArchivo] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const error = errorFormato ?? subida.error

  useEffect(() => {
    if (subida.estado === 'listo' && subida.dataset) onSubido?.(subida.dataset.id)
  }, [subida.estado, subida.dataset, onSubido])

  function procesarArchivo(archivo: File | undefined) {
    if (!archivo) return
    if (!extensionValida(archivo.name)) {
      setErrorFormato(new ErrorApi('formato_no_soportado'))
      return
    }
    setErrorFormato(null)
    setPrevia(null)
    setNombreArchivo(archivo.name)
    void leerPrevia(archivo).then(setPrevia)
    subida.iniciar(archivo)
  }

  function alSoltar(evento: DragEvent<HTMLDivElement>) {
    evento.preventDefault()
    setArrastrando(false)
    procesarArchivo(evento.dataTransfer.files[0])
  }

  function alCambiarInput(evento: ChangeEvent<HTMLInputElement>) {
    procesarArchivo(evento.target.files?.[0])
    evento.target.value = ''
  }

  function elegirOtro() {
    setErrorFormato(null)
    setPrevia(null)
    subida.reiniciar()
  }

  const porcentaje = subida.progreso.total > 0 ? Math.round((subida.progreso.cargado / subida.progreso.total) * 100) : 0

  return (
    <div className="min-w-0 space-y-6">
      {subida.estado !== 'subiendo' && subida.estado !== 'listo' && (
        <div
          role="group"
          aria-label={t('dropzone.titulo')}
          onDragOver={(evento) => {
            evento.preventDefault()
            setArrastrando(true)
          }}
          onDragLeave={() => setArrastrando(false)}
          onDrop={alSoltar}
          className={cn(
            'flex flex-col items-center gap-4 rounded-xl border-2 border-dashed bg-card px-6 py-12 text-center transition-colors',
            arrastrando ? 'border-primary bg-accent/60' : 'border-input',
          )}
        >
          <span className="inline-flex size-14 items-center justify-center rounded-full bg-accent text-accent-foreground">
            <Upload aria-hidden="true" className="size-6" />
          </span>
          <div className="space-y-1">
            <p className="font-medium">{t('dropzone.titulo')}</p>
            <p className="text-xs text-muted-foreground">{t('dropzone.formatos')}</p>
          </div>
          <Label htmlFor="archivo" className="sr-only">
            {t('dropzone.titulo')}
          </Label>
          <input
            ref={inputRef}
            id="archivo"
            type="file"
            accept=".csv,.gz,.zip"
            className="sr-only"
            onChange={alCambiarInput}
          />
          <div aria-hidden="true" className="flex items-center gap-3 text-xs text-muted-foreground">
            <span className="h-px w-8 bg-border" />
            {t('dropzone.o')}
            <span className="h-px w-8 bg-border" />
          </div>
          <Button type="button" onClick={() => inputRef.current?.click()}>
            {t('dropzone.elegir_archivo')}
          </Button>
        </div>
      )}

      {error && (
        <div
          role="alert"
          className="flex flex-col gap-3 rounded-xl border border-danger/20 bg-danger-soft p-4 sm:flex-row sm:items-center"
        >
          <CircleAlert aria-hidden="true" className="size-5 shrink-0 text-danger" />
          <p className="flex-1 text-sm font-medium text-danger">
            {t(`errores.${claveError(error)}`, {
              ...error.parametros,
              defaultValue: t('comun:error_generico'),
            })}
          </p>
          <Button variant="outline" size="sm" onClick={elegirOtro}>
            {t('acciones.elegir_otro')}
          </Button>
        </div>
      )}

      {(subida.estado === 'subiendo' || subida.estado === 'listo') && (
        <div className="rounded-xl border bg-card p-5 shadow-xs">
          <div className="flex flex-wrap items-center gap-3">
            <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
              <FileSpreadsheet aria-hidden="true" className="size-5" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">
                {subida.estado === 'listo' ? nombreArchivo : t('subiendo.titulo', { nombre: nombreArchivo })}
              </p>
              {subida.estado === 'listo' ? (
                <p className="mt-0.5 flex items-center gap-1.5 text-sm text-success">
                  <CircleCheck aria-hidden="true" className="size-4" />
                  {t('listo.titulo')}
                </p>
              ) : (
                <Progress
                  value={porcentaje}
                  className="mt-2"
                  aria-label={t('subiendo.titulo', { nombre: nombreArchivo })}
                />
              )}
            </div>
            {subida.estado === 'subiendo' && (
              <div className="flex shrink-0 items-center gap-3">
                <span className="text-sm font-medium tabular">{t('subiendo.porcentaje', { porcentaje })}</span>
                <Button variant="outline" size="sm" onClick={subida.cancelar}>
                  {t('subiendo.cancelar')}
                </Button>
              </div>
            )}
          </div>
        </div>
      )}

      {previa && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold">{t('previa.titulo')}</h2>
          <div className="overflow-hidden rounded-xl border bg-card shadow-xs">
            <Table>
              <TableHeader>
                <TableRow>
                  {previa.encabezado.map((columna, indice) => (
                    <TableHead key={indice} className="normal-case tracking-normal">
                      {columna}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {previa.filas.map((fila, indiceFila) => (
                  <TableRow key={indiceFila}>
                    {fila.map((celda, indiceCelda) => (
                      <TableCell key={indiceCelda} className="whitespace-nowrap">
                        {celda}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </section>
      )}
    </div>
  )
}
