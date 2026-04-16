# Docker 部署

## 前置条件

- Docker Engine 24+
- Docker Compose v2

## 快速开始

```bash
# 克隆并配置
git clone https://github.com/cloudQuant/backtrader_web.git
cd backtrader_web

# 创建环境文件
cp src/backend/.env.example src/backend/.env
# 编辑 .env 配置

# 启动服务
docker compose -f docker-compose.prod.yml up -d
```

## 服务

| 服务 | 端口 | 说明 |
|------|------|------|
| MySQL | 3306 | 数据库 |
| Redis | 6379 | 缓存 |
| 后端 | 8000 | API 服务器 |
| 前端 | 80, 443 | Web UI + HTTPS |

## 环境变量

### 必需

```bash
# 数据库
DB_PASSWORD=your_db_password
MYSQL_ROOT_PASSWORD=your_root_password

# 安全
SECRET_KEY=your-secret-key
JWT_SECRET_KEY=your-jwt-secret

# 管理员
ADMIN_PASSWORD=your-admin-password
```

### 可选

```bash
# 端口
HTTP_PORT=80
HTTPS_PORT=443

# 数据库
DB_HOST=mysql
DB_PORT=3306
DB_NAME=backtrader_web
DB_USER=backtrader

# Redis
REDIS_DATA_DIR=./runtime/redis

# 日志
BACKEND_LOGS_DIR=./runtime/backend/logs
```

## SSL/HTTPS

### Let's Encrypt (推荐)

```bash
# 初始化证书
./scripts/certbot-init.sh

# 启动证书服务
docker compose -f docker-compose.prod.yml up -d certbot
```

### 自定义证书

挂载您的证书文件：

```yaml
volumes:
  - /path/to/cert.pem:/etc/letsencrypt/live/aifortrader.cn/cert.pem
  - /path/to/key.pem:/etc/letsencrypt/live/aifortrader.cn/privkey.pem
```

## 数据持久化

持久化数据的卷：

```yaml
volumes:
  - ./runtime/mysql:/var/lib/mysql    # 数据库
  - ./runtime/redis:/data              # Redis 缓存
  - ./runtime/certbot:/etc/letsencrypt  # SSL 证书
  - ./datas:/opt/workspace/backtrader_web/datas  # 行情数据
  - ./strategies:/opt/workspace/backtrader_web/strategies  # 策略
```

## 健康检查

```bash
# 检查服务健康
curl http://localhost/health

# 查看容器状态
docker compose -f docker-compose.prod.yml ps
```

## 故障排查

### 端口已被占用

```bash
# 检查端口 80 占用情况
lsof -i :80

# 在 docker-compose.prod.yml 中修改端口
ports:
  - "8080:80"
```

### 数据库连接失败

```bash
# 查看 MySQL 日志
docker compose logs mysql

# 验证 .env 中的凭据
```
