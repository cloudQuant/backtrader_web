/// <reference types="vitest" />
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import { resolve } from 'path'

const FRONTEND_DEV_PORT = 3000
const BACKEND_PROXY_TARGET = process.env.VITE_API_TARGET || 'http://127.0.0.1:8000'
const ENABLE_BUILD_SOURCEMAP = process.env.VITE_BUILD_SOURCEMAP === 'true'

export default defineConfig({
  plugins: [
    vue(),
    AutoImport({
      resolvers: [ElementPlusResolver()],
      dts: 'auto-imports.d.ts',
    }),
    Components({
      resolvers: [ElementPlusResolver()],
      dts: 'components.d.ts',
    }),
  ],
  test: {
    globals: true,
    environment: 'happy-dom',
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    setupFiles: ['./src/test/setup.ts'],
    sequence: {
      setupFiles: 'first',
    },
    testTimeout: 10000,
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,vue}'],
      exclude: [
          'src/main.ts',
          'src/**/*.d.ts',
          'src/test/**',
          'src/i18n/**',
          'src/composables/useKeyboardShortcuts.ts',
        ],
      thresholds: {
        lines: 25,
        statements: 25,
        functions: 30,  // V8 reports 0% for Vue SFC <script setup> functions; real coverage is higher
        branches: 40,
      },
    },
  },
  css: {
    preprocessorOptions: {
      scss: {
        api: 'modern-compiler',
      },
    },
  },
  optimizeDeps: {
    include: ['monaco-editor'],
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: FRONTEND_DEV_PORT,
    strictPort: true,
    proxy: {
      '/api': {
        target: BACKEND_PROXY_TARGET,
        changeOrigin: true,
      },
      '/ws': {
        target: BACKEND_PROXY_TARGET.replace('http', 'ws'),
        ws: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: ENABLE_BUILD_SOURCEMAP,
    rollupOptions: {
      output: {
        manualChunks: {
          // Heavy editor surface — always lazy-loaded by the views that need it.
          'monaco-editor': ['monaco-editor'],
          // Charting libs are pulled in by analytics/report views; isolating
          // them keeps the entry chunk small.
          'echarts': ['echarts', 'echarts-gl', 'vue-echarts'],
        },
      },
    },
  },
})
