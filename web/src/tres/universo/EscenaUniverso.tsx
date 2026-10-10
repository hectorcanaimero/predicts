import { OrbitControls } from '@react-three/drei'
import { Canvas } from '@react-three/fiber'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { NubePuntos } from './NubePuntos'
import type { PuntoUniverso } from './transformaciones'

interface Props {
  puntos: PuntoUniverso[]
  onSeleccionar: (clienteId: string) => void
}

/** Escena 3D del universo de clientes (spec F8.2.T2): nube de puntos con control de órbita y
 * zoom, hover con tooltip y clic que abre el panel lateral del historial. Chunk aparte vía
 * `React.lazy` en `VistaUniverso`, igual que `EscenaProcesamiento` (F8.1.T1), para no cargar
 * `three` en el bundle inicial. */
export default function EscenaUniverso({ puntos, onSeleccionar }: Props) {
  const { t } = useTranslation('universo')
  const [hover, setHover] = useState<{ punto: PuntoUniverso; x: number; y: number } | null>(null)

  return (
    <div className="relative h-[28rem] w-full overflow-hidden rounded-lg bg-sidebar">
      <Canvas camera={{ position: [8, 8, 8], fov: 50 }} dpr={[1, 1.5]}>
        <ambientLight intensity={1.2} />
        <axesHelper args={[6]} />
        <NubePuntos
          puntos={puntos}
          onHover={(punto, x, y) => setHover(punto ? { punto, x, y } : null)}
          onSeleccionar={onSeleccionar}
        />
        <OrbitControls enableDamping makeDefault />
      </Canvas>
      <p className="pointer-events-none absolute bottom-2 left-2 text-xs text-white/80">{t('ejes.descripcion')}</p>
      {hover && (
        <div
          className="pointer-events-none fixed z-10 rounded bg-black/80 px-2 py-1 text-xs text-white"
          style={{ left: hover.x + 12, top: hover.y + 12 }}
        >
          <p className="font-medium">{hover.punto.cliente_id}</p>
          <p>
            {t('ejes.frecuencia')}: {hover.punto.frecuencia}
          </p>
          <p>
            {t('ejes.valor')}: {hover.punto.valor}
          </p>
          <p>
            {t('ejes.recencia')}: {hover.punto.recencia}
          </p>
          <p>{t(`estados.${hover.punto.estado}`)}</p>
        </div>
      )}
    </div>
  )
}
