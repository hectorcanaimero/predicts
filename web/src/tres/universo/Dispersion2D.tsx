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
export function Dispersion2D({ puntos, onSeleccionar }: Props) {
  const { t } = useTranslation('universo')

  return (
    <div className="space-y-1">
      <h3 className="text-sm font-medium">{t('dispersion.titulo')}</h3>
      {puntos.length === 0 ? (
        <p className="text-muted-foreground">{t('vacio')}</p>
      ) : (
        <ScatterChart width={640} height={420} margin={{ top: 10, right: 20, bottom: 10, left: 10 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis type="number" dataKey="frecuencia" name={t('ejes.frecuencia')} />
          <YAxis type="number" dataKey="valor" name={t('ejes.valor')} />
          <Tooltip
            cursor={{ strokeDasharray: '3 3' }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null
              const punto = payload[0].payload as PuntoUniverso
              return (
                <div className="rounded border bg-background p-2 text-xs shadow">
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
      )}
    </div>
  )
}
