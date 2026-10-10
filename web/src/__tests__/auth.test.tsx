import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import '../i18n'
import i18n from '../i18n'
import { _configurarIrALogin, cliente } from '../api/cliente'
import { SelectorIdioma } from '../components/layout/SelectorIdioma'
import { CLAVE_SESION } from '../hooks/useSesion'
import { Login } from '../routes/login'

const { navegar } = vi.hoisted(() => ({ navegar: vi.fn() }))

vi.mock('@tanstack/react-router', async (importOriginal) => {
  const real = await importOriginal<typeof import('@tanstack/react-router')>()
  return {
    ...real,
    useNavigate: () => navegar,
    Link: ({ children, to }: { children: ReactNode; to: string }) => <a href={to}>{children}</a>,
  }
})

const SESION = {
  usuario: { id: 'u1', email: 'ana@acme.com', rol: 'dueno' },
  empresa: { id: 'e1', nombre: 'Acme' },
  idioma: 'es' as const,
}

function limpiarCookies() {
  for (const fila of document.cookie.split('; ')) {
    const nombre = fila.split('=')[0]
    if (nombre) document.cookie = `${nombre}=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/`
  }
}

beforeEach(async () => {
  navegar.mockClear()
  limpiarCookies()
  _configurarIrALogin(() => {})
  await i18n.changeLanguage('es')
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function renderConQuery(elemento: ReactNode) {
  const queryClient = new QueryClient()
  render(<QueryClientProvider client={queryClient}>{elemento}</QueryClientProvider>)
  return queryClient
}

describe('login', () => {
  it('inicia sesión y navega a /proyectos', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify(SESION), { status: 200 })),
    )
    renderConQuery(<Login />)

    fireEvent.change(screen.getByLabelText('Correo'), { target: { value: 'ana@acme.com' } })
    fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'contrasena-larga' } })
    fireEvent.click(screen.getByRole('button', { name: 'Iniciar sesión' }))

    await waitFor(() => expect(navegar).toHaveBeenCalledWith({ to: '/proyectos' }))
  })

  it('si la API no responde, muestra el error genérico y vuelve a habilitar el botón', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('Failed to fetch')
      }),
    )
    renderConQuery(<Login />)

    fireEvent.change(screen.getByLabelText('Correo'), { target: { value: 'ana@acme.com' } })
    fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'contrasena-larga' } })
    fireEvent.click(screen.getByRole('button', { name: 'Iniciar sesión' }))

    await screen.findByRole('alert')
    expect(screen.getByRole('alert').textContent).toBe('Ocurrió un error. Intenta de nuevo.')
    expect((screen.getByRole('button', { name: 'Iniciar sesión' }) as HTMLButtonElement).disabled).toBe(false)
    expect(navegar).not.toHaveBeenCalled()
  })

  it('muestra el error de credenciales traducido en pt-BR, es y en', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(JSON.stringify({ codigo: 'credenciales_invalidas', parametros: {} }), {
            status: 401,
          }),
      ),
    )
    renderConQuery(<Login />)

    fireEvent.change(screen.getByLabelText('Correo'), { target: { value: 'ana@acme.com' } })
    fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'incorrecta' } })
    fireEvent.click(screen.getByRole('button', { name: 'Iniciar sesión' }))

    await screen.findByRole('alert')
    expect(screen.getByRole('alert').textContent).toBe('El correo o la contraseña son incorrectos.')

    await i18n.changeLanguage('en')
    expect(screen.getByRole('alert').textContent).toBe('Email or password is incorrect.')

    await i18n.changeLanguage('pt-BR')
    expect(screen.getByRole('alert').textContent).toBe('O e-mail ou a senha estão incorretos.')

    expect(navegar).not.toHaveBeenCalled()
  })
})

describe('cliente de API', () => {
  it('redirige a /login en 401 fuera de /auth, pero no para la sonda de sesión', async () => {
    const irALogin = vi.fn()
    _configurarIrALogin(irALogin)
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(JSON.stringify({ codigo: 'no_autenticado', parametros: {} }), {
            status: 401,
          }),
      ),
    )

    await cliente.GET('/api-keys')
    expect(irALogin).toHaveBeenCalledTimes(1)

    irALogin.mockClear()
    await cliente.GET('/auth/yo')
    expect(irALogin).not.toHaveBeenCalled()
  })

  it('envía X-CSRF-Token leído de la cookie predicts_csrf en métodos que cambian estado', async () => {
    document.cookie = 'predicts_csrf=token-de-prueba'
    let headerRecibido: string | null = null
    vi.stubGlobal(
      'fetch',
      vi.fn(async (request: Request) => {
        headerRecibido = request.headers.get('X-CSRF-Token')
        return new Response(null, { status: 204 })
      }),
    )

    await cliente.POST('/auth/logout')

    expect(headerRecibido).toBe('token-de-prueba')
  })
})

describe('selector de idioma', () => {
  it('cambia el idioma y lo persiste con PATCH /auth/yo cuando hay sesión', async () => {
    const llamadas: Array<{ metodo: string; idioma: string }> = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (request: Request) => {
        const url = new URL(request.url)
        if (url.pathname === '/auth/yo' && request.method === 'GET') {
          return new Response(JSON.stringify(SESION), { status: 200 })
        }
        if (url.pathname === '/auth/yo' && request.method === 'PATCH') {
          const body = (await request.json()) as { idioma: string }
          llamadas.push({ metodo: 'PATCH', idioma: body.idioma })
          return new Response(JSON.stringify({ ...SESION, idioma: body.idioma }), { status: 200 })
        }
        throw new Error(`ruta no simulada: ${request.method} ${url.pathname}`)
      }),
    )

    const queryClient = renderConQuery(<SelectorIdioma />)
    await waitFor(() => expect(queryClient.getQueryData(CLAVE_SESION)).toEqual(SESION))

    fireEvent.click(screen.getByRole('button', { name: 'English' }))

    await waitFor(() => expect(llamadas).toEqual([{ metodo: 'PATCH', idioma: 'en' }]))
    expect(i18n.language).toBe('en')
  })
})
