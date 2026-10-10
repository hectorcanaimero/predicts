import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import '../i18n'
import i18n from '../i18n'
import { BotonProbarDemo } from '../features/proyectos/BotonProbarDemo'
import { DemoRuta } from '../routes/_autenticado/demo'

const { navegar } = vi.hoisted(() => ({ navegar: vi.fn() }))

vi.mock('@tanstack/react-router', async (importOriginal) => {
  const real = await importOriginal<typeof import('@tanstack/react-router')>()
  return {
    ...real,
    useNavigate: () => navegar,
    Link: ({ children, to }: { children: ReactNode; to: string }) => <a href={to}>{children}</a>,
  }
})

function renderConQuery(elemento: ReactNode) {
  const queryClient = new QueryClient()
  render(<QueryClientProvider client={queryClient}>{elemento}</QueryClientProvider>)
}

beforeEach(async () => {
  await i18n.changeLanguage('es')
  navegar.mockClear()
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('botón "probar con datos de ejemplo"', () => {
  it('es un enlace a /demo', () => {
    renderConQuery(<BotonProbarDemo />)

    const enlace = screen.getByRole('link', { name: 'Probar con datos de ejemplo' })
    expect(enlace.getAttribute('href')).toBe('/demo')
  })
})

describe('ruta /demo', () => {
  it('crea el proyecto de demostración al entrar y redirige al progreso', async () => {
    const fetchFalso = vi.fn(async (request: Request) => {
      expect(request.method).toBe('POST')
      expect(new URL(request.url).pathname).toBe('/demo')
      return new Response(
        JSON.stringify({ proyecto_id: 'p1', dataset_id: 'd1', analisis_id: 'a1' }),
        { status: 201 },
      )
    })
    vi.stubGlobal('fetch', fetchFalso)

    renderConQuery(<DemoRuta />)

    await screen.findByText('Preparando tu proyecto de demostración…')
    await waitFor(() => expect(fetchFalso).toHaveBeenCalledTimes(1))
    await waitFor(() =>
      expect(navegar).toHaveBeenCalledWith({
        to: '/analisis/$analisisId/progreso',
        params: { analisisId: 'a1' },
      }),
    )
  })

  it('no vuelve a lanzar la demo dos veces al re-renderizar', async () => {
    const fetchFalso = vi.fn(
      async () =>
        new Response(
          JSON.stringify({ proyecto_id: 'p1', dataset_id: 'd1', analisis_id: 'a1' }),
          { status: 201 },
        ),
    )
    vi.stubGlobal('fetch', fetchFalso)

    renderConQuery(<DemoRuta />)

    await waitFor(() => expect(navegar).toHaveBeenCalledTimes(1))
    expect(fetchFalso).toHaveBeenCalledTimes(1)
  })

  it('muestra un error y permite reintentar', async () => {
    const fetchFalso = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ codigo: 'error_generico', parametros: {} }), {
          status: 500,
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ proyecto_id: 'p1', dataset_id: 'd1', analisis_id: 'a1' }),
          { status: 201 },
        ),
      )
    vi.stubGlobal('fetch', fetchFalso)

    renderConQuery(<DemoRuta />)

    await screen.findByRole('alert')
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))

    await waitFor(() => expect(fetchFalso).toHaveBeenCalledTimes(2))
    await waitFor(() =>
      expect(navegar).toHaveBeenCalledWith({
        to: '/analisis/$analisisId/progreso',
        params: { analisisId: 'a1' },
      }),
    )
  })
})
