import { defineConfig, devices } from '@playwright/test'

/** E2E de F6.3.T3: corre contra `docker compose` ya levantado (ver
 * `api/tests/e2e/docker-compose.e2e.yml`), no contra un `vite dev` ni un `webServer` propio de
 * Playwright -- por eso no hay `webServer` acá. `E2E_BASE_URL` por defecto apunta al puerto que
 * expone `web` en `deploy/docker-compose.yml` (`WEB_PORT`, 8080 por defecto). */
export default defineConfig({
  testDir: './e2e',
  timeout: 15 * 60 * 1000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:8080',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
