import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { claveError } from '@/api/cliente'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useEditarPlantilla, usePlantillas, useRegenerarPlantillas, type PlantillaSalida } from './hooks'

interface Props {
  analisisId: string
}

function FilaPlantilla({ analisisId, plantilla }: { analisisId: string; plantilla: PlantillaSalida }) {
  const { t } = useTranslation('resultados')
  const editar = useEditarPlantilla(analisisId)
  const [editando, setEditando] = useState(false)
  const [texto, setTexto] = useState(plantilla.texto)

  function guardar() {
    editar.mutate({ plantillaId: plantilla.id, texto }, { onSuccess: () => setEditando(false) })
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-normal text-muted-foreground">
          {plantilla.clave.split('::')[0]}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {editando ? (
          <>
            <textarea
              aria-label={t('mensajes.texto_de', { clave: plantilla.clave })}
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              className="flex min-h-20 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm"
            />
            <div className="flex gap-2">
              <Button
                size="sm"
                disabled={editar.isPending}
                aria-label={t('mensajes.acciones_de.guardar', { clave: plantilla.clave })}
                onClick={guardar}
              >
                {t('mensajes.acciones.guardar')}
              </Button>
              <Button
                size="sm"
                variant="outline"
                aria-label={t('mensajes.acciones_de.cancelar', { clave: plantilla.clave })}
                onClick={() => {
                  setTexto(plantilla.texto)
                  setEditando(false)
                }}
              >
                {t('mensajes.acciones.cancelar')}
              </Button>
            </div>
            {editar.error && (
              <p role="alert" className="text-sm text-destructive">
                {t(`mensajes.errores.${claveError(editar.error)}`, { defaultValue: t('comun:error_generico') })}
              </p>
            )}
          </>
        ) : (
          <>
            <p className="text-sm">{plantilla.texto}</p>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>{t(`mensajes.estados.${plantilla.estado}`, { defaultValue: plantilla.estado })}</span>
              {plantilla.motivo_revision && <span>— {plantilla.motivo_revision}</span>}
            </div>
            <Button
              size="sm"
              variant="outline"
              aria-label={t('mensajes.acciones_de.editar', { clave: plantilla.clave })}
              onClick={() => setEditando(true)}
            >
              {t('mensajes.acciones.editar')}
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  )
}

export function MensajesTab({ analisisId }: Props) {
  const { t } = useTranslation('resultados')
  const plantillas = usePlantillas(analisisId)
  const regenerar = useRegenerarPlantillas(analisisId)

  if (plantillas.isLoading) return <Skeleton className="h-40 w-full" />
  if (plantillas.isError) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {t('error_generico')}
      </p>
    )
  }
  if (!plantillas.data) return null

  const porTipo = new Map<string, PlantillaSalida[]>()
  for (const plantilla of plantillas.data) {
    porTipo.set(plantilla.tipo, [...(porTipo.get(plantilla.tipo) ?? []), plantilla])
  }

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <Button variant="outline" disabled={regenerar.isPending} onClick={() => regenerar.mutate()}>
          {regenerar.isPending ? t('mensajes.acciones.regenerando') : t('mensajes.acciones.regenerar')}
        </Button>
        {regenerar.error && (
          <p role="alert" className="text-sm text-destructive">
            {t(`mensajes.errores.${claveError(regenerar.error)}`, { defaultValue: t('comun:error_generico') })}
          </p>
        )}
      </div>

      {plantillas.data.length === 0 ? (
        <p className="text-muted-foreground">{t('mensajes.vacio')}</p>
      ) : (
        [...porTipo.entries()].map(([tipo, filas]) => (
          <div key={tipo} className="space-y-2">
            <h3 className="text-sm font-medium">{t(`mensajes.tipos.${tipo}`, { defaultValue: tipo })}</h3>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {filas.map((plantilla) => (
                <FilaPlantilla key={plantilla.id} analisisId={analisisId} plantilla={plantilla} />
              ))}
            </div>
          </div>
        ))
      )}
    </section>
  )
}
