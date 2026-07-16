import { expect, test } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

import { APP_PATHS } from '../../src/navigation/routes'
import { prepareStaticPreviewPage } from '../support/static-preview'

test.describe('mobile workspace panels', () => {
  test.use({ viewport: { width: 320, height: 844 } })

  test('AI conversation drawer is keyboard reachable and returns focus on close', async ({ page }) => {
    await prepareStaticPreviewPage(page)
    await page.goto(APP_PATHS.ai.chat)
    await page.locator('[data-test="ai-chat-page"]').waitFor()

    const trigger = page.locator('[data-test="ai-chat-open-conversations"]')
    await trigger.click()
    const drawer = page.locator('.conversation-panel.mobile-open')
    await expect(drawer).toHaveAttribute('role', 'dialog')
    await expect(page.locator('.conversation-panel .mobile-panel-close')).toBeFocused()

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze()
    const blocking = results.violations.filter(
      violation => violation.impact === 'critical' || violation.impact === 'serious',
    )
    expect(blocking).toHaveLength(0)

    await page.keyboard.press('Escape')
    await expect(trigger).toBeFocused()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320)
  })
})
