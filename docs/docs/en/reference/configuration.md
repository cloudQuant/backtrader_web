# Configuration

## Environment Variables

### Application

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | backtrader_web | Application name |
| `DEBUG` | false | Debug mode |
| `SECRET_KEY` | (required) | Flask secret key |
| `TZ` | Asia/Shanghai | Timezone |

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_TYPE` | sqlite | Database type |
| `DATABASE_URL` | sqlite://... | Connection URL |
| `DB_AUTO_CREATE_SCHEMA` | true | Auto-create schema |
| `DB_AUTO_CREATE_DEFAULT_ADMIN` | true | Auto-create admin |

### JWT Authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_SECRET_KEY` | (required) | JWT signing key |
| `JWT_ALGORITHM` | HS256 | Algorithm |
| `JWT_EXPIRE_MINUTES` | 10080 | Token TTL (7 days) |

### Server

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | 0.0.0.0 | Server host |
| `PORT` | 8000 | Server port |
| `CORS_ORIGINS` | * | CORS allowed origins |

### Admin User

| Variable | Default | Description |
|----------|---------|-------------|
| `ADMIN_USERNAME` | admin | Admin username |
| `ADMIN_PASSWORD` | (required) | Admin password |
| `ADMIN_EMAIL` | admin@example.com | Admin email |

### Backtest

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKTEST_TIMEOUT` | 300 | Timeout in seconds |

### Redis

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | redis://redis:6379/0 | Redis connection URL |

### AkShare (Market Data)

| Variable | Default | Description |
|----------|---------|-------------|
| `AKSHARE_SCHEDULER_TIMEZONE` | Asia/Shanghai | Scheduler timezone |
| `AKSHARE_SCRIPT_ROOT` | app/data_fetch/scripts | Scripts location |
| `AKSHARE_INTERFACE_BOOTSTRAP_MODE` | manual | Bootstrap mode |

## Configuration File

Alternatively, use `.env` file in `src/backend/`:

```bash
cp .env.example .env
```

## Production Configuration

```bash
# Security
SECRET_KEY=production-secret-key
JWT_SECRET_KEY=production-jwt-secret

# Database
DATABASE_TYPE=postgresql
DATABASE_URL=postgresql+asyncpg://user:pass@prod-host:5432/backtrader

# CORS
CORS_ORIGINS=https://your-domain.com
```
