import { useFrame } from '@react-three/fiber'
import { useEffect, useMemo, useRef } from 'react'
import * as THREE from 'three'

import { TOPE_PARTICULAS, type ParametrosEscena } from './mapeoEventos'

export const GRUPOS = ['archivo', 'clientes', 'productos', 'ciclos', 'recordatorios'] as const
export type NombreGrupo = (typeof GRUPOS)[number]

/** Posición de cada etapa en la escena: el archivo a la izquierda, los nodos de clientes y
 * productos agrupándose en el medio, los ciclos después y los recordatorios saliendo a la
 * derecha — el mismo orden del flujo real (`api/src/predicts/analisis/orquestador.py`). */
export const ANCLAS: Record<NombreGrupo, THREE.Vector3> = {
  archivo: new THREE.Vector3(-6, 0, 0),
  clientes: new THREE.Vector3(-2, 1.4, 0),
  productos: new THREE.Vector3(-2, -1.4, 0),
  ciclos: new THREE.Vector3(2, 0, 0),
  recordatorios: new THREE.Vector3(6, 0, 0),
}

export const COLOR: Record<NombreGrupo, THREE.Color> = {
  archivo: new THREE.Color('#60a5fa'),
  clientes: new THREE.Color('#34d399'),
  productos: new THREE.Color('#fbbf24'),
  ciclos: new THREE.Color('#a78bfa'),
  recordatorios: new THREE.Color('#f472b6'),
}

interface Props {
  parametros: ParametrosEscena
  /** Si está en falso (pestaña oculta), el `useFrame` no toca las matrices: ahorra el trabajo de
   * la GPU además de que `Canvas` ya deja de pedir frames. */
  activa: boolean
}

const matrizTmp = new THREE.Matrix4()
const posicionTmp = new THREE.Vector3()
const cuaternionIdentidad = new THREE.Quaternion()
const escalaUno = new THREE.Vector3(1, 1, 1)
const escalaCero = new THREE.Vector3(0, 0, 0)

/** Reparte `TOPE_PARTICULAS` índices entre los grupos según `particulas` de cada uno (ya en
 * escala log y acotado), en el mismo orden siempre: así una partícula no "salta" de grupo de un
 * render a otro solo porque cambiaron los contadores. */
function asignarGrupos(parametros: ParametrosEscena): (NombreGrupo | null)[] {
  const asignacion: (NombreGrupo | null)[] = new Array(TOPE_PARTICULAS).fill(null)
  let indice = 0
  for (const nombre of GRUPOS) {
    const cantidad = Math.min(parametros[nombre].particulas, TOPE_PARTICULAS - indice)
    for (let i = 0; i < cantidad; i++) asignacion[indice++] = nombre
  }
  return asignacion
}

export function Particulas({ parametros, activa }: Props) {
  const ref = useRef<THREE.InstancedMesh>(null)
  const asignacion = useMemo(() => asignarGrupos(parametros), [parametros])

  // El color por índice solo depende de a qué grupo quedó asignado: no hace falta recalcularlo
  // en cada frame, basta cuando cambia la asignación.
  useEffect(() => {
    const mesh = ref.current
    if (!mesh) return
    for (let i = 0; i < TOPE_PARTICULAS; i++) {
      const nombre = asignacion[i]
      mesh.setColorAt(i, nombre ? COLOR[nombre] : COLOR.archivo)
    }
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true
  }, [asignacion])

  useFrame(({ clock }) => {
    const mesh = ref.current
    if (!mesh || !activa) return
    const t = clock.getElapsedTime()
    for (let i = 0; i < TOPE_PARTICULAS; i++) {
      const nombre = asignacion[i]
      if (!nombre) {
        matrizTmp.compose(posicionTmp.set(0, 0, 0), cuaternionIdentidad, escalaCero)
        mesh.setMatrixAt(i, matrizTmp)
        continue
      }
      const ritmo = parametros[nombre].ritmo
      const velocidad = 0.4 + Math.min(2, ritmo / 80)
      const fase = i * 0.37
      const radio = 0.5 + 0.4 * Math.sin(fase)
      const ancla = ANCLAS[nombre]
      posicionTmp.set(
        ancla.x + radio * Math.cos(t * velocidad + fase),
        ancla.y + radio * Math.sin(t * velocidad + fase),
        ancla.z + 0.3 * Math.sin(t * velocidad * 0.7 + fase),
      )
      matrizTmp.compose(posicionTmp, cuaternionIdentidad, escalaUno)
      mesh.setMatrixAt(i, matrizTmp)
    }
    mesh.instanceMatrix.needsUpdate = true
  })

  return (
    <instancedMesh ref={ref} args={[undefined, undefined, TOPE_PARTICULAS]} frustumCulled={false}>
      <sphereGeometry args={[0.07, 6, 6]} />
      <meshBasicMaterial />
    </instancedMesh>
  )
}
