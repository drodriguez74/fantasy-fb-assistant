import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3001,
    host: '127.0.0.1',
    strictPort: true,
    // Free ngrok plans assign a new random *.ngrok-free.app hostname every
    // tunnel restart (no reserved subdomain) -- a leading-dot entry allows
    // any subdomain instead of needing to edit this file each time.
    allowedHosts: ['localhost', '.ngrok-free.app']
  },
  build: {
    outDir: 'dist'
  }
})
