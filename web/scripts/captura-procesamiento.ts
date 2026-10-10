/**
 * `npm run captura:procesamiento` (spec F8.1.T1): graba un GIF/MP4 corto de la escena 3D del
 * procesamiento para el contenido de la serie.
 *
 * No depende de un trabajo real corriendo: levanta el propio servidor de Vite del proyecto (con
 * los mismos plugins/alias/CSS que la app) sirviendo un arnés mínimo que monta
 * `EscenaProcesamiento` directamente con un "stream falso" — la misma secuencia de
 * etapas/contadores que emite `api/src/predicts/analisis/orquestador.py` — tal como permite la
 * spec, y usa Playwright (con el Chrome del sistema, sin descargar un navegador aparte) para
 * grabar el video y ffmpeg para convertirlo a mp4.
 */
import { spawnSync } from 'node:child_process'
import { mkdirSync, readdirSync, rmSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { chromium } from 'playwright'
import { createServer, type Plugin } from 'vite'

const DIR_PROYECTO = join(dirname(fileURLToPath(import.meta.url)), '..')
const DIR_SALIDA = join(DIR_PROYECTO, 'captura')
const ANCHO = 960
const ALTO = 320 // la escena mide `h-72` (288px): un poco más de alto evita recortar el overlay
const DURACION_MS = 8000

const HTML_ARNES = `<!doctype html>
<html lang="es">
  <head><meta charset="utf-8" /><title>captura</title></head>
  <body style="margin:0;background:#020617">
    <div id="root"></div>
    <script type="module" src="/captura-entry.tsx"></script>
  </body>
</html>
`

const ENTRY_TSX = `
import { useEffect, useState, StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@/styles.css'
import '@/i18n'
import i18n from '@/i18n'
import EscenaProcesamiento from '@/tres/procesamiento/EscenaProcesamiento'
import type { EventoTrabajo } from '@/hooks/useEventosTrabajo'

void i18n.changeLanguage('es')

// Stream falso (permitido por la spec F8.1.T1 para la captura): la misma secuencia de
// etapas/contadores reales del orquestador de análisis, sin necesitar un trabajo real corriendo.
const SECUENCIA: EventoTrabajo[] = [
  { etapa: 'leyendo', contadores: { filas: 80000, clientes: 600, productos: 180 }, progreso: 0.15 },
  { etapa: 'leyendo', contadores: { filas: 3200000, clientes: 9500, productos: 1400 }, progreso: 0.45 },
  { etapa: 'ciclos', contadores: { productos: 1400 }, progreso: 0.6 },
  { etapa: 'prediccion', contadores: { pares: 1400, recordatorios: 520 }, progreso: 0.85 },
  { etapa: 'listo', contadores: {}, progreso: 1 },
]

function Arnes() {
  const [indice, setIndice] = useState(0)

  useEffect(() => {
    if (indice >= SECUENCIA.length - 1) return
    const temporizador = setTimeout(() => setIndice((i) => i + 1), 1500)
    return () => clearTimeout(temporizador)
  }, [indice])

  return (
    <div style={{ width: ${ANCHO}, height: ${ALTO} }}>
      <EscenaProcesamiento eventos={SECUENCIA.slice(0, indice + 1)} conexion="abierta" />
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Arnes />
  </StrictMode>,
)
`

function pluginArnesCaptura(): Plugin {
  return {
    name: 'arnes-captura',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (req.url === '/captura.html') {
          void server.transformIndexHtml('/captura.html', HTML_ARNES).then((html) => {
            res.setHeader('Content-Type', 'text/html')
            res.end(html)
          })
          return
        }
        next()
      })
    },
    resolveId(id) {
      if (id === '/captura-entry.tsx') return id
    },
    load(id) {
      if (id === '/captura-entry.tsx') return ENTRY_TSX
    },
  }
}

async function main() {
  rmSync(DIR_SALIDA, { recursive: true, force: true })
  mkdirSync(DIR_SALIDA, { recursive: true })

  const servidor = await createServer({
    root: DIR_PROYECTO,
    configFile: false,
    resolve: { alias: { '@': join(DIR_PROYECTO, 'src') } },
    plugins: [react(), tailwindcss(), pluginArnesCaptura()],
    server: { port: 4173, strictPort: false },
    logLevel: 'warn',
  })
  await servidor.listen()
  const url = servidor.resolvedUrls?.local[0]
  if (!url) throw new Error('No se pudo levantar el servidor de Vite para la captura')

  const navegador = await chromium.launch({ channel: 'chrome' })
  const contexto = await navegador.newContext({
    viewport: { width: ANCHO, height: ALTO },
    recordVideo: { dir: DIR_SALIDA, size: { width: ANCHO, height: ALTO } },
  })
  const pagina = await contexto.newPage()
  await pagina.goto(`${url}captura.html`)
  await pagina.waitForTimeout(DURACION_MS)
  await contexto.close() // recién al cerrar el contexto Playwright termina de escribir el .webm
  await navegador.close()
  await servidor.close()

  const webm = readdirSync(DIR_SALIDA).find((archivo) => archivo.endsWith('.webm'))
  if (!webm) throw new Error('Playwright no generó el video de la captura')
  const rutaWebm = join(DIR_SALIDA, webm)
  const rutaMp4 = join(DIR_SALIDA, 'procesamiento.mp4')

  const ffmpeg = spawnSync('ffmpeg', [
    '-y',
    '-i', rutaWebm,
    '-vf', 'fps=24',
    '-pix_fmt', 'yuv420p',
    rutaMp4,
  ])
  if (ffmpeg.status !== 0) {
    throw new Error(`ffmpeg falló (código ${ffmpeg.status}): ${ffmpeg.stderr?.toString() ?? ''}`)
  }
  rmSync(rutaWebm)

  console.log(`Captura generada: ${rutaMp4}`)
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
