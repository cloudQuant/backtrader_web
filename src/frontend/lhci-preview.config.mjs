import { defineConfig } from 'vite'

/**
 * Lighthouse CI preview server config (iteration 193 Task D).
 *
 * The lighthouse job audits the built SPA without a live backend. Plain
 * `vite preview` serves index.html for every /api/* path (history-API
 * fallback), so the app's startup calls receive HTML 200s, the auth store
 * logs out, and authenticated pages never paint (NO_FCP).
 *
 * This plugin stubs the /api surface in the preview middleware: /auth/me
 * answers the injected LHCI_AUTH_TOKEN session and everything else returns
 * an empty-but-valid JSON envelope, so Critical_Page_Set routes render and
 * can be audited for performance / accessibility.
 */

const EMPTY_ENVELOPE = JSON.stringify({ items: [], total: 0, page: 1, limit: 20 })

function stubApi() {
  return {
    name: 'lhci-api-stub',
    configurePreviewServer(server) {
      server.middlewares.use('/api', (req, res) => {
        const url = req.url || ''
        if (url.includes('/auth/me')) {
          res.setHeader('Content-Type', 'application/json')
          res.end(JSON.stringify({
            id: 'lhci-static-preview',
            username: 'lhci-preview',
            is_admin: true,
          }))
          return
        }
        res.setHeader('Content-Type', 'application/json')
        res.end(EMPTY_ENVELOPE)
      })
    },
  }
}

export default defineConfig({
  plugins: [stubApi()],
})
