import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    globals: true,
    environment: 'happy-dom',
    setupFiles: [],
    include: ['src/test/**/*.test.{ts,js}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      exclude: [
        'node_modules/',
        'src/test/',
        'e2e/**',
        '**/*.d.ts',
        '**/*.config.*',
        '**/main.ts',
      ],
      thresholds: {
        lines: 50,
        functions: 45,
        branches: 40,
        statements: 50,
      },
    },
  },
})