# Deployment

Before deploying, assign owners for the application database, market warehouse, secrets, CORS, backups, logs, and gateway privileges. Production must not inherit development passwords or automatic-bootstrap flags.

## Deployment modes

| Scenario | Command |
| --- | --- |
| Local development | Backend `uvicorn app.main:app --reload --port 8000`; frontend `npm run dev` |
| Docker development | `docker compose -f docker/docker-compose.yml -f docker/compose/dev.yml up` |
| Docker production | `docker compose -f docker/docker-compose.yml -f docker/compose/prod.yml up -d` |
| Container deployment using host MySQL | `docker compose -f docker/docker-compose.yml -f docker/compose/local.yml up -d` |

## Pre-release checklist

- Replace `SECRET_KEY`, `JWT_SECRET_KEY`, admin password, and database passwords with deployment-specific high-entropy values.
- Allow CORS only for intended frontend origins; do not use broad production CORS.
- Verify `/health` and `/api/v1/health`, plus dependency-service health checks.
- Define backups, restore drills, and least-privilege accounts for both application and market databases.
- Set budget, audit, network-egress, and human-approval boundaries for AI, synchronization, and gateways.

- [Docker deployment](./docker.md)
- [Production](./production.md)
