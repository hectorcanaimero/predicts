import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CartesianGrid, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from 'recharts'

import { COLOR_ESTADO, ESTADOS, type PuntoUniverso } from './transformaciones'

interface Props {
  puntos: PuntoUniverso[]
  onSeleccionar: (clienteId: string) => void
}

/** Respaldo 2D (spec F8.2.T2): mismos puntos/colores/filtro que la nube 3D, en frecuencia × valor
 * (la recencia queda disponible en el tooltip), para cuando el usuario prefiere menos movimiento
 * o mientras se descarga el chunk de la escena. */
const ANCHO_DEFECTO = 640

/** Ancho disponible del contenedor (ResizeObserver); sin él (jsdom) queda `ANCHO_DEFECTO`. Se
 * prefiere a `ResponsiveContainer` porque éste no dibuja nada mientras no puede medir. */
function useAncho() {
  const ref = useRef<HTMLDivElement>(null)
  const [ancho, setAncho] = useState(ANCHO_DEFECTO)
  useEffect(() => {
    const elemento = ref.current
    if (!elemento || typeof ResizeObserver === 'undefined') return undefined
    const observador = new ResizeObserver(([entrada]) => {
      const medido = Math.floor(entrada.contentRect.width)
      if (medido > 0) setAncho(Math.max(320, medido))
    })
    observador.observe(elemento)
    return () => observador.disconnect()
  }, [])
  return { ref, ancho }
}

export function Dispersion2D({ puntos, onSeleccionar }: Props) {
  const { t } = useTranslation('universo')
  const { ref, ancho } = useAncho()

  return (
    <div ref={ref} className="space-y-3">
      <h3 className="text-sm font-semibold">{t('dispersion.titulo')}</h3>
      {puntos.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground">{t('vacio')}</p>
      ) : (
        <div className="overflow-x-auto">
          <ScatterChart
            width={ancho}
            height={Math.round(Math.min(480, Math.max(320, ancho * 0.5)))}
            margin={{ top: 10, right: 20, bottom: 10, left: 10 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(36, 15%, 87%)" />
            <XAxis type="number" dataKey="frecuencia" name={t('ejes.frecuencia')} />
            <YAxis type="number" dataKey="valor" name={t('ejes.valor')} />
            <Tooltip
              cursor={{ strokeDasharray: '3 3' }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null
                const punto = payload[0].payload as PuntoUniverso
                return (
                  <div className="space-y-0.5 rounded-lg border bg-card p-3 text-xs shadow-md">
                    <p className="font-medium">{punto.cliente_id}</p>
                    <p>
                      {t('ejes.frecuencia')}: {punto.frecuencia}
                    </p>
                    <p>
                      {t('ejes.valor')}: {punto.valor}
                    </p>
                    <p>
                      {t('ejes.recencia')}: {punto.recencia}
                    </p>
                    <p>{t(`estados.${punto.estado}`)}</p>
                  </div>
                )
              }}
            />
            {ESTADOS.map((estado) => (
              <Scatter
                key={estado}
                name={t(`estados.${estado}`)}
                data={puntos.filter((p) => p.estado === estado)}
                fill={COLOR_ESTADO[estado]}
                cursor="pointer"
                // recharts tipa `onClick` con `ScatterPointItem` (cx/cy/size/...), pero en
                // ejecución pasa el punto de `data` tal cual, con nuestros campos propios.
                onClick={(datum: unknown) => onSeleccionar((datum as PuntoUniverso).cliente_id)}
              />
            ))}
          </ScatterChart>
        </div>
      )}
    </div>
  )
}
