# ADR-008: Deprecated API Removal Strategy

**Status:** Accepted
**Date:** 2026-05-20
**Deciders:** cloud

## Context

The platform accumulated three sets of deprecated API endpoints from v1.0 development:
- `/api/v1/backtest/*` (singular) — superseded by `/api/v1/backtests/*` (plural)
- `/api/v1/live-trading-crypto/*` — superseded by `/api/v1/live-trading/*`
- `/api/v1/backtests/optimization/grid|bayesian` — superseded by `/api/v1/optimization/submit`

These deprecated endpoints were maintained with a multi-layer deprecation marking system (route-level `deprecated=True`, per-request headers via `mark_deprecated()`, and a global `DeprecationHeadersMiddleware`). This added maintenance burden, test complexity, and confusion for new developers.

## Decision

Remove all deprecated endpoints and their supporting infrastructure in a single clean-slate release (v0.1.0):

1. **Delete source files:** `app/api/backtest.py`, `app/api/live_trading.py`, `app/api/live_trading_complete.py`
2. **Remove from router:** Delete deprecated router registrations from `app/api/router.py`
3. **Remove middleware:** Delete `app/middleware/deprecation.py` and its registration in `main.py`
4. **Remove helper functions:** Delete `mark_deprecated()` and legacy optimization proxy functions
5. **Clean tests:** Delete test files for deprecated endpoints, update assertions that verified deprecation headers
6. **Document the change:** Update CHANGELOG, RELEASE_PLAN, and API documentation

The decision to remove all at once (rather than gradually) was made because:
- Frontend had already migrated to new endpoints (verified by code search)
- No external API consumers were identified (open-source project, pre-1.0)
- The deprecation headers had been in place for 3+ months
- Maintaining the compatibility layer was costing more than the migration benefit

## Consequences

### Positive

- ~500 lines of dead code removed
- No more `DeprecationHeadersMiddleware` overhead on every request
- Simpler router.py (no deprecated registrations)
- Test suite is smaller and faster (removed ~100 lines of deprecated endpoint tests)
- New developers see only the current API surface

### Negative

- Any undiscovered external consumers of deprecated endpoints will break (mitigated by RELEASE_PLAN migration guide)
- Cannot roll back without reverting to a previous branch

### Neutral

- `LiveTradingService` (Cerebro-based) is retained because `monitoring_service.py` still uses it for alert evaluation — this is a separate concern from the API layer
