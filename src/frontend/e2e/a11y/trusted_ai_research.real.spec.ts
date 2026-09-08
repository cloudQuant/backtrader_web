import { expect, test } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

const ENABLE_REAL_AI_RESEARCH_E2E = process.env.RUN_REAL_AI_RESEARCH_E2E === '1'
const API_BASE_URL = process.env.REAL_AI_RESEARCH_API_BASE || 'http://127.0.0.1:18096/api/v1'

type HttpResponse = {
  response: Response
  body: Record<string, unknown>
}

async function post(path: string, body: Record<string, unknown>): Promise<HttpResponse> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  })
  return { response, body: await response.json() as Record<string, unknown> }
}

test.skip(!ENABLE_REAL_AI_RESEARCH_E2E, 'Requires an isolated candidate FastAPI, PostgreSQL, and Vite stack.')

test('real trusted AI research UI/API chain has no blocking axe violations', async ({ page }) => {
  const username = `i196_real_ui_${Date.now()}`
  const password = 'Test12345678'
  const registration = await post('/auth/register', {
    username,
    email: `${username}@example.com`,
    password,
  })
  expect(registration.response.status).toBe(200)

  const login = await post('/auth/login', { username, password })
  expect(login.response.status).toBe(200)
  const token = login.body.access_token
  expect(typeof token).toBe('string')

  await page.addInitScript((accessToken) => {
    window.sessionStorage.setItem('auth', JSON.stringify({ token: accessToken, refreshToken: null }))
    window.localStorage.setItem('locale', 'zh-CN')
  }, token)

  const v2Responses: Array<{ path: string; status: number; response: Response }> = []
  page.on('response', response => {
    if (response.url().includes('/api/v1/strategy/ai-research/v2/')) {
      v2Responses.push({
        path: new URL(response.url()).pathname,
        status: response.status(),
        response,
      })
    }
  })

  await page.goto('/investment/strategies')
  await expect(page).toHaveURL(/\/investment\/strategies$/)
  const workbench = page.locator('[data-test="trusted-research-workbench"]')
  await expect(workbench).toBeVisible()

  const formFields = workbench.locator('.trusted-workbench__form input')
  const createDraft = workbench.locator('[data-test="trusted-research-create-draft"]')
  await expect(createDraft).toBeDisabled()
  await formFields.nth(0).fill('Does a stable signal persist after costs?')
  await formFields.nth(1).fill('The economic mechanism is documented before research starts.')
  await formFields.nth(2).fill('RB0')
  await expect(createDraft).toBeEnabled()

  await createDraft.click()
  await expect(workbench.locator('[data-test="trusted-research-draft"]')).toBeVisible()
  await workbench.locator('[data-test="trusted-research-confirm-precheck"]').click()

  const precheck = workbench.locator('[data-test="trusted-research-precheck"]')
  await expect(precheck).toBeVisible()
  await expect(precheck.locator('.trusted-workbench__status')).toHaveAttribute('data-status', 'PASS')
  await workbench.locator('[data-test="trusted-research-start-run"]').click()
  await expect(precheck).toHaveCount(0)

  const requiredPathPrefixes = [
    '/api/v1/strategy/ai-research/v2/hypotheses',
    '/api/v1/strategy/ai-research/v2/hypotheses/',
    '/api/v1/strategy/ai-research/v2/datasets',
    '/api/v1/strategy/ai-research/v2/epochs',
    '/api/v1/strategy/ai-research/v2/data-prechecks',
    '/api/v1/strategy/ai-research/v2/runs',
  ]
  for (const prefix of requiredPathPrefixes) {
    expect(v2Responses.some(item => item.path.startsWith(prefix) && item.status >= 200 && item.status < 300)).toBe(true)
  }

  const responseBodies = await Promise.all(v2Responses.map(async item => item.response.text()))
  expect(await workbench.innerText()).not.toContain('controlled://')
  expect(responseBodies.join('\n')).not.toContain('controlled://')

  const axeResults = await new AxeBuilder({ page })
    .include('[data-test="trusted-research-workbench"]')
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze()
  const blocking = axeResults.violations.filter(
    violation => violation.impact === 'critical' || violation.impact === 'serious',
  )
  expect(blocking).toEqual([])
})
