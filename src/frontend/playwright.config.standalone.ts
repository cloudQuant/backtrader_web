import { defineConfig, devices } from '@playwright/test';

const DEV_SERVER_URL = process.env.BASE_URL || 'http://localhost:3000';

/**
 * Playwright E2E 测试配置 - 独立模式
 *
 * 此配置不包含 webServer 自动启动
 * 用于手动启动应用后的测试
 */
export default defineConfig({
  testDir: 'e2e/tests',

  timeout: 30 * 1000,
  expect: {
    timeout: 5 * 1000,
  },
  retries: 0,
  workers: 1,  // 单线程运行

  reporter: [
    ['list'],
    ['html', { outputFolder: 'e2e-results/html-report' }],
  ],

  use: {
    baseURL: DEV_SERVER_URL,
    ignoreHTTPSErrors: true,
    viewport: { width: 1280, height: 720 },
    actionTimeout: 10 * 1000,
    navigationTimeout: 30 * 1000,
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
