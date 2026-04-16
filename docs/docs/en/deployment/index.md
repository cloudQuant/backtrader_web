# Deployment

## Deployment Options

### Development

For local development with hot-reload:

```bash
# Backend
cd src/backend
uvicorn app.main:app --reload --port 8000

# Frontend
cd src/frontend
npm run dev
```

### Docker Deployment

For production deployment using Docker:

```bash
# Build and start
docker compose -f docker-compose.prod.yml up -d

# View logs
docker compose -f docker-compose.prod.yml logs -f

# Stop
docker compose -f docker-compose.prod.yml down
```

## Guides

- [Docker Deployment](./docker.md) - Docker and Docker Compose setup
- [Production](./production.md) - Production environment configuration
