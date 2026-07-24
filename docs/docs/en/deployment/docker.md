# Docker deployment

The Compose base file is `docker/docker-compose.yml` and must be used with one environment override under `docker/compose/`.

## Development

```bash
docker compose -f docker/docker-compose.yml -f docker/compose/dev.yml up
```

The development override starts PostgreSQL, backend, and frontend. It exposes backend `8000` and frontend `3000` by default. Adjust ports through variables such as `LOCAL_BACKEND_PORT`, `LOCAL_FRONTEND_PORT`, and `LOCAL_DB_PORT`.

## Production

1. Set required values in a protected deployment environment: `DB_PASSWORD`, `MYSQL_ROOT_PASSWORD`, `SECRET_KEY`, `JWT_SECRET_KEY`, and `ADMIN_PASSWORD`.
2. Set `DB_NAME`, `DB_USER`, `CORS_ORIGINS`, `HTTP_PORT`, `HTTPS_PORT`, persistent directories, and `WEB_CONCURRENCY` as needed.
3. Start and check status:

```bash
docker compose -f docker/docker-compose.yml -f docker/compose/prod.yml up -d
docker compose -f docker/docker-compose.yml -f docker/compose/prod.yml ps
curl http://localhost/health
```

The production override contains MySQL, Redis, backend, frontend, and an optional Certbot container. Persist and back up data, strategies, workspaces, and log directories.

## Common operations

```bash
# Logs
docker compose -f docker/docker-compose.yml -f docker/compose/prod.yml logs -f backend

# Stop while retaining volumes
docker compose -f docker/docker-compose.yml -f docker/compose/prod.yml down

# Render configuration to catch missing variables
docker compose -f docker/docker-compose.yml -f docker/compose/prod.yml config
```

Never bake `.env`, certificates, database exports, or gateway credentials into images or commit them to Git.
