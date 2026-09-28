import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import serviceWorker from './sw/plugin.js'

export default defineConfig({
  plugins: [react(), serviceWorker()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  build: { outDir: 'dist', chunkSizeWarningLimit: 900 },
})
