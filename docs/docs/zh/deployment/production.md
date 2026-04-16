# 生产环境部署

## 要求

- **服务器**：2+ CPU 核心，4GB+ 内存
- **数据库**：PostgreSQL 14+ 或 MySQL 8+
- **Redis**：7+
- **SSL 证书**：Let's Encrypt 或商业证书

## 安全清单

- [ ] 修改所有默认密码
- [ ] 使用有效 SSL 证书启用 HTTPS
- [ ] 配置防火墙（仅允许 80、443）
- [ ] 启用限流
- [ ] 设置监控和告警
- [ ] 配置日志轮转
- [ ] 启用数据库备份

## 环境配置

### 数据库

```bash
# PostgreSQL
DATABASE_TYPE=postgresql
DATABASE_URL=postgresql+asyncpg://user:pass@prod-db:5432/backtrader

# MySQL
DATABASE_TYPE=mysql
DATABASE_URL=mysql+aiomysql://user:pass@prod-db:3306/backtrader
```

### 安全

```bash
# 生成安全密钥
SECRET_KEY=$(openssl rand -hex 32)
JWT_SECRET_KEY=$(openssl rand -hex 32)

# 生产环境 CORS
CORS_ORIGINS=https://your-domain.com
```

### 性能

```bash
# Workers (2x CPU 核心)
WORKERS=4

# 超时
TIMEOUT=300
```

## Nginx 配置

反向代理设置：

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

## 监控

### 健康检查

```bash
curl https://your-domain.com/health
```

### 指标

在 `/api/v1/monitoring/metrics` 访问 Prometheus 格式的指标。

## 备份

### 数据库备份

```bash
# PostgreSQL
pg_dump -h prod-db -U user backtrader > backup.sql

# MySQL
mysqldump -h prod-db -u user -p backtrader > backup.sql
```

### 自动备份

设置定时任务进行每日备份：

```bash
0 2 * * * /path/to/backup.sh
```

## 更新

```bash
# 拉取最新
git pull origin main

# 重新构建
docker compose -f docker-compose.prod.yml build

# 重启
docker compose -f docker-compose.prod.yml up -d
```
