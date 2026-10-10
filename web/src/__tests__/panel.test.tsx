import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import '../i18n'
import i18n from '../i18n'
import { etapasDelAnalisis } from '../features/analisis/etapas'
import { PasosAnalisis } from '../features/analisis/PasosAnalisis'
import { KpisAnalisis } from '../features/resultados/KpisAnalisis'
import type { MetricasBacktest } from '../features/resultados/tipos'

beforeEach(async () => {
  await i18n.changeLanguage('es')
})

afterEach(() => cleanup())

const RESUMEN = {
  totales: { clientes: 50, productos: 1935, filas: 6806 },
  recompra: { recordatorios: 2, clientes: 2 },
  riesgo: { clientes: 22, pares: 115, valor_en_riesgo_tienda: 10770.53 },
  ofertas: { ofertas: 240, clientes: 48 },
  contactar: { por_decision: { contactar: 19, revisar: 2 } },
}

const METRICAS = {
  modelo: { precision_at_k: { media: 0.29 }, brier: { media: 0.12 } },
  linea_base: { precision_at_k: { media: 0.2 }, brier: { media: 0.14 } },
} as unknown as MetricasBacktest

/** Texto completo de la tarjeta del KPI (etiqueta + valor + detalle). */
function tarjeta(etiqueta: string) {
  return screen.getByText(etiqueta).closest('div')?.parentElement?.textContent ?? ''
}

describe('KPIs del análisis', () => {
  it('muestra los totales del resumen y la precisión del backtest', () => {
    render(<KpisAnalisis resumen={RESUMEN} metricas={METRICAS} />)

    screen.getByRole('region', { name: 'Indicadores clave' })
    expect(tarjeta('Clientes analizados')).toContain('50')
    screen.getByText('para 2 clientes')
    screen.getByText('2 para revisar')
    screen.getByText('Brier 0,12 · base 0,14')
    expect(tarjeta('Ofertas sugeridas')).toContain('240')
    expect(tarjeta('Clientes en riesgo')).toContain('22')
    expect(tarjeta('Precisión del modelo')).toMatch(/29\s?%/)
  })

  it('no muestra nada cuando no hay resumen ni métricas', () => {
    const { container } = render(<KpisAnalisis resumen={null} metricas={null} />)
    expect(container.textContent).toBe('')
  })

  it('solo muestra los indicadores que existen', () => {
    render(<KpisAnalisis resumen={{ totales: { clientes: 10 } }} metricas={null} />)
    screen.getByText('Clientes analizados')
    expect(screen.queryByText('Recordatorios')).toBeNull()
    expect(screen.queryByText('Precisión del modelo')).toBeNull()
  })
})

describe('etapas del progreso', () => {
  it('arma las etapas según los tipos pedidos', () => {
    expect(etapasDelAnalisis(['recompra', 'riesgo'], [])).toEqual([
      'leyendo',
      'prediccion',
      'riesgo',
      'backtest',
      'listo',
    ])
    expect(etapasDelAnalisis(['ciclos'], [{ etapa: 'mensajes', contadores: {}, progreso: null }])).toEqual([
      'leyendo',
      'ciclos',
      'mensajes',
      'listo',
    ])
  })

  it('marca la etapa en curso con aria-current y las anteriores como completadas', () => {
    render(<PasosAnalisis etapas={['leyendo', 'ciclos', 'listo']} actual="ciclos" fallo={false} />)

    const pasos = screen.getAllByRole('listitem')
    expect(pasos[0].textContent).toContain('completada')
    expect(pasos[1].getAttribute('aria-current')).toBe('step')
    expect(pasos[1].textContent).toContain('Ciclos de recompra')
    expect(pasos[2].textContent).toContain('pendiente')
  })
})
