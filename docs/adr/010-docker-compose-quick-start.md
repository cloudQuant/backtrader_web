# ADR-010: Docker Compose Quick Start with SQLite

**Status:** Accepted
**Date:** 2026-05-20
**Deciders:** cloud

## Context

The existing `docker-compose.prod.yml` requires MySQL, Redis, and multiple environment variables (`DB_PASSWORD`, `MYSQL_ROOT_PASSWORD`, `SECRET_KEY`, `JWT_SECRET_KEY`, `ADMIN_PASSWORD`). This is appropriate for production but creates a high barrier for first-time users who just want to evaluate the platform.

New users reported friction in the "clone → try" workflow because they had to:
1. Set up MySQL or PostgreSQL
2. Configure multiple required environment variables
3. Understand the multi-service architecture before seeing any results

## Decision

Create a minimal `docker-compose.yml` at the project root that:

1. **Uses SQLite** — zero external database dependency
2. **Hardcodes safe defaults** — pre-configured `SECRET_KEY`, `JWT_SECRET_KEY`, `ADMIN_PASSWORD` (with clear comments that these must be changed for production)
3. **Two services only** — backend + frontend (no MySQL, no Redis, no Certbot)
4. **Single command start** — `docker compose up -d` with no `.env` file required
5. **Named volume** for SQLite data persistence across container restarts
6. **Health check** on backend before frontend starts

The production compose (`docker-compose.prod.yml`) remains unchanged for real deployments.

## Consequences

### Positive

- New users can evaluate the platform with a single `docker compose up -d` command
- No external database setup required
- Reduces time-to-first-backtest from ~10 minutes to ~2 minutes (just waiting for image build)
- Clear separation: `docker-compose.yml` = evaluation, `docker-compose.prod.yml` = production

### Negative

- Hardcoded secrets in the quick-start compose could be accidentally used in production (mitigated by comments and documentation)
- SQLite doesn't support concurrent writes well — not suitable for multi-user evaluation
- Users might not realize they need to switch to the production compose for real use

### Neutral

- The quick-start compose uses the same Dockerfile as production (no separate dev image needed)
- Frontend nginx config proxies `/api` to the backend container (same as production)
