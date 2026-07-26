# Docker 部署

Compose 基础文件在 `docker/docker-compose.yml`，必须与 `docker/compose/` 下的一个环境覆盖文件一起使用。

## 开发环境

```bash
docker compose -f docker/docker-compose.yml -f docker/compose/dev.yml up
```

开发覆盖启动 PostgreSQL、后端和前端；默认暴露后端 `8000`、前端 `3000`。可通过 `LOCAL_BACKEND_PORT`、`LOCAL_FRONTEND_PORT`、`LOCAL_DB_PORT` 等环境变量调整端口。

## 生产环境

1. 在受保护的部署环境设置必需变量：`DB_PASSWORD`、`MYSQL_ROOT_PASSWORD`、`SECRET_KEY`、`JWT_SECRET_KEY`、`ADMIN_PASSWORD`。
2. 按需设置 `DB_NAME`、`DB_USER`、`CORS_ORIGINS`、`HTTP_PORT`、`HTTPS_PORT`、持久化目录和 `WEB_CONCURRENCY`。
3. 启动并检查状态：

```bash
docker compose -f docker/docker-compose.yml -f docker/compose/prod.yml up -d
docker compose -f docker/docker-compose.yml -f docker/compose/prod.yml ps
curl http://localhost/health
```

生产覆盖包含 MySQL、Redis、后端、前端和可选 Certbot 容器。数据目录、策略目录、工作区和日志目录均应使用持久化卷并纳入备份。

## 常用操作

```bash
# 日志
docker compose -f docker/docker-compose.yml -f docker/compose/prod.yml logs -f backend

# 停止（保留卷）
docker compose -f docker/docker-compose.yml -f docker/compose/prod.yml down

# 查看最终渲染的配置，避免变量遗漏
docker compose -f docker/docker-compose.yml -f docker/compose/prod.yml config
```

不要把 `.env`、证书、数据库导出或网关凭据打进镜像或提交到 Git。
