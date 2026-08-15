import { expect, test, type Route } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

import { prepareStaticPreviewPage } from '../support/static-preview'

const CANONICAL_ID = 'futures:CFFEX:IF2609:CNY'
const OPTION_CANONICAL_ID = 'option:SSE:510050C2609M03000:CNY'

function json(route: Route, payload: unknown): Promise<void> {
  return route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify(payload),
  })
}

test('asset-analysis browser journey shows only the published research decision and has no blocking accessibility violations', async ({ page }) => {
  await prepareStaticPreviewPage(page)
  await page.route('**/api/v1/asset-research/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname

    if (path.endsWith('/capabilities')) {
      return json(route, {
        capability_version: 'asset-research-capabilities-v1',
        execution_disabled: true,
        asset_types: [
          'bond',
          'fund',
          'futures',
          'option',
          'fx',
          'crypto',
        ].map((assetType) => ({
          asset_type: assetType,
          source_capability_enabled: assetType === 'futures',
          instrument_catalog_ready: assetType === 'futures',
          research_enabled: assetType === 'futures',
          availability_reason:
            assetType === 'futures' ? null : 'SOURCE_CAPABILITY_UNAVAILABLE',
          short_open_research_allowed: false,
          reason_codes: [],
        })),
      })
    }
    if (path.endsWith('/instruments/search')) {
      return json(route, {
        asset_type: 'futures',
        items: [
          {
            asset_type: 'futures',
            identity_level: 'CONTRACT',
            symbol: 'IF2609',
            name: '沪深300股指期货2609',
            market: 'CFFEX',
            canonical_id: CANONICAL_ID,
            metadata_version: 'v1',
          },
        ],
      })
    }
    if (path.endsWith('/instruments/resolve') && request.method() === 'POST') {
      return json(route, {
        asset_type: 'futures',
        identity_level: 'CONTRACT',
        canonical_id: CANONICAL_ID,
        display_symbol: 'IF2609',
        name: '沪深300股指期货2609',
        timezone: 'Asia/Shanghai',
        identifier_type: 'CONTRACT',
        identifier_value: 'IF2609',
        metadata_version: 'v1',
        details: {},
      })
    }
    if (path.endsWith('/tasks') && request.method() === 'POST') {
      return json(route, {
        task_id: 'task-1',
        status: 'QUEUED',
        asset_type: 'futures',
        canonical_id: CANONICAL_ID,
        progress: 0,
        created_at: '2026-08-01T10:00:00Z',
      })
    }
    if (path.endsWith('/tasks/task-1/result')) {
      return json(route, {
        task_id: 'task-1',
        status: 'SUCCEEDED',
        report_id: 'report-1',
        prediction_id: 'prediction-1',
        published_decision: {
          asset_type: 'futures',
          market_view: 'NEUTRAL',
          normalized_direction: 'NEUTRAL',
          position_context: 'UNKNOWN',
          horizon_code: 'standard',
          quality_status: 'ELIGIBLE',
          recommendation: 'HOLD',
          actionability: 'RESEARCH_ONLY',
          trade_intent: 'NONE',
          reason_codes: ['MODEL_NOT_PROMOTED'],
          invalidation_conditions: ['合约流动性显著恶化'],
          execution_disabled: true,
        },
        report: {
          sections: [
            {
              section_id: 'futures',
              title: '合约研究',
              markdown: '年化 carry=0.031（证据 ID：detail:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa）',
              evidence_ids: ['detail:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'],
            },
          ],
          disclaimer: '仅用于研究。',
        },
      })
    }
    if (path.endsWith('/tasks/task-1')) {
      return json(route, {
        task_id: 'task-1',
        status: 'SUCCEEDED',
        asset_type: 'futures',
        canonical_id: CANONICAL_ID,
        progress: 100,
        report_id: 'report-1',
        prediction_id: 'prediction-1',
        created_at: '2026-08-01T10:00:00Z',
      })
    }
    if (path.endsWith('/signals/history')) {
      return json(route, { items: [], next_cursor: null })
    }
    if (path.endsWith('/signals/prediction-1/evidence')) {
      return json(route, {
        prediction_id: 'prediction-1',
        canonical_id: CANONICAL_ID,
        asset_type: 'futures',
        source: {
          source_id: 'fixture-source',
          provider: 'fixture-provider',
          license_status: 'APPROVED',
        },
        source_snapshot_hash: 'b'.repeat(64),
        license_tags: ['RESEARCH_ONLY'],
        versions: { feature_version: 'asset-research-features-v2' },
        reason_codes: ['MODEL_NOT_PROMOTED'],
      })
    }
    if (path.endsWith('/signals/summary')) {
      return json(route, {
        asset_type: 'futures',
        canonical_id: CANONICAL_ID,
        head_spec_hash: null,
        available_head_spec_hashes: [],
        cohort_selection_required: false,
        total_generated_count: 0,
        excluded_prediction_count: 0,
        generated_count: 0,
        scorable_count: 0,
        actioned_generated_count: 0,
        actioned_scorable_count: 0,
        actioned_success_count: 0,
        actioned_success_rate: null,
        coverage_rate: null,
        maturity_rate: null,
        brier_score: null,
        brier_skill_score: null,
        average_net_return: null,
        max_drawdown: null,
        calibration_bins: [],
        action_breakdown: [],
      })
    }
    return json(route, { detail: `unexpected asset-research request: ${path}` })
  })

  await page.goto('/investment/ai-assets/futures')
  await expect(page.locator('.asset-analysis-page')).toBeVisible()
  await expect(
    page.locator('.asset-analysis-page').getByRole('heading', { name: 'AI期货' }),
  ).toBeVisible()

  await page.locator('.instrument-input input').fill('IF2609')
  const submitButton = page.getByRole('button', { name: '开始 期货研究' })
  await expect(submitButton).toBeDisabled()
  await page.getByRole('button', { name: '搜索候选' }).click()
  await page.getByRole('button', { name: /确认 IF2609/ }).click()
  await expect(submitButton).toBeEnabled()
  await submitButton.click()

  await expect(page.getByText('已确认标的')).toBeVisible()
  await expect(page.locator('.decision-panel')).toContainText('持有')
  await expect(page.locator('.decision-panel')).toContainText('模型尚未满足发布为可行动信号的验证门槛')
  await expect(page.locator('.decision-panel')).toContainText('不能直接下单')
  await expect(page.locator('.decision-panel')).toContainText('规范方向')
  await expect(page.locator('.decision-panel')).toContainText('持仓上下文')
  await expect(page.locator('.decision-panel')).toContainText('执行状态')
  await expect(page.locator('.decision-panel')).toContainText('合约流动性显著恶化')
  await expect(page.locator('.decision-panel')).not.toContainText('prediction_heads')
  await expect(page.locator('.report-panel')).toContainText('detail:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')
  await expect(page.locator('.evidence-panel')).toContainText('公开证据清单')
  await expect(page.locator('.evidence-panel')).toContainText('fixture-source')
  await expect(page.locator('.evidence-panel')).not.toContainText('candidate_decision')

  // Element Plus applies the tag's enter transition after the published
  // decision is mounted.  Wait for the page's explicit accessible info-tag
  // color before asking Axe to assess the settled interactive state.
  await expect(page.locator('.decision-panel .el-tag--info')).toHaveCSS(
    'color',
    'rgb(58, 67, 82)',
  )

  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze()
  const blocking = results.violations.filter(
    violation => violation.impact === 'critical' || violation.impact === 'serious',
  )

  expect(blocking).toHaveLength(0)

  await page.setViewportSize({ width: 320, height: 844 })
  await submitButton.focus()
  await expect(submitButton).toBeFocused()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320)
})

