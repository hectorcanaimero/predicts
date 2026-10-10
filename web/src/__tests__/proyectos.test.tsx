import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import '../i18n'
import i18n from '../i18n'
import { Proyectos } from '../routes/_autenticado/proyectos/index'

vi.mock('@tanstack/react-router', async (importOriginal) => {
  const real = await importOriginal<typeof import('@tanstack/react-router')>()
  return {
    ...real,
    useNavigate: () => vi.fn(),
    Link: ({ children, to }: { children: ReactNode; to: string }) => <a href={to}>{children}</a>,
  }
})

interface ProyectoFalso {
  id: string
  nombre: string
  idioma_mensajes: 'pt-BR' | 'es' | 'en'
  tono: 'cercano' | 'neutro' | 'formal'
  descripcion: string | null
}

/** Servidor falso en memoria para `/proyectos`: soporta listar, crear, editar y borrar. */
function crearServidorProyectos(inicial: ProyectoFalso[]) {
  let lista = [...inicial]
  const llamadas: Array<{ metodo: string; path: string; body?: unknown }> = []

  const fetchFalso = vi.fn(async (request: Request) => {
    const url = new URL(request.url)
    const metodo = request.method
    const coincideId = url.pathname.match(/^\/proyectos\/([^/]+)$/)

    if (metodo === 'GET' && url.pathname === '/proyectos') {
      llamadas.push({ metodo, path: url.pathname })
      return new Response(JSON.stringify(lista), { status: 200 })
    }
    if (metodo === 'POST' && url.pathname === '/proyectos') {
      const body = (await request.json()) as Omit<ProyectoFalso, 'id'>
      llamadas.push({ metodo, path: url.pathname, body })
      const nuevo: ProyectoFalso = { id: `p${lista.length + 1}`, ...body }
      lista = [...lista, nuevo]
      return new Response(JSON.stringify(nuevo), { status: 201 })
    }
    if (metodo === 'PATCH' && coincideId) {
      const body = (await request.json()) as Partial<ProyectoFalso>
      llamadas.push({ metodo, path: url.pathname, body })
      lista = lista.map((p) => (p.id === coincideId[1] ? { ...p, ...body } : p))
      return new Response(JSON.stringify(lista.find((p) => p.id === coincideId[1])), { status: 200 })
    }
    if (metodo === 'DELETE' && coincideId) {
      llamadas.push({ metodo, path: url.pathname })
      lista = lista.filter((p) => p.id !== coincideId[1])
      return new Response(null, { status: 204 })
    }
    throw new Error(`ruta no simulada: ${metodo} ${url.pathname}`)
  })

  return { fetchFalso, llamadas }
}

function renderConQuery(elemento: ReactNode) {
  const queryClient = new QueryClient()
  render(<QueryClientProvider client={queryClient}>{elemento}</QueryClientProvider>)
  return queryClient
}

const PROYECTO_ACME: ProyectoFalso = {
  id: 'p1',
  nombre: 'Acme',
  idioma_mensajes: 'es',
  tono: 'neutro',
  descripcion: null,
}

beforeEach(async () => {
  await i18n.changeLanguage('es')
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('lista de proyectos', () => {
  it('muestra el estado de carga mientras llega la respuesta', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
    const { container } = render(
      <QueryClientProvider client={new QueryClient()}>
        <Proyectos />
      </QueryClientProvider>,
    )

    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0)
    expect(screen.queryByText('Proyectos')).toBeNull()
  })

  it('muestra el estado vacío con un llamado a crear el primero', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify([]), { status: 200 })))
    renderConQuery(<Proyectos />)

    await screen.findByText('Todavía no tienes proyectos')
    screen.getByRole('button', { name: 'Crear tu primer proyecto' })
  })

  it('muestra el estado de error con un botón para reintentar', async () => {
    const fetchFalso = vi.fn(async () =>
      new Response(JSON.stringify({ codigo: 'error_generico', parametros: {} }), { status: 500 }),
    )
    vi.stubGlobal('fetch', fetchFalso)
    renderConQuery(<Proyectos />)

    await screen.findByRole('alert')
    screen.getByText('Ocurrió un error al cargar la información.')

    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    await waitFor(() => expect(fetchFalso).toHaveBeenCalledTimes(2))
  })

  it('lista los proyectos existentes', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify([PROYECTO_ACME]), { status: 200 })),
    )
    renderConQuery(<Proyectos />)

    await screen.findByText('Acme')
    screen.getByRole('button', { name: 'Nuevo proyecto' })
  })

  it('crea un proyecto desde el diálogo y lo refleja en la lista', async () => {
    const { fetchFalso, llamadas } = crearServidorProyectos([])
    vi.stubGlobal('fetch', fetchFalso)
    renderConQuery(<Proyectos />)

    await screen.findByText('Todavía no tienes proyectos')
    fireEvent.click(screen.getByRole('button', { name: 'Crear tu primer proyecto' }))

    const dialogo = await screen.findByRole('dialog')
    fireEvent.change(within(dialogo).getByLabelText('Nombre'), { target: { value: 'Nueva Empresa' } })
    fireEvent.change(within(dialogo).getByLabelText('Idioma de los mensajes'), {
      target: { value: 'en' },
    })
    fireEvent.change(within(dialogo).getByLabelText('Tono'), { target: { value: 'formal' } })
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Guardar' }))

    await waitFor(() =>
      expect(llamadas).toContainEqual({
        metodo: 'POST',
        path: '/proyectos',
        body: { nombre: 'Nueva Empresa', idioma_mensajes: 'en', tono: 'formal', descripcion: null },
      }),
    )
    await screen.findByText('Nueva Empresa')
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('edita un proyecto existente desde el diálogo', async () => {
    const { fetchFalso, llamadas } = crearServidorProyectos([PROYECTO_ACME])
    vi.stubGlobal('fetch', fetchFalso)
    renderConQuery(<Proyectos />)

    await screen.findByText('Acme')
    fireEvent.click(screen.getByRole('button', { name: 'Editar' }))

    const dialogo = await screen.findByRole('dialog')
    expect((within(dialogo).getByLabelText('Nombre') as HTMLInputElement).value).toBe('Acme')
    fireEvent.change(within(dialogo).getByLabelText('Nombre'), { target: { value: 'Acme Corp' } })
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Guardar' }))

    await waitFor(() =>
      expect(llamadas).toContainEqual({
        metodo: 'PATCH',
        path: '/proyectos/p1',
        body: { nombre: 'Acme Corp', idioma_mensajes: 'es', tono: 'neutro', descripcion: null },
      }),
    )
    await screen.findByText('Acme Corp')
  })

  it('borra un proyecto tras confirmar', async () => {
    const { fetchFalso, llamadas } = crearServidorProyectos([PROYECTO_ACME])
    vi.stubGlobal('fetch', fetchFalso)
    renderConQuery(<Proyectos />)

    await screen.findByText('Acme')
    fireEvent.click(screen.getByRole('button', { name: 'Eliminar' }))

    const dialogo = await screen.findByRole('dialog')
    within(dialogo).getByText(/Acme/)
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Eliminar' }))

    await waitFor(() => expect(llamadas).toContainEqual({ metodo: 'DELETE', path: '/proyectos/p1' }))
    await screen.findByText('Todavía no tienes proyectos')
  })
})
