import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import '../i18n'
import i18n from '../i18n'
import { ResultadosAnalisis } from '../features/resultados/ResultadosAnalisis'

const ANALISIS_ID = 'a1'

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
  vi.restoreAllMocks()
})

function tramo(i: number) {
  return { desde: i / 10, hasta: (i + 1) / 10, n: 5, predicho: i / 10 + 0.05, observado: i / 10 + 0.03 }
}

const METRICAS = {
  version_modelo: 'v1',
  semanas: 4,
  horizonte: 7,
  n_pares: 100,
  k: 20,
  modelo: {
    precision_at_k: { media: 0.7, desvio: 0.05 },
    cobertura_at_k: { media: 0.5, desvio: null },
    brier: { media: 0.12, desvio: 0.01 },
    mae_dias: { media: 2.3, desvio: 0.4 },
    calibracion: Array.from({ length: 10 }, (_, i) => tramo(i)),
  },
  linea_base: {
    precision_at_k: { media: 0.4, desvio: 0.02 },
    cobertura_at_k: { media: 0.3, desvio: null },
    brier: { media: 0.2, desvio: 0.01 },
    mae_dias: { media: 4.1, desvio: 0.6 },
    calibracion: Array.from({ length: 10 }, (_, i) => tramo(i)),
  },
}

const ANALISIS_BASE = {
  id: ANALISIS_ID,
  dataset_id: 'd1',
  tipos: ['recompra', 'ciclos', 'riesgo', 'ofertas'],
  parametros: null,
  estado: 'listo',
  trabajo_id: null,
  version_modelo: 'v1',
  metricas: METRICAS,
  resumen: null,
  costo_ia: null,
}

const RECOMPRA_PAGINA_1 = [
  {
    cliente_id: 'c1', producto_id: 'p1', producto_nombre: 'Producto Uno', ciclo: 30, p: 0.8,
    fecha_probable: '2024-03-10', fecha_min: '2024-03-05', fecha_max: '2024-03-15',
    n_compras: 5, dias_desde_ultima: 25, posible_abandono: false, motivo: 'Motivo uno',
  },
  {
    cliente_id: 'c2', producto_id: 'p1', producto_nombre: 'Producto Uno', ciclo: 20, p: 0.6,
    fecha_probable: '2024-03-10', fecha_min: '2024-03-08', fecha_max: '2024-03-12',
    n_compras: 3, dias_desde_ultima: 18, posible_abandono: false, motivo: 'Motivo dos',
  },
] // fmt: skip

const RECOMPRA_PAGINA_2 = [
  {
    cliente_id: 'c3', producto_id: 'p2', producto_nombre: 'Producto Dos', ciclo: 15, p: 0.55,
    fecha_probable: '2024-03-11', fecha_min: '2024-03-09', fecha_max: '2024-03-13',
    n_compras: 4, dias_desde_ultima: 14, posible_abandono: false, motivo: 'Motivo tres',
  },
] // fmt: skip

const CICLOS = [
  { producto_id: 'p1', producto_nombre: 'Producto Uno', ciclo_mediano: 30, dispersion: 4, desvio_log: 0.2, clientes_recurrentes: 12 },
  { producto_id: 'p2', producto_nombre: 'Producto Dos', ciclo_mediano: 15, dispersion: 2, desvio_log: 0.1, clientes_recurrentes: 7 },
] // fmt: skip

const RIESGO = [
  { nivel: 'producto', cliente_id: 'c1', producto_id: 'p1', producto_nombre: 'Producto Uno', n_compras: 5, ciclo: 30, dispersion: 4, dias_desde_ultima: 80, atraso: 50, valor: 900, motivo: 'Motivo de riesgo uno' },
  { nivel: 'tienda', cliente_id: 'c4', producto_id: null, producto_nombre: null, n_compras: 10, ciclo: 20, dispersion: 3, dias_desde_ultima: 60, atraso: 40, valor: 500, motivo: 'Motivo de riesgo dos' },
] // fmt: skip

const OFERTAS = [
  { cliente_id: 'c1', producto_id: 'p3', producto_nombre: 'Producto Tres', puntaje: 0.9, p_recompra: 0.7, lift: 2.1, por_producto: 'p1', descuento: 0.1, fuentes: ['recompra'], motivo: 'Motivo oferta uno' },
  { cliente_id: 'c2', producto_id: 'p4', producto_nombre: 'Producto Cuatro', puntaje: 0.75, p_recompra: null, lift: 3.2, por_producto: 'p1', descuento: 0, fuentes: ['cocompra'], motivo: 'Motivo oferta dos' },
] // fmt: skip

function plantillaFija(id: string, clave: string, tipo: string, texto: string, estado = 'ok') {
  return { id, clave, tipo, idioma: 'es', tono: 'neutro', texto, estado, motivo_revision: null }
}

