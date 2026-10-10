import { Canvas } from '@react-three/fiber'
import { useTranslation } from 'react-i18next'

import type { EstadoConexionSSE, EventoTrabajo } from '@/hooks/useEventosTrabajo'
import { mapearEventos } from './mapeoEventos'
import { COLOR, GRUPOS, Particulas } from './Particulas'
import { usePestanaVisible } from './usePestanaVisible'

interface Props {
  eventos: EventoTrabajo[]
  conexion: EstadoConexionSSE
}

/** Escena 3D del procesamiento (spec F8.1.T1): partículas instanciadas que entran desde el
 * "archivo", se agrupan en clientes/productos, forman los ciclos y salen como recordatorios — la
 * cantidad y el ritmo de cada grupo son los contadores reales de `useEventosTrabajo`
 * (`mapearEventos`), nunca un valor decorativo. Chunk aparte vía `React.lazy` en
 * `VistaProcesamiento`, para no cargar `three` en el bundle inicial. */
export default function EscenaProcesamiento({ eventos, conexion }: Props) {
  const { t } = useTranslation('tres')
  const visible = usePestanaVisible()
  const parametros = mapearEventos(eventos)

  return (
    <div className="relative h-72 w-full overflow-hidden rounded-lg bg-sidebar">
      <Canvas frameloop={visible ? 'always' : 'never'} camera={{ position: [0, 0, 11], fov: 45 }} dpr={[1, 1.5]}>
        <ambientLight intensity={1.4} />
        <Particulas parametros={parametros} activa={visible} />
      </Canvas>
      <div className="pointer-events-none absolute inset-0 flex flex-col justify-between p-3 text-xs text-white">
        <p className="font-medium">
          {parametros.etapa === 'esperando'
            ? t(conexion === 'conectando' ? 'escena.conectando' : 'escena.esperando')
            : t(`escena.etapas.${parametros.etapa}`)}
        </p>
        <ul className="flex flex-wrap gap-3">
          {GRUPOS.map((nombre) => (
            <li key={nombre} className="flex items-center gap-1.5">
              <span
                className="inline-block h-2 w-2 rounded-full"
                style={{ backgroundColor: `#${COLOR[nombre].getHexString()}` }}
              />
              {t(`escena.grupos.${nombre}`)}: {parametros[nombre].total.toLocaleString()}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
