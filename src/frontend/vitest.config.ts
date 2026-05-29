import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import path from 'path'

// Iteration 175 §2 — High_Coverage_Core modules and their >= 90% per-path
// thresholds. Listed inline so the source-of-truth lives next to the global
// thresholds. Mirrored in src/__tests__/coverage_core.md for human review.
const HIGH_COVERAGE_CORE_THRESHOLDS = {
  'src/stores/auth.ts':                     { lines: 90, functions: 90, branches: 90, statements: 90 },
  'src/stores/theme.ts':                    { lines: 90, functions: 90, branches: 88, statements: 90 },
  'src/stores/backtest.ts':                 { lines: 90, functions: 90, branches: 90, statements: 90 },
  'src/stores/strategy.ts':                 { lines: 90, functions: 90, branches: 90, statements: 90 },
  'src/stores/knowledgeBase.ts':            { lines: 90, functions: 90, branches: 90, statements: 90 },
  'src/api/index.ts':                       { lines: 90, functions: 85, branches: 80, statements: 90 },
  'src/composables/useBacktestRuntime.ts':  { lines: 90, functions: 90, branches: 88, statements: 90 },
  'src/utils/markdown-sanitizer.ts':        { lines: 90, functions: 90, branches: 90, statements: 90 },
}

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
      reporter: ['text', 'json', 'json-summary', 'html'],
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
        // Iteration 175 §2 — global ratchet 60 → 75
        // (174 set the floor at 60; 175 raises to 75. See PROGRESS.md §2.)
        lines: 75,
        functions: 75,
        branches: 75,
        statements: 75,
        ...HIGH_COVERAGE_CORE_THRESHOLDS,
      },
    },
  },
})
