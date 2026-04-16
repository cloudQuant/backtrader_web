# 部署运维

## 部署方式

### 开发环境

本地开发，支持热重载：

```bash
# 后端
cd src/backend
uvicorn app.main:app --reload --port 8000

# 前端
cd src/frontend
npm run dev
```

### Docker 部署

使用 Docker 进行生产部署：

```bash
# 构建并启动
docker compose -f docker-compose.prod.yml up -d

# 查看日志
docker compose -f docker-compose.prod.yml logs -f

# 停止
docker compose -f docker-compose.prod.yml down
```

## 部署指南

- [Docker 部署](./docker.md) - Docker 和 Docker Compose 配置
- [生产环境](./production.md) - 生产环境配置
