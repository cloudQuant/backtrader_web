# Command Line Interface

## Backend CLI

### Start Server

```bash
cd src/backend
uvicorn app.main:app --reload --port 8000
```

### Options

| Option | Description |
|--------|-------------|
| `--host` | Host to bind (default: 0.0.0.0) |
| `--port` | Port to bind (default: 8000) |
| `--reload` | Enable auto-reload |
| `--workers` | Number of workers |

### Database Migrations

```bash
# Create migration
alembic revision --autogenerate -m "message"

# Upgrade
alembic upgrade head

# Downgrade
alembic downgrade -1
```

## Frontend CLI

### Development Server

```bash
cd src/frontend
npm run dev
```

### Build

```bash
npm run build
```

### Type Check

```bash
npm run typecheck
```

### Lint

```bash
npm run lint
```

## Scripts

### Environment Verification

```bash
./scripts/verify-dev-env.sh --preinstall
./scripts/verify-dev-env.sh --postinstall
```

### Docker Deployment

```bash
./scripts/certbot-init.sh     # Initialize SSL
./scripts/certbot-renew.sh    # Renew SSL
```

## Testing

### Backend Tests

```bash
cd src/backend
pytest

# With coverage
pytest --cov=app --cov-report=term

# Specific file
pytest tests/test_auth.py
```

### Frontend Tests

```bash
cd src/frontend
npm run test

# E2E tests
npm run test:e2e
```
