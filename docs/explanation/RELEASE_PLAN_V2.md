# Release Plan: v0.1.0 — Initial Public Release

## 1. Release Overview

- **Target date:** 2026 Q2
- **Version:** 0.1.0
- **Type:** Initial public release
- **Theme:** First stable open-source release with clean API surface

This release removes all deprecated API endpoints that have been superseded by newer,
more consistent alternatives. Users must migrate to the new endpoints before upgrading.

---

## 2. Breaking Changes

### APIs to Remove

| Deprecated Endpoint | Replacement | Migration Guide |
|---|---|---|
| `POST /api/v1/backtest/run` | `POST /api/v1/backtests/run` | Change URL path |
| `GET /api/v1/backtest/` | `GET /api/v1/backtests/` | Change URL path |
| `GET /api/v1/backtest/{task_id}` | `GET /api/v1/backtests/{task_id}` | Change URL path |
| `GET /api/v1/backtest/{task_id}/status` | `GET /api/v1/backtests/{task_id}/status` | Change URL path |
| `POST /api/v1/backtest/{task_id}/cancel` | `POST /api/v1/backtests/{task_id}/cancel` | Change URL path |
| `DELETE /api/v1/backtest/{task_id}` | `DELETE /api/v1/backtests/{task_id}` | Change URL path |
| `POST /api/v1/backtests/optimization/grid` | `POST /api/v1/optimization/submit` | New request body format |
| `POST /api/v1/backtests/optimization/bayesian` | `POST /api/v1/optimization/submit` | New request body format |
| `POST /api/v1/live-trading-crypto/live/submit` | `POST /api/v1/live-trading/` | New request body format |
| `GET /api/v1/live-trading-crypto/live/tasks` | `GET /api/v1/live-trading/` | Change URL path |
| All `/api/v1/live-trading-crypto/*` | `/api/v1/live-trading/*` | See migration guide |

### Code Changes

- Remove `app/api/backtest.py` (legacy backtest router)
- Remove `app/api/live_trading.py` (legacy crypto trading router)
- Remove deprecated optimization endpoints from `app/api/backtest_enhanced.py`
- Remove `DeprecationHeadersMiddleware` (no longer needed)
- Update `app/api/router.py` to remove deprecated router registrations

---

## 3. Migration Guide for Users

### Step 1: Update API URLs

Replace all deprecated endpoint URLs with their new equivalents (see table above).

All singular `/backtest/` paths become plural `/backtests/`. All `/live-trading-crypto/`
paths become `/live-trading/`.

### Step 2: Update Request Bodies

For optimization endpoints, the new format uses a unified `POST /api/v1/optimization/submit`
with a `method` field:

```json
{
  "strategy_id": "...",
  "method": "grid",
  "param_ranges": {
    "fast_period": {"min": 5, "max": 20, "step": 5},
    "slow_period": {"min": 20, "max": 60, "step": 10}
  }
}
```

For Bayesian optimization, change the `method` field:

```json
{
  "strategy_id": "...",
  "method": "bayesian",
  "param_ranges": {
    "fast_period": {"min": 5, "max": 20},
    "slow_period": {"min": 20, "max": 60}
  }
}
```

### Step 3: Update Live Trading

The new `/api/v1/live-trading/` endpoint supports all broker types (crypto, futures, stocks)
through a unified interface. Specify the broker type in the request body:

```json
{
  "strategy_id": "...",
  "broker_type": "crypto",
  "broker_config": {
    "exchange": "binance",
    "api_key": "...",
    "api_secret": "..."
  }
}
```

---

## 4. Pre-Release Checklist

- [x] All deprecated endpoints removed
- [x] Migration guide published (this document)
- [x] All tests pass without deprecated code
- [x] Frontend updated to use new endpoints only
- [x] CHANGELOG.md updated
- [x] Version bumped to 0.1.0
- [x] Alembic migration chain unified (single head)
- [ ] Docker images tested and optimized
- [ ] GitHub Release created with full release notes
- [ ] Documentation updated (API.md, API_OVERVIEW.md)

---

## 5. Timeline

| Week | Task | Status |
|------|------|--------|
| Week 1 | Publish migration guide, announce deprecation timeline | ✅ |
| Week 2 | Remove deprecated backend code, update tests | ✅ |
| Week 3 | Update frontend to use new endpoints only | ✅ (already migrated) |
| Week 4 | v2.0.0-beta release, community testing | ⬜ |
| Week 5 | Bug fixes from beta feedback | ⬜ |
| Week 6 | v2.0.0 stable release | ⬜ |

---

## 6. Rollback Plan

If critical issues are found after release:

1. Revert to v1.x branch
2. Re-enable deprecated endpoints as compatibility layer
3. Publish hotfix with extended deprecation timeline

---

## 7. Communication Plan

- [ ] Blog post announcing v2.0.0 timeline (4 weeks before)
- [ ] GitHub Discussion thread for migration questions
- [ ] In-app notification for users still using deprecated endpoints
- [ ] Email notification to registered users (if applicable)
