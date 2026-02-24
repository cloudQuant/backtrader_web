# E2E Test Coverage Analysis Report

> Generated: 2026-02-24 | Project: backtrader_web

## 1. Executive Summary

The project has **3 independent E2E test suites** across different locations, totaling **~80 test cases**. Current coverage is **moderate** — most pages have basic load/visibility tests, but deep interaction flows (actual backtest execution, strategy CRUD completion, optimization workflow, report export) are largely missing or shallow.

**Overall E2E Coverage Score: ~45%**

| Dimension | Score | Notes |
|-----------|-------|-------|
| Page Load Coverage | 90% | Almost all routes tested for basic loading |
| User Flow Coverage | 30% | Only auth flow is end-to-end; others are shallow |
| API Integration Coverage | 15% | Very few tests verify actual API calls through UI |
| Error Handling Coverage | 10% | Minimal error path testing |
| Responsive Layout | 20% | Only backtest and data pages have viewport tests |

---

## 2. Test Suite Inventory

### Suite A: Frontend Playwright (TypeScript)
**Location:** `src/frontend/e2e/tests/`
**Framework:** Playwright + TypeScript
**Test Count:** 7 spec files, ~35 tests

| File | Tests | Scope |
|------|-------|-------|
| `smoke.spec.ts` | 2 | Playwright sanity check |
| `basic.spec.ts` | 7 | Page load for all main routes |
| `auth.spec.ts` | 7 | Login, register, form validation, storage state |
| `backtest.spec.ts` | 5 | Page load, form elements, strategy selector |
| `strategy.spec.ts` | 6 | Page load, tabs, create button, search |
| `live-trading.spec.ts` | 4 | Page load, title, buttons |
| `portfolio.spec.ts` | 4 | Page load, overview cards, tabs |

### Suite B: Python Playwright (pytest)
**Location:** `tests/e2e/`
**Framework:** Playwright (Python) + pytest
**Test Count:** 6 files, ~40 tests

| File | Tests | Scope |
|------|-------|-------|
| `test_auth.py` | 10 | Login, register, redirect, validation |
| `test_backtest.py` | 15 | Page load, form, history, navigation, responsive |
| `test_dashboard.py` | 12 | Stats cards, quick actions, sidebar nav, logout |
| `test_data.py` | 12 | Query form, data display, download, responsive |
| `test_settings.py` | 5 | User info, password change, about |
| `test_strategy.py` | 14 | Gallery, create dialog, templates, search, actions |

### Suite C: Standalone Script
**Location:** `tests/test_backtest_e2e.py`
**Framework:** Playwright (Python) standalone
**Test Count:** 1 full E2E flow

| Script | Scope |
|--------|-------|
| `test_backtest_e2e.py` | Login → Select Strategy → Run Backtest → Verify Results (complete flow) |

---

## 3. Route Coverage Matrix

### Frontend Routes (from `src/frontend/src/router/index.ts`)

| Route | Page | Suite A | Suite B | Suite C | Deep Flow |
|-------|------|---------|---------|---------|-----------|
| `/login` | LoginPage | ✅ | ✅ | ✅ | ✅ Auth flow |
| `/register` | RegisterPage | ✅ | ✅ | — | ✅ Register flow |
| `/` | Dashboard | ✅ | ✅ | — | ⚠️ Shallow |
| `/backtest` | BacktestPage | ✅ | ✅ | ✅ | ✅ Full run (Suite C only) |
| `/backtest/:id` | BacktestResultPage | ❌ | ❌ | ❌ | ❌ Not tested |
| `/optimization` | OptimizationPage | ❌ | ❌ | ❌ | ❌ Not tested |
| `/strategy` | StrategyPage | ✅ | ✅ | — | ⚠️ Dialog open only |
| `/data` | DataPage | ✅ | ✅ | — | ⚠️ No actual query |
| `/live-trading` | LiveTradingPage | ✅ | ❌ | — | ❌ No interaction |
| `/live-trading/:id` | LiveTradingDetailPage | ❌ | ❌ | ❌ | ❌ Not tested |
| `/portfolio` | PortfolioPage | ✅ | ❌ | — | ❌ No interaction |
| `/settings` | SettingsPage | ❌ | ✅ | — | ❌ No password change |

### Backend API Coverage via E2E

