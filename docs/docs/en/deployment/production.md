# Production

## Operating principle

Production aims for recoverability, auditability, and least privilege—not exposing a development environment to the internet. Application data, the market warehouse, AI providers, and trading gateways require separate access controls, backups, and owners.

## Minimum checklist

- [ ] Use a dedicated MySQL/PostgreSQL application database and complete backup/restore drills.
- [ ] Give the market-data warehouse a separate connection, read/write grants, and retention policy.
- [ ] Supply `SECRET_KEY`, `JWT_SECRET_KEY`, database passwords, and gateway credentials through a secrets manager or protected environment variables.
- [ ] Pin `CORS_ORIGINS`, terminate TLS at a reverse proxy, and restrict administrative access.
- [ ] Disable development bootstrap such as `DB_AUTO_CREATE_SCHEMA` and `DB_AUTO_CREATE_DEFAULT_ADMIN`.
- [ ] Define log retention, monitoring, alerts, AI-cost budgets, data-source incident response, and human gateway approval.

## Health and upgrades

```bash
curl -fsS http://localhost/health
curl -fsS http://localhost:8000/api/v1/health

docker compose -f docker/docker-compose.yml -f docker/compose/prod.yml pull
docker compose -f docker/docker-compose.yml -f docker/compose/prod.yml up -d
docker compose -f docker/docker-compose.yml -f docker/compose/prod.yml ps
```

Before an upgrade, back up databases, strategies, workspaces, and runtime logs. Afterwards, run health, login-smoke, warehouse-access, and controlled-backtest checks. Roll back to a verified image and a rehearsed restore point if anything is abnormal.

## AI and trading boundaries

- Route AI calls through approved providers with timeout, budget, and audit controls; never log raw secrets.
- Apply sensitive-information checks and authorization isolation to production knowledge-base uploads.
- Separate gateway credentials and real-trading authority from normal application accounts. Default to simulation/isolated validation, human approval, and risk limits.

See [Docker deployment](./docker.md) for Compose variables and container operations.
