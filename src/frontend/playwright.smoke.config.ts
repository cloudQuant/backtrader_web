import { defineConfig, devices } from '@playwright/test'
import baseConfig from './playwright.config'

/**
 * PR-blocking smoke journeys run against the single browser installed by the
 * quality workflow. Keeping this separate from the full cross-browser E2E
 * config also lets Playwright discover the smoke directory outside testDir.
 */
export default defineConfig({
  ...baseConfig,
  testDir: './e2e/smoke-175',
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
