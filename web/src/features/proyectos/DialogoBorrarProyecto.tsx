import { useTranslation } from 'react-i18next'

import { claveError } from '@/api/cliente'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useBorrarProyecto, type Proyecto } from './hooks'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  proyecto: Proyecto
  onBorrado?: () => void
}

/** Confirmación de borrado; la API borra en cascada datasets y análisis (ver F6.1.T2). */
export function DialogoBorrarProyecto({ open, onOpenChange, proyecto, onBorrado }: Props) {
  const { t } = useTranslation('proyectos')
  const borrar = useBorrarProyecto()

  async function confirmar() {
    try {
      await borrar.mutateAsync(proyecto.id)
      onOpenChange(false)
      onBorrado?.()
    } catch {
      // el error queda en `borrar.error` y se muestra abajo
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('borrar.titulo')}</DialogTitle>
          <DialogDescription>{t('borrar.descripcion', { nombre: proyecto.nombre })}</DialogDescription>
        </DialogHeader>
        {borrar.error && (
          <p role="alert" className="text-sm text-destructive">
            {t(`errores.${claveError(borrar.error)}`, {
              ...borrar.error.parametros,
              defaultValue: t('comun:error_generico'),
            })}
          </p>
        )}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            {t('comun:cancelar')}
          </Button>
          <Button
            type="button"
            variant="destructive"
            disabled={borrar.isPending}
            onClick={() => void confirmar()}
          >
            {borrar.isPending ? t('borrar.eliminando') : t('borrar.confirmar')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
