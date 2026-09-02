# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-09-02

### Added — Iteration 175 (Quality Hardening & Observability Depth)

- OpenTelemetry business-span coverage for four namespaces (`backtrader.backtest.*`, `backtrader.strategy.*`, `backtrader.ai.*`, `backtrader.live.*`) with 13 phase spans and `bt.*` business attributes; opt-in via `OTEL_ENABLED=true`, true-no-op cold path otherwise.
- Jaeger all-in-one service in `docker/compose/dev.yml` under `--profile observability` (OTLP gRPC 4317, HTTP 4318, UI 16686).
- Playwright `e2e/a11y/` suite for 7 Critical_Page_Set pages (axe-core WCAG 2.1 A/AA scan, blocks on critical/serious).
- Playwright `e2e/i18n/en-us-no-chinese.spec.ts` and `e2e/smoke-175/journeys.spec.ts` (5 user journeys).
- `scripts/dev/check_i18n_coverage.py` (strict + check-parity); `scripts/ci/check_orm_schema_drift.py` (blocking) and `scripts/ci/check_migration_safety.py` (advisory) for DB migration governance.
- `scripts/dev/check_all.sh` and root `pyproject.toml` `[tool.uv.workspace]` for monorepo entry-point.
- Five new CI jobs: `backend-mypy-services`, `frontend-a11y`, `frontend-i18n`, `frontend-e2e-smoke`, `monorepo-check` (advisory).
- New documentation: `docs/explanation/accessibility-baseline.md`, `docs/explanation/python-monorepo.md`, `docs/how-to/database-migration-playbook.md`, `docs/reference/frontend-bundle-budget.md`.
- `business_span()` helper in `app/utils/tracing.py` and 8 unit tests (`tests/test_telemetry_e2e.py` 8/8 green).

### Changed — Iteration 175

- Frontend coverage thresholds raised to lines/functions/branches/statements ≥ 75% (global) and ≥ 90% (8 High_Coverage_Core modules).
- Lighthouse `categories:accessibility` threshold raised from 0.8 → 0.9 across 7 pages.
- Vite `manualChunks` split into 5 vendor chunks (`element-plus`, `vue-router`, `pinia`, `echarts`, `monaco-editor`).
- `scripts/ci/check_bundle_size.sh` enforces entry chunk gzip ≤ 300 KB and login-route non-vendor JS ≤ 4 (blocking).
- `mypy` strict scope expanded to 3 services subpackages (`optimization`, `log_parser`, `ai_trading`).
- `iterations/README.md` updated; 173B disposition formalised in `docs/iterations/迭代175-质量加固与可观测性纵深/173B_disposition.md` (T2/T7/T10 all deferred to 176).
- Modernized the backend analytics integration for Fincore 0.5, preserving manual fallbacks and explicit per-metric provenance where a Fincore operation is not applicable.
- Hardened PostgreSQL initialization for legacy uppercase enum labels without applying text functions to native enum columns.
- Retired the legacy workstation release script so it cannot bypass the protected-tag, artifact-only release workflow.

### Notes — Iteration 175 deferrals

- Six remaining `app.services.*` subpackages and a11y/i18n content-side cleanups deferred to iteration 176 — see `docs/iterations/迭代175-质量加固与可观测性纵深/RETROSPECTIVE.md` and `docs/explanation/REFACTORING_BACKLOG.md` § "176 候选".

## [0.2.0-rc1] - 2026-05-24

### Added

- Strategy trust kernel for backtest results, including strategy scoring, overfitting diagnostics, and strategy explanation surfaces.
- Overfitting detection support for Walk-forward, Out-of-Sample, and Monte Carlo methods with frontend evidence cards and rerun controls.
- API performance baselines with `pytest-benchmark` for login, strategy listing, backtest submission/result retrieval, RAG search, and KB Chat roundtrip.
- Backtest task throughput baselines for five-strategy submission, status polling, and submit-and-poll roundtrip.
- Docker Hub release workflow for tag-triggered backend/frontend image publishing.
- v0.2.0 RC release notes in `docs/RELEASE_NOTES_V0.2.0.md`.

### Changed

- Split large backend services by extracting workspace lifecycle/unit/optimization helpers and manual gateway helper/IB Client Portal modules while preserving compatibility facades.
- Split large frontend views into focused AI chat and workspace components plus rendering composables.
- Raised frontend coverage thresholds to lines/statements `34%`, functions `40%`, and branches `45%`.
- Extended backend B904 and mypy ratchets to selected service/API scopes.
- Updated README coverage target tables and v0.2.0 RC quick-start guidance.

### Quality

- Documented API and backtest throughput baselines in `docs/perf-baseline-v0.2.0.md`.
- Added `pytest-benchmark` to backend development dependencies and registered the `performance` pytest marker.
- Fixed AppLayout test stubs for current Element Plus icon, drawer, dropdown, and theme-switching behavior.

### Known Boundaries

- This is a release candidate, not the final v0.2.0 production release.
- Performance baselines measure API, database, serialization, and task orchestration overhead; they do not run real strategy subprocesses.
- AI observability, multi-model routing, VaR/CVaR, factor analytics, performance attribution, and market-regime detection remain planned for later v0.2.x iterations.
- Docker Hub publishing requires `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` GitHub secrets.

## [0.1.0] - 2026-05-20

### Breaking Changes

