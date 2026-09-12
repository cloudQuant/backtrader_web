import { expect, test, type Page, type Route } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

import { prepareStaticPreviewPage } from '../support/static-preview'

const HASH = 'a'.repeat(64)

function json(route: Route, payload: unknown): Promise<void> {
  return route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify(payload),
  })
}

function precheck(status: 'PASS' | 'BLOCKED', id: string) {
  return {
    id,
    hypothesis_version_id: 'hypothesis-1',
    dataset_snapshot_id: 'dataset-1',
    experiment_epoch_id: 'epoch-1',
    profile_id: 'isolated-profile',
    profile_version: 'v1',
    promotion_policy_version: 'promotion-v1',
    input_hash: 'c'.repeat(64),
    evidence_hash: 'd'.repeat(64),
    status,
    reason_code: status === 'BLOCKED' ? 'BLOCKED_TOPOLOGY_CAPABILITY:sandbox_runner' : null,
    details: {},
    checked_at: '2026-09-05T00:00:00Z',
    expires_at: '2099-09-05T00:15:00Z',
  }
}

async function expectNoBlockingAxeViolation(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page })
    .include('[data-test="trusted-research-workbench"]')
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze()
  const blocking = results.violations.filter(
    violation => violation.impact === 'critical' || violation.impact === 'serious',
  )

  expect(blocking).toHaveLength(0)
}

test('trusted AI research on the investment route preserves the same binding across a precheck retry', async ({ page }) => {
  await prepareStaticPreviewPage(page)

  const calls: string[] = []
  const precheckBodies: Array<Record<string, unknown>> = []
  let precheckCount = 0

  await page.route('**/api/v1/strategy/ai-research/v2/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname

    if (path.endsWith('/hypotheses') && request.method() === 'POST') {
      calls.push('draft')
      return json(route, {
        id: 'hypothesis-1',
        content_hash: HASH,
        canonical_payload: { research_question: 'server canonical payload' },
      })
    }
    if (path.endsWith('/hypotheses/hypothesis-1/confirm') && request.method() === 'POST') {
      calls.push('confirm')
      return json(route, { id: 'hypothesis-1', content_hash: HASH })
    }
    if (path.endsWith('/datasets') && request.method() === 'POST') {
      calls.push('dataset')
      return json(route, { id: 'dataset-1' })
    }
    if (path.endsWith('/epochs') && request.method() === 'POST') {
      calls.push('epoch')
      return json(route, { id: 'epoch-1' })
    }
    if (path.endsWith('/data-prechecks') && request.method() === 'POST') {
      calls.push('precheck')
      precheckBodies.push(request.postDataJSON() as Record<string, unknown>)
      precheckCount += 1
      return json(route, precheck(precheckCount === 1 ? 'BLOCKED' : 'PASS', `precheck-${precheckCount}`))
    }
    if (path.endsWith('/runs') && request.method() === 'POST') {
      calls.push('submit')
      return json(route, {
        run: {
          id: 'run-1',
          hypothesis_version_id: 'hypothesis-1',
          dataset_snapshot_id: 'dataset-1',
          data_precheck_id: 'precheck-2',
          experiment_epoch_id: 'epoch-1',
          protocol_version: 'v2',
          status: 'QUEUED',
          stage_cursor: 'CLARIFY',
          promotion_policy_version: 'promotion-v1',
          request_hash: HASH,
          capability_profile_id: 'isolated-profile',
          capability_profile_version: 'v1',
          capability_evidence_hash: 'e'.repeat(64),
          trace_id: 'trace-run-1',
          created_at: '2026-09-05T00:00:00Z',
        },
        task: {
          id: 'task-1',
          run_id: 'run-1',
          status: 'QUEUED',
          stage_cursor: 'CLARIFY',
          attempt_count: 0,
          created_at: '2026-09-05T00:00:00Z',
        },
      })
    }
    if (path.endsWith('/runs/run-1') && request.method() === 'GET') {
      calls.push('workbench')
      return json(route, {
        run: {
          id: 'run-1',
          hypothesis_version_id: 'hypothesis-1',
          protocol_version: 'v2',
          status: 'QUEUED',
          stage_cursor: 'CLARIFY',
          promotion_policy_version: 'promotion-v1',
          request_hash: HASH,
          capability_profile_id: 'isolated-profile',
          capability_profile_version: 'v1',
          capability_evidence_hash: 'e'.repeat(64),
          trace_id: 'trace-run-1',
          created_at: '2026-09-05T00:00:00Z',
        },
        task: {
          id: 'task-1',
          run_id: 'run-1',
          status: 'QUEUED',
          stage_cursor: 'CLARIFY',
          attempt_count: 0,
          created_at: '2026-09-05T00:00:00Z',
        },
        candidates: [],
        ledger: [],
        model_invocations: [],
        evaluations: [],
        gates: [],
        decisions: [],
        evidence_packages: [],
        holdout_commands: [],
        evidence_class: 'PROTOCOL_V2_PENDING',
      })
    }
    return json(route, { detail: `unexpected trusted-research request: ${path}` })
  })

  await page.goto('/investment/strategies')

  const workbench = page.locator('[data-test="trusted-research-workbench"]')
  const formFields = workbench.locator('.trusted-workbench__form input')
  const createDraft = workbench.locator('[data-test="trusted-research-create-draft"]')

  await expect(page).toHaveURL(/\/investment\/strategies$/)
  await expect(page.locator('[data-test="ai-research-hero"]')).toBeVisible()
  await expect(workbench).toBeVisible()
  await expect(createDraft).toBeDisabled()

  await formFields.nth(0).fill('Does a stable signal persist after costs?')
  await formFields.nth(1).fill('The economic mechanism is documented before research starts.')
  await formFields.nth(2).fill('RB0')
  await formFields.nth(10).fill('')
  await expect(createDraft).toBeDisabled()
  await formFields.nth(10).fill('isolated-profile')
  await expect(createDraft).toBeEnabled()

  await createDraft.focus()
  await page.keyboard.press('Enter')
  await expect(workbench.locator('[data-test="trusted-research-draft"]')).toBeVisible()
  await workbench.locator('[data-test="trusted-research-confirm-precheck"]').click()

  const blockedPrecheck = workbench.locator('[data-test="trusted-research-precheck"]')
  const retryPrecheck = workbench.locator('[data-test="trusted-research-retry-precheck"]')
  await expect(retryPrecheck).toBeVisible()
  await expect(blockedPrecheck).toHaveAttribute('aria-live', 'polite')
  expect(calls).toEqual(['draft', 'confirm', 'dataset', 'epoch', 'precheck'])
  await expectNoBlockingAxeViolation(page)

  await retryPrecheck.focus()
  await page.keyboard.press('Enter')
  await expect(workbench.locator('[data-test="trusted-research-start-run"]')).toBeVisible()
  expect(calls).toEqual(['draft', 'confirm', 'dataset', 'epoch', 'precheck', 'precheck'])
  expect(precheckBodies).toHaveLength(2)
  expect(precheckBodies[1]).toEqual(precheckBodies[0])

  await workbench.locator('[data-test="trusted-research-start-run"]').click()
  await expect(workbench.locator('[data-test="trusted-research-precheck"]')).toHaveCount(0)
  expect(calls).toEqual(['draft', 'confirm', 'dataset', 'epoch', 'precheck', 'precheck', 'submit', 'workbench'])

  await expectNoBlockingAxeViolation(page)
})