| API Group | Endpoints | Covered by E2E |
|-----------|-----------|----------------|
| **Auth** | register, login, login/refresh, me, change-password | ✅ register, login, me |
| **Backtest** | run, get result, status, list, cancel, delete | ⚠️ Only run (Suite C) |
| **Strategy** | CRUD, templates, template detail, readme, config | ⚠️ Only list/templates |
| **Optimization** | strategy-params, submit, progress, results | ❌ None |
| **Live Trading** | list, add, delete, get, start, stop, orders, positions | ❌ None |
| **Portfolio** | overview, positions, trades, equity-curve, allocation | ❌ None |
| **Data** | query market data | ❌ None |
| **Analytics** | dashboard stats | ⚠️ Implicit via dashboard |
| **Report Export** | HTML, PDF, Excel | ❌ None |
| **WebSocket** | backtest progress, realtime data | ❌ None |
| **Comparison** | compare backtests | ❌ None |
| **Monitoring** | alerts | ❌ None |

---

## 4. Critical Gaps (Priority-Ordered)

### 🔴 P0 — Missing Critical Flows

1. **Backtest Result Page (`/backtest/:id`)** — No tests for viewing completed backtest results, charts, metrics display
2. **Optimization Page (`/optimization`)** — Entire page untested (no load, no flow)
3. **Strategy CRUD Complete Flow** — Can open create dialog but never submits, no edit/delete verification
4. **Data Query Execution** — Form exists but never submits a query and verifies chart/table data

### 🟡 P1 — Missing Important Interactions

5. **Report Export** — No test for HTML/PDF/Excel download from backtest results
6. **Live Trading Detail (`/live-trading/:id`)** — No detail page test
7. **Live Trading Start/Stop** — No start/stop flow tested
8. **Password Change Flow** — Settings page loads but change-password never executed
9. **Backtest Cancel/Delete** — No cancellation or deletion tested
10. **WebSocket Real-time Updates** — No WebSocket message verification

### 🟢 P2 — Enhancement Opportunities

11. **Cross-browser Testing** — Only Chromium tested
12. **Accessibility Testing** — No a11y assertions
13. **Performance Metrics** — No LCP/FCP measurements
14. **Error Recovery** — Minimal offline/network error testing
15. **i18n Verification** — Chinese locale assumed but never tested programmatically
16. **Test Data Cleanup** — No teardown for created users/strategies

---

## 5. Test Quality Issues

| Issue | Severity | Details |
|-------|----------|---------|
| **Duplicate login in every test** | Medium | Suite A repeats login 30+ times; should use `storageState` |
| **`waitForTimeout` overuse** | Medium | Both suites rely on fixed delays instead of smart waits |
| **Weak assertions** | High | Many tests assert `"策略" in content` — too broad, won't catch regressions |
| **No test data isolation** | Medium | Tests share state (users, strategies), can interfere |
| **Two parallel suites** | Low | TS and Python suites overlap ~60%; consider consolidating |
| **Suite C standalone** | Low | `test_backtest_e2e.py` not integrated into pytest suite |

---

## 6. Recommended Improvements

### Phase 1: Quick Wins (1-2 days)
- [ ] Add `storageState` reuse to Suite A (eliminate repeated logins)
- [ ] Replace `waitForTimeout` with `waitForSelector` / `waitForURL` throughout
- [ ] Add `/optimization` page load test
- [ ] Add `/backtest/:id` result page test (navigate from backtest history)
- [ ] Integrate Suite C into pytest e2e suite

### Phase 2: Deep Flow Coverage (3-5 days)
- [ ] **Strategy CRUD flow**: Create → Verify in list → Edit → Delete → Verify removed
- [ ] **Data Query flow**: Enter symbol → Submit → Verify chart renders and table has rows
- [ ] **Backtest full flow** (in TS suite): Select strategy → Configure → Run → Wait → View results
- [ ] **Optimization flow**: Select strategy → Configure params → Submit → View progress → See results
- [ ] **Report Export flow**: Run backtest → Download HTML report → Verify content

### Phase 3: Robustness (ongoing)
- [ ] Network error handling tests for all pages
- [ ] Add responsive tests for all pages (mobile + tablet)
- [ ] Consolidate TS and Python suites into one canonical suite
- [ ] Add CI pipeline integration (GitHub Actions workflow exists in README but not wired)
- [ ] Test data factory + cleanup hooks

---

## 7. Metrics Summary

| Metric | Current | Target |
|--------|---------|--------|
| Total E2E tests | ~80 | 120+ |
| Routes covered (load) | 9/12 (75%) | 12/12 (100%) |
| Routes covered (deep flow) | 2/12 (17%) | 8/12 (67%) |
| API endpoints covered | 5/30+ (17%) | 15/30+ (50%) |
| Avg test execution time | ~3-5 min | <5 min |
| CI integration | ❌ No | ✅ Yes |
