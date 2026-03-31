# Operations Guide

This guide covers system administration, maintenance, and troubleshooting for the Backtrader Web platform.

## Task Execution Model and Multi-Instance Limits

### 当前架构说明

- **回测任务**：任务状态持久化在数据库中，但实际执行由当前 API 进程在本地调度（`asyncio.create_task`）。
- **参数优化任务**：任务状态与结果已落库（`optimization_tasks` 表），进程重启后可通过 DB 恢复；取消会写入 DB，其他实例轮询 DB 可感知取消并停止。
- **取消操作**：回测取消仅对当前实例有效；优化任务取消会持久化到 DB，执行线程轮询 DB 可跨实例生效。

**重要**：回测仍为单实例取消语义；参数优化已支持多实例取消（通过 DB 状态同步）。

### 部署建议

| 部署模式 | 支持情况 | 说明 |
|----------|----------|------|
| 单实例单进程 | ✅ 推荐 | 回测取消、优化任务可预期 |
| 多 worker (同机) | ⚠️ 部分支持 | 回测取消可能失败；优化取消通过 DB 可跨 worker 生效 |
| 多实例 (水平扩展) | ⚠️ 部分支持 | 回测取消仅对所在实例有效；优化任务可落库、取消可跨实例 |

### 演进方向

如需多实例可靠取消与任务持久化，建议引入 Redis/RabbitMQ 任务队列，由独立 worker 进程执行任务。

## Health Monitoring

### Health Check Endpoints

The application provides several health check endpoints:

```bash
# Basic health check
curl http://localhost:8000/api/v1/monitoring/health

# Detailed metrics
curl http://localhost:8000/api/v1/monitoring/metrics
```

**Health Response:**

```json
{
  "status": "healthy",
  "database": "connected",
  "cache": "connected",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

### Monitoring Commands

```bash
# Check service status
sudo systemctl status backtrader

# Check resource usage
htop

# Check disk space
df -h

# Check memory usage
free -h

# Check process status
ps aux | grep uvicorn
```

## Logging

### Log Locations

| Component | Location | Description |
|------------|----------|-------------|
| Application | `/var/log/backtrader/` | Application logs |
| System (systemd) | `journalctl -u backtrader` | Service logs |
| Nginx | `/var/log/nginx/` | Web server logs |
| PostgreSQL | `/var/log/postgresql/` | Database logs |

### Log Levels

Configure in `.env`:

```ini
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL
SQL_ECHO=false  # Enable SQL query logging
```

### Viewing Logs

```bash
# Real-time application logs
tail -f /var/log/backtrader/out.log

# Systemd service logs
sudo journalctl -u backtrader -f

# Last 100 lines
sudo journalctl -u backtrader -n 100

# Logs since boot
sudo journalctl -u backtrader -b
```

### Log Rotation

Configuration file: `/etc/logrotate.d/backtrader`

```bash
# Test log rotation
sudo logrotate -d /etc/logrotate.d/backtrader

# Force rotation
sudo logrotate -f /etc/logrotate.d/backtrader
```

## Database Management

### Backup

**Automated Daily Backup:**

```bash
#!/bin/bash
# /opt/scripts/backup-database.sh
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups"
DB_NAME="backtrader"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# PostgreSQL backup
pg_dump -U backtrader "$DB_NAME" | gzip > "$BACKUP_DIR/${DB_NAME}_${DATE}.sql.gz"

# Retain last 30 days
find "$BACKUP_DIR" -name "${DB_NAME}_*.sql.gz" -mtime +30 -delete

echo "Backup completed: ${DB_NAME}_${DATE}.sql.gz"
```

**Manual Backup:**

```bash
# Full database backup
pg_dump -U backtrader -d backtrader > backup.sql

# Compressed backup
pg_dump -U backtrader -d backtrader | gzip > backup.sql.gz
```

### Restore

```bash
# From SQL file
psql -U backtrader -d backtrader < backup.sql

# From compressed backup
gunzip -c backup.sql.gz | psql -U backtrader -d backtrader
```

### Database Maintenance

```bash
# Vacuum and analyze
psql -U backtrader -d backtrader -c "VACUUM ANALYZE;"

# Reindex
psql -U backtrader -d backtrader -c "REINDEX DATABASE backtrader;"

# Check table sizes
psql -U backtrader -d backtrader -c "
    SELECT schemaname, tablename,
           pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
    FROM pg_tables
    WHERE schemaname = 'public'
    ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
"
```

## Common Issues and Solutions

### High Memory Usage

**Symptoms**: Service crashes or becomes slow

**Solutions:**

```bash
# Check memory usage
free -h

# Restart service
sudo systemctl restart backtrader

# Configure memory limits (systemd)
# In /etc/systemd/system/backtrader.service:
[Service]
MemoryMax=2G
```

### Database Connection Pool Exhausted

**Symptoms**: Application can't connect to database

**Solutions:**

```bash
# Check PostgreSQL connections
psql -U postgres -c "SELECT count(*) FROM pg_stat_activity;"

