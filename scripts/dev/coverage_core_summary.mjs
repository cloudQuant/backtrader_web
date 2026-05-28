#!/usr/bin/env node
// Iteration 175 §2.5 — emit two markdown tables to $GITHUB_STEP_SUMMARY:
//   Table A: global lines/functions/branches/statements vs 75% threshold
//   Table B: per-module High_Coverage_Core indicators vs 90% threshold
//
// Reads coverage/coverage-summary.json (produced by vitest's `json-summary`
// reporter). Exits 0 even when thresholds fail — vitest itself enforces the
// thresholds; this script is purely informational.

import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'

const REPO_ROOT = process.cwd()
const SUMMARY_PATH = path.join(REPO_ROOT, 'coverage', 'coverage-summary.json')
const GLOBAL_THRESHOLD = 75
const CORE_THRESHOLD = 90

const HIGH_COVERAGE_CORE = [
  'src/stores/auth.ts',
  'src/stores/theme.ts',
  'src/stores/backtest.ts',
  'src/stores/strategy.ts',
  'src/stores/knowledgeBase.ts',
  'src/api/index.ts',
  'src/composables/useBacktestRuntime.ts',
  'src/utils/markdown-sanitizer.ts',
]

const out = process.env.GITHUB_STEP_SUMMARY || '/dev/stdout'

function emit(line) {
  fs.appendFileSync(out, line + '\n')
}

function fmt(n) {
  if (n === null || n === undefined || Number.isNaN(n)) return 'n/a'
  return Number(n).toFixed(2)
}

function statusEmoji(pct, threshold) {
  if (pct === null || pct === undefined || Number.isNaN(pct)) return '⏭️ no-data'
  return pct >= threshold ? '✅' : '❌'
}

function loadSummary() {
  if (!fs.existsSync(SUMMARY_PATH)) {
    emit('### Coverage Core Summary')
    emit('')
    emit(`> ⚠️ \`${path.relative(REPO_ROOT, SUMMARY_PATH)}\` not found — did vitest run with the \`json-summary\` reporter?`)
    return null
  }
  return JSON.parse(fs.readFileSync(SUMMARY_PATH, 'utf-8'))
}

function findEntry(summary, relativePath) {
  // coverage-summary.json keys are absolute paths; match by suffix.
  const suffix = relativePath.replaceAll('/', path.sep)
  const found = Object.keys(summary).find(k =>
    k !== 'total' && (k.endsWith(suffix) || k.endsWith(relativePath))
  )
  return found ? summary[found] : null
}

function main() {
  const summary = loadSummary()
  if (!summary) return

  emit('### Coverage Core Summary (Iteration 175 §2)')
  emit('')

  // ----- Table A: global -----
  emit(`#### Global (threshold: ${GLOBAL_THRESHOLD}%)`)
  emit('')
  emit('| Metric | Threshold | Actual | Status |')
  emit('|--------|----------:|-------:|:------:|')
  const total = summary.total || {}
  for (const metric of ['lines', 'functions', 'branches', 'statements']) {
    const pct = total[metric]?.pct
    emit(`| ${metric} | ${GLOBAL_THRESHOLD} | ${fmt(pct)} | ${statusEmoji(pct, GLOBAL_THRESHOLD)} |`)
  }
  emit('')

  // ----- Table B: High_Coverage_Core -----
  emit(`#### High_Coverage_Core (threshold: ${CORE_THRESHOLD}%)`)
  emit('')
  emit('| Module | lines | functions | branches | statements | Status |')
  emit('|--------|------:|----------:|---------:|-----------:|:------:|')
  for (const modulePath of HIGH_COVERAGE_CORE) {
    const entry = findEntry(summary, modulePath)
    if (!entry) {
      emit(`| \`${modulePath}\` | n/a | n/a | n/a | n/a | ⏭️ no-data |`)
      continue
    }
    const lines = entry.lines?.pct
    const functions = entry.functions?.pct
    const branches = entry.branches?.pct
    const statements = entry.statements?.pct
    const allPass = [lines, functions, branches, statements].every(
      pct => pct !== null && pct !== undefined && pct >= CORE_THRESHOLD
    )
    emit(
      `| \`${modulePath}\` | ${fmt(lines)} | ${fmt(functions)} | ${fmt(branches)} | ${fmt(statements)} | ${
        allPass ? '✅' : '❌'
      } |`
    )
  }
  emit('')
  emit(
    '> Tables A and B are informational. The authoritative gate is vitest itself — thresholds are configured in `vitest.config.ts` and a sub-threshold result fails the `frontend-test` CI job.'
  )
  emit('')
}

main()
