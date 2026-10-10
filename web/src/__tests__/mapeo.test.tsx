import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import '../i18n'
import i18n from '../i18n'
import { MapeoDataset } from '../features/mapeo/MapeoDataset'

const DATASET_ID = 'd1'

const DETECCION = {
  codificacion: 'utf-8',
  separador: ',',
  encabezado: true,
  vista_previa: [],
  columnas: [
    {
      nombre: 'fecha_compra',
      tipo: 'VARCHAR',
      porcentaje_nulos: 0,
      valores_muestra: ['01/02/2024', '02/02/2024'],
      candidatos_fecha: [
        { formato: 'dd/mm/aaaa', porcentaje: 1.0 },
        { formato: 'mm/dd/aaaa', porcentaje: 0.0 },
      ],
      separador_decimal: null,
    },
    {
      nombre: 'id_cliente',
      tipo: 'VARCHAR',
      porcentaje_nulos: 0,
      valores_muestra: ['c1', 'c2'],
      candidatos_fecha: [],
      separador_decimal: null,
    },
    {
      nombre: 'sku_producto',
      tipo: 'VARCHAR',
      porcentaje_nulos: 0,
      valores_muestra: ['SKU-1', 'SKU-2'],
      candidatos_fecha: [],
      separador_decimal: null,
    },
    {
      nombre: 'vendedor',
      tipo: 'VARCHAR',
      porcentaje_nulos: 0,
      valores_muestra: ['Juan', 'Ana'],
      candidatos_fecha: [],
      separador_decimal: null,
    },
  ],
}

const DATASET = {
  id: DATASET_ID,
  proyecto_id: 'p1',
  nombre_archivo: 'ventas.csv',
  tamano_bytes: 100,
  sha256: 'abc',
  estado: 'subido',
  deteccion: DETECCION,
}

const SUGERENCIAS = {
  columnas: [
    { columna: 'fecha_compra', campo: 'fecha', confianza: 0.95, origen: 'jev', estado: 'prellenado' },
    { columna: 'id_cliente', campo: 'cliente_id', confianza: 0.9, origen: 'jev', estado: 'prellenado' },
    { columna: 'sku_producto', campo: 'producto_id', confianza: 0.6, origen: 'jev', estado: 'revisar' },
    { columna: 'vendedor', campo: 'ignorar', confianza: 0.99, origen: 'jev', estado: 'prellenado' },
  ],
  producto_id_tipo: { tipo: 'sku', confianza: 0.55, origen: 'jev' },
  origen: 'jev',
  firma_encabezados: 'firma1',
}

function crearServidorMapeo() {
  const llamadas: Array<{ metodo: string; path: string; body?: unknown }> = []

  const fetchFalso = vi.fn(async (request: Request) => {
    const url = new URL(request.url)
    const metodo = request.method

    if (metodo === 'GET' && url.pathname === `/datasets/${DATASET_ID}`) {
      return new Response(JSON.stringify(DATASET), { status: 200 })
    }
    if (metodo === 'GET' && url.pathname === `/datasets/${DATASET_ID}/mapeo`) {
      return new Response(JSON.stringify(SUGERENCIAS), { status: 200 })
    }
    if (metodo === 'PUT' && url.pathname === `/datasets/${DATASET_ID}/mapeo`) {
      const body = await request.json()
      llamadas.push({ metodo, path: url.pathname, body })
      return new Response(
        JSON.stringify({ id: DATASET_ID, estado: 'mapeado', mapeo: body }),
        { status: 200 },
      )
    }
    if (metodo === 'POST' && url.pathname === `/datasets/${DATASET_ID}/ingesta`) {
      llamadas.push({ metodo, path: url.pathname })
      return new Response(JSON.stringify({ trabajo_id: 't1', estado: 'ingiriendo' }), { status: 202 })
    }
    throw new Error(`ruta no simulada: ${metodo} ${url.pathname}`)
  })

  return { fetchFalso, llamadas }
}

function renderConQuery(elemento: ReactNode) {
  const queryClient = new QueryClient()
  render(<QueryClientProvider client={queryClient}>{elemento}</QueryClientProvider>)
}

function valorDe(nombreAccesible: string): string {
  return (screen.getByRole('combobox', { name: nombreAccesible }) as HTMLSelectElement).value
}

function botonConfirmarDeshabilitado(): boolean {
  return (screen.getByRole('button', { name: 'Confirmar e iniciar ingesta' }) as HTMLButtonElement)
    .disabled
}

