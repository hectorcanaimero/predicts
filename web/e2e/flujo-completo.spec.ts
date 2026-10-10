import { expect, test } from '@playwright/test'
import { fileURLToPath } from 'node:url'

import { emailUnico } from './helpers/datos'
import { t } from './helpers/i18n'

/** CSV de fixture generado para este e2e (`api/tests/e2e/dataset.csv`, ver el comentario al
 * inicio de ese archivo): cabeceras que ya coinciden con los nombres de `CAMPOS_ESQUEMA`
 * (`cliente_id`, `fecha`, `producto_id`, ...) y suficiente historial repetido para que los 4
 * tipos de análisis salgan "viables" en la pantalla de calidad (ver `datos/calidad.py`). */
const CSV_FIXTURE = fileURLToPath(new URL('../../api/tests/e2e/dataset.csv', import.meta.url))

/** Columnas del CSV de fixture, en el mismo orden que sus cabeceras; el nombre de columna y el
 * campo interno a elegir son el mismo string a propósito (ver el generador del CSV), así no
 * hace falta una tabla columna→campo separada para el mapeo. */
const CAMPOS_A_MAPEAR = [
  'cliente_id',
  'fecha',
  'producto_id',
  'producto_nombre',
  'pedido_id',
  'cantidad',
  'precio_unitario',
  'valor_total',
  'categoria',
  'marca',
]

const TIPOS_ANALISIS = ['recompra', 'ciclos', 'riesgo', 'ofertas'] as const

test.describe('flujo completo (registro a exportación)', () => {
  // `locale` tiene que ser exactamente uno de `IDIOMAS` (`web/src/i18n/index.ts`): el
  // detector de i18next no recorta la región ("es-ES" no matchea "es", nonExplicitSupportedLngs
  // no está activado), así que "es-ES"/"en-US" caerían al fallback `pt-BR` en silencio.
  test.use({ locale: 'es' })

  test('registra, crea proyecto, sube el CSV, mapea, espera calidad, corre los 4 análisis, ve resultados y exporta', async ({
    page,
  }, testInfo) => {
    const idioma = 'es' as const
    const inicio = Date.now()

    // 1. Registro ------------------------------------------------------------------------------
    await page.goto('/registro')
    await page.getByLabel(t(idioma, 'auth', 'registro.nombre_empresa')).fill('Tienda E2E')
    await page.getByLabel(t(idioma, 'auth', 'registro.email')).fill(emailUnico('flujo'))
    await page.getByLabel(t(idioma, 'auth', 'registro.contrasena')).fill('contrasena-e2e-123')
    // exact: true -- sin esto, "Idioma" matchea también el aria-label="idioma" (minúscula, sin
    // traducir) del selector de idioma de la UI en el header de `__root.tsx`.
    await page.getByLabel(t(idioma, 'auth', 'registro.idioma'), { exact: true }).selectOption('es')
    await page.getByRole('button', { name: t(idioma, 'auth', 'registro.enviar') }).click()
    await page.waitForURL('**/inicio')

    // 2. Crear proyecto -------------------------------------------------------------------------
    // No hay ningún link visible de "proyectos" en /inicio ni en el header (ver hallazgo del
    // F6.3.T3): se navega directo por URL, como haría alguien con la app en una pestaña.
    await page.goto('/proyectos')
    await page.getByRole('button', { name: t(idioma, 'proyectos', 'vacio.crear') }).click()
    const dialogoProyecto = page.getByRole('dialog')
    await dialogoProyecto.getByLabel(t(idioma, 'proyectos', 'dialogo.nombre')).fill('Proyecto E2E')
    await dialogoProyecto.getByRole('button', { name: t(idioma, 'comun', 'guardar') }).click()
    await expect(dialogoProyecto).toBeHidden()

    await page.getByRole('link', { name: 'Proyecto E2E' }).click()
    await expect(page).toHaveURL(/\/proyectos\/[^/]+$/)
    const proyectoId = new URL(page.url()).pathname.split('/').pop() as string

    // 3. Subir el CSV de fixture ----------------------------------------------------------------
    await page.goto(`/proyectos/${proyectoId}/datasets/nuevo`)
    await page.locator('#archivo').setInputFiles(CSV_FIXTURE)
    await page.waitForURL(/\/datasets\/[^/]+\/mapeo$/, { timeout: 60_000 })
    const datasetId = new URL(page.url()).pathname.split('/')[2]

    // 4. Confirmar el mapeo de columnas ---------------------------------------------------------
    for (const campo of CAMPOS_A_MAPEAR) {
      await page.locator(`select[aria-label="${campo}"]`).selectOption(campo)
    }
    const tipoProductoId = page.locator('#producto_id_tipo')
    if (await tipoProductoId.count()) await tipoProductoId.selectOption('sku')

    const confirmar = page.getByRole('button', { name: t(idioma, 'mapeo', 'acciones.confirmar') })
    await expect(confirmar).toBeEnabled()
    await confirmar.click()
    await page.waitForURL(/\/datasets\/[^/]+\/calidad/, { timeout: 30_000 })
    expect(new URL(page.url()).pathname).toContain(datasetId)

    // 5. Esperar el informe de calidad (ingesta + clasificación de productos vía los Jev/9router
    // falsos de `api/tests/e2e/`) ---------------------------------------------------------------
    const continuarAnalisis = page.getByRole('button', {
      name: t(idioma, 'calidad', 'acciones.continuar_analisis'),
    })
    await expect(continuarAnalisis).toBeVisible({ timeout: 120_000 })
    await continuarAnalisis.click()
    await page.waitForURL(/\/datasets\/[^/]+\/analisis\/nuevo$/, { timeout: 30_000 })

    // 6. Elegir los 4 análisis y lanzarlos -------------------------------------------------------
    for (const tipo of TIPOS_ANALISIS) {
      await page.getByTestId(`tarjeta-${tipo}`).click()
    }
    const lanzar = page.getByRole('button', { name: t(idioma, 'analisis', 'nuevo.acciones.lanzar') })
    await expect(lanzar).toBeEnabled()
    await lanzar.click()
    await page.waitForURL(/\/analisis\/[^/]+\/progreso$/, { timeout: 30_000 })

    // 7. Progreso del análisis: la propia pantalla redirige a resultados cuando queda "listo" ----
    await page.waitForURL(/\/analisis\/[a-f0-9-]+$/, { timeout: 180_000 })

    // 8. Ver resultados --------------------------------------------------------------------------
    await expect(page.getByRole('tab', { name: t(idioma, 'resultados', 'pestanas.recordatorios') })).toBeVisible()
    await expect(page.getByRole('tab', { name: t(idioma, 'resultados', 'pestanas.ciclos') })).toBeVisible()
    await expect(page.getByRole('tab', { name: t(idioma, 'resultados', 'pestanas.riesgo') })).toBeVisible()
    await expect(page.getByRole('tab', { name: t(idioma, 'resultados', 'pestanas.ofertas') })).toBeVisible()

    // 9. Exportar (pestaña por defecto: recordatorios/recompra) -----------------------------------
    const descargaPromesa = page.waitForEvent('download')
    await page.getByRole('button', { name: t(idioma, 'resultados', 'exportar.boton') }).click()
    const descarga = await descargaPromesa
    expect(descarga.suggestedFilename().length).toBeGreaterThan(0)

    // Tiempo total del flujo (objetivo del PRD: ≤ 10 min para un usuario nuevo) -------------------
    const duracionMs = Date.now() - inicio
    const duracionMin = (duracionMs / 60_000).toFixed(1)
    console.log(`[flujo-completo] duración total: ${duracionMs} ms (${duracionMin} min)`)
    await testInfo.attach('tiempo-flujo-completo', {
      body: JSON.stringify({ duracion_ms: duracionMs, duracion_min: Number(duracionMin) }),
      contentType: 'application/json',
    })
  })
})

