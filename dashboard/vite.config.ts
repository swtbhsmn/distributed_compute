import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '')
  const proxyTarget = env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000'

  return {
    plugins: [react()],
    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (id.includes('node_modules/@mui') || id.includes('node_modules/@emotion')) return 'mui'
            if (id.includes('node_modules/lucide-react')) return 'icons'
          },
        },
      },
    },
    server: {
      port: 5173,
      proxy: {
        '/api': proxyTarget,
        '/health': proxyTarget,
      },
    },
  }
})
