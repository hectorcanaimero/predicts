import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import '../i18n'
import i18n from '../i18n'
import type { EventoTrabajo } from '../hooks/useEventosTrabajo'
import { mapearEventos, TOPE_PARTICULAS } from '../tres/procesamiento/mapeoEventos'
import { VistaProcesamiento } from '../features/analisis/VistaProcesamiento'

function evento(etapa: string, contadores: Record<string, number> = {}): EventoTrabajo {
  return { etapa, contadores, progreso: null }
}

function stubMovimientoReducido(reducido: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockImplementation((query: string) => ({
      matches: query === '(prefers-reduced-motion: reduce)' && reducido,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  )
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('mapearEventos (pura, sin WebGL)', () => {
  it('sin eventos: etapa "esperando" y todos los grupos en cero', () => {
    const parametros = mapearEventos([])
    expect(parametros.etapa).toBe('esperando')
    expect(parametros.archivo).toEqual({ total: 0, particulas: 0, ritmo: 0 })
    expect(parametros.recordatorios).toEqual({ total: 0, particulas: 0, ritmo: 0 })
  })

  it('etapa "leyendo": toma filas/clientes/productos reales y calcula el ritmo como el delta', () => {
    const parametros = mapearEventos([
      evento('leyendo', { filas: 1000, clientes: 10, productos: 5 }),
      evento('leyendo', { filas: 2500, clientes: 12, productos: 6 }),
    ])
    expect(parametros.etapa).toBe('entrada')
    expect(parametros.archivo.total).toBe(2500)
    expect(parametros.clientes.total).toBe(12)
    expect(parametros.productos.total).toBe(6)
    // ritmo > 0 porque hubo un delta real (1500 filas nuevas) entre los dos eventos de "leyendo"
    expect(parametros.archivo.ritmo).toBeGreaterThan(0)
  })

  it('etapa "ciclos": no inventa un nuevo contador de filas, conserva lo ya leído y agrega los ciclos', () => {
    const parametros = mapearEventos([
      evento('leyendo', { filas: 5000, clientes: 20, productos: 8 }),
      evento('ciclos', { productos: 8 }),
    ])
    expect(parametros.etapa).toBe('ciclos')
    expect(parametros.archivo.total).toBe(5000) // sigue el último valor real de "leyendo"
    expect(parametros.ciclos.total).toBe(8)
  })

  it('etapa "prediccion": expone los recordatorios reales generados', () => {
    const parametros = mapearEventos([
      evento('leyendo', { filas: 5000, clientes: 20, productos: 8 }),
      evento('ciclos', { productos: 8 }),
      evento('prediccion', { pares: 8, recordatorios: 3 }),
    ])
    expect(parametros.etapa).toBe('recordatorios')
    expect(parametros.recordatorios.total).toBe(3)
  })

  it('etapas posteriores (riesgo, ofertas, ...) siguen mostrando la salida sin fabricar nuevos recordatorios', () => {
    const parametros = mapearEventos([
      evento('prediccion', { pares: 8, recordatorios: 3 }),
      evento('riesgo', { pares: 8, clientes: 20 }),
      evento('ofertas', { ofertas: 2, clientes: 5 }),
    ])
    expect(parametros.etapa).toBe('recordatorios')
    expect(parametros.recordatorios.total).toBe(3) // no cambia: "ofertas"/"riesgo" no traen "recordatorios"
  })

  it('etapas terminales: "listo" y "error"', () => {
    expect(mapearEventos([evento('prediccion', { recordatorios: 1 }), evento('listo')]).etapa).toBe('listo')
    expect(mapearEventos([evento('leyendo', { filas: 10 }), evento('error')]).etapa).toBe('error')
  })

  it('escala logarítmica: millones de filas siguen acotados al tope de partículas en pantalla', () => {
    const chico = mapearEventos([evento('leyendo', { filas: 10 })])
    const grande = mapearEventos([evento('leyendo', { filas: 10_000_000 })])
    expect(grande.archivo.particulas).toBeGreaterThan(chico.archivo.particulas)
    expect(grande.archivo.particulas).toBeLessThanOrEqual(TOPE_PARTICULAS)
  })
})

describe('VistaProcesamiento: respaldo 2D con prefers-reduced-motion', () => {
  it('usa la vista 2D (sin canvas) cuando el sistema pide menos movimiento', async () => {
    stubMovimientoReducido(true)
    await i18n.changeLanguage('es')

    const { container } = render(
      <VistaProcesamiento eventos={[evento('leyendo', { filas: 100 })]} conexion="abierta" />,
    )

    await screen.findByText('Etapa: leyendo')
    expect(container.querySelector('canvas')).toBeNull()
  })
})
