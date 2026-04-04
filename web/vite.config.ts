import path from 'path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8100',
      '/auth': 'http://localhost:8100',
      '/agents': 'http://localhost:8100',
      '/conversations': 'http://localhost:8100',
      '/messages': 'http://localhost:8100',
      '/dashboard/custom': 'http://localhost:8100',
      '/dashboard': 'http://localhost:8100',
      '/onboarding': 'http://localhost:8100',
      '/healthz': 'http://localhost:8100',
      '/knowledge': 'http://localhost:8100',
      '/skills': 'http://localhost:8100',
      '/user': 'http://localhost:8100',
      '/jobs': 'http://localhost:8100',
      '/scheduled-jobs': 'http://localhost:8100',
      '/workers': 'http://localhost:8100',
      '/attachments': 'http://localhost:8100',
      '/shared': 'http://localhost:8100',
      '/ws': { target: 'http://localhost:8100', ws: true },
    },
  },
})
