# Production Deployment Guide

This guide covers deploying the Backtrader Web platform to a production server.

## System Requirements

### Server Requirements

- **OS**: Ubuntu 20.04+ or CentOS 8+
- **CPU**: 2+ cores recommended
- **Memory**: 4GB+ RAM recommended
- **Disk**: 20GB+ SSD recommended
- **Network**: Stable internet connection

### Software Requirements

- Python 3.8+
- PostgreSQL 13+ (production) or SQLite (development)
- Nginx 1.18+ (for reverse proxy)
- Certbot (for TLS certificates)

## Deployment Steps

### 1. System Preparation

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install Python and development tools
sudo apt install -y python3 python3-pip python3-venv git nginx

# Install PostgreSQL (optional, for production)
sudo apt install -y postgresql postgresql-contrib
```

### 2. Create Deployment User

```bash
# Create dedicated user for the application
sudo useradd -m -s /bin/bash backtrader
sudo passwd backtrader

# Add to sudo group for initial setup (optional)
sudo usermod -aG sudo backtrader
```

### 3. Deploy Application

```bash
# Switch to deployment user
sudo su - backtrader

# Clone repository
cd /opt
sudo git clone https://github.com/your-org/backtrader_web.git
sudo chown -R backtrader:backtrader backtrader_web
cd backtrader_web

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
cd src/backend
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
# Create production environment file
cat > .env << 'EOF'
DATABASE_TYPE=postgresql
DATABASE_URL=postgresql+asyncpg://backtrader:PASSWORD@localhost/backtrader
SECRET_KEY=$(openssl rand -hex 32)
JWT_SECRET_KEY=$(openssl rand -hex 32)
DEBUG=false
JWT_EXPIRE_MINUTES=1440
CORS_ORIGINS=https://your-domain.com
EOF

# Secure the environment file
chmod 600 .env
```

### 5. Configure PostgreSQL (Optional)

```bash
# Create database and user
sudo -u postgres psql << 'EOF'
CREATE DATABASE backtrader;
CREATE USER backtrader WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE backtrader TO backtrader;
\q
EOF

# Run migrations (if using Alembic)
cd src/backend
alembic upgrade head
```

### 6. Configure systemd Service

Create `/etc/systemd/system/backtrader.service`:

```ini
[Unit]
Description=Backtrader Web Backend
After=network.target postgresql.service

[Service]
Type=simple
User=backtrader
Group=backtrader
WorkingDirectory=/opt/backtrader_web/src/backend
Environment="PATH=/opt/backtrader_web/venv/bin"
ExecStart=/opt/backtrader_web/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable backtrader
sudo systemctl start backtrader
sudo systemctl status backtrader
```

### 7. Configure Supervisor (Alternative)

Create `/etc/supervisor/conf.d/backtrader.conf`:

```ini
[program:backtrader]
command=/opt/backtrader_web/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
directory=/opt/backtrader_web/src/backend
user=backtrader
autostart=true
autorestart=true
stderr_logfile=/var/log/backtrader.err.log
stdout_logfile=/var/log/backtrader.out.log
```

Enable and start:

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start backtrader
```

### 8. Configure Nginx Reverse Proxy

Create `/etc/nginx/sites-available/backtrader`:

```nginx
upstream backtrader_backend {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name your-domain.com;

    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # TLS Configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256...';

    # Security Headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";

    location / {
        proxy_pass http://backtrader_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location /ws/ {
        proxy_pass http://backtrader_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

Enable and restart Nginx:

```bash
sudo ln -s /etc/nginx/sites-available/backtrader /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 9. Configure TLS/HTTPS with Let's Encrypt

```bash
# Install Certbot
sudo apt install -y certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal is configured automatically
sudo certbot renew --dry-run
```

### 10. Configure Firewall

```bash
# Configure UFW (Uncomplicated Firewall)
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
sudo ufw status
```

### 11. Configure Log Rotation

Create `/etc/logrotate.d/backtrader`:

```
/var/log/backtrader/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 backtrader backtrader
    sharedscripts
    postrotate
        systemctl reload backtrader > /dev/null 2>&1 || true
    endscript
}
```

## Security Checklist

- [ ] Change default passwords
- [ ] Set strong SECRET_KEY and JWT_SECRET_KEY
- [ ] Enable HTTPS/TLS
- [ ] Configure firewall
- [ ] Set up database backups
- [ ] Disable DEBUG mode
- [ ] Configure CORS properly
- [ ] Set up log monitoring
- [ ] Configure rate limiting
- [ ] Regular security updates

## Performance Tuning

### Database Optimization

```bash
# PostgreSQL configuration (postgresql.conf)
shared_buffers = 256MB
effective_cache_size = 1GB
maintenance_work_mem = 64MB
checkpoint_completion_target = 0.9
wal_buffers = 16MB
default_statistics_target = 100
```

### Application Optimization

- Use Gunicorn with multiple workers for production
- Enable Redis caching for frequently accessed data
- Configure connection pooling
- Enable response compression

## Health Check

Verify deployment:

```bash
# Check service status
sudo systemctl status backtrader

# Check API health
curl http://localhost:8000/api/v1/monitoring/health

# Check logs
sudo journalctl -u backtrader -f
```

## Backup Strategy

### Database Backup

```bash
# Daily backup script
cat > /opt/backup-backup.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
pg_dump -U backtrader backtrader | gzip > /backups/backtrader_$DATE.sql.gz
find /backups -name "backtrader_*.sql.gz" -mtime +30 -delete
EOF

chmod +x /opt/backup-backup.sh

# Add to crontab
crontab -e
# Add: 0 2 * * * /opt/backup-backup.sh
```

### Application Backup

```bash
# Backup strategy files and configurations
tar -czf /backups/backtrader-config-$(date +%Y%m%d).tar.gz \
    /opt/backtrader_web/.env \
    /opt/backtrader_web/src/strategies/
```

## Troubleshooting

### Service Won't Start

```bash
# Check service logs
sudo journalctl -u backtrader -n 50

# Check application logs
tail -f /var/log/backtrader/out.log

# Verify configuration
sudo systemd-analyze verify backtrader.service
```

### Database Connection Issues

```bash
# Check PostgreSQL status
sudo systemctl status postgresql

# Verify connectivity
psql -U backtrader -d backtrader -h localhost
```

### Nginx Issues

```bash
# Test Nginx configuration
sudo nginx -t

# Check error logs
sudo tail -f /var/log/nginx/error.log
```

## Next Steps

After deployment:

1. Monitor system performance
2. Set up alerting
3. Configure regular backups
4. Plan for scaling
5. Review [Operations Guide](OPERATIONS.md)
