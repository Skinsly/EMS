import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

export default defineConfig({
  plugins: [
    vue(),
    Components({
      resolvers: [ElementPlusResolver({ importStyle: 'css' })],
      dts: false
    }),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['site-icon.svg', 'pwa-192.png', 'pwa-512.png', 'pwa-512-maskable.png'],
      manifest: {
        name: 'EMS',
        short_name: 'EMS',
        description: 'EMS 工程管理系统',
        theme_color: '#2563eb',
        background_color: '#0b1220',
        display: 'fullscreen',
        orientation: 'portrait',
        start_url: '/',
        scope: '/',
        lang: 'zh-CN',
        icons: [
          {
            src: '/pwa-192.png',
            sizes: '192x192',
            type: 'image/png'
          },
          {
            src: '/pwa-512.png',
            sizes: '512x512',
            type: 'image/png'
          },
          {
            src: '/pwa-512-maskable.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable any'
          }
        ]
      }
    })
  ],
  build: {
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/vue') || id.includes('node_modules/vue-router') || id.includes('node_modules/pinia')) {
            return 'vendor-vue'
          }
          if (id.includes('node_modules/axios')) {
            return 'vendor-http'
          }
          if (id.includes('node_modules/@element-plus/icons-vue')) {
            return 'vendor-icons'
          }
          if (id.includes('node_modules/markdown-it')) {
            return 'vendor-markdown'
          }
          if (id.includes('node_modules/element-plus')) {
            return 'vendor-element-plus'
          }
          return undefined
        }
      }
    }
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      }
    }
  }
})
