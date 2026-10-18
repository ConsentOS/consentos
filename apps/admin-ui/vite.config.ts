import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { defineConfig } from 'vite'

/**
 * Vite plugin that provides a no-op ``virtual:consentos-extensions`` module.
 *
 * A build that ships extensions replaces this plugin with one that
 * resolves the module to its own registration code. Here it exports
 * nothing, so ``discoverExtensions()`` does nothing.
 */
function extensions() {
  const virtualModuleId = 'virtual:consentos-extensions'
  const resolvedId = '\0' + virtualModuleId

  return {
    name: 'consentos-extensions',
    resolveId(id: string) {
      if (id === virtualModuleId) return resolvedId
    },
    load(id: string) {
      if (id === resolvedId) return 'export default undefined;'
    },
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss(), extensions()],
  resolve: {
    alias: {
      '@core': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
