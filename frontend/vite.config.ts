import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发期将 /api 代理到后端，避免跨域配置（后端 CORS 也已放行 5173）
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/static': { target: 'http://127.0.0.1:8000', changeOrigin: true }
    }
  }
})
