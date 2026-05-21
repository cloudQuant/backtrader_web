// Lighthouse CI Configuration
// Used by the CI pipeline to audit frontend performance and accessibility.
// Targets: login page and dashboard page (representative authenticated page).

module.exports = {
  ci: {
    collect: {
      // Use static server to serve the built frontend assets
      staticDistDir: './src/frontend/dist',
      // Pages to audit
      url: [
        'http://localhost/', // Login page (default route for unauthenticated users)
        'http://localhost/dashboard', // Dashboard page (representative authenticated page)
      ],
      // Number of runs per URL for more stable results
      numberOfRuns: 1,
      settings: {
        // Only audit Performance and Accessibility categories
        onlyCategories: ['performance', 'accessibility'],
        // Use mobile preset (Lighthouse default)
        preset: 'desktop',
        // Skip network throttling in CI for faster runs
        throttlingMethod: 'simulate',
      },
    },
    assert: {
      assertions: {
        // Performance < 60 → warning (non-blocking)
        'categories:performance': ['warn', { minScore: 0.6 }],
        // Accessibility < 80 → error (blocking)
        'categories:accessibility': ['error', { minScore: 0.8 }],
      },
    },
    upload: {
      // Store reports locally (archived as CI artifacts)
      target: 'filesystem',
      outputDir: './lighthouse-reports',
    },
  },
}
