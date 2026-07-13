import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { prepareStaticPreviewPage } from '../support/static-preview'

// Login page — no auth state required; uses the project's default storageState.
// Iteration 175 §3.2 / Requirement 3 acceptance test.

test.describe.configure({ mode: 'serial' })
test.use({ storageState: { cookies: [], origins: [] } })

test('a11y - /login (Critical_Page_Set #1)', async ({ page }) => {
  test.setTimeout(60_000)
  await prepareStaticPreviewPage(page, { authenticated: false })
  await page.goto('/login')
  await page.waitForLoadState('networkidle')

  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze()

  const blocking = results.violations.filter(
    v => v.impact === 'critical' || v.impact === 'serious'
  )

  if (blocking.length > 0) {
    console.log('::group::a11y violations on /login')
    for (const v of blocking) {
      console.log(
        JSON.stringify({
          url: page.url(),
          id: v.id,
          impact: v.impact,
          help: v.helpUrl,
          nodes: v.nodes.map(n => n.target.join(' ')),
        })
      )
    }
    console.log('::endgroup::')
  }

  expect(blocking).toHaveLength(0)
})
