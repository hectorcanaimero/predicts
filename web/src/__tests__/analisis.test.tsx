import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import '../i18n'
import i18n from '../i18n'
import { ProgresoAnalisis } from '../features/analisis/ProgresoAnalisis'
import { SeleccionAnalisis } from '../features/analisis/SeleccionAnalisis'

const DATASET_ID = 'd1'
const ANALISIS_ID = 'a1'
const TRABAJO_ID = 't1'

function bloqueSSE(id: number, evento: string, datos: Record<string, unknown>): string {
  return `id: ${id}\nevent: ${evento}\ndata: ${JSON.stringify(datos)}`
}

/** `cerrar=false` deja el stream abierto (sin `controller.close()`) para que el hook no intente
 * reconectar durante el test. */
function respuestaSSE(bloques: string[], cerrar = true): Response {
  const texto = bloques.map((bloque) => `${bloque}\n\n`).join('')
  const stream = new ReadableStream<Uint8Array>({
    start(controlador) {
      controlador.enqueue(new TextEncoder().encode(texto))
      if (cerrar) controlador.close()
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

const INFORME_CALIDAD_BASE = {
  filas: 500,
  clientes: 50,
  productos: 20,
  fecha_min: '2024-01-01T00:00:00',
  fecha_max: '2024-06-01T00:00:00',
  duplicados_exactos: 0,
  descartadas: {},
  distribucion_compras_cliente: { minimo: 1, maximo: 18, promedio: 6.5, mediana: 7 },
  pares: { total_pares: 40, con_historia_suficiente: 30, porcentaje: 0.75 },
}

const MOTIVO_OFERTAS = 'ningún cliente compró más de un producto distinto, no hay co-compra para calcular ofertas'

function crearServidorNuevo(
  opciones: { ofertasViable?: boolean; ofertasRespuesta?: 'ok' | 'invalida' } = {},
) {
  const llamadas: Array<{ metodo: string; path: string; body?: unknown }> = []
  const fetchFalso = vi.fn(async (request: Request) => {
    const url = new URL(request.url)
    const metodo = request.method

    if (metodo === 'GET' && url.pathname === `/datasets/${DATASET_ID}/calidad`) {
      return new Response(
        JSON.stringify({
          ...INFORME_CALIDAD_BASE,
          viabilidad: {
            recompra: { viable: true, motivo: null },
            riesgo: { viable: true, motivo: null },
            ofertas: opciones.ofertasViable
              ? { viable: true, motivo: null }
              : { viable: false, motivo: MOTIVO_OFERTAS },
          },
        }),
        { status: 200 },
      )
    }
    if (metodo === 'POST' && url.pathname === `/datasets/${DATASET_ID}/ofertas`) {
      llamadas.push({ metodo, path: url.pathname })
      // El `File` de jsdom no sobrevive al paso por el `FormData`/`Request` nativos en este
      // entorno de test (ni el nombre ni el contenido): la respuesta la decide la opción del
      // servidor falso, no lo que trae el archivo.
      if (opciones.ofertasRespuesta === 'invalida') {
        return new Response(JSON.stringify({ codigo: 'ofertas_columnas', parametros: {} }), { status: 422 })
      }
      return new Response(JSON.stringify({ productos: 3 }), { status: 201 })
    }
    if (metodo === 'POST' && url.pathname === `/datasets/${DATASET_ID}/analisis`) {
      const body = (await request.json()) as Record<string, unknown>
      llamadas.push({ metodo, path: url.pathname, body })
      return new Response(
        JSON.stringify({
          id: ANALISIS_ID,
          dataset_id: DATASET_ID,
          tipos: body.tipos,
          parametros: body.parametros,
          estado: 'en_cola',
          trabajo_id: TRABAJO_ID,
          version_modelo: null,
          metricas: null,
          resumen: null,
          costo_ia: null,
        }),
        { status: 202 },
      )
    }
    throw new Error(`ruta no simulada: ${metodo} ${url.pathname}`)
  })
  return { fetchFalso, llamadas }
}

describe('elegir análisis', () => {
  it('muestra las tarjetas con los parámetros por defecto y deshabilita las que no alcanzan por viabilidad', async () => {
    const { fetchFalso } = crearServidorNuevo({ ofertasViable: false })
    vi.stubGlobal('fetch', fetchFalso)
    renderConQuery(<SeleccionAnalisis datasetId={DATASET_ID} onLanzado={vi.fn()} />)

    await screen.findByText('Recordatorios de recompra')
    screen.getByText('Ciclos por producto')
    screen.getByText('Riesgo de abandono')
    await screen.findByText(`No alcanza: ${MOTIVO_OFERTAS}`)

    expect(screen.getByTestId('tarjeta-ofertas').getAttribute('aria-disabled')).toBe('true')
    expect((screen.getByRole('spinbutton', { name: 'Mínimo de compras' }) as HTMLInputElement).value).toBe('3')
    expect((screen.getByRole('spinbutton', { name: 'Horizonte (días)' }) as HTMLInputElement).value).toBe('7')
    expect((screen.getByRole('spinbutton', { name: 'Umbral de probabilidad' }) as HTMLInputElement).value).toBe(
      '0.5',
    )

    // No viable: un clic no la selecciona.
    fireEvent.click(screen.getByTestId('tarjeta-ofertas'))
    expect(screen.getByTestId('tarjeta-ofertas').getAttribute('aria-pressed')).toBe('false')

    // Viable: un clic sí la selecciona.
    fireEvent.click(screen.getByTestId('tarjeta-recompra'))
    expect(screen.getByTestId('tarjeta-recompra').getAttribute('aria-pressed')).toBe('true')
  })

  it('lanza el análisis con los tipos elegidos y los parámetros editados', async () => {
    const { fetchFalso, llamadas } = crearServidorNuevo({ ofertasViable: false })
    vi.stubGlobal('fetch', fetchFalso)
    const onLanzado = vi.fn()
    renderConQuery(<SeleccionAnalisis datasetId={DATASET_ID} onLanzado={onLanzado} />)

    await screen.findByText('Recordatorios de recompra')
    fireEvent.click(screen.getByTestId('tarjeta-recompra'))
    fireEvent.click(screen.getByTestId('tarjeta-ciclos'))
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Mínimo de compras' }), {
      target: { value: '5' },
    })

    fireEvent.click(screen.getByRole('button', { name: 'Lanzar análisis' }))

    await waitFor(() =>
      expect(llamadas).toContainEqual({
        metodo: 'POST',
        path: `/datasets/${DATASET_ID}/analisis`,
        body: {
          tipos: ['recompra', 'ciclos'],
          parametros: { desde: null, hasta: null, min_compras: 5, horizonte: 7, umbral: 0.5 },
        },
      }),
    )
    await waitFor(() => expect(onLanzado).toHaveBeenCalledWith(ANALISIS_ID))
  })

  it('exige elegir al menos un análisis', async () => {
    const { fetchFalso } = crearServidorNuevo({ ofertasViable: false })
    vi.stubGlobal('fetch', fetchFalso)
    renderConQuery(<SeleccionAnalisis datasetId={DATASET_ID} onLanzado={vi.fn()} />)

    await screen.findByText('Recordatorios de recompra')
    expect((screen.getByRole('button', { name: 'Lanzar análisis' }) as HTMLButtonElement).disabled).toBe(true)
    screen.getByText('Elige al menos un análisis.')
  })

  it('sube la lista de ofertas antes de lanzar cuando se elige ofertas', async () => {
    const { fetchFalso, llamadas } = crearServidorNuevo({ ofertasViable: true, ofertasRespuesta: 'ok' })
    vi.stubGlobal('fetch', fetchFalso)
    const onLanzado = vi.fn()
    renderConQuery(<SeleccionAnalisis datasetId={DATASET_ID} onLanzado={onLanzado} />)

    await screen.findByText('Ofertas')
    fireEvent.click(screen.getByTestId('tarjeta-ofertas'))

    const archivo = new File(['producto_id,descuento\np1,0.1\n'], 'ofertas.csv', { type: 'text/csv' })
    fireEvent.change(screen.getByLabelText('Lista de ofertas (opcional)'), { target: { files: [archivo] } })
    fireEvent.click(screen.getByRole('button', { name: 'Lanzar análisis' }))

    await screen.findByText('3 productos cargados.')
    await waitFor(() =>
      expect(llamadas).toContainEqual({ metodo: 'POST', path: `/datasets/${DATASET_ID}/ofertas` }),
    )
    await waitFor(() => expect(onLanzado).toHaveBeenCalledWith(ANALISIS_ID))
  })

  it('muestra el error traducido y no lanza el análisis si la lista de ofertas es inválida', async () => {
    const { fetchFalso, llamadas } = crearServidorNuevo({ ofertasViable: true, ofertasRespuesta: 'invalida' })
    vi.stubGlobal('fetch', fetchFalso)
    const onLanzado = vi.fn()
    renderConQuery(<SeleccionAnalisis datasetId={DATASET_ID} onLanzado={onLanzado} />)

    await screen.findByText('Ofertas')
    fireEvent.click(screen.getByTestId('tarjeta-ofertas'))
    const archivo = new File(['no es un csv valido'], 'invalida.csv', { type: 'text/csv' })
    fireEvent.change(screen.getByLabelText('Lista de ofertas (opcional)'), { target: { files: [archivo] } })
    fireEvent.click(screen.getByRole('button', { name: 'Lanzar análisis' }))

    await screen.findByText('El CSV de ofertas debe tener las columnas producto_id y descuento.')
    expect(llamadas.some((l) => l.path === `/datasets/${DATASET_ID}/analisis`)).toBe(false)
    expect(onLanzado).not.toHaveBeenCalled()
  })
})

function crearServidorProgreso(opciones: {
  bloquesSSE: string[]
  cerrarSSE?: boolean
  estadoAnalisis?: string
  errorCodigo?: string | null
}) {
  const llamadas: Array<{ metodo: string; path: string }> = []
  let cancelado = false
  // `useEventosTrabajo` llama a `fetch(url, init)` directamente (no por el cliente
  // openapi-fetch, que en cambio pasa un `Request`): hay que aceptar las dos formas.
  const fetchFalso = vi.fn(async (entrada: Request | string, init?: RequestInit) => {
    const esRequest = entrada instanceof Request
    const url = new URL(esRequest ? (entrada as Request).url : (entrada as string))
    const metodo = esRequest ? (entrada as Request).method : init?.method ?? 'GET'

    if (metodo === 'GET' && url.pathname === `/analisis/${ANALISIS_ID}`) {
      return new Response(
        JSON.stringify({
          id: ANALISIS_ID,
          dataset_id: DATASET_ID,
          tipos: ['recompra'],
          parametros: null,
          estado: cancelado ? 'cancelado' : opciones.estadoAnalisis ?? 'corriendo',
          trabajo_id: TRABAJO_ID,
          version_modelo: null,
          metricas: null,
          resumen: null,
          costo_ia: null,
        }),
        { status: 200 },
      )
    }
    if (metodo === 'GET' && url.pathname === `/trabajos/${TRABAJO_ID}/eventos`) {
      return respuestaSSE(opciones.bloquesSSE, opciones.cerrarSSE ?? true)
    }
    if (metodo === 'GET' && url.pathname === `/trabajos/${TRABAJO_ID}`) {
      return new Response(
        JSON.stringify({
          id: TRABAJO_ID,
          tipo: 'analisis',
          estado: cancelado ? 'cancelado' : opciones.errorCodigo ? 'error' : 'corriendo',
          error_codigo: opciones.errorCodigo ?? null,
          error_detalle: null,
          duracion_s: null,
          memoria_pico_mb: null,
          creado_en: '2024-01-01T00:00:00',
          iniciado_en: null,
          terminado_en: null,
        }),
        { status: 200 },
      )
    }
    if (metodo === 'POST' && url.pathname === `/trabajos/${TRABAJO_ID}/cancelar`) {
      llamadas.push({ metodo, path: url.pathname })
      cancelado = true
      return new Response(null, { status: 204 })
    }
    throw new Error(`ruta no simulada: ${metodo} ${url.pathname}`)
  })
  return { fetchFalso, llamadas }
}

describe('progreso del análisis', () => {
  it('muestra el progreso 2D con un stream falso y pasa a resultados cuando termina', async () => {
    const { fetchFalso } = crearServidorProgreso({
      bloquesSSE: [
        bloqueSSE(1, 'leyendo', { contadores: { filas: 10 } }),
        bloqueSSE(2, 'listo', { contadores: { filas: 10 }, progreso: 1 }),
      ],
    })
    vi.stubGlobal('fetch', fetchFalso)
    const onCompletado = vi.fn()
    renderConQuery(<ProgresoAnalisis analisisId={ANALISIS_ID} onCompletado={onCompletado} />)

    await screen.findByText('Etapa: listo')
    screen.getByText('filas: 10')
    await waitFor(() => expect(onCompletado).toHaveBeenCalledWith(ANALISIS_ID))
  })

  it('cancela un análisis en curso', async () => {
    const { fetchFalso, llamadas } = crearServidorProgreso({
      bloquesSSE: [bloqueSSE(1, 'leyendo', { contadores: { filas: 5 } })],
      cerrarSSE: false,
    })
    vi.stubGlobal('fetch', fetchFalso)
    renderConQuery(<ProgresoAnalisis analisisId={ANALISIS_ID} onCompletado={vi.fn()} />)

    await screen.findByText('Etapa: leyendo')
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))

    await waitFor(() =>
      expect(llamadas).toContainEqual({ metodo: 'POST', path: `/trabajos/${TRABAJO_ID}/cancelar` }),
    )
    await screen.findByText('Análisis cancelado.')
    expect((screen.getByRole('button', { name: 'Cancelar' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('muestra el error traducido cuando el trabajo termina por memoria', async () => {
    const { fetchFalso } = crearServidorProgreso({
      bloquesSSE: [bloqueSSE(1, 'error', { contadores: {} })],
      errorCodigo: 'memoria_excedida',
    })
    vi.stubGlobal('fetch', fetchFalso)
    renderConQuery(<ProgresoAnalisis analisisId={ANALISIS_ID} onCompletado={vi.fn()} />)

    await screen.findByText('El análisis superó la memoria disponible.')
    expect((screen.getByRole('button', { name: 'Cancelar' }) as HTMLButtonElement).disabled).toBe(true)
  })
})
