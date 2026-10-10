import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { claveError } from '@/api/cliente'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useCalidad } from '@/features/calidad/hooks'
import { useLanzarAnalisis, useSubirListaOfertas } from './hooks'
import { PARAMETROS_FORM_INICIAL, TARJETAS, type ParametrosFormulario, type TipoTarjeta } from './tipos'

interface Props {
  datasetId: string
  onLanzado: (analisisId: string) => void
}

/** Pantalla "Elegir análisis": tarjetas con viabilidad (FR-7, informe de calidad), parámetros con
 * default y ayuda (FR-15) y la subida opcional de la lista de ofertas (FR-14). */
export function SeleccionAnalisis({ datasetId, onLanzado }: Props) {
  const { t } = useTranslation('analisis')
  const calidad = useCalidad(datasetId, true)
  const [seleccionados, setSeleccionados] = useState<Set<TipoTarjeta>>(new Set())
  const [parametros, setParametros] = useState<ParametrosFormulario>(PARAMETROS_FORM_INICIAL)
  const [archivoOfertas, setArchivoOfertas] = useState<File | null>(null)

  const subirOfertas = useSubirListaOfertas(datasetId)
  const lanzar = useLanzarAnalisis(datasetId)

  function alternar(tipo: TipoTarjeta, viable: boolean) {
    if (!viable) return
    setSeleccionados((anteriores) => {
      const siguientes = new Set(anteriores)
      if (siguientes.has(tipo)) siguientes.delete(tipo)
      else siguientes.add(tipo)
      return siguientes
    })
  }

  async function lanzarAnalisis() {
    // Los errores quedan en `subirOfertas.error`/`lanzar.error` (ver más abajo); acá solo se
    // corta la cadena para no seguir al siguiente paso.
    try {
      if (archivoOfertas) await subirOfertas.mutateAsync(archivoOfertas)
      const analisis = await lanzar.mutateAsync({ tipos: [...seleccionados], parametros })
      onLanzado(analisis.id)
    } catch {
      // ya quedó reflejado en el estado de la mutación correspondiente
    }
  }

  const error = subirOfertas.error ?? lanzar.error
  const enviando = subirOfertas.isPending || lanzar.isPending

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {TARJETAS.map((tipo) => {
          const viabilidad = calidad.data?.viabilidad[tipo]
          const viable = viabilidad?.viable ?? true
          const elegida = seleccionados.has(tipo)
          return (
            <Card
              key={tipo}
              role="button"
              tabIndex={viable ? 0 : -1}
              aria-pressed={elegida}
              aria-disabled={!viable}
              data-testid={`tarjeta-${tipo}`}
              onClick={() => alternar(tipo, viable)}
              onKeyDown={(evento) => {
                if (evento.key === 'Enter' || evento.key === ' ') alternar(tipo, viable)
              }}
              className={
                !viable
                  ? 'cursor-not-allowed opacity-50'
                  : elegida
                    ? 'cursor-pointer border-primary ring-1 ring-primary'
                    : 'cursor-pointer'
              }
            >
              <CardHeader>
                <CardTitle>{t(`nuevo.tarjetas.${tipo}.nombre`)}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm text-muted-foreground">
                <p>{t(`nuevo.tarjetas.${tipo}.descripcion`)}</p>
                {!viable && viabilidad?.motivo && (
                  <p className="text-destructive">{t('nuevo.no_viable', { motivo: viabilidad.motivo })}</p>
                )}
              </CardContent>
            </Card>
          )
        })}
      </div>

      <div className="max-w-md space-y-4">
        <h2 className="text-lg font-medium">{t('nuevo.parametros.titulo')}</h2>

        <div className="space-y-1">
          <Label>{t('nuevo.parametros.periodo.etiqueta')}</Label>
          <div className="flex gap-2">
            <Input
              type="date"
              aria-label={t('nuevo.parametros.desde')}
              value={parametros.desde}
              onChange={(e) => setParametros({ ...parametros, desde: e.target.value })}
            />
            <Input
              type="date"
              aria-label={t('nuevo.parametros.hasta')}
              value={parametros.hasta}
              onChange={(e) => setParametros({ ...parametros, hasta: e.target.value })}
            />
          </div>
          <p className="text-xs text-muted-foreground">{t('nuevo.parametros.periodo.ayuda')}</p>
        </div>

        <div className="space-y-1">
          <Label htmlFor="min_compras">{t('nuevo.parametros.min_compras.etiqueta')}</Label>
          <Input
            id="min_compras"
            type="number"
            min={2}
            value={parametros.minCompras}
            onChange={(e) => setParametros({ ...parametros, minCompras: Number(e.target.value) })}
          />
          <p className="text-xs text-muted-foreground">{t('nuevo.parametros.min_compras.ayuda')}</p>
        </div>

        <div className="space-y-1">
          <Label htmlFor="horizonte">{t('nuevo.parametros.horizonte.etiqueta')}</Label>
          <Input
            id="horizonte"
            type="number"
            min={1}
            value={parametros.horizonte}
            onChange={(e) => setParametros({ ...parametros, horizonte: Number(e.target.value) })}
          />
          <p className="text-xs text-muted-foreground">{t('nuevo.parametros.horizonte.ayuda')}</p>
        </div>

        <div className="space-y-1">
          <Label htmlFor="umbral">{t('nuevo.parametros.umbral.etiqueta')}</Label>
          <Input
            id="umbral"
            type="number"
            min={0}
            max={1}
            step={0.01}
            value={parametros.umbral}
            onChange={(e) => setParametros({ ...parametros, umbral: Number(e.target.value) })}
          />
          <p className="text-xs text-muted-foreground">{t('nuevo.parametros.umbral.ayuda')}</p>
        </div>
      </div>

      {seleccionados.has('ofertas') && (
        <div className="max-w-md space-y-1">
          <Label htmlFor="archivo_ofertas">{t('nuevo.ofertas_lista.titulo')}</Label>
          <Input
            id="archivo_ofertas"
            type="file"
            accept=".csv"
            onChange={(e) => setArchivoOfertas(e.target.files?.[0] ?? null)}
          />
          <p className="text-xs text-muted-foreground">{t('nuevo.ofertas_lista.ayuda')}</p>
          {subirOfertas.isPending && <p>{t('nuevo.ofertas_lista.subiendo')}</p>}
          {subirOfertas.data && (
            <p>{t('nuevo.ofertas_lista.subida_ok', { productos: subirOfertas.data.productos })}</p>
          )}
        </div>
      )}

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {t(`nuevo.errores.${claveError(error)}`, { defaultValue: t('comun:error_generico') })}
        </p>
      )}

      {seleccionados.size === 0 && <p className="text-sm text-muted-foreground">{t('nuevo.ninguna_seleccionada')}</p>}

      <Button disabled={seleccionados.size === 0 || enviando} onClick={() => void lanzarAnalisis()}>
        {enviando ? t('nuevo.acciones.lanzando') : t('nuevo.acciones.lanzar')}
      </Button>
    </div>
  )
}
