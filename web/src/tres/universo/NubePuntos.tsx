import type { ThreeEvent } from '@react-three/fiber'
import { useEffect, useRef } from 'react'
import * as THREE from 'three'

import type { PuntoUniverso } from './transformaciones'

interface Props {
  puntos: PuntoUniverso[]
  onHover: (punto: PuntoUniverso | null, x: number, y: number) => void
  onSeleccionar: (clienteId: string) => void
}

const matrizTmp = new THREE.Matrix4()
const posicionTmp = new THREE.Vector3()
const cuaternionIdentidad = new THREE.Quaternion()
const escalaUno = new THREE.Vector3(1, 1, 1)
const colorTmp = new THREE.Color()

/** Nube de puntos del universo de clientes (spec F8.2.T2): un `InstancedMesh` con una esfera por
 * cliente, posición y color ya calculados por `clientesAPuntos` (pura, testeada sin WebGL). El
 * hover/clic usa el sistema de eventos de r3f sobre instancias (`event.instanceId`), sin
 * raycasting manual. */
export function NubePuntos({ puntos, onHover, onSeleccionar }: Props) {
  const ref = useRef<THREE.InstancedMesh>(null)

  useEffect(() => {
    const mesh = ref.current
    if (!mesh) return
    for (let i = 0; i < puntos.length; i++) {
      const [x, y, z] = puntos[i].posicion
      matrizTmp.compose(posicionTmp.set(x, y, z), cuaternionIdentidad, escalaUno)
      mesh.setMatrixAt(i, matrizTmp)
      mesh.setColorAt(i, colorTmp.set(puntos[i].color))
    }
    mesh.instanceMatrix.needsUpdate = true
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true
  }, [puntos])

  if (puntos.length === 0) return null

  return (
    <instancedMesh
      key={puntos.length}
      ref={ref}
      args={[undefined, undefined, puntos.length]}
      onPointerMove={(e: ThreeEvent<PointerEvent>) => {
        e.stopPropagation()
        if (e.instanceId != null) onHover(puntos[e.instanceId] ?? null, e.clientX, e.clientY)
      }}
      onPointerOut={(e: ThreeEvent<PointerEvent>) => onHover(null, e.clientX, e.clientY)}
      onClick={(e: ThreeEvent<MouseEvent>) => {
        e.stopPropagation()
        if (e.instanceId != null) onSeleccionar(puntos[e.instanceId].cliente_id)
      }}
    >
      <sphereGeometry args={[0.12, 8, 8]} />
      <meshBasicMaterial />
    </instancedMesh>
  )
}
