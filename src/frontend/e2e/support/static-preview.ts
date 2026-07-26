import type { Page } from '@playwright/test'

type StaticPreviewOptions = {
  authenticated?: boolean
}

/**
 * Makes static-preview checks independent from a running backend.
 *
 * Accessibility and locale checks exercise the rendered client routes rather
 * than the API. Giving them a small deterministic API surface avoids an
 * authentication redirect or unhandled request error masking the page under
 * test in CI's `vite preview` job.
 */
export async function prepareStaticPreviewPage(
  page: Page,
  { authenticated = true }: StaticPreviewOptions = {},
): Promise<void> {
  await page.addInitScript((shouldAuthenticate) => {
    if (shouldAuthenticate) {
      window.sessionStorage.setItem('auth', JSON.stringify({
        token: 'static-preview-token',
        refreshToken: null,
      }))
    } else {
      window.sessionStorage.removeItem('auth')
    }
  }, authenticated)

  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const json = (payload: unknown) => route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(payload),
    })

    if (path.endsWith('/auth/me')) {
      return json({
        id: 'static-preview-user',
        username: 'Static Preview User',
        email: 'static-preview@example.com',
        is_active: true,
        is_admin: true,
        created_at: '2026-07-12T00:00:00Z',
      })
    }
    if (path.endsWith('/me/ai/available-models')) {
      return json({ providers: [], models: [], preferences: { provider: null, model: null } })
    }
    if (path.endsWith('/me/ai/usage')) {
      return json({
        summary: { total_calls: 0, failed_calls: 0, total_tokens: 0, estimated_cost_usd: 0 },
        by_day: [],
        by_service: [],
        by_model: [],
      })
    }
    if (path.includes('/knowledge-base/')) {
      return json({ total: 0, items: [], skip: 0, limit: 100 })
    }
    if (path.includes('/kb-chat/conversations')) {
      return json({ total: 0, items: [] })
    }
    if (path.includes('/workspace/')) {
      return json({ total: 0, items: [] })
    }
    if (path.includes('/backtests')) {
      return json({ total: 0, items: [], offset: 0, limit: 20 })
    }
    if (path.includes('/strateg')) {
      return json({ total: 0, items: [], templates: [] })
    }
    return json({ total: 0, items: [] })
  })
}
