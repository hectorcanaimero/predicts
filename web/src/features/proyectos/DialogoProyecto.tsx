import { type FormEvent, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { claveError } from '@/api/cliente'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { IDIOMAS, type Idioma } from '@/i18n'
import { useActualizarProyecto, useCrearProyecto, type Proyecto, type ProyectoEntrada } from './hooks'

const TONOS = ['cercano', 'neutro', 'formal'] as const

const NOMBRE_IDIOMA: Record<Idioma, string> = {
  'pt-BR': 'Português',
  es: 'Español',
  en: 'English',
}

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  proyecto?: Proyecto
}

/** Crear/editar proyecto (nombre, idioma de los mensajes, tono, descripción); ver F6.1.T2.
 * Quien la usa solo monta este componente mientras el diálogo está abierto, así que el estado
 * del formulario parte siempre de `proyecto` sin necesidad de un efecto para resincronizarlo. */
export function DialogoProyecto({ open, onOpenChange, proyecto }: Props) {
  const { t } = useTranslation('proyectos')
  const crear = useCrearProyecto()
  const actualizar = useActualizarProyecto(proyecto?.id ?? '')
  const [nombre, setNombre] = useState(proyecto?.nombre ?? '')
  const [idiomaMensajes, setIdiomaMensajes] = useState<Idioma>(proyecto?.idioma_mensajes ?? 'pt-BR')
  const [tono, setTono] = useState<ProyectoEntrada['tono']>(proyecto?.tono ?? 'neutro')
  const [descripcion, setDescripcion] = useState(proyecto?.descripcion ?? '')

  const mutacion = proyecto ? actualizar : crear
  const error = mutacion.error

  async function enviar(evento: FormEvent) {
    evento.preventDefault()
    const datos = { nombre, idioma_mensajes: idiomaMensajes, tono, descripcion: descripcion || null }
    try {
      if (proyecto) await actualizar.mutateAsync(datos)
      else await crear.mutateAsync(datos)
      onOpenChange(false)
    } catch {
      // el error queda en `mutacion.error` y se muestra abajo
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t(proyecto ? 'dialogo.editar_titulo' : 'dialogo.crear_titulo')}</DialogTitle>
        </DialogHeader>
        <form onSubmit={enviar} className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="nombre">{t('dialogo.nombre')}</Label>
            <Input
              id="nombre"
              required
              value={nombre}
              onChange={(evento) => setNombre(evento.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="idioma_mensajes">{t('dialogo.idioma_mensajes')}</Label>
            <select
              id="idioma_mensajes"
              value={idiomaMensajes}
              onChange={(evento) => setIdiomaMensajes(evento.target.value as Idioma)}
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
            >
              {IDIOMAS.map((opcion) => (
                <option key={opcion} value={opcion}>
                  {NOMBRE_IDIOMA[opcion]}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="tono">{t('dialogo.tono')}</Label>
            <select
              id="tono"
              value={tono}
              onChange={(evento) => setTono(evento.target.value as ProyectoEntrada['tono'])}
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
            >
              {TONOS.map((opcion) => (
                <option key={opcion} value={opcion}>
                  {t(`dialogo.tonos.${opcion}`)}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="descripcion">{t('dialogo.descripcion')}</Label>
            <textarea
              id="descripcion"
              rows={3}
              value={descripcion}
              onChange={(evento) => setDescripcion(evento.target.value)}
              className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm"
            />
          </div>
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {t(`errores.${claveError(error)}`, {
                ...error.parametros,
                defaultValue: t('comun:error_generico'),
              })}
            </p>
          )}
          <DialogFooter>
            <Button type="submit" disabled={mutacion.isPending}>
              {mutacion.isPending ? t('dialogo.guardando') : t('comun:guardar')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