# Terminate idle connections
psql -U postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle';"

# Increase max connections (postgresql.conf)
max_connections = 200
```

### Disk Space Full

**Symptoms**: Service stops working

**Solutions:**

```bash
# Check disk space
df -h

# Clean old logs
sudo journalctl --vacuum-time=30d

# Clean package cache
sudo apt clean
sudo apt autoremove

# Find large files
du -h /var/log | sort -h | tail -20
```

### API Timeout Issues

**Symptoms**: Requests timing out

**Solutions:**

```bash
# Check worker processes
ps aux | grep uvicorn

# Increase timeout (nginx proxy_read_timeout)
proxy_read_timeout 300s;
proxy_connect_timeout 300s;
proxy_send_timeout 300s;
```

## Performance Tuning

### Application Level

```python
# uvicorn production config
workers = multiprocessing.cpu_count() * 2 + 1
max_requests = 1000
max_requests_jitter = 100
timeout = 300
keepalive = 2
```

### Database Level

```sql
-- PostgreSQL tuning
ALTER SYSTEM SET shared_buffers = '256MB';
ALTER SYSTEM SET effective_cache_size = '1GB';
ALTER SYSTEM SET maintenance_work_mem = '64MB';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;
ALTER SYSTEM SET wal_buffers = '16MB';
ALTER SYSTEM SET default_statistics_target = 100;
-- Reload configuration
SELECT pg_reload_conf();
```

### System Level

```bash
# Optimize file descriptors
ulimit -n 65536

# Configure in /etc/security/limits.conf
backtrader soft nofile 65536
backtrader hard nofile 65536
```

## Alerting Configuration

### Monitored Metrics

1. **Service Availability**: Backend service running
2. **API Response Time**: < 1s for most endpoints
3. **Error Rate**: < 1% for all requests
4. **Database Connections**: < 80% of max
5. **Disk Space**: > 20% free
6. **Memory Usage**: < 80%

### Example Alert Script

```bash
#!/bin/bash
# /opt/scripts/check-health.sh
HEALTH_URL="http://localhost:8000/api/v1/monitoring/health"
ALERT_EMAIL="admin@example.com"

STATUS=$(curl -s "$HEALTH_URL" | jq -r '.status')

if [ "$STATUS" != "healthy" ]; then
    echo "ALERT: Backtrader service is unhealthy!" | mail -s "Service Alert" "$ALERT_EMAIL"
fi
```

## Upgrade Procedure

### Application Upgrade

```bash
# 1. Backup current deployment
sudo systemctl stop backtrader
cp -r /opt/backtrader_web /opt/backtrader_web.backup

# 2. Pull latest code
cd /opt/backtrader_web
git remote set-url origin https://github.com/cloudQuant/backtrader_web.git
git fetch origin
git checkout main
git pull origin main

# 3. Update dependencies (pyproject.toml 为单一来源)
cd src/backend
source ../venv/bin/activate
pip install -e ".[postgres,redis,backtrader,data]" --upgrade

# 4. Run migrations (if any)
alembic upgrade head

# 5. Restart service
sudo systemctl start backtrader
sudo systemctl status backtrader
```

### Database Migration

```bash
# Backup before migration
pg_dump -U backtrader backtrader > backup_before_migration.sql

# Run migrations
alembic upgrade head

# Verify migration
psql -U backtrader -d backtrader -c "\dt"
```

## Security Maintenance

### Regular Updates

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Update Python packages
pip list --outdated
pip install --upgrade package_name
```

### Certificate Renewal

```bash
# Check certificate expiry
sudo certbot certificates

# Manual renewal
sudo certbot renew

# Test renewal
sudo certbot renew --dry-run
```

## Disaster Recovery

### Recovery Procedures

**1. Restore from Backup:**

```bash
# Stop services
sudo systemctl stop backtrader

# Restore database
gunzip -c /backups/backtrader_YYYYMMDD.sql.gz | psql -U backtrader backtrader

# Restore application
rm -rf /opt/backtrader_web
cp -r /opt/backtrader_web.backup /opt/backtrader_web

# Start services
sudo systemctl start backtrader
```

**2. Failover to Backup Server:**

```bash
# Update DNS to point to backup server
# Promote standby database if using replication
# Update load balancer configuration
```

## Support Resources

- **Installation Guide**: [INSTALLATION.md](INSTALLATION.md)
- **Deployment Guide**: [DEPLOYMENT.md](DEPLOYMENT.md)
- **API Documentation**: http://your-domain.com/docs
- **GitHub Issues**: https://github.com/cloudQuant/backtrader_web/issues

## Contact Information

For production support:
- Email: support@example.com
- Slack: #backtrader-support
- Documentation: https://docs.example.com
