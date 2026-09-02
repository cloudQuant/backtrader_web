# AI for Investor v0.2.0 Release Notes

> Release: `v0.2.0`
> Status: source release promotion; tag and GitHub Release publication remain a separately authorized protected-tag operation
> Date: 2026-09-02

## Release theme

v0.2.0 consolidates the completed 166-169 release-train work with the latest Fincore compatibility updates:

- **Iteration 166: AI trust kernel** — make AI-generated and AI-reviewed strategies easier to evaluate.
- **Iteration 169: engineering sustainability** — reduce large-file risk, extend ratchets, establish performance baselines, and prepare release infrastructure.

Iterations 167 and 168 remain in the v0.2.x release train roadmap. Their AI observability, multi-model routing, VaR/CVaR, factor, attribution, and market-regime work is intentionally not marketed as shipped in v0.2.0.

## Highlights shipped in v0.2.0

### AI strategy trust kernel

- Strategy scoring service and API are available for backtest results.
- Backtest result pages integrate a strategy score card with radar-style breakdown and evidence details.
- Overfitting detection supports Walk-forward, Out-of-Sample, and Monte Carlo methods.
- Overfitting diagnostics include method-level evidence, rerun controls, and task progress handling.
- Strategy explanation combines static AST analysis with LLM JSON explanation when configured, plus static fallback when AI is unavailable.

### Knowledge base and AI Copilot hardening

- RAG and KB Chat responses expose diagnostic reason codes and messages.
- AIChat shows diagnostic banners, safer citation fallback, and unindexed-document guidance.
- Strategy drafts can be saved, added to a workspace, backtested, and reviewed through the Copilot flow.

### Engineering debt reduction

- `workspace_service.py` was sliced into smaller workspace modules while preserving service facade behavior.
- `manual_gateway_service.py` was sliced into helper and IB Client Portal modules while preserving compatibility.
- `AIChatPage.vue` and `TradingWorkspaceUnitsTab.vue` were split into display components and composables.
- B904 and mypy ratchets were extended to selected backend service/API scopes.

### Performance and quality baselines

- API performance baselines were added with `pytest-benchmark` for login, strategy list, backtest submission/result retrieval, RAG search, and KB chat roundtrip.
- Backtest task throughput baselines were added for five-strategy submission, status polling, and submit-and-poll roundtrip.
- Baseline results are documented in `perf-baseline-v0.2.0.md`.
- Frontend coverage thresholds increased to lines/statements `34%`, functions `40%`, and branches `45%`.

### Release infrastructure

- `.github/workflows/docker-publish.yml` validates that a protected version tag points exactly to the current `master` commit, then builds non-published backend and frontend artifacts with retained metadata.
- The workflow deliberately has no registry credentials and does not push images.
- `scripts/ops/release.sh` is retired as a mutation-capable local release path; release promotion proceeds through `release/vX.Y.Z` pull requests and the protected-tag workflow.

### Fincore 0.5 compatibility

- The backend uses Fincore 0.5 domain metrics on Python 3.11+ while retaining explicit manual fallbacks for unsupported metrics and Python 3.10.
- Returns are normalized at the analytics adapter boundary, and metric provenance remains visible to callers.
- PostgreSQL startup handles legacy uppercase native-enum labels through enum-value migration rather than applying `LOWER()` to the enum column.

## Release artifacts and tagging

This promotion does not create a Git tag, publish images, or create a GitHub Release. Those actions must be performed later by an authorized release manager after `master` contains the exact candidate commit.

The artifact workflow requires a protected `v0.2.0` tag resolving exactly to `master`; it produces local image IDs and release metadata only. It neither logs in to a registry nor claims registry digests.

## Validation checklist

Backend targeted validation:

```bash
cd src/backend
ruff check tests/perf/test_api_performance.py tests/perf/test_backtest_throughput.py pyproject.toml
pytest tests/perf/ -q --tb=short
```

Frontend targeted validation:

```bash
cd src/frontend
npx eslint src/test/components/common/AppLayout.test.ts vitest.config.ts
npm run test -- --run src/test/components/common/AppLayout.test.ts
npm run test -- --run --coverage
```

Release documentation validation:

```bash
python scripts/check_doc_links.py
```

Docker dry-run build, without pushing:

```bash
docker build -f src/backend/Dockerfile -t ai-for-investor-backend:v0.2.0-dryrun .
docker build -f src/frontend/Dockerfile -t ai-for-investor-frontend:v0.2.0-dryrun src/frontend
```

## Known boundaries

- API/backtest performance baselines intentionally avoid real strategy subprocess execution.
- This source promotion does not itself create the protected tag or a GitHub Release.
- The release-artifact workflow is artifact-only; production publication requires separately configured protected release controls.
- AI observability, multi-model routing, VaR/CVaR, factor analytics, performance attribution, and market regime detection are planned for later v0.2.x iterations.
- Full local Docker compose smoke testing requires production-grade secrets in environment variables; placeholder repository `.env` values must not be reused for production.
