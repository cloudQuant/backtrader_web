/**
 * Iteration 175 §3.5 — Lighthouse CI puppeteerScript hook.
 *
 * For the public login route (`/login`) the hook is a no-op.
 * For authenticated pages we inject a pre-issued token via localStorage so
 * Lighthouse can render the page without going through an interactive login.
 *
 * The token is read from environment:
 *   LHCI_AUTH_TOKEN     — bearer access token to inject
 *   LHCI_AUTH_USER      — optional username for components that read it
 *
 * The script is intentionally defensive: if no token is provided we log a
 * warning and continue, which lets local runs see the unauthenticated SPA
 * behaviour without breaking the LHCI workflow.
 */

module.exports = async (browser, context) => {
  // context shape provided by lhci: { url, options } when running collect.
  const url = context && context.url ? String(context.url) : ''

  // Public login page — nothing to inject.
  if (/\/login(\/|$|\?)/.test(url)) return

  const token = process.env.LHCI_AUTH_TOKEN || ''
  const username = process.env.LHCI_AUTH_USER || ''

  if (!token) {
    // eslint-disable-next-line no-console
    console.warn(
      `[lhci/login.js] LHCI_AUTH_TOKEN not set — ${url} will be audited without auth state`
    )
    return
  }

  const page = await browser.newPage()
  try {
    // Visit the login page so the SPA registers its own origin in the browser
    // context, then drop the token into storage and reload.
    const origin = new URL(url).origin
    await page.goto(`${origin}/login`, { waitUntil: 'domcontentloaded' })
    await page.evaluate(
      ({ tok, user }) => {
        try {
          // The auth store persists via pinia-plugin-persistedstate under
          // sessionStorage key 'auth' (JSON with .token). The plain
          // localStorage keys are kept for older app versions.
          window.sessionStorage.setItem('auth', JSON.stringify({
            token: tok,
            refreshToken: null,
            user: user || undefined,
          }))
          window.localStorage.setItem('access_token', tok)
          window.localStorage.setItem('token', tok)
          if (user) {
            window.localStorage.setItem('username', user)
          }
        } catch {
          /* private mode — ignore */
        }
      },
      { tok: token, user: username }
    )
  } finally {
    await page.close()
  }
}