test('asset switch discards a delayed prior task response in the browser', async ({ page }) => {
  await prepareStaticPreviewPage(page)

  let releaseOldTask!: () => void
  let markOldTaskRequested!: () => void
  const oldTaskResponse = new Promise<void>((resolve) => {
    releaseOldTask = resolve
  })
  const oldTaskRequested = new Promise<void>((resolve) => {
    markOldTaskRequested = resolve
  })

  await page.route('**/api/v1/asset-research/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname

    if (path.endsWith('/capabilities')) {
      return json(route, {
        capability_version: 'asset-research-capabilities-v1',
        execution_disabled: true,
        asset_types: ['futures', 'option'].map((assetType) => ({
          asset_type: assetType,
          source_capability_enabled: true,
          instrument_catalog_ready: true,
          research_enabled: true,
          availability_reason: null,
          short_open_research_allowed: false,
          reason_codes: [],
        })),
      })
    }
    if (path.endsWith('/instruments/search')) {
      const assetType = url.searchParams.get('asset_type')
      const isOption = assetType === 'option'
      return json(route, {
        asset_type: assetType,
        items: [
          {
            asset_type: assetType,
            identity_level: 'CONTRACT',
            symbol: isOption ? '510050C2609M03000' : 'IF2609',
            name: isOption ? '上证50ETF购2609' : '沪深300股指期货2609',
            market: isOption ? 'SSE' : 'CFFEX',
            canonical_id: isOption ? OPTION_CANONICAL_ID : CANONICAL_ID,
            metadata_version: 'v1',
          },
        ],
      })
    }
    if (path.endsWith('/instruments/resolve') && request.method() === 'POST') {
      const body = request.postDataJSON() as { asset_type: 'futures' | 'option' }
      const isOption = body.asset_type === 'option'
      return json(route, {
        asset_type: body.asset_type,
        identity_level: 'CONTRACT',
        canonical_id: isOption ? OPTION_CANONICAL_ID : CANONICAL_ID,
        display_symbol: isOption ? '510050C2609M03000' : 'IF2609',
        name: isOption ? '上证50ETF购2609' : '沪深300股指期货2609',
        timezone: 'Asia/Shanghai',
        identifier_type: 'CONTRACT',
        identifier_value: isOption ? '510050C2609M03000' : 'IF2609',
        metadata_version: 'v1',
        details: {},
      })
    }
    if (path.endsWith('/tasks') && request.method() === 'POST') {
      const body = request.postDataJSON() as { asset_type: 'futures' | 'option' }
      const isOption = body.asset_type === 'option'
      return json(route, {
        task_id: isOption ? 'task-new' : 'task-old',
        status: 'QUEUED',
        asset_type: body.asset_type,
        canonical_id: isOption ? OPTION_CANONICAL_ID : CANONICAL_ID,
        progress: 0,
        created_at: '2026-08-02T10:00:00Z',
      })
    }
    if (path.endsWith('/tasks/task-old')) {
      markOldTaskRequested()
      await oldTaskResponse
      return json(route, {
        task_id: 'task-old',
        status: 'SUCCEEDED',
        asset_type: 'futures',
        canonical_id: CANONICAL_ID,
        progress: 100,
        report_id: 'old-report',
        prediction_id: 'old-prediction',
        created_at: '2026-08-02T10:00:00Z',
      })
    }
    if (path.endsWith('/tasks/task-new/result')) {
      return json(route, {
        task_id: 'task-new',
        status: 'SUCCEEDED',
        report_id: 'new-report',
        prediction_id: 'new-prediction',
        published_decision: {
          asset_type: 'option',
          market_view: 'NEUTRAL',
          normalized_direction: 'NEUTRAL',
          position_context: 'UNKNOWN',
          horizon_code: 'standard',
          quality_status: 'ELIGIBLE',
          recommendation: 'HOLD',
          actionability: 'RESEARCH_ONLY',
          trade_intent: 'NONE',
          reason_codes: ['MODEL_NOT_PROMOTED'],
          execution_disabled: true,
        },
        report: {
          sections: [{ section_id: 'option', title: '期权研究', markdown: '新期权研报' }],
          disclaimer: '仅用于研究。',
        },
      })
    }
    if (path.endsWith('/tasks/task-new')) {
      return json(route, {
        task_id: 'task-new',
        status: 'SUCCEEDED',
        asset_type: 'option',
        canonical_id: OPTION_CANONICAL_ID,
        progress: 100,
        report_id: 'new-report',
        prediction_id: 'new-prediction',
        created_at: '2026-08-02T10:00:00Z',
      })
    }
    if (path.endsWith('/signals/history')) {
      return json(route, { items: [], next_cursor: null })
    }
    if (path.endsWith('/signals/summary')) {
      return json(route, {
        asset_type: 'option',
        canonical_id: OPTION_CANONICAL_ID,
        head_spec_hash: null,
        available_head_spec_hashes: [],
        cohort_selection_required: false,
        total_generated_count: 0,
        excluded_prediction_count: 0,
        generated_count: 0,
        scorable_count: 0,
        actioned_generated_count: 0,
        actioned_scorable_count: 0,
        actioned_success_count: 0,
        actioned_success_rate: null,
        coverage_rate: null,
        maturity_rate: null,
        brier_score: null,
        brier_skill_score: null,
        average_net_return: null,
        max_drawdown: null,
        calibration_bins: [],
        action_breakdown: [],
      })
    }
    if (path.endsWith('/signals/new-prediction/evidence')) {
      return json(route, {
        prediction_id: 'new-prediction',
        canonical_id: OPTION_CANONICAL_ID,
        asset_type: 'option',
        source: { source_id: 'fixture-source', license_status: 'RESEARCH_APPROVED' },
        source_snapshot_hash: 'c'.repeat(64),
        license_tags: ['RESEARCH_ONLY'],
        versions: {},
        reason_codes: ['MODEL_NOT_PROMOTED'],
      })
    }
    return json(route, { detail: `unexpected asset-research request: ${path}` })
  })

  await page.goto('/investment/ai-assets/futures')
  await page.locator('.instrument-input input').fill('IF2609')
  await page.getByRole('button', { name: '搜索候选' }).click()
  await page.getByRole('button', { name: /确认 IF2609/ }).click()
  await page.getByRole('button', { name: '开始 期货研究' }).click()
  await oldTaskRequested

  await page.locator('.domain-subnav-item', { hasText: 'AI期权' }).click()
  await expect(
    page.locator('.asset-analysis-page').getByRole('heading', { name: 'AI期权' }),
  ).toBeVisible()
  await page.locator('.instrument-input input').fill('510050C2609M03000')
  await page.getByRole('button', { name: '搜索候选' }).click()
  await page.getByRole('button', { name: /确认 510050C2609M03000/ }).click()
  await page.getByRole('button', { name: '开始 期权研究' }).click()
  await expect(page.locator('.report-panel')).toContainText('新期权研报')

  releaseOldTask()
  await expect(page.locator('.report-panel')).toContainText('新期权研报')
  await expect(page.locator('.report-panel')).not.toContainText('旧期货研报')
})
