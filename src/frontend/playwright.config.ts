import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright E2E 测试配置
 *
 * 基于 SCAMPER 头脑风暴的最佳实践:
 * - 使用 storageState 消除重复登录
 * - 只在失败时截图和录制视频
 * - 并行执行独立测试
 * - 智能等待替代硬编码延迟
 */
export default defineConfig({
  // 测试文件位置
  testDir: './e2e/tests',

  // 每个测试的超时时间
  timeout: 30 * 1000,

  // 期望断言超时
  expect: {
    timeout: 5 * 1000,
  },

  // 失败时重试
  retries: process.env.CI ? 2 : 0,

  // 并行执行工作进程
  // 使用单 worker 避免并行测试时的登录冲突
  workers: 1,

  // 报告器配置
  reporter: [
    ['html', { outputFolder: 'e2e-results/html-report' }],
    ['json', { outputFile: 'e2e-results/test-results.json' }],
    ['junit', { outputFile: 'e2e-results/junit-results.xml' }],
    ['list'],
  ],

  // 共享配置
  use: {
    // 基础 URL
    baseURL: process.env.BASE_URL || 'http://localhost:5173',

    // 追踪配置（仅在失败时记录）
    trace: 'retain-on-failure',

    // 截图配置（仅在失败时截图）
    screenshot: 'only-on-failure',

    // 视频配置（仅在失败时录制）
    video: 'retain-on-failure',

    // 浏览器视口大小
    viewport: { width: 1280, height: 720 },

    // 忽略 HTTPS 错误（开发环境）
    ignoreHTTPSErrors: true,

    // 智能等待
    actionTimeout: 10 * 1000,
    navigationTimeout: 30 * 1000,
  },

  // 项目配置 - 多浏览器测试
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
    // 移动端测试
    {
      name: 'Mobile Chrome',
      use: { ...devices['Pixel 5'] },
    },
    {
      name: 'Mobile Safari',
      use: { ...devices['iPhone 12'] },
    },
  ],

  // 开发服务器配置
  // 注意: 需要手动启动前端服务: npm run dev (端口 5173)
  // 设置 reuseExistingServer: true 假设服务器已在运行
  // 当 BASE_URL 环境变量设置时，禁用自动启动服务器
  webServer: process.env.BASE_URL ? undefined : {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: true,  // 只使用已存在的服务器
    timeout: 5000,  // 快速失败
  },
});
