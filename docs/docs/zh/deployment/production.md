# 生产环境

## 上线原则

生产环境的目标是可恢复、可审计和最小权限，而不是把开发环境直接暴露到公网。应用库、行情仓、AI 提供方和交易网关应分别配置访问权限、备份和责任人。

## 最低清单

- [ ] 使用独立的 MySQL/PostgreSQL 应用数据库，并完成备份和恢复演练。
- [ ] 为行情仓单独设置连接、读写权限和数据保留策略。
- [ ] 以密钥管理服务或受控环境变量提供 `SECRET_KEY`、`JWT_SECRET_KEY`、数据库密码和网关凭据。
- [ ] 固定允许的 `CORS_ORIGINS`，由反向代理终结 TLS，并限制管理端入口。
- [ ] 关闭 `DB_AUTO_CREATE_SCHEMA` 与 `DB_AUTO_CREATE_DEFAULT_ADMIN` 等开发自举。
- [ ] 记录日志保留、监控、告警、AI 成本预算、数据源故障处理和网关人工审批流程。

## 健康检查与升级

```bash
curl -fsS http://localhost/health
curl -fsS http://localhost:8000/api/v1/health

docker compose -f docker/docker-compose.yml -f docker/compose/prod.yml pull
docker compose -f docker/docker-compose.yml -f docker/compose/prod.yml up -d
docker compose -f docker/docker-compose.yml -f docker/compose/prod.yml ps
```

升级前先备份数据库、策略、工作区与运行日志；升级后执行健康检查、登录冒烟测试、数据仓访问测试和受控回测。出现异常时回滚到已验证镜像和已演练的数据恢复点。

## AI 与交易边界

- AI 请求应走被批准的提供方，配置超时、预算和审计；不要记录原始密钥。
- 生产知识库上传需经过敏感信息检查和权限隔离。
- 网关凭据和真实交易权限应与普通应用账号分离；以模拟/隔离验证、人工审批和风险限额为默认。

Docker 变量与容器操作见[Docker 部署](./docker.md)。
