import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import '../i18n'
import i18n from '../i18n'
import { CalidadDataset } from '../features/calidad/CalidadDataset'
import { useEventosTrabajo } from '../hooks/useEventosTrabajo'

const DATASET_ID = 'd1'
const TRABAJO_ID = 't1'

function bloqueSSE(id: number, evento: string, datos: Record<string, unknown>): string {
  return `id: ${id}\nevent: ${evento}\ndata: ${JSON.stringify(datos)}`
}

/** Construye un `Response` cuyo cuerpo es un `ReadableStream` de texto `text/event-stream`:
 * emite `bloques` y cierra el stream (sin un evento final `listo`/`error`, simula un corte de
 * red que el hook debe reconectar). */
function respuestaSSE(bloques: string[]): Response {
  const texto = bloques.map((bloque) => `${bloque}\n\n`).join('')
  const stream = new ReadableStream<Uint8Array>({
    start(controlador) {
      controlador.enqueue(new TextEncoder().encode(texto))
      controlador.close()
    },
  })
  return new Response(stream)
}

function renderConQuery(elemento: ReactNode) {
  const queryClient = new QueryClient()
  render(<QueryClientProvider client={queryClient}>{elemento}</QueryClientProvider>)
  return queryClient
}

beforeEach(async () => {
  await i18n.changeLanguage('es')
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('useEventosTrabajo', () => {
  function HookDeEventos({ trabajoId }: { trabajoId: string }) {
    const { eventos, conexion } = useEventosTrabajo(trabajoId)
    return (
      <div>
        <p data-testid="conexion">{conexion}</p>
        <ul data-testid="eventos">
          {eventos.map((evento, indice) => (
            <li key={indice}>
              {evento.etapa}:{JSON.stringify(evento.contadores)}
            </li>
          ))}
        </ul>
      </div>
    )
  }

  it('recibe eventos por SSE y se reconecta con Last-Event-ID tras un corte', async () => {
    const llamadas: Array<Record<string, string>> = []
    const respuestas = [
      respuestaSSE([bloqueSSE(5, 'leyendo', { contadores: { leidas: 10 } })]),
      respuestaSSE([bloqueSSE(6, 'listo', { contadores: { leidas: 20 }, progreso: 1 })]),
    ]
    let indice = 0
    const fetchFalso = vi.fn(async (_url: string, init?: RequestInit) => {
      llamadas.push((init?.headers as Record<string, string>) ?? {})
      const respuesta = respuestas[Math.min(indice, respuestas.length - 1)]
      indice += 1
      return respuesta
    })
    vi.stubGlobal('fetch', fetchFalso)

    render(<HookDeEventos trabajoId={TRABAJO_ID} />)

    await screen.findByText('leyendo:{"leidas":10}')
    expect(llamadas[0]['Last-Event-ID']).toBeUndefined()

    // El primer stream se cerró sin un evento final: se reconecta solo, mandando el último id
    // visto como `Last-Event-ID`.
    await waitFor(() => expect(fetchFalso).toHaveBeenCalledTimes(2), { timeout: 3000 })
    expect(llamadas[1]['Last-Event-ID']).toBe('5')

    await screen.findByText('listo:{"leidas":20}')
    await waitFor(() => expect(screen.getByTestId('conexion').textContent).toBe('cerrada'))
    expect(fetchFalso).toHaveBeenCalledTimes(2) // "listo" es terminal: no reconecta más
  })
})

const INFORME_CALIDAD = {
  filas: 500,
  clientes: 50,
  productos: 20,
  fecha_min: '2024-01-01T00:00:00',
  fecha_max: '2024-06-01T00:00:00',
  duplicados_exactos: 3,
  descartadas: {},
  distribucion_compras_cliente: { minimo: 1, maximo: 18, promedio: 6.5, mediana: 7 },
  pares: { total_pares: 40, con_historia_suficiente: 30, porcentaje: 0.75 },
  viabilidad: {
    recompra: { viable: true, motivo: null },
    riesgo: { viable: true, motivo: null },
    ofertas: {
      viable: false,
      motivo: 'ningún cliente compró más de un producto distinto, no hay co-compra para calcular ofertas',
    },
  },
}

const PRODUCTO_A_REVISAR = {
  id: 'pr1',
  nombre: 'Café 500g',
  categoria: 'Alimentos',
  categoria_origen: 'jev',
  tipo: 'recompra',
  tipo_origen: 'jev',
  confianza: 0.6,
  estado_revision: 'revisar',
  estadisticas: null,
}

const GRUPO_PROPUESTO = {
  id: 'g1',
  nombre: 'Grupo 1',
  estado: 'propuesto',
  similitud: 0.92,
  productos: [
    { id: 'pr2', nombre: 'Coca Cola 500ml', categoria: null },
    { id: 'pr3', nombre: 'Coca-Cola 500 ml', categoria: null },
  ],
}

/** Servidor falso: la ingesta ya terminó (sin `trabajoId`, como al volver directo a la ruta),
 * así que `CalidadDataset` pide el informe de entrada. */
function crearServidorCalidad() {
  let productos = [PRODUCTO_A_REVISAR]
  let grupos = [GRUPO_PROPUESTO]
  const llamadas: Array<{ metodo: string; path: string; body?: unknown }> = []

  const fetchFalso = vi.fn(async (request: Request) => {
    const url = new URL(request.url)
    const metodo = request.method
    const coincideProducto = url.pathname.match(/^\/productos\/([^/]+)$/)
    const coincideGrupo = url.pathname.match(/^\/productos\/grupos\/([^/]+)\/(confirmar|rechazar)$/)

    if (metodo === 'GET' && url.pathname === `/datasets/${DATASET_ID}/calidad`) {
      return new Response(JSON.stringify(INFORME_CALIDAD), { status: 200 })
    }
    if (metodo === 'GET' && url.pathname === `/datasets/${DATASET_ID}/productos`) {
      return new Response(JSON.stringify(productos), { status: 200 })
    }
    if (metodo === 'PATCH' && coincideProducto) {
      const body = (await request.json()) as Record<string, unknown>
      llamadas.push({ metodo, path: url.pathname, body })
      productos = productos.map((p) =>
        p.id === coincideProducto[1] ? { ...p, ...body, estado_revision: 'ok' } : p,
      )
      return new Response(JSON.stringify(productos.find((p) => p.id === coincideProducto[1])), {
        status: 200,
      })
    }
    if (metodo === 'GET' && url.pathname === '/productos/grupos') {
      return new Response(JSON.stringify(grupos), { status: 200 })
    }
    if (metodo === 'POST' && coincideGrupo) {
      llamadas.push({ metodo, path: url.pathname })
      const grupoId = coincideGrupo[1]
      const grupo = grupos.find((g) => g.id === grupoId)
      grupos = grupos.filter((g) => g.id !== grupoId)
      return new Response(
        JSON.stringify({ ...grupo, estado: coincideGrupo[2] === 'confirmar' ? 'confirmado' : 'rechazado' }),
        { status: 200 },
      )
    }
    throw new Error(`ruta no simulada: ${metodo} ${url.pathname}`)
  })

  return { fetchFalso, llamadas }
}

describe('calidad del dataset', () => {
  it('muestra el informe de calidad con sus tarjetas y la viabilidad por análisis', async () => {
    const { fetchFalso } = crearServidorCalidad()
    vi.stubGlobal('fetch', fetchFalso)
    renderConQuery(<CalidadDataset datasetId={DATASET_ID} />)

    await screen.findByText('Informe de calidad')
    expect(screen.getByTestId('tarjeta-filas').textContent).toBe('500')
    expect(screen.getByTestId('tarjeta-clientes').textContent).toBe('50')
    expect(screen.getByTestId('tarjeta-productos').textContent).toBe('20')
    expect(screen.getByTestId('tarjeta-duplicados').textContent).toBe('3')

    expect(screen.getAllByText('Viable')).toHaveLength(2) // recompra y riesgo
    screen.getByText('No alcanza') // ofertas
    screen.getByText(
      'ningún cliente compró más de un producto distinto, no hay co-compra para calcular ofertas',
    )
  })

  it('corrige en línea el tipo y la categoría de un producto a revisar', async () => {
    const { fetchFalso, llamadas } = crearServidorCalidad()
    vi.stubGlobal('fetch', fetchFalso)
    renderConQuery(<CalidadDataset datasetId={DATASET_ID} />)

    await screen.findByText('Productos a revisar')
    screen.getByText('Café 500g')

    fireEvent.change(screen.getByRole('combobox', { name: 'Tipo de Café 500g' }), {
      target: { value: 'durable' },
    })
    await waitFor(() =>
      expect(llamadas).toContainEqual({
        metodo: 'PATCH',
        path: '/productos/pr1',
        body: { tipo: 'durable' },
      }),
    )

    const categoria = screen.getByLabelText('Categoría de Café 500g')
    fireEvent.change(categoria, { target: { value: 'Bebidas' } })
    fireEvent.blur(categoria)
    await waitFor(() =>
      expect(llamadas).toContainEqual({
        metodo: 'PATCH',
        path: '/productos/pr1',
        body: { categoria: 'Bebidas' },
      }),
    )
  })

  it('confirma y rechaza propuestas de productos equivalentes', async () => {
    const { fetchFalso, llamadas } = crearServidorCalidad()
    vi.stubGlobal('fetch', fetchFalso)
    renderConQuery(<CalidadDataset datasetId={DATASET_ID} />)

    await screen.findByText('Coca Cola 500ml · Coca-Cola 500 ml')
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar' }))

    await waitFor(() =>
      expect(llamadas).toContainEqual({
        metodo: 'POST',
        path: '/productos/grupos/g1/confirmar',
      }),
    )
    await screen.findByText('No hay propuestas de productos equivalentes.')
  })
})
