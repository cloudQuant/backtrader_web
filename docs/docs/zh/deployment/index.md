# 部署运维

部署前先确认应用数据库、行情仓、密钥、CORS、备份、日志和网关权限的责任人。生产部署不应沿用开发默认密码或自动自举开关。

## 部署方式

| 场景 | 命令 |
| --- | --- |
| 本地开发 | 后端 `uvicorn app.main:app --reload --port 8000`，前端 `npm run dev` |
| Docker 开发 | `docker compose -f docker/docker-compose.yml -f docker/compose/dev.yml up` |
| Docker 生产 | `docker compose -f docker/docker-compose.yml -f docker/compose/prod.yml up -d` |
| 连接本机 MySQL 的容器化部署 | `docker compose -f docker/docker-compose.yml -f docker/compose/local.yml up -d` |

## 发布前检查

- 将 `SECRET_KEY`、`JWT_SECRET_KEY`、管理员密码和数据库密码替换为部署环境的高熵值。
- 只向前端域名开放 CORS；不要使用宽泛生产 CORS。
- 验证应用健康检查 `/health` 和 `/api/v1/health`，并检查依赖服务健康状态。
- 明确应用数据库和行情仓的备份、恢复演练与最小权限账号。
- 对 AI、同步和网关能力配置预算、审计、网络出口和人工审批边界。

- [Docker 部署](./docker.md)
- [生产环境](./production.md)
