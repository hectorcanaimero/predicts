import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import '../i18n'
import i18n from '../i18n'
import { Dispersion2D } from '../tres/universo/Dispersion2D'
import { PanelHistorial } from '../tres/universo/PanelHistorial'
import { clientesAPuntos, COLOR_ESTADO, type ClienteUniverso } from '../tres/universo/transformaciones'
import { VistaUniverso } from '../tres/universo/VistaUniverso'

function renderConQuery(elemento: ReactNode) {
  const queryClient = new QueryClient()
  render(<QueryClientProvider client={queryClient}>{elemento}</QueryClientProvider>)
  return queryClient
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

function cliente(parcial: Partial<ClienteUniverso> & { cliente_id: string }): ClienteUniverso {
  return { frecuencia: 1, valor: 1, recencia: 1, estado: 'activo', grupo: 0, ...parcial }
}

beforeEach(async () => {
  await i18n.changeLanguage('es')
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('clientesAPuntos (pura, sin WebGL)', () => {
  it('sin clientes: sin puntos', () => {
    expect(clientesAPuntos([])).toEqual([])
  })

  it('normaliza cada eje con el min/max de la propia muestra, a [-5, 5]', () => {
    const puntos = clientesAPuntos([
      cliente({ cliente_id: 'min', frecuencia: 0, valor: 10, recencia: 100 }),
      cliente({ cliente_id: 'max', frecuencia: 20, valor: 50, recencia: 300 }),
    ])
    const min = puntos.find((p) => p.cliente_id === 'min')!
    const max = puntos.find((p) => p.cliente_id === 'max')!
    expect(min.posicion).toEqual([-5, -5, -5])
    expect(max.posicion).toEqual([5, 5, 5])
  })

  it('un solo cliente (min === max en los tres ejes): queda en el origen, sin dividir por cero', () => {
    const [punto] = clientesAPuntos([cliente({ cliente_id: 'c1', frecuencia: 5, valor: 5, recencia: 5 })])
    expect(punto.posicion).toEqual([0, 0, 0])
  })

  it('color por estado: coincide con COLOR_ESTADO', () => {
    const puntos = clientesAPuntos([
      cliente({ cliente_id: 'c1', estado: 'activo' }),
      cliente({ cliente_id: 'c2', estado: 'en_recompra', frecuencia: 2 }),
      cliente({ cliente_id: 'c3', estado: 'en_riesgo', frecuencia: 3 }),
    ])
    expect(puntos.map((p) => p.color)).toEqual([
      COLOR_ESTADO.activo,
      COLOR_ESTADO.en_recompra,
      COLOR_ESTADO.en_riesgo,
    ])
  })

  it('conserva cliente_id, estado, grupo y los valores reales (sin escalar) para el tooltip', () => {
    const [punto] = clientesAPuntos([
      cliente({ cliente_id: 'c1', frecuencia: 7, valor: 42, recencia: 15, estado: 'en_riesgo', grupo: 2 }),
    ])
    expect(punto).toMatchObject({ cliente_id: 'c1', estado: 'en_riesgo', grupo: 2, frecuencia: 7, valor: 42, recencia: 15 })
  })
})

describe('Dispersion2D: respaldo 2D', () => {
  const puntos = clientesAPuntos([
    cliente({ cliente_id: 'c1', frecuencia: 1, valor: 10, estado: 'activo' }),
    cliente({ cliente_id: 'c2', frecuencia: 2, valor: 20, estado: 'en_riesgo' }),
  ])

  it('sin puntos: muestra el mensaje de vacío en vez del gráfico', () => {
    const { container } = render(<Dispersion2D puntos={[]} onSeleccionar={vi.fn()} />)
    expect(screen.getByText('No hay clientes para mostrar.')).toBeTruthy()
    expect(container.querySelector('svg')).toBeNull()
  })

  it('dibuja un punto por cliente', () => {
    const { container } = render(<Dispersion2D puntos={puntos} onSeleccionar={vi.fn()} />)
    expect(container.querySelectorAll('.recharts-scatter-symbol')).toHaveLength(puntos.length)
  })

  it('clic en un punto abre el historial del cliente correspondiente', () => {
    const onSeleccionar = vi.fn()
    const { container } = render(<Dispersion2D puntos={puntos} onSeleccionar={onSeleccionar} />)
    const simbolos = container.querySelectorAll('.recharts-scatter-symbol')
    fireEvent.click(simbolos[0])
    expect(onSeleccionar).toHaveBeenCalledWith(expect.any(String))
    expect(['c1', 'c2']).toContain(onSeleccionar.mock.calls[0][0])
  })
})

describe('PanelHistorial', () => {
  const ANALISIS_ID = 'a1'

  function stubFetch(respuesta: { status: number; cuerpo: unknown }) {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify(respuesta.cuerpo), { status: respuesta.status })),
    )
  }

  it('muestra el skeleton mientras carga', () => {
    stubFetch({ status: 200, cuerpo: { cliente_id: 'c1', productos: [] } })
    renderConQuery(<PanelHistorial analisisId={ANALISIS_ID} clienteId="c1" onCerrar={vi.fn()} />)
    expect(document.querySelectorAll('[data-slot="skeleton"], .animate-pulse').length).toBeGreaterThan(0)
  })

  it('con productos: muestra el historial del cliente', async () => {
    stubFetch({
      status: 200,
      cuerpo: {
        cliente_id: 'c1',
        productos: [
          {
            producto_id: 'p1', producto_nombre: 'Producto Uno', n_compras: 4, cantidad_total: 8,
            valor_total: 120, ultima_compra: '2024-05-01', ciclo: 20, proxima_compra: '2024-05-21',
          },
        ],
      },
    }) // fmt: skip
    renderConQuery(<PanelHistorial analisisId={ANALISIS_ID} clienteId="c1" onCerrar={vi.fn()} />)

    await screen.findByText('Producto Uno')
    screen.getByText('Compras: 4')
    screen.getByText('Próxima compra: 2024-05-21')
  })

  it('sin historial (404 no_encontrado): muestra el mensaje de vacío, no el de error', async () => {
    stubFetch({ status: 404, cuerpo: { codigo: 'no_encontrado' } })
    renderConQuery(<PanelHistorial analisisId={ANALISIS_ID} clienteId="c1" onCerrar={vi.fn()} />)

    await screen.findByText('Sin historial de compras.')
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('error genérico: muestra el mensaje de error', async () => {
    stubFetch({ status: 500, cuerpo: { codigo: 'error_interno' } })
    renderConQuery(<PanelHistorial analisisId={ANALISIS_ID} clienteId="c1" onCerrar={vi.fn()} />)

    await screen.findByRole('alert')
  })

  it('cerrar dispara onCerrar', async () => {
    stubFetch({ status: 200, cuerpo: { cliente_id: 'c1', productos: [] } })
    const onCerrar = vi.fn()
    renderConQuery(<PanelHistorial analisisId={ANALISIS_ID} clienteId="c1" onCerrar={onCerrar} />)

    fireEvent.click(screen.getByText('Cerrar'))
    expect(onCerrar).toHaveBeenCalled()
  })
})

describe('VistaUniverso: flujo completo con respaldo 2D', () => {
  const ANALISIS_ID = 'a1'
  const UNIVERSO = [
    cliente({ cliente_id: 'c1', frecuencia: 1, valor: 10, recencia: 5, estado: 'activo' }),
    cliente({ cliente_id: 'c2', frecuencia: 5, valor: 50, recencia: 40, estado: 'en_riesgo' }),
  ]

  function crearServidor() {
    return vi.fn(async (entrada: Request) => {
      const url = new URL(entrada.url)
      if (url.pathname === `/analisis/${ANALISIS_ID}/universo`) {
        return new Response(JSON.stringify(UNIVERSO), { status: 200 })
      }
      if (url.pathname === `/analisis/${ANALISIS_ID}/universo/c1`) {
        return new Response(
          JSON.stringify({
            cliente_id: 'c1',
            productos: [
              {
                producto_id: 'p1', producto_nombre: 'Producto Uno', n_compras: 2, cantidad_total: 2,
                valor_total: 50, ultima_compra: '2024-01-01', ciclo: 10, proxima_compra: '2024-01-11',
              },
            ],
          }),
          { status: 200 },
        ) // fmt: skip
      }
      throw new Error(`ruta no simulada: ${url.pathname}`)
    })
  }

  it('usa el respaldo 2D con prefers-reduced-motion y abre el panel al elegir un cliente', async () => {
    stubMovimientoReducido(true)
    vi.stubGlobal('fetch', crearServidor())

    const { container } = render(<VistaUniverso analisisId={ANALISIS_ID} />, {
      wrapper: ({ children }) => (
        <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
      ),
    })

    await screen.findByText('Frecuencia vs. valor')
    expect(container.querySelector('canvas')).toBeNull()
    expect(container.querySelectorAll('.recharts-scatter-symbol')).toHaveLength(2)

    fireEvent.click(container.querySelectorAll('.recharts-scatter-symbol')[0])
    await screen.findByText('Producto Uno')

    fireEvent.click(screen.getByText('Cerrar'))
    expect(screen.queryByText('Producto Uno')).toBeNull()
  })

  it('el filtro por estado oculta los puntos del estado desmarcado', async () => {
    stubMovimientoReducido(true)
    vi.stubGlobal('fetch', crearServidor())

    const { container } = render(<VistaUniverso analisisId={ANALISIS_ID} />, {
      wrapper: ({ children }) => (
        <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
      ),
    })

    await screen.findByText('Frecuencia vs. valor')
    fireEvent.click(screen.getByRole('checkbox', { name: 'En riesgo' }))

    await waitFor(() => expect(container.querySelectorAll('.recharts-scatter-symbol')).toHaveLength(1))
  })
})
