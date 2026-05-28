#!/usr/bin/env node
// Iteration 175 §7.2 — list assets that load when a given route is opened.
//
// Strategy: parse `dist/.vite/manifest.json` (vite produces this when
// `build.manifest = true` is set). When the manifest is unavailable we fall
// back to scanning `dist/assets/*.js` for the route module name (the file is
// hashed but still includes the source basename, e.g. `Login-XXXX.js`).
//
// Usage:
//   node list_route_assets.mjs <route> <dist_dir> [--kind=non-vendor-js|js|all]
//
// Examples:
//   node list_route_assets.mjs /login src/frontend/dist
//   node list_route_assets.mjs /login src/frontend/dist --kind=non-vendor-js
//
// Exits 0 with one asset filename per line on stdout. Empty stdout means no
// matching files (caller should treat that as 0 count, not failure).

import fs from 'node:fs'
import path from 'node:path'

const VENDOR_CHUNKS = new Set([
  'element-plus',
  'vue-router',
  'pinia',
  'echarts',
  'monaco-editor',
])

// Maps known route paths to the source view filename hint (without hash).
// Extend as more routes are added to the smoke checks.
const ROUTE_VIEW_HINTS = {
  '/login': ['Login', 'LoginView', 'LoginPage'],
  '/dashboard': ['Dashboard', 'DashboardView', 'DashboardPage', 'Home'],
  '/ai-chat': ['AIChatPage', 'AIChat'],
  '/backtests': ['BacktestList', 'Backtests'],
  '/backtest-detail': ['BacktestDetail', 'BacktestResult'],
  '/knowledge-base': ['KnowledgeBasePage', 'KnowledgeBase'],
  '/strategies': ['Strategy', 'StrategyList', 'Strategies'],
}

function parseArgs(argv) {
  const positional = []
  const opts = { kind: 'non-vendor-js' }
  for (const arg of argv.slice(2)) {
    if (arg.startsWith('--kind=')) {
      opts.kind = arg.slice('--kind='.length)
    } else {
      positional.push(arg)
    }
  }
  if (positional.length < 2) {
    console.error('Usage: list_route_assets.mjs <route> <dist_dir> [--kind=...]')
    process.exit(2)
  }
  return { route: positional[0], distDir: positional[1], kind: opts.kind }
}

function isVendorChunk(filename) {
  const base = path.basename(filename)
  for (const v of VENDOR_CHUNKS) {
    if (base.startsWith(`${v}-`) || base.startsWith(`${v}.`)) return true
  }
  return false
}

function scanFallback(route, distDir, kind) {
  // No manifest — scan dist/assets for filename containing the view hint.
  const assetsDir = path.join(distDir, 'assets')
  if (!fs.existsSync(assetsDir)) return []
  const hints = ROUTE_VIEW_HINTS[route] || []
  const all = fs.readdirSync(assetsDir).filter(f => f.endsWith('.js'))
  let matched
  if (hints.length === 0) {
    // Default: just the entry chunk + any file matching route slug.
    const slug = route.replace(/^\//, '').replace(/[\/:]/g, '-') || 'index'
    matched = all.filter(f => f.startsWith(`index-`) || f.toLowerCase().includes(slug.toLowerCase()))
  } else {
    matched = all.filter(f => f.startsWith('index-') || hints.some(h => f.toLowerCase().startsWith(`${h.toLowerCase()}-`) || f.toLowerCase().startsWith(`${h.toLowerCase()}.`)))
  }
  return filterByKind(matched, kind)
}

function filterByKind(files, kind) {
  if (kind === 'all' || kind === 'js') return files
  if (kind === 'non-vendor-js') return files.filter(f => !isVendorChunk(f))
  return files
}

function listFromManifest(manifest, route, distDir, kind) {
  const hints = ROUTE_VIEW_HINTS[route] || []
  const matched = new Set()

  // Always include entries that look like the SPA entry html (root chunk).
  for (const [src, entry] of Object.entries(manifest)) {
    if (!entry || typeof entry !== 'object') continue
    if (entry.isEntry && entry.file && entry.file.endsWith('.js')) {
      matched.add(entry.file)
    }
  }

  // Walk imports/dynamicImports of any entry that matches the route hints.
  function walk(srcKey, visited = new Set()) {
    if (visited.has(srcKey)) return
    visited.add(srcKey)
    const entry = manifest[srcKey]
    if (!entry) return
    if (entry.file && entry.file.endsWith('.js')) matched.add(entry.file)
    for (const dep of entry.imports || []) walk(dep, visited)
    for (const dep of entry.dynamicImports || []) walk(dep, visited)
    for (const dep of entry.css || []) {
      if (dep.endsWith('.js')) matched.add(dep)
    }
  }

  for (const [src, entry] of Object.entries(manifest)) {
    if (!entry || typeof entry !== 'object') continue
    if (hints.some(h => src.toLowerCase().includes(h.toLowerCase()))) {
      walk(src)
    }
  }

  return filterByKind(Array.from(matched).sort(), kind)
}

function main() {
  const { route, distDir, kind } = parseArgs(process.argv)
  const manifestPath = path.join(distDir, '.vite', 'manifest.json')
  let files = []
  if (fs.existsSync(manifestPath)) {
    try {
      const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf-8'))
      files = listFromManifest(manifest, route, distDir, kind)
    } catch (err) {
      console.error(`WARN: failed to parse ${manifestPath}: ${err.message}`)
      files = scanFallback(route, distDir, kind)
    }
  } else {
    files = scanFallback(route, distDir, kind)
  }
  for (const f of files) {
    process.stdout.write(`${f}\n`)
  }
}

main()
