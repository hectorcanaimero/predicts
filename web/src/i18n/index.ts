import i18n from 'i18next'
import LanguageDetector from 'i18next-browser-languagedetector'
import { initReactI18next } from 'react-i18next'

export const IDIOMAS = ['pt-BR', 'es', 'en'] as const
export type Idioma = (typeof IDIOMAS)[number]

const modulos = import.meta.glob<{ default: Record<string, string> }>(
  './locales/*/*.json',
  { eager: true },
)

const resources: Record<string, Record<string, Record<string, string>>> = {}

for (const [ruta, modulo] of Object.entries(modulos)) {
  const coincidencia = ruta.match(/\.\/locales\/([^/]+)\/([^/]+)\.json$/)
  if (!coincidencia) continue
  const [, idioma, namespace] = coincidencia
  resources[idioma] ??= {}
  resources[idioma][namespace] = modulo.default
}

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: 'pt-BR',
    supportedLngs: IDIOMAS,
    ns: ['comun'],
    defaultNS: 'comun',
    interpolation: { escapeValue: false },
    detection: { order: ['navigator', 'htmlTag'], caches: [] },
  })

export default i18n
