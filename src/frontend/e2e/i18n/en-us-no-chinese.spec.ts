import { test, expect } from '@playwright/test'
import { APP_PATHS } from '../../src/navigation/routes'
import { prepareStaticPreviewPage } from '../support/static-preview'

/**
 * Iteration 175 §4.8 / §4.9 — when the UI is in en-US locale, no
 * user-visible text on Critical_Page_Set may contain Chinese characters.
 *
 * Strategy: inject `localStorage.setItem('locale', 'en-US')` before the SPA
 * boots (matches the locale persistence key used by stores/theme.ts), navigate
 * to each page, then assert the body innerText does not match the CJK range.
 *
 * The login page accepts an empty storageState (no auth required); the other
 * 6 pages reuse the project's default storageState.
 */

const PAGES_AUTHENTICATED = [
  APP_PATHS.dashboard,
  APP_PATHS.ai.chat,
  APP_PATHS.backtest.list,
  APP_PATHS.backtest.result(1),
  APP_PATHS.ai.knowledgeBase,
  APP_PATHS.research.strategies,
  APP_PATHS.trading.workspaces,
  APP_PATHS.config.gateways,
  APP_PATHS.config.dataScripts,
] as const

test.describe('en-US locale should never render Chinese characters', () => {
  test('login page', async ({ browser }) => {
    test.setTimeout(45_000)
    const context = await browser.newContext({ storageState: { cookies: [], origins: [] } })
    const page = await context.newPage()
    await page.addInitScript(() => {
      try {
        window.localStorage.setItem('locale', 'en-US')
        window.localStorage.setItem('lang', 'en-US')
      } catch {
        /* private mode — fail open, the assertion below catches CJK leaks */
      }
    })
    await prepareStaticPreviewPage(page, { authenticated: false })
    await page.goto('/login')
    await page.waitForLoadState('networkidle')
    const text = await page.locator('body').innerText()
    await context.close()
    expect(text, 'login page body must not contain CJK characters under en-US').not.toMatch(
      /[\u4e00-\u9fff]/
    )
  })

  for (const url of PAGES_AUTHENTICATED) {
    test(`page ${url}`, async ({ page }) => {
      test.setTimeout(45_000)
      await prepareStaticPreviewPage(page)
      await page.addInitScript(() => {
        try {
          window.localStorage.setItem('locale', 'en-US')
          window.localStorage.setItem('lang', 'en-US')
        } catch {
          /* ignore */
        }
      })
      await page.goto(url)
      await page.waitForLoadState('networkidle')
      const text = await page.locator('body').innerText()
      expect(text, `${url} body must not contain CJK characters under en-US`).not.toMatch(
        /[\u4e00-\u9fff]/
      )
    })
  }
})
