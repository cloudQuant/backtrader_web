# 开发指南

本节涵盖 Backtrader Web 的开发指南。

## 项目结构

```
backtrader_web/
├── src/
│   ├── backend/              # FastAPI 后端
│   │   ├── app/
│   │   │   ├── api/        # API 路由 (15+ 模块)
│   │   │   ├── services/   # 业务逻辑
│   │   │   ├── db/         # 数据库层
│   │   │   ├── models/     # ORM 模型
│   │   │   └── schemas/    # Pydantic 模型
│   │   └── strategies/     # 内置策略
│   └── frontend/           # Vue3 前端
│       ├── src/
│       │   ├── api/        # API 调用
│       │   ├── components/ # 组件
│       │   ├── views/      # 页面
│       │   └── stores/     # Pinia 状态
│       └── package.json
├── strategies/             # 118 内置策略模板
├── tests/                 # 测试
└── docs/                 # 文档
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + TypeScript + Vite + Element Plus + Echarts |
| 后端 | FastAPI + Uvicorn + Pydantic + SQLAlchemy 2.0 |
| 数据库 | SQLite (默认) / PostgreSQL / MySQL |
| 测试 | pytest + Playwright + Vitest |

## 开发指南

- [架构设计](./architecture.md) - 系统架构
- [API 参考](./api.md) - RESTful API 文档
- [数据库设计](./database.md) - 数据库设计和模型
