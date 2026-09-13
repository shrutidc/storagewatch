import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    // Fail rather than quietly moving to 3001: Auth0's allowed callback URLs
    // and the backend's CORS list both name port 3000, so a dev server that
    // silently relocates produces a login error that looks like broken auth
    // rather than an occupied port.
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      }
    }
  },
})
