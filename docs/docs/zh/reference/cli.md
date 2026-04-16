# 命令行接口

## 后端 CLI

### 启动服务器

```bash
cd src/backend
uvicorn app.main:app --reload --port 8000
```

### 选项

| 选项 | 说明 |
|------|------|
| `--host` | 绑定主机 (默认: 0.0.0.0) |
| `--port` | 绑定端口 (默认: 8000) |
| `--reload` | 启用自动重载 |
| `--workers` | Worker 数量 |

### 数据库迁移

```bash
# 创建迁移
alembic revision --autogenerate -m "message"

# 升级
alembic upgrade head

# 降级
alembic downgrade -1
```

## 前端 CLI

### 开发服务器

```bash
cd src/frontend
npm run dev
```

### 构建

```bash
npm run build
```

### 类型检查

```bash
npm run typecheck
```

### Lint

```bash
npm run lint
```

## 脚本

### 环境验证

```bash
./scripts/verify-dev-env.sh --preinstall
./scripts/verify-dev-env.sh --postinstall
```

### Docker 部署

```bash
./scripts/certbot-init.sh     # 初始化 SSL
./scripts/certbot-renew.sh    # 续期 SSL
```

## 测试

### 后端测试

```bash
cd src/backend
pytest

# 带覆盖率
pytest --cov=app --cov-report=term

# 特定文件
pytest tests/test_auth.py
```

### 前端测试

```bash
cd src/frontend
npm run test

# E2E 测试
npm run test:e2e
```
