/// <reference types="vitest/config" />
import path from 'path';
import { defineConfig } from 'vite';

/** No-op virtual module for extensions (see vite.config.ts for details). */
function extensions() {
  const virtualModuleId = 'virtual:consentos-extensions'
  const resolvedId = '\0' + virtualModuleId
  return {
    name: 'consentos-extensions',
    resolveId(id: string) { if (id === virtualModuleId) return resolvedId },
    load(id: string) { if (id === resolvedId) return 'export default undefined;' },
  }
}

export default defineConfig({
  plugins: [extensions()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
  resolve: {
    alias: {
      '@core': path.resolve(__dirname, 'src'),
    },
  },
});