beforeEach(async () => {
  await i18n.changeLanguage('es')
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('mapeo de columnas', () => {
  it('prellena cada columna con la sugerencia de Jev y muestra la insignia de confianza', async () => {
    const { fetchFalso } = crearServidorMapeo()
    vi.stubGlobal('fetch', fetchFalso)
    renderConQuery(<MapeoDataset datasetId={DATASET_ID} />)

    await screen.findByRole('combobox', { name: 'fecha_compra' })
    expect(valorDe('fecha_compra')).toBe('fecha')
    expect(valorDe('id_cliente')).toBe('cliente_id')
    expect(valorDe('sku_producto')).toBe('producto_id')
    expect(valorDe('vendedor')).toBe('ignorar')

    expect(screen.getAllByText('Sugerido')).toHaveLength(3) // fecha_compra, id_cliente, vendedor
    expect(screen.getAllByText('Revisar')).toHaveLength(2) // sku_producto y producto_id_tipo

    expect(valorDe('Formato de fecha')).toBe('dd/mm/aaaa')
    expect(valorDe('Tipo de identificador de producto')).toBe('sku')
  })

  it('valida en vivo: campos obligatorios faltantes y campos duplicados', async () => {
    const { fetchFalso } = crearServidorMapeo()
    vi.stubGlobal('fetch', fetchFalso)
    renderConQuery(<MapeoDataset datasetId={DATASET_ID} />)

    await screen.findByRole('combobox', { name: 'fecha_compra' })
    expect(screen.queryByRole('alert')).toBeNull()

    // Deja de mapear el cliente: falta un campo obligatorio.
    fireEvent.change(screen.getByRole('combobox', { name: 'id_cliente' }), {
      target: { value: 'ignorar' },
    })
    await screen.findByRole('alert')
    screen.getByText('Falta asignar el campo obligatorio "cliente_id".')
    expect(botonConfirmarDeshabilitado()).toBe(true)

    // Vuelve a mapearlo, pero duplicado con otra columna: campo duplicado.
    fireEvent.change(screen.getByRole('combobox', { name: 'id_cliente' }), {
      target: { value: 'cliente_id' },
    })
    fireEvent.change(screen.getByRole('combobox', { name: 'vendedor' }), {
      target: { value: 'cliente_id' },
    })
    await screen.findByText('El campo "cliente_id" está asignado a más de una columna.')
    expect(botonConfirmarDeshabilitado()).toBe(true)

    // Corrige el duplicado: la validación se limpia y el botón vuelve a habilitarse.
    fireEvent.change(screen.getByRole('combobox', { name: 'vendedor' }), {
      target: { value: 'ignorar' },
    })
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
    expect(botonConfirmarDeshabilitado()).toBe(false)
  })

  it('guarda como plantilla y confirma el mapeo, iniciando la ingesta', async () => {
    const alIngestaIniciada = vi.fn()
    const { fetchFalso, llamadas } = crearServidorMapeo()
    vi.stubGlobal('fetch', fetchFalso)
    renderConQuery(<MapeoDataset datasetId={DATASET_ID} onIngestaIniciada={alIngestaIniciada} />)

    await screen.findByRole('combobox', { name: 'fecha_compra' })

    fireEvent.click(screen.getByLabelText('Guardar como plantilla'))
    fireEvent.change(screen.getByLabelText('Nombre de la plantilla'), {
      target: { value: 'Plantilla ventas' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar e iniciar ingesta' }))

    await waitFor(() =>
      expect(llamadas).toContainEqual({
        metodo: 'PUT',
        path: `/datasets/${DATASET_ID}/mapeo`,
        body: {
          columnas: [
            { columna: 'fecha_compra', campo: 'fecha' },
            { columna: 'id_cliente', campo: 'cliente_id' },
            { columna: 'sku_producto', campo: 'producto_id' },
            { columna: 'vendedor', campo: 'ignorar' },
          ],
          producto_id_tipo: 'sku',
          formato_fecha: 'dd/mm/aaaa',
          guardar_como_plantilla: true,
          nombre_plantilla: 'Plantilla ventas',
        },
      }),
    )
    await waitFor(() =>
      expect(llamadas).toContainEqual({ metodo: 'POST', path: `/datasets/${DATASET_ID}/ingesta` }),
    )
    await waitFor(() => expect(alIngestaIniciada).toHaveBeenCalledWith('t1'))
  })
})
