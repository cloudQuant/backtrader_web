import { expect, test, type BrowserContext, type Page, type TestInfo } from '@playwright/test';
import { restorePersistedAuthSession } from '../support/auth';

type FeaturePage = {
  name: string;
  path: string;
  expected: RegExp;
  adminOnly?: boolean;
};

const featurePages: FeaturePage[] = [
  { name: 'home dashboard', path: '/', expected: /仪表盘|Dashboard|最近回测|Quick/i },
  {
    name: 'research strategies',
    path: '/research/strategies',
    expected: /策略库与我的策略|Strategy library and my strategies/i,
  },
  { name: 'research workspaces', path: '/research/workspaces', expected: /新建工作区|策略研究|Workspace/i },
  // The retired tools page redirects to the research-workspace entry point.
  { name: 'research tools', path: '/research/tools', expected: /新建工作区|策略研究|Workspace/i },
  { name: 'data quote', path: '/data/quote', expected: /行情报价|Quote/i },
  { name: 'data market', path: '/data/market', expected: /数据治理中心|市场数据|Market/i },
  { name: 'data topics', path: '/data/topics', expected: /DataTopic|主题|Topic/i },
  { name: 'data scripts', path: '/data/scripts', expected: /脚本|Scripts/i },
  { name: 'data tasks', path: '/data/tasks', expected: /任务|Tasks/i },
  { name: 'data executions', path: '/data/executions', expected: /执行|Executions/i },
  { name: 'data tables', path: '/data/tables', expected: /数据表|Tables/i },
  { name: 'data sync', path: '/data/sync', expected: /同步|Sync/i, adminOnly: true },
  { name: 'data interfaces', path: '/data/interfaces', expected: /接口|Interfaces/i, adminOnly: true },
  { name: 'data governance', path: '/data/governance', expected: /治理|Governance/i, adminOnly: true },
  { name: 'data airflow', path: '/data/airflow', expected: /Airflow|DAG/i, adminOnly: true },
  { name: 'news intelligence', path: '/data/intelligence/news', expected: /新闻情报|News Intelligence/i },
  { name: 'options chain', path: '/data/intelligence/options', expected: /期权链|Options Chain/i },
  { name: 'scanners', path: '/data/intelligence/scanners', expected: /条件扫描|Scanners/i },
  { name: 'trading workspaces', path: '/trading/workspaces', expected: /新建工作区|策略交易|Trading/i },
  { name: 'trading brokers', path: '/trading/brokers', expected: /Broker|券商|配置/i },
  { name: 'trading gateways', path: '/trading/gateways', expected: /账户管理|Gateways|网关/i },
  { name: 'trading ai', path: '/trading/ai', expected: /AI交易|AI Trading|自然语言/i },
  { name: 'portfolio overview', path: '/portfolio/overview', expected: /组合|Portfolio|总资产/i },
  // Ledger is retired and intentionally redirects to the unified portfolio overview.
  { name: 'portfolio ledger', path: '/portfolio/ledger', expected: /组合|Portfolio|总资产/i },
  { name: 'ai chat', path: '/ai/chat', expected: /知识问答|Knowledge Q&A|Knowledge Base/i },
  { name: 'ai knowledge base', path: '/ai/knowledge-base', expected: /知识库|Knowledge Base/i },
  { name: 'config ai observability', path: '/config/ai/observability', expected: /AI成本|AI Cost|Usage/i, adminOnly: true },
  { name: 'config prompt governance', path: '/config/ai/prompt-governance', expected: /Prompt治理|Prompt Governance/i, adminOnly: true },
  { name: 'admin settings', path: '/admin/settings', expected: /系统设置|Settings|个人设置/i, adminOnly: true },
];

const legacyPaths: FeaturePage[] = [
  {
    name: 'legacy strategy',
    path: '/strategy',
    expected: /策略库与我的策略|Strategy library and my strategies/i,
  },
  { name: 'legacy workspace', path: '/workspace', expected: /新建工作区|策略研究|Workspace/i },
  { name: 'legacy backtest', path: '/backtest', expected: /新建工作区|策略研究|Workspace/i },
  { name: 'legacy quote', path: '/quote', expected: /行情报价|Quote/i },
  { name: 'legacy brokers', path: '/brokers', expected: /Broker|券商|配置/i },
  { name: 'legacy gateways', path: '/gateways', expected: /账户管理|Gateways|网关/i },
  { name: 'legacy portfolio', path: '/portfolio', expected: /组合|Portfolio|总资产/i },
  { name: 'legacy portfolio ledger', path: '/portfolio-ledger', expected: /组合|Portfolio|总资产/i },
  { name: 'legacy ai chat', path: '/ai-chat', expected: /知识问答|Knowledge Q&A|Knowledge Base/i },
  { name: 'legacy knowledge base', path: '/knowledge-base', expected: /知识库|Knowledge Base/i },
  { name: 'legacy news intelligence', path: '/news-intelligence', expected: /新闻情报|News Intelligence/i },
  { name: 'legacy options chain', path: '/options-chain', expected: /期权链|Options Chain/i },
  { name: 'legacy scanners', path: '/scanners', expected: /条件扫描|Scanners/i },
  { name: 'legacy quant tools', path: '/quant-tools', expected: /新建工作区|策略研究|Workspace/i },
  { name: 'legacy ai trading', path: '/ai-trading', expected: /AI交易|AI Trading|自然语言/i },
  { name: 'legacy ai prompt governance', path: '/ai/prompt-governance', expected: /Prompt治理|Prompt Governance/i, adminOnly: true },
  { name: 'legacy ai observability', path: '/ai/observability', expected: /AI成本|AI Cost|Usage/i, adminOnly: true },
];

