import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// The browser only ever talks to one origin. In development, Vite forwards /api to the backend;
// in Docker, nginx does the same. So the API needs no CORS settings at all.
const API_TARGET = process.env.API_TARGET ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1', // this machine only
    port: 5173,
    proxy: {
      '/api': {
        target: API_TARGET,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    restoreMocks: true,
  },
})