- **Removed deprecated API endpoints:**
  - `/api/v1/backtest/*` (use `/api/v1/backtests/*`)
  - `/api/v1/live-trading-crypto/*` (use `/api/v1/live-trading/*`)
  - `/api/v1/backtests/optimization/grid` (use `/api/v1/optimization/submit`)
  - `/api/v1/backtests/optimization/bayesian` (use `/api/v1/optimization/submit`)
- Removed `DeprecationHeadersMiddleware` (no longer needed)

### Added

- Database performance indexes for backtest_tasks, optimization_tasks, paper_trading_orders
- API performance monitoring middleware with X-Process-Time header
- Slow request logging (>500ms threshold)
- Knowledge base retrieval settings with quant-oriented defaults for hybrid search, context window size, query threshold, and conversation-memory behavior
- Retrieval diagnostics in RAG / KB Chat responses, including actual search query, retrieval profile, search mode, history usage, and index coverage ratio
- Conversation-aware query rewriting for follow-up questions so AI chat can reuse recent user intent and cited document titles
- Knowledge base UI controls for editing retrieval profile, search mode, top_k, min similarity, context chunk budget, and prompt suffix
- AI chat UI panels for retrieval diagnostics and current knowledge-base retrieval profile visibility
- AI trading logs table with full audit trail (migration 0005)
- Composite listing indexes for backtest task queries (migration 0004)
- Trading workspace fields for enhanced workspace management (migration 0003)

### Changed

- Unified Alembic migration chain (fixed dual-head branch issue)
- Optimized slow request threshold from 5s to 500ms
- Updated frontend dependencies: axios, dayjs, dompurify, autoprefixer
- Upgraded the RAG scorer from a single keyword hit ratio to a configurable hybrid ranking pipeline that combines title hits, content hits, phrase overlap, recency reranking, and per-document diversification
- Strengthened AI Copilot prompt orchestration for quant research, strategy review, and Backtrader code generation with explicit assumptions, risk, data, and backtest sections
- KB Chat now inherits retrieval behavior from per-knowledge-base settings instead of hard-coded `top_k=10` / `min_similarity=0`
- Backtrader strategy generation prompts now target the full `AIStrategyDraft` schema, including assumptions, risk points, data source hints, backtest defaults, and execution plan

### Removed

- `app/api/backtest.py` — legacy singular backtest routes
- `app/api/live_trading.py` — legacy crypto trading routes
- `app/api/live_trading_complete.py` — orphaned Cerebro-based API
- `app/middleware/deprecation.py` — deprecation headers middleware
- Legacy optimization proxy functions from `backtest_enhanced.py`

## [1.0.0] - 2026-03-26

### Added

#### Core Features

- **Backtest Engine**: Full Backtrader integration with async execution
- **Strategy Management**: Create, edit, delete, version control for strategies
- **Parameter Optimization**: Grid search and Bayesian optimization support
- **Paper Trading**: Simulated trading with real-time data
- **Live Trading**: MT5/CTP exchange integration with gateway management
- **Analytics Dashboard**: Performance metrics, equity curves, drawdown analysis
- **Real-time Monitoring**: WebSocket-based live updates

#### Backend Architecture

- FastAPI async REST API with JWT authentication
- SQLAlchemy 2.0 async ORM with repository pattern
- RBAC permission system (admin/user roles)
- Strategy sandbox execution for security
- Alembic database migrations
- Multi-database support (SQLite/PostgreSQL/MySQL)

#### Frontend Features

- Vue 3 + TypeScript + Vite SPA
- Element Plus UI components
- ECharts visualization (K-lines, equity curves, metrics)
- Monaco Editor for strategy code editing
- Pinia state management
- i18n internationalization (Chinese/English)

#### Testing & Quality

- 1785+ backend unit tests with 86%+ coverage
- Playwright E2E tests (5 browser targets)
- Ruff linting (line-length=100)
- TypeScript strict mode
- Pre-commit hooks

#### CI/CD Pipeline

- GitHub Actions CI with lint, test, security scan
- Nightly test runs with coverage badges
- PR automation with review checklists
- Preview deployments

### Security

- JWT token-based authentication
- Password hashing with bcrypt
- Strategy code sandboxing
- Input validation with Pydantic
- CORS configuration
- Rate limiting support

### Documentation

- API documentation (OpenAPI/Swagger)
- Architecture design document
- Development guide
- Strategy development guide
- Project context for AI agents

---

## Version History Summary

| Version | Date | Key Changes |
|---------|------|-------------|
| 0.2.0 | 2026-09-02 | General availability: Iteration 175 hardening, Fincore 0.5 compatibility, and release guardrails |
| 0.2.0-rc1 | 2026-05-24 | AI trust kernel, engineering debt reduction, performance baselines, Docker release workflow |
| 1.0.0 | 2026-03-26 | Initial stable release |
| 0.9.0 | 2026-03-20 | Live trading integration |
| 0.8.0 | 2026-03-15 | Paper trading system |
| 0.7.0 | 2026-03-10 | Parameter optimization |
| 0.6.0 | 2026-03-05 | Analytics dashboard |
| 0.5.0 | 2026-02-28 | Strategy management |
| 0.4.0 | 2026-02-20 | Backtest engine |
| 0.3.0 | 2026-02-15 | Authentication system |
| 0.1.0 | 2026-02-01 | Project scaffolding |

---

For detailed commit history, see [GitHub Releases](https://github.com/user/ai-for-investor/releases).
