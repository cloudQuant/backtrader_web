# AI for Investor v0.2.0 RC1 Release Notes

> Release candidate: `v0.2.0-rc1`
> Status: candidate build for validation, not the final v0.2.0 production release
> Date: 2026-05-24

## Release theme

v0.2.0 RC1 packages the first two completed stages of the 166-169 release train:

- **Iteration 166: AI trust kernel** — make AI-generated and AI-reviewed strategies easier to evaluate.
- **Iteration 169: engineering sustainability** — reduce large-file risk, extend ratchets, establish performance baselines, and prepare release infrastructure.

Iterations 167 and 168 remain in the v0.2.x release train roadmap. Their AI observability, multi-model routing, VaR/CVaR, factor, attribution, and market-regime work is intentionally not marketed as shipped in this RC.

## Highlights shipped in RC1

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

- Docker Hub publishing workflow is available in `.github/workflows/docker-publish.yml`.
- Tagging `v0.2.0-rc1` builds and pushes backend/frontend images when Docker Hub credentials are configured.
- Published image tags use both release tag and short commit SHA tags.

## Docker image publishing

Required GitHub secrets:

- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

Tag-triggered release:

```bash
git tag v0.2.0-rc1
git push origin v0.2.0-rc1
```

Expected images:

```text
docker.io/$DOCKERHUB_USERNAME/ai-for-investor-backend:v0.2.0-rc1
docker.io/$DOCKERHUB_USERNAME/ai-for-investor-frontend:v0.2.0-rc1
docker.io/$DOCKERHUB_USERNAME/ai-for-investor-backend:sha-<commit>
docker.io/$DOCKERHUB_USERNAME/ai-for-investor-frontend:sha-<commit>
```

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
docker build -f src/backend/Dockerfile -t ai-for-investor-backend:v0.2.0-rc1-dryrun .
docker build -f src/frontend/Dockerfile -t ai-for-investor-frontend:v0.2.0-rc1-dryrun src/frontend
```

## Known boundaries

- RC1 is not the final v0.2.0 production release.
- API/backtest performance baselines intentionally avoid real strategy subprocess execution.
- Docker Hub publishing requires repository secrets and only runs on release tags or manual dispatch.
- AI observability, multi-model routing, VaR/CVaR, factor analytics, performance attribution, and market regime detection are planned for later v0.2.x iterations.
- Full local Docker compose smoke testing requires production-grade secrets in environment variables; placeholder repository `.env` values must not be reused for production.
