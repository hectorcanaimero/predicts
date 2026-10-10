import type { EventoTrabajo } from '@/hooks/useEventosTrabajo'

/** Tope de partículas simultáneas en pantalla (rendimiento, laptop común a 60fps). */
export const TOPE_PARTICULAS = 2000

/** Partículas por cada 1 punto de `log10(total + 1)`: escala para que millones de filas sigan
 * siendo un número de partículas manejable en pantalla. */
const ESCALA_LOG = 130

/** Etapas reales del orquestador de análisis (`api/src/predicts/analisis/orquestador.py`):
 * `leyendo` lee las compras del período y agrupa clientes/productos; `ciclos` calcula los ciclos
 * de recompra por par cliente/producto; `prediccion` genera los recordatorios; el resto
 * (`riesgo`, `ofertas`, `contactar`, `backtest`, `mensajes`) sigue trabajando sobre esos mismos
 * recordatorios, así que la escena los muestra como continuación de la salida. */
const ETAPAS_LEYENDO = new Set(['leyendo'])
const ETAPAS_CICLOS = new Set(['ciclos'])
const ETAPAS_RECORDATORIOS = new Set([
  'prediccion',
  'riesgo',
  'ofertas',
  'contactar',
  'backtest',
  'mensajes',
])

export type EtapaEscena = 'esperando' | 'entrada' | 'ciclos' | 'recordatorios' | 'listo' | 'error'

export interface GrupoEscena {
  /** valor real del contador, sin escalar (para los textos superpuestos). */
  total: number
  /** partículas visibles para este grupo, ya acotadas a `TOPE_PARTICULAS`. */
  particulas: number
  /** partículas nuevas por segundo: delta real entre los dos últimos eventos de esta etapa (el
   * backend emite como máximo 1 evento/seg por trabajo, así que el delta entre eventos
   * consecutivos de una misma etapa es, en la práctica, el ritmo por segundo). */
  ritmo: number
}

export interface ParametrosEscena {
  etapa: EtapaEscena
  archivo: GrupoEscena
  clientes: GrupoEscena
  productos: GrupoEscena
  ciclos: GrupoEscena
  recordatorios: GrupoEscena
}

function escalaLog(total: number): number {
  return total > 0 ? Math.log10(total + 1) * ESCALA_LOG : 0
}

function grupo(actual: number, anterior: number): GrupoEscena {
  const delta = Math.max(0, actual - anterior)
  return {
    total: actual,
    particulas: Math.min(TOPE_PARTICULAS, Math.round(escalaLog(actual))),
    ritmo: Math.round(escalaLog(delta)),
  }
}

/** Último valor de `contadores[clave]` entre los eventos de `etapas`, y el valor anterior a ese
 * (para poder calcular el ritmo). Los eventos de otras etapas no tocan `clave`: cada evento SSE
 * solo trae los contadores de su propia etapa. */
function ultimosDosValores(
  eventos: EventoTrabajo[],
  etapas: Set<string>,
  clave: string,
): [actual: number, anterior: number] {
  let actual = 0
  let anterior = 0
  for (const evento of eventos) {
    if (!etapas.has(evento.etapa)) continue
    const valor = evento.contadores[clave]
    if (valor == null) continue
    anterior = actual
    actual = valor
  }
  return [actual, anterior]
}

function etapaEscena(ultimaEtapa: string | undefined): EtapaEscena {
  if (!ultimaEtapa) return 'esperando'
  if (ultimaEtapa === 'listo') return 'listo'
  if (ultimaEtapa === 'error') return 'error'
  if (ETAPAS_LEYENDO.has(ultimaEtapa)) return 'entrada'
  if (ETAPAS_CICLOS.has(ultimaEtapa)) return 'ciclos'
  if (ETAPAS_RECORDATORIOS.has(ultimaEtapa)) return 'recordatorios'
  return 'esperando'
}

/** Mapea los eventos SSE del trabajo (`useEventosTrabajo`) a los parámetros de la escena 3D.
 * Pura: sin WebGL, sin estado, para poder testearla sin montar el `Canvas`. */
export function mapearEventos(eventos: EventoTrabajo[]): ParametrosEscena {
  const [filasAct, filasAnt] = ultimosDosValores(eventos, ETAPAS_LEYENDO, 'filas')
  const [clientesAct, clientesAnt] = ultimosDosValores(eventos, ETAPAS_LEYENDO, 'clientes')
  const [productosAct, productosAnt] = ultimosDosValores(eventos, ETAPAS_LEYENDO, 'productos')
  const [ciclosAct, ciclosAnt] = ultimosDosValores(eventos, ETAPAS_CICLOS, 'productos')
  const [recordatoriosAct, recordatoriosAnt] = ultimosDosValores(
    eventos,
    new Set(['prediccion']),
    'recordatorios',
  )

  return {
    etapa: etapaEscena(eventos[eventos.length - 1]?.etapa),
    archivo: grupo(filasAct, filasAnt),
    clientes: grupo(clientesAct, clientesAnt),
    productos: grupo(productosAct, productosAnt),
    ciclos: grupo(ciclosAct, ciclosAnt),
    recordatorios: grupo(recordatoriosAct, recordatoriosAnt),
  }
}