function crearServidor() {
  const llamadas: Array<{ metodo: string; path: string; query: URLSearchParams; body?: unknown }> = []
  let plantillas = [
    plantillaFija('pl1', 'producto:p1::recordatorio', 'recordatorio', 'Hola, te recordamos tu compra.'),
    plantillaFija('pl2', 'producto:p2::oferta', 'oferta', 'Tenemos una oferta para ti.', 'revisar'),
  ]
  let regenerada = false

  const fetchFalso = vi.fn(async (entrada: Request | string, init?: RequestInit) => {
    const esRequest = entrada instanceof Request
    const url = new URL(esRequest ? (entrada as Request).url : (entrada as string))
    const metodo = esRequest ? (entrada as Request).method : init?.method ?? 'GET'
    const query = url.searchParams
    llamadas.push({ metodo, path: url.pathname, query })

    if (metodo === 'GET' && url.pathname === `/analisis/${ANALISIS_ID}`) {
      return new Response(JSON.stringify(ANALISIS_BASE), { status: 200 })
    }

    if (metodo === 'GET' && url.pathname === `/analisis/${ANALISIS_ID}/resultados`) {
      const tipo = query.get('tipo')
      const pagina = query.get('pagina')
      if (tipo === 'recompra') {
        const resultados = pagina === '2' ? RECOMPRA_PAGINA_2 : RECOMPRA_PAGINA_1
        return new Response(JSON.stringify({ pagina: Number(pagina), tam_pagina: 20, total: 25, resultados }), {
          status: 200,
        })
      }
      if (tipo === 'ciclos') {
        return new Response(JSON.stringify({ pagina: 1, tam_pagina: 20, total: 2, resultados: CICLOS }), {
          status: 200,
        })
      }
      if (tipo === 'riesgo') {
        return new Response(JSON.stringify({ pagina: 1, tam_pagina: 20, total: 2, resultados: RIESGO }), {
          status: 200,
        })
      }
      if (tipo === 'ofertas') {
        return new Response(JSON.stringify({ pagina: 1, tam_pagina: 20, total: 2, resultados: OFERTAS }), {
          status: 200,
        })
      }
      throw new Error(`tipo no simulado: ${tipo}`)
    }

    if (metodo === 'GET' && url.pathname === `/analisis/${ANALISIS_ID}/exportar`) {
      return new Response('cliente,producto\nc1,p1\n', {
        status: 200,
        headers: { 'content-disposition': 'attachment; filename="recordatorios.csv"' },
      })
    }

    if (metodo === 'GET' && url.pathname === `/analisis/${ANALISIS_ID}/plantillas`) {
      const salida = regenerada
        ? [...plantillas, plantillaFija('pl3', 'general::reactivacion', 'reactivacion', 'Mensaje regenerado.')]
        : plantillas
      return new Response(JSON.stringify(salida), { status: 200 })
    }

    if (metodo === 'PATCH' && url.pathname.startsWith('/plantillas-mensaje/')) {
      const id = url.pathname.split('/').pop()
      const body = (await (entrada as Request).json()) as { texto: string }
      llamadas[llamadas.length - 1].body = body
      plantillas = plantillas.map((p) => (p.id === id ? { ...p, texto: body.texto, estado: 'editada' } : p))
      const actualizada = plantillas.find((p) => p.id === id)
      return new Response(JSON.stringify(actualizada), { status: 200 })
    }

    if (metodo === 'POST' && url.pathname === `/analisis/${ANALISIS_ID}/plantillas/regenerar`) {
      regenerada = true
      return new Response(JSON.stringify({ trabajo_id: 'tr1' }), { status: 202 })
    }

    throw new Error(`ruta no simulada: ${metodo} ${url.pathname}`)
  })

  return { fetchFalso, llamadas }
}

