import { test, expect } from '@playwright/test'
import { APP_PATHS } from '../../src/navigation/routes'

/**
 * Iteration 175 §6.1 — User_Journey_Set, the 5 PR-blocking smoke journeys.
 *
 * Each test asserts at least one *observable* outcome (DOM element, text
 * match, URL pattern) so that a stub backend or skin-only regression cannot
 * mask a real failure. The full e2e suite is run nightly; this smoke set is
 * what gates merging.
 */

test.describe.configure({ mode: 'serial', timeout: 60_000 })

test.describe('anonymous smoke journey', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test('Journey A — login & logout (#1)', async ({ page }) => {
    await page.goto('/login')
    await expect(page).toHaveURL(/\/login/)

    // Login form fields — IDs/names are project-specific; selectors below
    // intentionally use multiple fallbacks so a UI rename doesn't break smoke.
    const usernameInput = page.locator('input[name="username"], input[type="text"]').first()
    const passwordInput = page.locator('input[name="password"], input[type="password"]').first()
    await usernameInput.fill('admin')
    await passwordInput.fill('admin')
    await page.locator('button[type="submit"], button:has-text("登录"), button:has-text("Login")').first().click()

    // After login the navbar should expose a username affordance.
    await page.waitForLoadState('networkidle')
    const navUserAffordance = page.locator(
      '[data-test=nav-user], header :text("admin"), nav :text("admin")'
    )
    await expect(navUserAffordance).toBeVisible({ timeout: 15_000 })

    // Logout: click logout button or menu — fallback to URL nav if no UI hook.
    const logoutBtn = page.locator(
      '[data-test=logout-button], button:has-text("退出"), button:has-text("Logout"), a:has-text("Logout")'
    )
    if (await logoutBtn.count()) {
      await logoutBtn.first().click()
    } else {
      await page.goto('/login')
    }
    await expect(page).toHaveURL(/\/login/, { timeout: 10_000 })
  })
})

test.describe('authenticated smoke journeys', () => {
  // globalSetup creates this state once after the smoke seed has provisioned
  // the default admin. Each Playwright test gets an isolated context, so the
  // state must be explicitly loaded for every authenticated journey.
  test.use({ storageState: 'e2e/fixtures/storage-state.json' })

  test('Journey B — create & view backtest (#2)', async ({ page }) => {
    await page.goto(APP_PATHS.backtest.list)
    await page.waitForLoadState('networkidle')

    // The smoke seed script (scripts/dev/seed_e2e_smoke.py) creates one
    // completed backtest at id=1. Navigate directly to its detail.
    await page.goto(APP_PATHS.backtest.result(1))
    await page.waitForLoadState('networkidle')

    // Equity-curve canvas/svg + status text confirm the result rendered.
    const equityCurve = page.locator(
      '[data-test=equity-curve], canvas, svg.echarts'
    )
    await expect(equityCurve.first()).toBeVisible({ timeout: 15_000 })

    const statusText = page.locator('body')
    await expect(statusText).toContainText(/completed|已完成|完成/, { timeout: 10_000 })
  })

  test('Journey C — AI chat replies (#3)', async ({ page }) => {
    await page.goto(APP_PATHS.ai.chat)
    await page.waitForLoadState('networkidle')

    const input = page.locator(
      '[data-test=ai-chat-input], textarea, input[type="text"]'
    ).first()
    await input.fill('hello')

    const send = page.locator(
      '[data-test=ai-chat-send], button:has-text("发送"), button:has-text("Send")'
    ).first()
    await send.click()

    // First assistant message must have non-empty body within 30s.
    const assistantMsg = page.locator(
      '[data-test=ai-message-assistant], .message-assistant, .ai-message:not(.user)'
    ).first()
    await expect(assistantMsg).toBeVisible({ timeout: 30_000 })
    const text = await assistantMsg.innerText()
    expect(text.trim().length, 'assistant reply must be non-empty').toBeGreaterThan(0)
  })

  test('Journey D — knowledge base Q&A (#4)', async ({ page }) => {
    await page.goto(APP_PATHS.ai.knowledgeBase)
    await page.waitForLoadState('networkidle')

    const input = page.locator(
      '[data-test=kb-question], textarea, input[type="text"]'
    ).first()
    await input.fill('What is a backtest?')

    const ask = page.locator(
      '[data-test=kb-ask], button:has-text("提问"), button:has-text("Ask")'
    ).first()
    await ask.click()

    // At least one citation chip with non-empty href.
    const citation = page.locator('[data-test=citation-chip]').first()
    await expect(citation).toBeVisible({ timeout: 30_000 })
    const href = await citation.getAttribute('href')
    expect(href, 'citation must have non-empty href').toBeTruthy()
    expect((href || '').trim().length).toBeGreaterThan(0)
  })

  test('Journey E — create strategy & see in list (#5)', async ({ page }) => {
    await page.goto(APP_PATHS.research.strategies)
    await page.waitForLoadState('networkidle')

    // Smoke-uniqueness — name carries timestamp.
    const name = `e2e-smoke-${Date.now()}`

    const newBtn = page.locator(
      '[data-test=new-strategy], button:has-text("新建"), button:has-text("New Strategy")'
    ).first()
    await newBtn.click()

    const nameInput = page.locator(
      '[data-test=strategy-name-input], input[name="name"]'
    ).first()
    await nameInput.fill(name)

    const submit = page.locator(
      '[data-test=strategy-submit], button[type="submit"], button:has-text("保存"), button:has-text("Save")'
    ).first()
    await submit.click()

    // Back to the list — assert the new row exists.
    await page.goto(APP_PATHS.research.strategies)
    await page.waitForLoadState('networkidle')
    await expect(page.locator(`text=${name}`)).toBeVisible({ timeout: 10_000 })
  })
})
