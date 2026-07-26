import { expect, test } from '@playwright/test'

import { APP_PATHS } from '../../src/navigation/routes'
import { prepareStaticPreviewPage } from '../support/static-preview'

test.describe('strategy code editor', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test('allows code to be entered in the create strategy dialog', async ({ page }) => {
    await prepareStaticPreviewPage(page)
    await page.goto(APP_PATHS.research.strategies)

    await page.getByRole('button', { name: /创建策略|Create Strategy/ }).click()

    const codeInput = page.locator('textarea.strategy-code-input')
    await expect(codeInput).toBeVisible()
    await codeInput.fill('print("strategy editor works")')

    await expect(codeInput).toHaveValue('print("strategy editor works")')
  })
})
