# Implementation Plan: Best Practices Improvement

## Overview

Systematic improvement of the Backtrader Web platform following industry best practices, organized into 4 phases with dependency ordering. Phase 1 (Quick Wins) establishes foundational tooling consistency; Phase 2 (CI Enhancement) builds on that to strengthen quality gates; Phase 3 (Infrastructure) adds development environment and observability; Phase 4 (Monitoring) adds security scanning and performance auditing.

## Tasks

- [x] 1. Phase 1: Quick Wins - Pre-Commit Sync & Security Scan
  - [x] 1.1 Update Pre-Commit Ruff version to match project
    - Update `.pre-commit-config.yaml` Ruff hook `rev` from `v0.8.6` to `v0.15.11`
    - Add comment above the repo entry explaining how to update: `pre-commit autoupdate --repo https://github.com/astral-sh/ruff-pre-commit`
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 1.2 Upgrade security scan to blocking gate in CI
    - Remove `continue-on-error: true` from `backend-security` job level and all its steps in `.github/workflows/ci.yml`
    - Create `scripts/bandit_gate.sh` that runs Bandit, parses JSON output, exits non-zero only for HIGH severity + MEDIUM/HIGH confidence issues, outputs LOW/MEDIUM as warnings
    - Update `backend-security` job to use `bandit_gate.sh` instead of raw bandit command
    - Move `backend-security` from Advisory to Blocker section in `ci-summary` job
    - Add `needs.backend-security.result == 'failure'` to the failure condition in ci-summary
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [x] 1.3 Migrate JWT library from python-jose to PyJWT
    - Replace `python-jose[cryptography]>=3.3.0` with `PyJWT[crypto]>=2.8.0` in `src/backend/pyproject.toml`
    - Update `[[tool.mypy.overrides]]` module list: replace `jose.*` with `jwt.*`
    - Modify `src/backend/app/utils/security.py`: replace `from jose import JWTError, jwt` with `import jwt` and `from jwt.exceptions import InvalidTokenError`
    - Update exception handling: catch `InvalidTokenError` instead of `JWTError`
    - Verify `create_access_token` and `decode_access_token` function signatures remain unchanged
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x]* 1.4 Write property test for JWT token round-trip
    - **Property 1: JWT Token Round-Trip**
    - Create `src/backend/tests/test_jwt_migration.py` with Hypothesis property test
    - Generate random payloads with `sub`, `username`, `token_type`, `exp` fields
    - Verify encode then decode produces identical `sub`, `username`, `token_type` values
    - Minimum 100 iterations
    - **Validates: Requirements 4.2, 4.3, 4.4**

  - [x] 1.5 Implement Markdown XSS sanitizer
    - Install `dompurify` (already in dependencies) and `marked` if not present
    - Create `src/frontend/src/utils/markdown-sanitizer.ts` with `renderMarkdown(raw, options?)` function
    - Configure DOMPurify with explicit `ALLOWED_TAGS` and `ALLOWED_ATTR` whitelist per design
    - Handle null/undefined input by returning empty string
    - _Requirements: 16.1, 16.2, 16.3_

  - [x]* 1.6 Write property test for XSS sanitization
    - **Property 4: XSS Sanitization Removes Dangerous Content**
    - Create `src/frontend/src/utils/__tests__/markdown-sanitizer.spec.ts` with fast-check property test
    - Generate HTML strings containing dangerous elements (script, iframe, object, embed, form, javascript: URIs, event handlers)
    - Verify output never contains dangerous elements while preserving safe Markdown content
    - Minimum 100 iterations
    - **Validates: Requirements 16.1, 16.2**

  - [x]* 1.7 Write unit tests for Markdown sanitizer (8+ XSS payload cases)
    - Add to `src/frontend/src/utils/__tests__/markdown-sanitizer.spec.ts`
    - Cover: script tag injection (2 cases), event handler injection (2 cases), protocol XSS javascript:/data: (2 cases), iframe embedding (2 cases)
    - _Requirements: 16.4_