test.describe('login + una pantalla, por idioma', () => {
  for (const [idioma, locale] of [
    ['es', 'es'],
    ['en', 'en'],
  ] as const) {
    test(`repite login y la pantalla de proyectos vacía en "${idioma}"`, async ({ browser }) => {
      const contexto = await browser.newContext({ locale })
      const page = await contexto.newPage()
      const email = emailUnico(`login-${idioma}`)
      const contrasena = 'contrasena-e2e-123'

      // Cuenta nueva (no hay usuarios precreados) y logout inmediato, para probar el login en sí
      // y no solo el registro.
      await page.goto('/registro')
      await page.getByLabel(t(idioma, 'auth', 'registro.nombre_empresa')).fill('Tienda E2E i18n')
      await page.getByLabel(t(idioma, 'auth', 'registro.email')).fill(email)
      await page.getByLabel(t(idioma, 'auth', 'registro.contrasena')).fill(contrasena)
      await page.getByLabel(t(idioma, 'auth', 'registro.idioma'), { exact: true }).selectOption(idioma)
      await page.getByRole('button', { name: t(idioma, 'auth', 'registro.enviar') }).click()
      await page.waitForURL('**/inicio')

      // Logout: el trigger del menú muestra el email de la sesión (ver `MenuUsuario.tsx`).
      await page.getByRole('button', { name: email }).click()
      await page.getByRole('menuitem', { name: t(idioma, 'auth', 'menu.cerrar_sesion') }).click()
      await page.waitForURL('**/login')

      // Login -----------------------------------------------------------------------------------
      await page.getByLabel(t(idioma, 'auth', 'login.email')).fill(email)
      await page.getByLabel(t(idioma, 'auth', 'login.contrasena')).fill(contrasena)
      await page.getByRole('button', { name: t(idioma, 'auth', 'login.enviar') }).click()
      await page.waitForURL('**/inicio')

      // Una pantalla: proyectos vacíos, en el idioma del contexto ---------------------------------
      await page.goto('/proyectos')
      await expect(page.getByRole('heading', { name: t(idioma, 'proyectos', 'vacio.titulo') })).toBeVisible()
      await expect(page.getByRole('button', { name: t(idioma, 'proyectos', 'vacio.crear') })).toBeVisible()

      await contexto.close()
    })
  }
})
