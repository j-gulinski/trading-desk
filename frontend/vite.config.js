import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    proxy: {
      '/api/market-data': { target: 'http://localhost:8001', changeOrigin: true },
      '/api/pricing': { target: 'http://localhost:8002', changeOrigin: true },
      '/api/monitoring': { target: 'http://localhost:8003', changeOrigin: true },
      '/api/books': { target: 'http://localhost:8004', changeOrigin: true },
      '/api/blotter': { target: 'http://localhost:8006', changeOrigin: true },
      '/api/trade-generation': { target: 'http://localhost:8007', changeOrigin: true },
      '/api/trade-action': { target: 'http://localhost:8008', changeOrigin: true }
    }
  }
})