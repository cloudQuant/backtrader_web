# 配置

## 环境变量

### 应用

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `APP_NAME` | backtrader_web | 应用名称 |
| `DEBUG` | false | 调试模式 |
| `SECRET_KEY` | (必需) | Flask 密钥 |
| `TZ` | Asia/Shanghai | 时区 |

### 数据库

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_TYPE` | sqlite | 数据库类型 |
| `DATABASE_URL` | sqlite://... | 连接 URL |
| `DB_AUTO_CREATE_SCHEMA` | true | 自动创建架构 |
| `DB_AUTO_CREATE_DEFAULT_ADMIN` | true | 自动创建管理员 |

### JWT 认证

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `JWT_SECRET_KEY` | (必需) | JWT 签名密钥 |
| `JWT_ALGORITHM` | HS256 | 算法 |
| `JWT_EXPIRE_MINUTES` | 10080 | 令牌过期时间 (7 天) |

### 服务器

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `HOST` | 0.0.0.0 | 服务器主机 |
| `PORT` | 8000 | 服务器端口 |
| `CORS_ORIGINS` | * | CORS 允许源 |

### 管理员用户

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ADMIN_USERNAME` | admin | 管理员用户名 |
| `ADMIN_PASSWORD` | (必需) | 管理员密码 |
| `ADMIN_EMAIL` | admin@example.com | 管理员邮箱 |

### 回测

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `BACKTEST_TIMEOUT` | 300 | 超时时间（秒） |

### Redis

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `REDIS_URL` | redis://redis:6379/0 | Redis 连接 URL |

### AkShare (行情数据)

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AKSHARE_SCHEDULER_TIMEZONE` | Asia/Shanghai | 调度器时区 |
| `AKSHARE_SCRIPT_ROOT` | app/data_fetch/scripts | 脚本位置 |
| `AKSHARE_INTERFACE_BOOTSTRAP_MODE` | manual | 引导模式 |

## 配置文件

也可以使用 `src/backend/` 中的 `.env` 文件：

```bash
cp .env.example .env
```

## 生产配置

```bash
# 安全
SECRET_KEY=production-secret-key
JWT_SECRET_KEY=production-jwt-secret

# 数据库
DATABASE_TYPE=postgresql
DATABASE_URL=postgresql+asyncpg://user:pass@prod-host:5432/backtrader

# CORS
CORS_ORIGINS=https://your-domain.com
```
