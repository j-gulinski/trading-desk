import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    proxy: {
      '/monitoring': {
        target: 'http://monitoring-service:8003',
        changeOrigin: true,
        rewrite: p => p.replace('/monitoring', '')
      }
    }
  }
})
