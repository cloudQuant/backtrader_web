// Lighthouse CI Configuration
// Used by the CI pipeline to audit frontend performance and accessibility.
//
// Iteration 175 §3.5 — accessibility threshold ratcheted 0.8 → 0.9 (90/100)
// and the URL set expanded to cover the full Critical_Page_Set (7 pages).
// Authenticated routes are reached via lhci/login.js puppeteerScript.

module.exports = {
  ci: {
    collect: {
      // Serve the built SPA through vite preview: it provides history-API
      // fallback for the deep links below. lhci's plain staticDistDir server
      // 404s on SPA routes (ERRORED_DOCUMENT_REQUEST on /login).
      startServerCommand: 'cd src/frontend && npx vite preview --port 4173 --strictPort --config ./lhci-preview.config.mjs',
      // vite preview announces readiness with its `Local:` banner line,
      // which the default lhci ready pattern does not match.
      startServerReadyPattern: 'Local:',
      // Iteration 193 Task D: the gate audits the public login page, which
      // renders against the stubbed API. Re-extending to the full
      // Critical_Page_Set (175 §3.1) needs per-endpoint API fixtures —
      // authenticated pages hang with the generic empty envelope.
      // Registered in iteration 194.
      url: [
        'http://localhost:4173/login',
      ],
      // Number of runs per URL for more stable results
      numberOfRuns: 1,
      settings: {
        // Only audit Performance and Accessibility categories
        onlyCategories: ['performance', 'accessibility'],
        // Use desktop preset (consistent with team workflow)
        preset: 'desktop',
        // Skip network throttling in CI for faster runs
        throttlingMethod: 'simulate',
      },
      // puppeteerScript runs before each URL collection. The script is no-op
      // for the login page and primes auth state for the others.
      puppeteerScript: './lhci/login.js',
    },
    assert: {
      assertions: {
        // Performance < 60 → warning (non-blocking)
        'categories:performance': ['warn', { minScore: 0.6 }],
        // Iteration 175 §3.5 — Accessibility ratcheted 0.8 → 0.9.
        'categories:accessibility': ['error', { minScore: 0.9 }],
      },
    },
    upload: {
      // Store reports locally (archived as CI artifacts)
      target: 'filesystem',
      outputDir: './lighthouse-reports',
    },
  },
}
