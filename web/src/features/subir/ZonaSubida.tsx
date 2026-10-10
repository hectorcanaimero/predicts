import { type ChangeEvent, type DragEvent, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { claveError, ErrorApi } from '@/api/cliente'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
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
    void leerPrevia(archivo).then(setPrevia)
    subida.iniciar(archivo)
  }

  function alSoltar(evento: DragEvent<HTMLDivElement>) {
    evento.preventDefault()
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

  const porcentaje =
    subida.progreso.total > 0 ? Math.round((subida.progreso.cargado / subida.progreso.total) * 100) : 0

  return (
    <div className="space-y-4">
      {subida.estado !== 'subiendo' && subida.estado !== 'listo' && (
        <div
          role="group"
          aria-label={t('dropzone.titulo')}
          onDragOver={(evento) => evento.preventDefault()}
          onDrop={alSoltar}
          className="flex flex-col items-center gap-3 rounded-md border-2 border-dashed p-8 text-center"
        >
          <p className="text-muted-foreground">{t('dropzone.titulo')}</p>
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
          <Button type="button" onClick={() => inputRef.current?.click()}>
            {t('dropzone.elegir_archivo')}
          </Button>
        </div>
      )}

      {error && (
        <div role="alert" className="space-y-2">
          <p className="text-sm text-destructive">
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

      {previa && (
        <div className="space-y-2">
          <h2 className="text-sm font-medium">{t('previa.titulo')}</h2>
          <Table>
            <TableHeader>
              <TableRow>
                {previa.encabezado.map((columna, indice) => (
                  <TableHead key={indice}>{columna}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {previa.filas.map((fila, indiceFila) => (
                <TableRow key={indiceFila}>
                  {fila.map((celda, indiceCelda) => (
                    <TableCell key={indiceCelda}>{celda}</TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {subida.estado === 'subiendo' && (
        <div className="space-y-2">
          <Progress value={porcentaje} />
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span>{t('subiendo.porcentaje', { porcentaje })}</span>
            <Button variant="outline" size="sm" onClick={subida.cancelar}>
              {t('subiendo.cancelar')}
            </Button>
          </div>
        </div>
      )}

      {subida.estado === 'listo' && <p className="text-sm text-muted-foreground">{t('listo.titulo')}</p>}
    </div>
  )
}
