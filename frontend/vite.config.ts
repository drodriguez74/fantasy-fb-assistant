import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3001,
    host: '127.0.0.1',
    strictPort: true,
    allowedHosts: ['localhost', '5c3df140dd60.ngrok-free.app']
  },
  build: {
    outDir: 'dist'
  }
})
