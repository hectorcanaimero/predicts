import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import '../i18n'
import i18n from '../i18n'
import { ChatAgente } from '../features/agente/ChatAgente'

const DATASET_ID = 'd1'

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

function fetchFalsoDe(respuesta: unknown, status = 200) {
  return vi.fn(async (request: Request) => {
    const url = new URL(request.url)
    if (request.method === 'POST' && url.pathname === '/agente/preguntas') {
      return new Response(JSON.stringify(respuesta), { status })
    }
    throw new Error(`sin manejar: ${request.method} ${url.pathname}`)
  })
}

async function preguntar(texto: string) {
  fireEvent.change(screen.getByLabelText('Tu pregunta'), { target: { value: texto } })
  fireEvent.click(screen.getByRole('button', { name: 'Preguntar' }))
}

describe('ChatAgente', () => {
  it('envía una pregunta y muestra la respuesta, las consultas y las filas de muestra', async () => {
    const respuesta = {
      respuesta: 'El producto más comprado es Café 500g.',
      consultas: [
        {
          sql: 'SELECT producto_id, count(*) AS n FROM compras GROUP BY producto_id ORDER BY n DESC LIMIT 1',
          filas_muestra: [{ producto_id: 'p1', n: 42 }],
          n_filas: 1,
        },
      ],
      advertencias: [],
      costo_ia: {},
    }
    const fetchFalso = fetchFalsoDe(respuesta)
    vi.stubGlobal('fetch', fetchFalso)

    renderConQuery(<ChatAgente datasetId={DATASET_ID} />)

    await preguntar('¿Cuál es el producto más comprado?')

    await screen.findByText('¿Cuál es el producto más comprado?')
    await screen.findByText('El producto más comprado es Café 500g.')

    expect(fetchFalso).toHaveBeenCalledTimes(1)

    // La primera pregunta no manda historial todavía.
    const peticion = fetchFalso.mock.calls[0][0] as Request
    const texto = await peticion.clone().text()
    expect(JSON.parse(texto)).toEqual({
      dataset_id: DATASET_ID,
      pregunta: '¿Cuál es el producto más comprado?',
      historial: [],
    })

    // El desplegable "cómo lo calculé" trae la consulta resaltada y la tabla de filas.
    fireEvent.click(screen.getByText('Cómo lo calculé'))
    screen.getByText('SELECT') // la consulta resaltada
    screen.getByRole('columnheader', { name: 'producto_id' }) // la tabla de filas de muestra
    screen.getByRole('cell', { name: 'p1' })
    screen.getByRole('cell', { name: '42' })
  })

  it('manda el historial de la sesión en la siguiente pregunta', async () => {
    const primera = {
      respuesta: 'Hay 500 compras en total.',
      consultas: [],
      advertencias: [],
      costo_ia: {},
    }
    const segunda = {
      respuesta: 'El cliente con más compras es c1.',
      consultas: [],
      advertencias: [],
      costo_ia: {},
    }
    let llamadas = 0
    const fetchFalso = vi.fn(async (request: Request) => {
      void request
      llamadas += 1
      return new Response(JSON.stringify(llamadas === 1 ? primera : segunda), { status: 200 })
    })
    vi.stubGlobal('fetch', fetchFalso)

    renderConQuery(<ChatAgente datasetId={DATASET_ID} />)

    await preguntar('¿Cuántas compras hay?')
    await screen.findByText('Hay 500 compras en total.')

    await preguntar('¿Y qué cliente compró más?')
    await screen.findByText('El cliente con más compras es c1.')

    const segundaPeticion = fetchFalso.mock.calls[1][0] as Request
    const cuerpo = JSON.parse(await segundaPeticion.clone().text())
    expect(cuerpo.historial).toEqual([
      { rol: 'usuario', contenido: '¿Cuántas compras hay?' },
      { rol: 'agente', contenido: 'Hay 500 compras en total.' },
    ])
  })

  it('muestra las advertencias de forma visible, sin esconderlas en el desplegable', async () => {
    const respuesta = {
      respuesta: 'No encontré datos suficientes para los últimos 30 días.',
      consultas: [],
      advertencias: ['Los datos de los últimos 30 días están incompletos.'],
      costo_ia: {},
    }
    vi.stubGlobal('fetch', fetchFalsoDe(respuesta))

    renderConQuery(<ChatAgente datasetId={DATASET_ID} />)
    await preguntar('¿Cómo van las ventas del último mes?')

    const advertencia = await screen.findByText('Los datos de los últimos 30 días están incompletos.')
    expect(advertencia.closest('[role="alert"]')).not.toBeNull()
  })

  it('traduce el error cuando el dataset todavía no está listo', async () => {
    vi.stubGlobal(
      'fetch',
      fetchFalsoDe({ codigo: 'dataset_no_listo', parametros: { estado: 'procesando' } }, 409),
    )

    renderConQuery(<ChatAgente datasetId={DATASET_ID} />)
    await preguntar('¿Cuántos productos hay?')

    await waitFor(() => screen.getByText('El dataset todavía no está listo para preguntas.'))
  })

  it('cae al mensaje de error genérico ante un error desconocido', async () => {
    vi.stubGlobal('fetch', fetchFalsoDe({}, 500))

    renderConQuery(<ChatAgente datasetId={DATASET_ID} />)
    await preguntar('¿Cuántos clientes hay?')

    await waitFor(() => screen.getByText('Ocurrió un error al preguntarle al agente. Intenta de nuevo.'))
  })
})
