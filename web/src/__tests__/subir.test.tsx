import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import '../i18n'
import i18n from '../i18n'
import { ZonaSubida } from '../features/subir/ZonaSubida'

/** `XMLHttpRequest` falso: `subida.ts` lo usa directamente (no el cliente openapi-fetch) para
 * tener progreso real de subida y cancelación. Captura la última instancia creada para que los
 * tests puedan simular `onprogress`, `onload` y `abort()`. */
class XhrFalso {
  static ultima: XhrFalso | undefined

  method = ''
  url = ''
  withCredentials = false
  status = 0
  responseText = ''
  enviado: FormData | null = null
  abortado = false
  upload: { onprogress: ((evento: ProgressEvent) => void) | null } = { onprogress: null }
  onload: (() => void) | null = null
  onerror: (() => void) | null = null
  onabort: (() => void) | null = null

  constructor() {
    XhrFalso.ultima = this
  }

  open(method: string, url: string) {
    this.method = method
    this.url = url
  }

  setRequestHeader() {
    // no-op en el falso
  }

  send(body: FormData) {
    this.enviado = body
  }

  abort() {
    this.abortado = true
    this.onabort?.()
  }

  simularProgreso(cargado: number, total: number) {
    this.upload.onprogress?.({ lengthComputable: true, loaded: cargado, total } as ProgressEvent)
  }

  simularRespuesta(status: number, cuerpo: unknown) {
    this.status = status
    this.responseText = JSON.stringify(cuerpo)
    this.onload?.()
  }
}

function archivoCsv(contenido = 'nombre,valor\nA,1\nB,2\n') {
  return new File([contenido], 'ventas.csv', { type: 'text/csv' })
}

beforeEach(async () => {
  await i18n.changeLanguage('es')
  XhrFalso.ultima = undefined
  vi.stubGlobal('XMLHttpRequest', XhrFalso)
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('subir dataset', () => {
  it('selecciona un archivo por botón, muestra la vista previa y sube con progreso', async () => {
    render(<ZonaSubida proyectoId="p1" />)

    const input = screen.getByLabelText('Arrastra aquí tu archivo CSV, .csv.gz o .zip', {
      selector: 'input',
    })
    fireEvent.change(input, { target: { files: [archivoCsv()] } })

    await screen.findByText('Vista previa')
    screen.getByRole('columnheader', { name: 'nombre' })
    screen.getByRole('columnheader', { name: 'valor' })
    screen.getByRole('cell', { name: 'A' })

    expect(XhrFalso.ultima?.method).toBe('POST')
    expect(XhrFalso.ultima?.url).toBe('http://localhost:8000/proyectos/p1/datasets')

    XhrFalso.ultima?.simularProgreso(50, 100)
    await screen.findByText('50%')
  })

  it('selecciona un archivo arrastrándolo a la zona', async () => {
    render(<ZonaSubida proyectoId="p1" />)

    const zona = screen.getByRole('group', { name: 'Arrastra aquí tu archivo CSV, .csv.gz o .zip' })
    fireEvent.drop(zona, { dataTransfer: { files: [archivoCsv()] } })

    await screen.findByText('Vista previa')
    expect(XhrFalso.ultima?.method).toBe('POST')
  })

  it('cancela la subida en curso y vuelve a permitir elegir archivo', async () => {
    render(<ZonaSubida proyectoId="p1" />)

    fireEvent.change(
      screen.getByLabelText('Arrastra aquí tu archivo CSV, .csv.gz o .zip', { selector: 'input' }),
      { target: { files: [archivoCsv()] } },
    )
    await screen.findByText('0%')

    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))

    expect(XhrFalso.ultima?.abortado).toBe(true)
    await screen.findByRole('button', { name: 'Elegir archivo' })
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('al terminar, avisa con el id del dataset creado', async () => {
    const alSubido = vi.fn()
    render(<ZonaSubida proyectoId="p1" onSubido={alSubido} />)

    fireEvent.change(
      screen.getByLabelText('Arrastra aquí tu archivo CSV, .csv.gz o .zip', { selector: 'input' }),
      { target: { files: [archivoCsv()] } },
    )
    await screen.findByText('0%')

    XhrFalso.ultima?.simularRespuesta(201, {
      id: 'd1',
      proyecto_id: 'p1',
      nombre_archivo: 'ventas.csv',
      tamano_bytes: 20,
      sha256: 'abc',
      estado: 'pendiente',
      deteccion: null,
    })

    await waitFor(() => expect(alSubido).toHaveBeenCalledWith('d1'))
  })

  it('muestra un error traducido cuando el formato no es soportado', async () => {
    render(<ZonaSubida proyectoId="p1" />)

    fireEvent.change(
      screen.getByLabelText('Arrastra aquí tu archivo CSV, .csv.gz o .zip', { selector: 'input' }),
      { target: { files: [new File(['x'], 'informe.pdf', { type: 'application/pdf' })] } },
    )

    await screen.findByRole('alert')
    screen.getByText('Formato no soportado. Usa un archivo .csv, .csv.gz o .zip.')
    expect(XhrFalso.ultima).toBeUndefined()
  })

  it('muestra un error traducido cuando el servidor rechaza el archivo por tamaño', async () => {
    render(<ZonaSubida proyectoId="p1" />)

    fireEvent.change(
      screen.getByLabelText('Arrastra aquí tu archivo CSV, .csv.gz o .zip', { selector: 'input' }),
      { target: { files: [archivoCsv()] } },
    )
    await screen.findByText('0%')

    XhrFalso.ultima?.simularRespuesta(413, { codigo: 'archivo_muy_grande', parametros: { max_mb: 200 } })

    await screen.findByRole('alert')
    screen.getByText('El archivo supera el límite de 200 MB.')
    fireEvent.click(screen.getByRole('button', { name: 'Elegir otro archivo' }))
    await screen.findByRole('button', { name: 'Elegir archivo' })
  })
})