function createFeaturePageContextOptions(testInfo: TestInfo) {
  const use = testInfo.project.use;
  return {
    colorScheme: use.colorScheme,
    deviceScaleFactor: use.deviceScaleFactor,
    extraHTTPHeaders: use.extraHTTPHeaders,
    geolocation: use.geolocation,
    hasTouch: use.hasTouch,
    ignoreHTTPSErrors: use.ignoreHTTPSErrors,
    isMobile: use.isMobile,
    javaScriptEnabled: use.javaScriptEnabled,
    locale: use.locale,
    permissions: use.permissions,
    screen: use.screen,
    timezoneId: use.timezoneId,
    userAgent: use.userAgent,
    viewport: use.viewport,
  };
}

async function navigateToFeaturePage(page: Page, target: FeaturePage, baseURL: string) {
  await page.goto(new URL(target.path, baseURL).toString(), { waitUntil: 'domcontentloaded' });

  // WebKit can occasionally leave a blank document for a direct route load.
  // Retry the document once; the caller still verifies the app shell and page.
  const appShellVisible = await page
    .locator('.app-main-content')
    .isVisible({ timeout: 5_000 })
    .catch(() => false);
  if (!appShellVisible) {
    await page.reload({ waitUntil: 'domcontentloaded' });
  }
}

async function assertFeaturePageUsable(page: Page, target: FeaturePage, baseURL: string) {
  const pageErrors: string[] = [];
  const apiFailures: string[] = [];
  const onPageError = (error: Error) => {
    // Some route redirects cancel an in-flight request after the destination renders.
    if (error.message === 'Request aborted') return;
    pageErrors.push(error.message);
  };
  const onResponse = (response: { status: () => number; url: () => string }) => {
    const status = response.status();
    if (!response.url().includes('/api/')) return;
    if (status === 401 || status === 403 || status >= 500) {
      apiFailures.push(`${status} ${response.url()}`);
    }
  };
  page.on('pageerror', onPageError);
  page.on('response', onResponse);

  try {
    await navigateToFeaturePage(page, target, baseURL);
    await expect(page).not.toHaveURL(/\/login(?:\?.*)?$/);
    await expect(page.locator('.app-main-content')).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('body')).toContainText(target.expected, { timeout: 10_000 });

    const usableSurface = page.locator(
      [
        'button:visible',
        'input:visible',
        'textarea:visible',
        '.el-tabs:visible',
        '.el-table:visible',
        '.el-card:visible',
        '.echarts:visible',
        'canvas:visible',
      ].join(', '),
    );
    await expect(usableSurface.first()).toBeVisible({ timeout: 10_000 });

    expect(pageErrors, `${target.name} should not raise uncaught browser errors`).toEqual([]);
    expect(apiFailures, `${target.name} should not return unauthorized or server-error API responses`).toEqual([]);
  } finally {
    page.off('pageerror', onPageError);
    page.off('response', onResponse);
  }
}

async function assertFeaturePageInNewPage(
  context: BrowserContext,
  target: FeaturePage,
  baseURL: string,
) {
  // A shared browser context preserves the project device configuration, while
  // a fresh page prevents a prior route's cancelled requests or dynamic imports
  // from surfacing as uncaught errors for the next route.
  const page = await context.newPage();
  try {
    await restorePersistedAuthSession(page);
    await assertFeaturePageUsable(page, target, baseURL);
  } finally {
    await page.close();
  }
}

test.describe('产品域与旧路径 E2E 巡检', () => {
  test.describe.configure({ mode: 'serial' });

  let context: BrowserContext;
  let baseURL: string;

  test.beforeAll(async ({ browser }, testInfo) => {
    baseURL = String(testInfo.project.use.baseURL ?? 'http://127.0.0.1:3000');
    context = await browser.newContext(createFeaturePageContextOptions(testInfo));
  });

  test.afterAll(async () => {
    await context.close();
  });

  test.describe('产品域功能页 E2E 巡检', () => {
    for (const target of featurePages) {
      test(`${target.name} loads and exposes usable controls`, async () => {
        await assertFeaturePageInNewPage(context, target, baseURL);
      });
    }
  });

  test.describe('旧功能路径兼容 E2E 巡检', () => {
    for (const target of legacyPaths) {
      test(`${target.name} remains usable`, async () => {
        await assertFeaturePageInNewPage(context, target, baseURL);
      });
    }
  });
});
