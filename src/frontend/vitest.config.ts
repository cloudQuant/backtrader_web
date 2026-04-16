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
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/test/**/*.test.{ts,js}'],
    testTimeout: 10000,
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
        'src/i18n/**',
        'src/composables/useKeyboardShortcuts.ts',
      ],
      thresholds: {
        lines: 25,
        functions: 30,
        branches: 40,
        statements: 25,
      },
    },
  },
})
