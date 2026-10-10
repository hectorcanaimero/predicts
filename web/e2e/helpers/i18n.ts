import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

/** Lee los mismos JSON de `src/i18n/locales/` que carga la app (ver `src/i18n/index.ts`), para
 * que los selectores del e2e busquen el texto real que la UI muestra en cada idioma en vez de
 * tener una copia hardcodeada que se desincroniza en silencio cuando alguien traduce distinto. */
const RAIZ_LOCALES = fileURLToPath(new URL('../../src/i18n/locales', import.meta.url))

export type Idioma = 'pt-BR' | 'es' | 'en'

const cache = new Map<string, unknown>()

function cargarNamespace(idioma: Idioma, namespace: string): Record<string, unknown> {
  const clave = `${idioma}/${namespace}`
  let datos = cache.get(clave)
  if (datos === undefined) {
    const contenido = readFileSync(`${RAIZ_LOCALES}/${idioma}/${namespace}.json`, 'utf-8')
    datos = JSON.parse(contenido)
    cache.set(clave, datos)
  }
  return datos as Record<string, unknown>
}

/** Equivalente de `useTranslation(namespace).t(clave, variables)`: `clave` puede tener puntos
 * (`"nuevo.acciones.lanzar"`) y `variables` interpola `{{nombre}}` igual que i18next. */
export function t(
  idioma: Idioma,
  namespace: string,
  clave: string,
  variables: Record<string, string | number> = {},
): string {
  let valor: unknown = cargarNamespace(idioma, namespace)
  for (const parte of clave.split('.')) {
    if (typeof valor !== 'object' || valor === null) {
      throw new Error(`clave de traducción "${namespace}:${clave}" no encontrada en "${idioma}"`)
    }
    valor = (valor as Record<string, unknown>)[parte]
  }
  if (typeof valor !== 'string') {
    throw new Error(`clave de traducción "${namespace}:${clave}" no encontrada en "${idioma}"`)
  }
  return valor.replace(/\{\{(\w+)\}\}/g, (_coincidencia, nombre: string) => String(variables[nombre] ?? ''))
}