- [x] 2. Checkpoint - Phase 1 verification
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Phase 2: CI Enhancement - Coverage, Mypy, ESLint, OpenAPI, Migrations
  - [x] 3.1 Raise coverage gate to 70% and add diff-cover
    - Update `src/backend/.coveragerc`: remove `app/services/workspace_service.py` and `app/services/sync_service.py` from both `[run] omit` and `[report] omit`
    - Update `.github/workflows/ci.yml` `backend-test` job: change `--cov-fail-under=50` to `--cov-fail-under=70`
    - Add `diff-cover` to `[dev]` dependencies in `src/backend/pyproject.toml`
    - Add diff-cover step in `backend-test` job: run `diff-cover coverage.xml --compare-branch=origin/master --fail-under=60`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [x] 3.2 Enable strict Mypy type checking in CI
    - Update `src/backend/pyproject.toml` `[tool.mypy]`: set `check_untyped_defs = true`
    - Add `[[tool.mypy.overrides]]` for `app.api.*` and `app.schemas.*` with `disallow_untyped_defs = true`
    - Add mypy step to `backend-lint` job in `.github/workflows/ci.yml`: `mypy app`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 3.3 Upgrade ESLint to v9 flat config
    - Create `src/frontend/eslint.config.js` with flat config including Vue 3, TypeScript, and existing custom rules
    - Delete `src/frontend/.eslintrc.cjs`
    - Update `src/frontend/package.json`: upgrade `eslint` to `^9.0.0`, upgrade `eslint-plugin-vue` and `@typescript-eslint/*` to v9-compatible versions
    - Update `lint` and `lint:fix` scripts in `package.json`: remove `--ext` parameter
    - Update `.github/workflows/ci.yml` `frontend-lint` job: remove `--ext` from eslint command
    - Update `.pre-commit-config.yaml` `frontend-eslint` hook: remove `--ext` parameter from entry command
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [x] 3.4 Add OpenAPI schema validation to CI
    - Create `scripts/export_openapi.py`: import FastAPI app, export OpenAPI JSON to file
    - Create `scripts/check_api_compat.py`: compare current vs base branch OpenAPI schema for breaking changes
    - Add `openapi-spec-validator` to `[dev]` dependencies in `src/backend/pyproject.toml`
    - Add `check-openapi` pre-flight job in `.github/workflows/ci.yml`: export schema, validate against OpenAPI 3.1, archive as artifact (7 days retention)
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x] 3.5 Enhance Alembic migration validation in CI
    - Create `src/backend/alembic/versions/001_baseline.py` baseline migration covering all existing ORM tables
    - Enhance `check-migrations` job in `.github/workflows/ci.yml`: add `alembic upgrade head` step (120s timeout) and `alembic check` step
    - Update `scripts/check_alembic_heads.py` to verify single head and unbroken chain
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

