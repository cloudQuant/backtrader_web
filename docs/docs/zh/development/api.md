# API 参考

运行服务的 Swagger UI（`/docs`）和 OpenAPI（`/openapi.json`）是唯一权威的接口清单：部分模块受依赖或配置影响，会按环境可选注册。

## 约定

- API 前缀：`/api/v1`。
- 页面和绝大多数 API 需要 JWT；管理员配置路由还要求管理员身份。
- 请求和响应使用 Pydantic 模型验证；输入不合法返回 422。
- 预期业务失败由 API 映射为 HTTP 错误；敏感数据库、账号和密钥不会出现在错误消息中。
- 长任务先提交再读取状态/结果；前端可通过对应事件或轮询更新界面。

## 主要领域

| 域 | 常用前缀 | 说明 |
| --- | --- | --- |
| 认证与状态 | `/auth`、`/status` | 登录、令牌、健康检查、可选路由状态 |
| 策略与回测 | `/strategy`、`/backtests`、`/analytics`、`/optimization` | 策略、版本、回测、分析和优化 |
| 工作区与交易 | `/workspace`、`/live-trading`、`/portfolio`、`/portfolio-ledger` | 研究/交易工作区、网关、组合与账本 |
| 数据 | `/data`、`/data/trust`、`/quote` | 行情、覆盖、质量预检、数据管理与报价 |
| AI 与知识 | `/knowledge-base`、`/rag`、`/kb-chat` | 文档、索引、检索、对话与诊断 |

## 示例：健康检查

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/health
```

提交回测、查询结果或配置网关前，请在 Swagger UI 读取该环境的 schema、认证要求与响应模型；不要从旧版 `/api/v1/backtest/*` 或历史会话端点复制请求。
