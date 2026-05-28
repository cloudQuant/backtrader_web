# High_Coverage_Core Module Registry

> Iteration 175 §2 — modules with >= 90% per-path coverage thresholds.

## Overview

These 8 modules are the High_Coverage_Core: any test gap that would let one of
them slip below 90% on lines / functions / branches / statements is caught at
PR time by the `frontend-test` job. The module list is the source of truth in
`vitest.config.ts` (and `vite.config.ts` for older callers); the table here is
the human-readable view used in PR reviews.

## Modules

| # | Path | Role | Notes |
|---|------|------|-------|
| 1 | `src/stores/auth.ts`                    | Pinia store: auth credentials & session refresh | sessionStorage-persisted via `pinia-plugin-persistedstate` |
| 2 | `src/stores/theme.ts`                   | Pinia store: user UI preferences (theme / language / sidebar collapse) | localStorage-persisted |
| 3 | `src/stores/backtest.ts`                | Pinia store: backtest task lifecycle | feeds `BacktestRuntime` composables |
| 4 | `src/stores/strategy.ts`                | Pinia store: strategy CRUD / list cache | |
| 5 | `src/stores/knowledgeBase.ts`           | Pinia store: KB documents / chat sessions | |
| 6 | `src/api/index.ts`                      | Axios instance + retry interceptor + ElMessage suppression | 174-iter-2 §3 entry point |
| 7 | `src/composables/useBacktestRuntime.ts` | Composable: backtest run/pause/resume/cancel | dependency-injection design |
| 8 | `src/utils/markdown-sanitizer.ts`       | DOMPurify whitelist + marked render | XSS-critical |

> Total: 8 modules (within the 8–20 bound in Requirement 2.2).

## Exempted line ranges

> Format: `<repo-relative path>:<start_line>-<end_line>` — adjacent to a Chinese
> or English reason ≤ 200 chars.

(none registered yet — exemption requests must be raised in PR description and
linked here before merging the change.)

## How thresholds are enforced

1. Per-path keys in `vitest.config.ts > test.coverage.thresholds` apply 90/90/90/90
   to each entry above.
2. `scripts/dev/coverage_core_summary.mjs` runs after `npm run test -- --coverage`
   in CI and writes a markdown table of global + High_Coverage_Core results to
   `$GITHUB_STEP_SUMMARY`. See `.github/workflows/ci.yml` `frontend-test` job.
3. Any module below threshold causes vitest itself to exit non-zero, which fails
   the `frontend-test` CI job (Requirement 2.6).

## Adjusting the registry

To add or remove a module:

1. Edit the inline `HIGH_COVERAGE_CORE_THRESHOLDS` in **both** `vitest.config.ts`
   and `vite.config.ts`.
2. Update the table in this file.
3. Reference this file from the PR description.