- [x] 4. Checkpoint - Phase 2 verification
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Phase 3: Infrastructure - Docker, Logging, Seed Data, OpenTelemetry
  - [x] 5.1 Create Docker development environment
    - Create `docker/backend.dev.Dockerfile` with Python 3.11, hot-reload support
    - Create `docker/frontend.dev.Dockerfile` with Node 20, Vite dev server
    - Create `docker/entrypoint-dev.sh` handling DB_AUTO_CREATE_SCHEMA, DB_AUTO_CREATE_DEFAULT_ADMIN, SEED_DATA env vars
    - Create `docker-compose.dev.yml` with backend, frontend, postgres services, volume mounts, healthchecks, configurable ports via LOCAL_BACKEND_PORT/LOCAL_FRONTEND_PORT/LOCAL_DB_PORT
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

  - [x] 5.2 Implement structured JSON logging
    - Enhance `src/backend/app/utils/logger.py`: update `_serialize_log` to output JSON with `timestamp` (ISO 8601 ms), `level`, `message`, `module`, `request_id` fields
    - Add `LOG_FORMAT` environment variable support in `src/backend/app/config.py`
    - Update `src/backend/app/middleware/logging.py`: ensure `request_id` (8-char hex) is generated per request, bound via loguru, and returned in `X-Request-ID` header
    - Implement fallback logic: LOG_FORMAT=json → JSON; DEBUG=true without LOG_FORMAT → colored text; DEBUG=false without LOG_FORMAT → JSON
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [x]* 5.3 Write property test for structured logging fields
    - **Property 2: Structured Logging Contains Required Fields**
    - Create `src/backend/tests/test_structured_logging.py` with Hypothesis property test
    - Generate random log messages (non-empty, up to 10000 chars) at all valid levels
    - Verify JSON output is parseable and contains all required fields with correct formats
    - Minimum 100 iterations
    - **Validates: Requirements 8.1, 8.2**

  - [x]* 5.4 Write property test for request ID generation
    - **Property 3: Request ID Generation**
    - Add to `src/backend/tests/test_structured_logging.py`
    - Generate random HTTP requests to non-skipped paths
    - Verify X-Request-ID header is exactly 8 characters of hex/base64-safe characters
    - Minimum 100 iterations
    - **Validates: Requirements 8.5**

  - [x] 5.5 Create development data seed script
    - Create `scripts/seed_dev_data.py`: generate 2+ users, 3+ strategies, 3+ backtest records, 2+ knowledge bases with documents
    - Support `--reset` flag to clear and regenerate
    - Implement idempotency: skip existing records, print skip/create counts per entity type
    - Handle database unavailability with stderr error message and non-zero exit
    - Complete within 30 seconds
    - Wire into `docker/entrypoint-dev.sh` via SEED_DATA=true env var
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7_

  - [x] 5.6 Move OpenTelemetry to core dependencies
    - Move all packages from `[otel]` optional group to core `dependencies` in `src/backend/pyproject.toml`
    - Remove the `[otel]` optional dependency group
    - Update `src/backend/app/telemetry.py`: remove ImportError fallback logic, add OTEL_ENABLED env var check (accepts true/1/yes case-insensitive)
    - When enabled: initialize TracerProvider, instrument FastAPI/SQLAlchemy/httpx, export via OTLP gRPC
    - When disabled: skip SDK initialization, zero overhead
    - Support OTEL_EXPORTER_OTLP_ENDPOINT (default localhost:4317) and OTEL_SERVICE_NAME (default backtrader-web-api)
    - Handle unreachable collector gracefully: log warning, continue serving
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6_

- [x] 6. Checkpoint - Phase 3 verification
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Phase 4: Monitoring & Security - Lighthouse, Dependency Scanning, Health Check
  - [x] 7.1 Add Lighthouse CI for frontend performance auditing
    - Create `lighthouserc.js` configuration targeting login page and a dashboard page
    - Add Lighthouse CI job to `.github/workflows/ci.yml`: run audits for Performance and Accessibility
    - Performance < 60 → warning annotation (non-blocking); Accessibility < 80 → job failure
    - Archive HTML reports as artifacts (7 days retention)
    - Add bundle size comparison step in `frontend-build` job: compare entry chunk vs target branch, warn if >10% growth
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_

  - [x] 7.2 Implement dependency locking and vulnerability scanning
    - Create `scripts/generate_lockfiles.sh` to generate `requirements-dev.lock` and `requirements-prod.lock`
    - Create `scripts/check_lockfile_sync.py` to compare `pip freeze` output against lockfile
    - Add lockfile sync check step to CI: run after pip install, fail if versions mismatch
    - Add `npm audit --audit-level=high` step to CI frontend job
    - Update `.github/workflows/nightly.yml`: add full npm audit + pip-audit scan, auto-create GitHub Issue for high/critical vulns not covered by existing issues in last 7 days
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

  - [x] 7.3 Implement health check endpoint CI validation
    - Update health check endpoint in `src/backend/app/api/` to return standardized response: `status`, `version`, `database`, `uptime` fields
    - Return HTTP 503 with `status: "unhealthy"` when database connection fails (>5s timeout)
    - Add health check validation step to `integration-test` job in `.github/workflows/ci.yml`: verify 200 status, JSON format, required fields, response time <2000ms
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5_

- [x] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation between phases
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Phase dependencies: Phase 2 requires Phase 1 completion (especially Req 5 before Req 1, 2, 7)
- Cross-phase dependencies: Req 3 → Req 12, Req 4 → Req 15, Req 8 → Req 14, Req 6 → Req 13, Req 6 → Req 15

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.5"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.6", "1.7"] },
    { "id": 2, "tasks": ["1.4"] },
    { "id": 3, "tasks": ["3.1", "3.2", "3.3", "3.4", "3.5"] },
    { "id": 4, "tasks": ["5.1", "5.2"] },
    { "id": 5, "tasks": ["5.3", "5.4", "5.5", "5.6"] },
    { "id": 6, "tasks": ["7.1", "7.2", "7.3"] }
  ]
}
```
