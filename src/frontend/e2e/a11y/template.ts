import { test, expect, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { prepareStaticPreviewPage } from '../support/static-preview'

/**
 * Iteration 175 §3 — A11y baseline scan helper.
 *
 * Each Critical_Page_Set spec follows the same pattern:
 *   1. Navigate to the page (logged-in pages reuse the auth fixture's
 *      storageState in playwright.config.ts).
 *   2. Wait for network idle (axe needs the DOM to settle).
 *   3. Run AxeBuilder with the WCAG 2.1 A/AA tag set, 30s timeout.
 *   4. Filter violations to only critical/serious — these are the impact
 *      levels that block the PR (Requirement 3.2). minor/moderate are surfaced
 *      as warnings but do not fail the job.
 *   5. On failure, dump the violation list as a ::group:: console block so
 *      the GitHub Actions log groups it nicely. The job summary step renders
 *      a markdown table from the same data (Requirement 3.7).
 */

export interface A11yScanOptions {
  /** Path under baseURL, e.g. '/dashboard'. */
  url: string
  /** Locator selector that confirms the page rendered before scanning. */
  readySelector?: string
  /** Pre-scan hook (e.g. open a tab/menu, dismiss a tooltip). */
  beforeScan?: (page: Page) => Promise<void>
}

export function registerA11yPageSpec(label: string, opts: A11yScanOptions): void {
  test(`a11y - ${label} (${opts.url})`, async ({ page }) => {
    test.setTimeout(60_000)

    await prepareStaticPreviewPage(page)
    await page.goto(opts.url)
    await page.waitForLoadState('networkidle')
    if (opts.readySelector) {
      await page.waitForSelector(opts.readySelector, { timeout: 15_000 })
    }
    if (opts.beforeScan) {
      await opts.beforeScan(page)
    }

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze()

    const blocking = results.violations.filter(
      v => v.impact === 'critical' || v.impact === 'serious'
    )

    if (blocking.length > 0) {
      console.log(`::group::a11y violations on ${opts.url}`)
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

    // Surface non-blocking violations as a friendly note.
    const nonBlocking = results.violations.filter(
      v => v.impact !== 'critical' && v.impact !== 'serious'
    )
    if (nonBlocking.length > 0) {
      console.log(
        `[a11y] ${opts.url}: ${nonBlocking.length} minor/moderate violation(s) — not blocking`
      )
    }

    expect(blocking).toHaveLength(0)
  })
}
