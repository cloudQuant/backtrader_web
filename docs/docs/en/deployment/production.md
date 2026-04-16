# Production Deployment

## Requirements

- **Server**: 2+ CPU cores, 4GB+ RAM
- **Database**: PostgreSQL 14+ or MySQL 8+
- **Redis**: 7+
- **SSL Certificate**: Let's Encrypt or commercial

## Security Checklist

- [ ] Change all default passwords
- [ ] Enable HTTPS with valid SSL certificate
- [ ] Configure firewall (allow 80, 443 only)
- [ ] Enable rate limiting
- [ ] Set up monitoring and alerts
- [ ] Configure log rotation
- [ ] Enable database backups

## Environment Configuration

### Database

```bash
# PostgreSQL
DATABASE_TYPE=postgresql
DATABASE_URL=postgresql+asyncpg://user:pass@prod-db:5432/backtrader

# MySQL
DATABASE_TYPE=mysql
DATABASE_URL=mysql+aiomysql://user:pass@prod-db:3306/backtrader
```

### Security

```bash
# Generate secure keys
SECRET_KEY=$(openssl rand -hex 32)
JWT_SECRET_KEY=$(openssl rand -hex 32)

# Production CORS
CORS_ORIGINS=https://your-domain.com
```

### Performance

```bash
# Workers (2x CPU cores)
WORKERS=4

# Timeout
TIMEOUT=300
```

## Nginx Configuration

For reverse proxy setup:

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }

    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
    }
}
```

## Monitoring

### Health Check

```bash
curl https://your-domain.com/health
```

### Metrics

Access Prometheus-format metrics at `/api/v1/monitoring/metrics`.

## Backup

### Database Backup

```bash
# PostgreSQL
pg_dump -h prod-db -U user backtrader > backup.sql

# MySQL
mysqldump -h prod-db -u user -p backtrader > backup.sql
```

### Automated Backup

Set up cron job for daily backups:

```bash
0 2 * * * /path/to/backup.sh
```

## Updates

```bash
# Pull latest
git pull origin main

# Rebuild
docker compose -f docker-compose.prod.yml build

# Restart
docker compose -f docker-compose.prod.yml up -d
```
