# 开发指南

开发文档描述当前仓库的分层边界；发布 API 与运行行为以测试和 OpenAPI 为准。

## 目录与职责

```text
src/backend/app/
├── api/        # HTTP / WebSocket 路由、认证和输入输出边界
├── services/   # 业务编排：数据、RAG、回测、工作区、交易与风险
├── models/     # SQLAlchemy ORM 模型
├── schemas/    # Pydantic 请求/响应模型
├── db/         # 引擎、会话、仓库与迁移支撑
└── utils/      # 安全、沙箱、日志等基础设施

src/frontend/src/
├── api/        # API 客户端
├── views/      # 路由页面
├── components/ # 可复用 UI
├── composables/# 页面与领域组合逻辑
├── stores/     # Pinia 状态
└── navigation/ # 路由与导航约定
```

## 继续阅读

- [架构设计](./architecture.md)
- [API 参考](./api.md)
- [数据库与数据边界](./database.md)
- 工程代码规范：`docs/reference/CODING_STANDARDS.md`
- 工程测试手册：`docs/how-to/TESTING.md`
