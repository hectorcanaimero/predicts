import { tanstackRouter } from '@tanstack/router-plugin/vite'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'
import { configDefaults, defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [
    tanstackRouter({ target: 'react', autoCodeSplitting: true }),
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    // `e2e/` son specs de Playwright (`playwright.config.ts`), no de vitest; sin esto, el glob
    // por defecto de vitest (`**/*.spec.ts`) también las recoge e intenta correrlas acá.
    exclude: [...configDefaults.exclude, 'e2e/**'],
  },
})
