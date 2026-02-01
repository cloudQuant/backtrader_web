# Backtrader Web

基于 Backtrader 的现代化量化回测 Web 平台

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![Vue](https://img.shields.io/badge/Vue-3.4+-green.svg)](https://vuejs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-teal.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 项目简介

Backtrader Web 是一个为量化交易开发者打造的 Web 回测平台，提供：

- 🚀 **开箱即用** - 5分钟完成首次回测
- 📊 **专业图表** - Echarts K线图 + 10+ 分析图表
- 🔌 **API优先** - RESTful API 100% 覆盖
- 💾 **多数据库** - 支持 SQLite/PostgreSQL/MySQL/MongoDB
- 🎯 **策略管理** - YAML配置 + 代码编辑器

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + TypeScript + Vite + Element Plus + Echarts |
| 后端 | FastAPI + Uvicorn + Pydantic + SQLAlchemy 2.0 |
| 数据库 | SQLite (默认) / PostgreSQL / MySQL / MongoDB |
| 回测引擎 | Backtrader |

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+

### 安装步骤

```bash
# 克隆项目
git clone https://gitee.com/xxx/backtrader_web.git
cd backtrader_web

# 后端
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000

# 前端 (新终端)
cd frontend
npm install
npm run dev
```

### 访问

- 前端: http://localhost:5173
- 后端API文档: http://localhost:8000/docs

## 项目结构

```
backtrader_web/
├── backend/                 # FastAPI 后端
│   ├── app/
│   │   ├── api/            # API 路由
│   │   ├── services/       # 业务逻辑
│   │   ├── db/             # 数据库层
│   │   ├── models/         # ORM 模型
│   │   └── schemas/        # Pydantic 模型
│   └── strategies/         # 内置策略
├── frontend/               # Vue3 前端
│   ├── src/
│   │   ├── api/           # API 调用
│   │   ├── components/    # 组件
│   │   ├── views/         # 页面
│   │   └── stores/        # Pinia 状态
│   └── package.json
└── docs/                   # 文档
    └── AGILE_DEVELOPMENT.md
```

## 配置说明

环境变量配置 (`.env`):

```bash
# 数据库 (默认SQLite，无需额外安装)
DATABASE_TYPE=sqlite
DATABASE_URL=sqlite:///./backtrader.db

# 可选: 使用 PostgreSQL
# DATABASE_TYPE=postgresql
# DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/backtrader

# JWT 配置
SECRET_KEY=your-secret-key
JWT_EXPIRE_MINUTES=1440
```

## 开发文档

详细的敏捷开发文档请查看: [docs/AGILE_DEVELOPMENT.md](docs/AGILE_DEVELOPMENT.md)

包含:
- 产品愿景和目标
- 用户故事和验收标准
- Sprint 规划
- 技术架构设计
- 开发规范

## 参与贡献

1. Fork 本仓库
2. 新建 `feature/xxx` 分支
3. 提交代码
4. 新建 Pull Request

## 许可证

[MIT License](LICENSE)
