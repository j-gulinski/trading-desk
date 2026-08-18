import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    proxy: {
      '/api/monitoring': {
        target: 'http://monitoring-service:8003',
        changeOrigin: true,
        rewrite: p => p.replace('/api/monitoring', '')
      },
      '/api/market-data': {
        target: 'http://market-data-service:8001',
        changeOrigin: true,
        rewrite: p => p.replace('/api/market-data', '')
      },
      '/api/pricing': {
        target: 'http://pricing-service:8002',
        changeOrigin: true,
        rewrite: p => p.replace('/api/pricing', '')
      },
      '/api/blotter': {
        target: 'http://blotter-service:8006',
        changeOrigin: true,
        rewrite: p => p.replace('/api/blotter', '')
      },
      '/api/books': {
        target: 'http://books-service:8004',
        changeOrigin: true,
        rewrite: p => p.replace('/api/books', '')
      },
      '/api/trade-action': {
        target: 'http://trade-action-service:8008',
        changeOrigin: true,
        rewrite: p => p.replace('/api/trade-action', '')
      }
    }
  }
})
