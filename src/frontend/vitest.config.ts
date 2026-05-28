import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue() as any],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    globals: true,
    environment: 'happy-dom',
    setupFiles: ['./src/__tests__/setup.ts'],
    include: ['src/**/*.test.{ts,js}', 'src/**/__tests__/**/*.test.{ts,js}'],
    testTimeout: 10000,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      exclude: [
        'node_modules/',
        'src/__tests__/',
        'e2e/**',
        '**/*.d.ts',
        '**/*.config.*',
        '**/main.ts',
        'src/i18n/**',
        'src/composables/useKeyboardShortcuts.ts',
      ],
      thresholds: {
        lines: 45,
        functions: 50,
        branches: 55,
        statements: 45,
      },
    },
  },
})
