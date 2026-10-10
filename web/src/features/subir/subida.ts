import { aErrorApi, ErrorApi, URL_BASE_API } from '@/api/cliente'
import type { components } from '@/api/schema'

export type Dataset = components['schemas']['DatasetSalida']

const EXTENSIONES_VALIDAS = ['.csv', '.csv.gz', '.zip']
const TAMANO_BLOQUE_PREVIA = 64 * 1024
const FILAS_PREVIA = 10
const COOKIE_CSRF = 'predicts_csrf'

export function extensionValida(nombreArchivo: string): boolean {
  const minuscula = nombreArchivo.toLowerCase()
  return EXTENSIONES_VALIDAS.some((ext) => minuscula.endsWith(ext))
}

export interface Previa {
  encabezado: string[]
  filas: string[][]
}

/** Lee el primer bloque del archivo en el navegador y lo parte en filas/columnas (coma como
 * separador, sin manejar comillas: es solo una vista previa, no el parseo real del backend).
 * Para `.csv.gz`/`.zip` no hay vista previa: requeriría descomprimir en el navegador. */
export async function leerPrevia(archivo: File): Promise<Previa | null> {
  if (!archivo.name.toLowerCase().endsWith('.csv')) return null
  const truncado = archivo.size > TAMANO_BLOQUE_PREVIA
  const texto = await archivo.slice(0, TAMANO_BLOQUE_PREVIA).text()
  let lineas = texto.split(/\r?\n/).filter((linea) => linea.length > 0)
  if (truncado) lineas = lineas.slice(0, -1)
  const [encabezado, ...resto] = lineas.map((linea) => linea.split(','))
  return { encabezado: encabezado ?? [], filas: resto.slice(0, FILAS_PREVIA) }
}

export class SubidaCancelada extends Error {}

export interface ProgresoSubida {
  cargado: number
  total: number
}

export interface ControladorSubida {
  promesa: Promise<Dataset>
  cancelar: () => void
}

function leerCookieCsrf(): string | undefined {
  const fila = document.cookie.split('; ').find((c) => c.startsWith(`${COOKIE_CSRF}=`))
  return fila?.slice(COOKIE_CSRF.length + 1)
}

/** Sube `archivo` a `/proyectos/{proyectoId}/datasets` con progreso real y cancelación: usa
 * XMLHttpRequest (no el cliente openapi-fetch) porque es la única API con evento de progreso
 * de subida y `abort()` nativo. */
export function subirDataset(
  proyectoId: string,
  archivo: File,
  onProgreso: (progreso: ProgresoSubida) => void,
): ControladorSubida {
  const xhr = new XMLHttpRequest()
  const promesa = new Promise<Dataset>((resolve, reject) => {
    xhr.open('POST', `${URL_BASE_API}/proyectos/${proyectoId}/datasets`)
    xhr.withCredentials = true
    const csrf = leerCookieCsrf()
    if (csrf) xhr.setRequestHeader('X-CSRF-Token', csrf)
    xhr.upload.onprogress = (evento) => {
      if (evento.lengthComputable) onProgreso({ cargado: evento.loaded, total: evento.total })
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText) as Dataset)
        return
      }
      try {
        reject(aErrorApi(JSON.parse(xhr.responseText)))
      } catch {
        reject(new ErrorApi('error_generico'))
      }
    }
    xhr.onerror = () => reject(new ErrorApi('error_generico'))
    xhr.onabort = () => reject(new SubidaCancelada())
    const datos = new FormData()
    datos.append('archivo', archivo)
    xhr.send(datos)
  })
  return { promesa, cancelar: () => xhr.abort() }
}
