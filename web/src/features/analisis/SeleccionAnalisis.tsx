import { BellRing, Check, CircleAlert, RefreshCw, Tag, TriangleAlert, type LucideIcon } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { claveError } from '@/api/cliente'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useCalidad } from '@/features/calidad/hooks'
import { cn } from '@/lib/utils'
import { useLanzarAnalisis, useSubirListaOfertas } from './hooks'
import { PARAMETROS_FORM_INICIAL, TARJETAS, type ParametrosFormulario, type TipoTarjeta } from './tipos'

interface Props {
  datasetId: string
  onLanzado: (analisisId: string) => void
}

const ICONO: Record<TipoTarjeta, LucideIcon> = {
  recompra: BellRing,
  ciclos: RefreshCw,
  riesgo: TriangleAlert,
  ofertas: Tag,
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
      <section aria-labelledby="titulo-elegir" className="space-y-3">
        <h2 id="titulo-elegir" className="text-sm font-semibold">
          {t('nuevo.elegir_titulo')}
        </h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {TARJETAS.map((tipo) => {
            const viabilidad = calidad.data?.viabilidad[tipo]
            const viable = viabilidad?.viable ?? true
            const elegida = seleccionados.has(tipo)
            const Icono = ICONO[tipo]
            return (
              <div
                key={tipo}
                role="button"
                tabIndex={viable ? 0 : -1}
                aria-pressed={elegida}
                aria-disabled={!viable}
                data-testid={`tarjeta-${tipo}`}
                onClick={() => alternar(tipo, viable)}
                onKeyDown={(evento) => {
                  if (evento.key === 'Enter' || evento.key === ' ') {
                    evento.preventDefault()
                    alternar(tipo, viable)
                  }
                }}
                className={cn(
                  'relative flex flex-col gap-3 rounded-xl border bg-card p-5 text-left shadow-xs transition-[border-color,box-shadow,background-color]',
                  !viable && 'cursor-not-allowed bg-muted/50',
                  viable && !elegida && 'cursor-pointer hover:border-primary/40 hover:shadow-sm',
                  elegida && 'cursor-pointer border-primary bg-accent/40 ring-1 ring-primary',
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <span
                    className={cn(
                      'inline-flex size-10 items-center justify-center rounded-lg',
                      elegida ? 'bg-primary text-primary-foreground' : 'bg-accent text-accent-foreground',
                      !viable && 'bg-muted text-muted-foreground',
                    )}
                  >
                    <Icono aria-hidden="true" className="size-5" />
                  </span>
                  <span
                    aria-hidden="true"
                    className={cn(
                      'inline-flex size-5 items-center justify-center rounded-full border-2',
                      elegida ? 'border-primary bg-primary text-primary-foreground' : 'border-input bg-card',
                    )}
                  >
                    {elegida && <Check className="size-3" strokeWidth={3} />}
                  </span>
                </div>
                <div className="space-y-1">
                  <p className={cn('font-semibold leading-tight', !viable && 'text-muted-foreground')}>
                    {t(`nuevo.tarjetas.${tipo}.nombre`)}
                  </p>
                  <p className="text-sm text-muted-foreground">{t(`nuevo.tarjetas.${tipo}.descripcion`)}</p>
                </div>
                {!viable && viabilidad?.motivo && (
                  <p className="flex items-start gap-1.5 rounded-md bg-danger-soft px-2.5 py-2 text-xs text-danger">
                    <CircleAlert aria-hidden="true" className="mt-px size-3.5 shrink-0" />
                    {t('nuevo.no_viable', { motivo: viabilidad.motivo })}
                  </p>
                )}
              </div>
            )
          })}
        </div>
      </section>

      <section aria-labelledby="titulo-parametros" className="rounded-xl border bg-card p-5 shadow-xs sm:p-6">
        <h2 id="titulo-parametros" className="font-semibold">
          {t('nuevo.parametros.titulo')}
        </h2>
        <p className="mt-0.5 text-sm text-muted-foreground">{t('nuevo.parametros.descripcion')}</p>

        <div className="mt-5 grid gap-x-6 gap-y-5 md:grid-cols-2">
          <div className="space-y-1.5 md:col-span-2">
            <Label>{t('nuevo.parametros.periodo.etiqueta')}</Label>
            <div className="grid max-w-lg grid-cols-2 gap-2">
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

          <div className="space-y-1.5">
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

          <div className="space-y-1.5">
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

          <div className="space-y-1.5">
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

          {seleccionados.has('ofertas') && (
            <div className="space-y-1.5">
              <Label htmlFor="archivo_ofertas">{t('nuevo.ofertas_lista.titulo')}</Label>
              <Input
                id="archivo_ofertas"
                type="file"
                accept=".csv"
                className="pt-2"
                onChange={(e) => setArchivoOfertas(e.target.files?.[0] ?? null)}
              />
              <p className="text-xs text-muted-foreground">{t('nuevo.ofertas_lista.ayuda')}</p>
              {subirOfertas.isPending && (
                <p className="text-sm text-muted-foreground">{t('nuevo.ofertas_lista.subiendo')}</p>
              )}
              {subirOfertas.data && (
                <p className="text-sm text-success">
                  {t('nuevo.ofertas_lista.subida_ok', { productos: subirOfertas.data.productos })}
                </p>
              )}
            </div>
          )}
        </div>
      </section>

      {error && (
        <p
          role="alert"
          className="flex items-start gap-2 rounded-xl border border-danger/20 bg-danger-soft p-4 text-sm text-danger"
        >
          <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          {t(`nuevo.errores.${claveError(error)}`, { defaultValue: t('comun:error_generico') })}
        </p>
      )}

      <div className="sticky bottom-4 z-10 flex flex-col gap-3 rounded-xl border bg-card/95 p-4 shadow-md backdrop-blur sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-muted-foreground" aria-live="polite">
          {seleccionados.size === 0
            ? t('nuevo.ninguna_seleccionada')
            : t('nuevo.seleccionados', { count: seleccionados.size })}
        </p>
        <Button size="lg" disabled={seleccionados.size === 0 || enviando} onClick={() => void lanzarAnalisis()}>
          {enviando ? t('nuevo.acciones.lanzando') : t('nuevo.acciones.lanzar')}
        </Button>
      </div>
    </div>
  )
}
