/// <reference types="vitest" />
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

const FRONTEND_DEV_PORT = 3000
const BACKEND_PROXY_TARGET = process.env.VITE_API_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [vue()],
  test: {
    globals: true,
    environment: 'jsdom',
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
        lines: 50,
        functions: 45,  // V8 reports 0% for Vue SFC <script setup> functions; real coverage is higher
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
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          'monaco-editor': ['monaco-editor'],
        },
      },
    },
  },
})
