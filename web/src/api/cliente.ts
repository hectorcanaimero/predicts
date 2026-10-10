import createClient, { type Middleware } from 'openapi-fetch'

import type { paths } from './schema'

export const URL_BASE_API =
  (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

const COOKIE_CSRF = 'predicts_csrf'
const HEADER_CSRF = 'X-CSRF-Token'
const METODOS_PROTEGIDOS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

/** Error de la API: `{codigo, parametros}` (ver `api/src/predicts/errores.py`). */
export class ErrorApi extends Error {
  constructor(
    public codigo: string,
    public parametros: Record<string, unknown> = {},
  ) {
    super(codigo)
  }
}

function leerCookie(nombre: string): string | undefined {
  const fila = document.cookie.split('; ').find((c) => c.startsWith(`${nombre}=`))
  return fila?.slice(nombre.length + 1)
}

/** Reasignable en tests; por defecto navega de verdad a /login. */
export let irALogin = () => {
  window.location.assign('/login')
}

export function _configurarIrALogin(fn: () => void): void {
  irALogin = fn
}

const middleware: Middleware = {
  onRequest({ request }) {
    if (METODOS_PROTEGIDOS.has(request.method)) {
      const csrf = leerCookie(COOKIE_CSRF)
      if (csrf) request.headers.set(HEADER_CSRF, csrf)
    }
    return request
  },
  async onResponse({ request, response }) {
    // Login/registro/recuperar/restablecer/yo manejan su propio 401 (credenciales, sesión
    // todavía no iniciada); solo las rutas protegidas fuera de /auth/ fuerzan la redirección.
    // Con base relativa (`/api`, detrás del proxy de nginx) el pathname trae ese prefijo.
    const basePath = new URL(URL_BASE_API, window.location.origin).pathname.replace(/\/$/, '')
    const ruta = new URL(request.url).pathname.slice(basePath.length)
    const esRutaAuth = ruta.startsWith('/auth/')
    if (response.status === 401 && !esRutaAuth) {
      irALogin()
    }
    return response
  },
}

export const cliente = createClient<paths>({
  baseUrl: URL_BASE_API,
  credentials: 'include',
  // Indirección para que los tests puedan reemplazar `globalThis.fetch` después de importar
  // este módulo (openapi-fetch, si no, fija la referencia a `fetch` al crear el cliente).
  fetch: (...args: Parameters<typeof fetch>) => globalThis.fetch(...args),
})
cliente.use(middleware)

/** Convierte el `error` de openapi-fetch (shape `{codigo, parametros}`) en `ErrorApi`. */
export function aErrorApi(error: unknown): ErrorApi {
  if (
    error &&
    typeof error === 'object' &&
    'codigo' in error &&
    typeof (error as { codigo: unknown }).codigo === 'string'
  ) {
    const parametros = 'parametros' in error ? (error as { parametros?: unknown }).parametros : {}
    return new ErrorApi(
      (error as { codigo: string }).codigo,
      (parametros as Record<string, unknown>) ?? {},
    )
  }
  return new ErrorApi('error_generico')
}

/** Clave de traducción para un `ErrorApi`: distingue por `parametros.motivo` cuando existe
 * (p. ej. `contrasena_invalida` con `motivo: "corta"` → `contrasena_invalida_corta`). */
export function claveError(error: ErrorApi): string {
  const motivo = error.parametros.motivo
  return typeof motivo === 'string' ? `${error.codigo}_${motivo}` : error.codigo
}
