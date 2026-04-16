# Docker Deployment

## Prerequisites

- Docker Engine 24+
- Docker Compose v2

## Quick Start

```bash
# Clone and configure
git clone https://github.com/cloudQuant/backtrader_web.git
cd backtrader_web

# Create environment file
cp src/backend/.env.example src/backend/.env
# Edit .env with your configuration

# Start services
docker compose -f docker-compose.prod.yml up -d
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| MySQL | 3306 | Database |
| Redis | 6379 | Cache |
| Backend | 8000 | API Server |
| Frontend | 80, 443 | Web UI + HTTPS |

## Environment Variables

### Required

```bash
# Database
DB_PASSWORD=your_db_password
MYSQL_ROOT_PASSWORD=your_root_password

# Security
SECRET_KEY=your-secret-key
JWT_SECRET_KEY=your-jwt-secret

# Admin
ADMIN_PASSWORD=your-admin-password
```

### Optional

```bash
# Ports
HTTP_PORT=80
HTTPS_PORT=443

# Database
DB_HOST=mysql
DB_PORT=3306
DB_NAME=backtrader_web
DB_USER=backtrader

# Redis
REDIS_DATA_DIR=./runtime/redis

# Logs
BACKEND_LOGS_DIR=./runtime/backend/logs
```

## SSL/HTTPS

### Let's Encrypt (Recommended)

```bash
# Initialize certificate
./scripts/certbot-init.sh

# Start with certificate
docker compose -f docker-compose.prod.yml up -d certbot
```

### Custom Certificate

Mount your certificate files:

```yaml
volumes:
  - /path/to/cert.pem:/etc/letsencrypt/live/aifortrader.cn/cert.pem
  - /path/to/key.pem:/etc/letsencrypt/live/aifortrader.cn/privkey.pem
```

## Data Persistence

Volumes for persistent data:

```yaml
volumes:
  - ./runtime/mysql:/var/lib/mysql    # Database
  - ./runtime/redis:/data              # Redis cache
  - ./runtime/certbot:/etc/letsencrypt  # SSL certificates
  - ./datas:/opt/workspace/backtrader_web/datas  # Market data
  - ./strategies:/opt/workspace/backtrader_web/strategies  # Strategies
```

## Health Checks

```bash
# Check service health
curl http://localhost/health

# View container status
docker compose -f docker-compose.prod.yml ps
```

## Troubleshooting

### Port Already in Use

```bash
# Check what's using port 80
lsof -i :80

# Change port in docker-compose.prod.yml
ports:
  - "8080:80"
```

### Database Connection Failed

```bash
# Check MySQL logs
docker compose logs mysql

# Verify credentials in .env
```
