import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig, loadEnv } from 'vite'

// AwdaxP (awdaxp/) has no CORS. In dev the app calls same-origin /api and /health; Vite forwards them.
// Set AWDAX_API in .env.local to point at another host (default http://127.0.0.1:8000).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const backend = env.AWDAX_API?.trim() || 'http://127.0.0.1:8000'

  return {
    plugins: [react(), tailwindcss()],
    server: {
      proxy: {
        '/api': { target: backend, changeOrigin: true, ws: true },
        '/health': { target: backend, changeOrigin: true },
        '/ready': { target: backend, changeOrigin: true },
      },
    },
  }
})
