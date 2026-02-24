# E2E 测试环境设置指南

本指南帮助你设置和运行 Backtrader Web 的 E2E 测试。

## 前提条件

- Node.js 18+
- 已安装后端和前端依赖

## 快速开始

### 1. 安装 Playwright

```bash
cd src/frontend
npm install -D @playwright/test
```

### 2. 安装浏览器

```bash
npx playwright install
```

### 3. 运行测试

```bash
# 开发模式 - 使用 UI 模式
npm run test:e2e:ui

# 无头模式
npm run test:e2e

# 单个测试文件
npx playwright test e2e/tests/auth.spec.ts

# 调试模式
npx playwright test --debug
```

## 目录结构

```
e2e/
├── pages/              # Page Object Model
│   ├── BasePage.ts
│   ├── AuthPage.ts
│   ├── DashboardPage.ts
│   ├── StrategyPage.ts
│   └── BacktestPage.ts
├── fixtures/           # 测试数据工厂
│   └── test-data.fixture.ts
├── tests/              # 测试用例
│   ├── auth.spec.ts
│   ├── strategy.spec.ts
│   └── backtest.spec.ts
└── playwright.config.ts # 配置
```

## 最佳实践

### SCAMPER 应用

| 技术 | 应用 |
|------|------|
| **Substitute** | 用智能等待替代 sleep |
| **Combine** | 在一个测试中覆盖完整流程 |
| **Eliminate** | 使用 storageState 消除重复登录 |
| **Put to Other Uses** | 测试结果用于性能监控 |
| **Modify** | 细化断言粒度 |

### 编写测试

1. **使用 Page Objects**: 所有页面操作封装在 `pages/` 目录
2. **使用测试数据工厂**: 避免硬编码，使用 `fixtures/` 中的工厂
3. **智能等待**: 使用 `waitForSelector` 替代 `page.waitForTimeout`
4. **独立测试**: 每个测试应该独立运行

### CI/CD 集成

```yaml
# .github/workflows/e2e.yml
name: E2E Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
      - name: Install dependencies
        run: cd src/frontend && npm ci
      - name: Install Playwright
        run: npx playwright install --with-deps
      - name: Run E2E tests
        run: npm run test:e2e
      - uses: actions/upload-artifact@v3
        if: failure()
        with:
          name: playwright-report
          path: src/frontend/e2e-results/
```

## 生成登录状态

首次运行测试前，需要生成登录状态文件：

```bash
npx playwright test e2e/tests/auth.spec.ts -g "保存登录状态"
```

这将创建 `e2e/fixtures/storage-state.json` 用于其他测试。

## 故障排查

### 测试超时

- 增加 `playwright.config.ts` 中的 timeout 设置
- 检查后端服务是否正在运行

### 元素找不到

- 确保前端应用正在运行
- 检查选择器是否正确
- 使用 `--debug` 模式查看页面状态

### 测试不稳定

- 使用智能等待替代固定延迟
- 增加重试次数: `retries: 2`