describe('resultados del análisis', () => {
  it('pestaña Recordatorios: pagina, ordena y exporta', async () => {
    const { fetchFalso, llamadas } = crearServidor()
    vi.stubGlobal('fetch', fetchFalso)
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:mock')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    const clicEnlace = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

    renderConQuery(<ResultadosAnalisis analisisId={ANALISIS_ID} />)

    await screen.findByText('c1')
    screen.getByText('c2')
    screen.getByText('Recordatorios por día')

    // paginación: la página 2 trae otro cliente.
    fireEvent.click(screen.getByRole('button', { name: 'Siguiente' }))
    await screen.findByText('c3')

    // orden: cambiar la columna manda `orden` con el mismo sentido (desc por defecto).
    fireEvent.change(screen.getByRole('combobox', { name: 'Ordenar por' }), { target: { value: 'motivo' } })
    await waitFor(() =>
      expect(llamadas.some((l) => l.path.endsWith('/resultados') && l.query.get('orden') === '-motivo')).toBe(true),
    )

    // alternar a ascendente quita el `-`.
    fireEvent.click(screen.getByRole('button', { name: 'Descendente ↓' }))
    await waitFor(() =>
      expect(llamadas.some((l) => l.path.endsWith('/resultados') && l.query.get('orden') === 'motivo')).toBe(true),
    )

    // exportar: dispara la descarga con el nombre del `Content-Disposition`.
    fireEvent.click(screen.getByRole('button', { name: 'Exportar CSV' }))
    await waitFor(() => expect(clicEnlace).toHaveBeenCalled())
    expect(llamadas.some((l) => l.path.endsWith('/exportar') && l.query.get('tipo') === 'recordatorios')).toBe(true)
  })

  it('pestaña Ciclos: tabla y dispersión', async () => {
    const { fetchFalso } = crearServidor()
    vi.stubGlobal('fetch', fetchFalso)
    renderConQuery(<ResultadosAnalisis analisisId={ANALISIS_ID} />)

    await screen.findByText('c1')
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Ciclos por producto' }))

    await screen.findByText('Producto Uno')
    screen.getByText('Producto Dos')
    screen.getByText('Ciclo vs. clientes recurrentes')
  })

  it('pestaña Riesgo: motivo y valor', async () => {
    const { fetchFalso } = crearServidor()
    vi.stubGlobal('fetch', fetchFalso)
    renderConQuery(<ResultadosAnalisis analisisId={ANALISIS_ID} />)

    await screen.findByText('c1')
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Riesgo' }))

    await screen.findByText('Motivo de riesgo uno')
    screen.getByText('900')
    screen.getByText('Tienda')
  })

  it('pestaña Ofertas: por cliente', async () => {
    const { fetchFalso, llamadas } = crearServidor()
    vi.stubGlobal('fetch', fetchFalso)
    renderConQuery(<ResultadosAnalisis analisisId={ANALISIS_ID} />)

    await screen.findByText('c1')
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Ofertas' }))

    await screen.findByText('Producto Tres')
    screen.getByText('Producto Cuatro')
    await waitFor(() =>
      expect(llamadas.some((l) => l.path.endsWith('/resultados') && l.query.get('orden') === 'cliente_id')).toBe(
        true,
      ),
    )
  })

  it('pestaña Precisión: modelo vs. línea base y calibración', async () => {
    const { fetchFalso } = crearServidor()
    vi.stubGlobal('fetch', fetchFalso)
    renderConQuery(<ResultadosAnalisis analisisId={ANALISIS_ID} />)

    await screen.findByText('c1')
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Precisión' }))

    await screen.findByText('Precisión en el top-K')
    screen.getByText('70% (± 5%)')
    screen.getByText('40% (± 2%)')
    screen.getByText('Calibración por deciles')
  })

  it('pestaña Mensajes: edita una plantilla y regenera', async () => {
    const { fetchFalso, llamadas } = crearServidor()
    vi.stubGlobal('fetch', fetchFalso)
    renderConQuery(<ResultadosAnalisis analisisId={ANALISIS_ID} />)

    await screen.findByText('c1')
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Mensajes' }))

    await screen.findByText('Hola, te recordamos tu compra.')
    screen.getByText('Tenemos una oferta para ti.')

    fireEvent.click(screen.getByRole('button', { name: 'Editar producto:p1::recordatorio' }))
    const campo = screen.getByRole('textbox', { name: 'Mensaje de producto:p1::recordatorio' })
    fireEvent.change(campo, { target: { value: 'Mensaje editado a mano.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar producto:p1::recordatorio' }))

    await screen.findByText('Mensaje editado a mano.')
    await screen.findByText('Editada a mano')
    expect(llamadas).toContainEqual(
      expect.objectContaining({ metodo: 'PATCH', path: '/plantillas-mensaje/pl1', body: { texto: 'Mensaje editado a mano.' } }),
    )

    fireEvent.click(screen.getByRole('button', { name: 'Regenerar plantillas' }))
    await waitFor(() =>
      expect(llamadas.some((l) => l.metodo === 'POST' && l.path === `/analisis/${ANALISIS_ID}/plantillas/regenerar`)).toBe(
        true,
      ),
    )
    await screen.findByText('Mensaje regenerado.')
  })

  it('no_listo: avisa cuando el análisis todavía no terminó', async () => {
    const fetchFalso = vi.fn(async (entrada: Request) => {
      const url = new URL(entrada.url)
      if (url.pathname === `/analisis/${ANALISIS_ID}`) {
        return new Response(JSON.stringify({ ...ANALISIS_BASE, estado: 'corriendo' }), { status: 200 })
      }
      throw new Error(`ruta no simulada: ${url.pathname}`)
    })
    vi.stubGlobal('fetch', fetchFalso)
    renderConQuery(<ResultadosAnalisis analisisId={ANALISIS_ID} />)

    await screen.findByText('El análisis todavía no tiene resultados.')
  })
})
