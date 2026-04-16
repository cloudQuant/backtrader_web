# Backtrader Web

基于 Backtrader 的现代化量化交易全栈管理平台

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![Vue](https://img.shields.io/badge/Vue-3.4+-green.svg)](https://vuejs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-teal.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 项目简介

Backtrader Web 是一个为量化交易开发者打造的**全功能量化交易管理平台**，提供从策略开发、回测分析到模拟交易、实盘监控的全流程解决方案：

- 🚀 **开箱即用** - 5分钟完成首次回测
- 📊 **专业图表** - Echarts K线图 + 10+ 分析图表
- 🔌 **API优先** - 15+ 模块，80+ RESTful API 端点
- 💾 **多数据库** - 支持 SQLite / PostgreSQL / MySQL
- 🎯 **策略管理** - 策略版本控制 + 代码编辑器 + 118 内置模板
- 📈 **模拟交易** - 完整的模拟交易环境
- 🔴 **实盘交易** - 多券商实盘对接 (CTP/CCXT)
- 📡 **实时行情** - WebSocket 实时推送
- 🚨 **监控告警** - 实时监控和告警系统

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + TypeScript + Vite + Element Plus + Echarts |
| 后端 | FastAPI + Uvicorn + Pydantic + SQLAlchemy 2.0 |
| 数据库 | SQLite (默认) / PostgreSQL / MySQL |
| 回测引擎 | Backtrader + fincore (标准化指标) |
| 测试 | pytest + Playwright (E2E) + Vitest (前端) |

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 20+
- Docker (可选，用于容器化部署)

### 安装步骤

```bash
# 克隆项目
git clone https://github.com/cloudQuant/backtrader_web.git
cd backtrader_web

# 步骤 1：安装前环境检查
./scripts/verify-dev-env.sh --preinstall

# 步骤 2：安装项目依赖
# 后端
cd src/backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e ".[dev,backtrader]"
cp .env.example .env

# 安装后环境检查
cd ../..
./scripts/verify-dev-env.sh --postinstall

# 前端（新终端）
cd src/frontend
npm install
```

### 启动服务

**开发模式：**
```bash
# 后端
cd src/backend && uvicorn app.main:app --reload --port 8000

# 前端
cd src/frontend && npm run dev
```

**Docker 部署：**
```bash
# 生产环境
docker compose -f docker-compose.prod.yml up -d
```

### 访问地址

- 前端: http://localhost:8080 (开发) / http://localhost (生产 Docker)
- 后端 API 文档: http://localhost:8000/docs
- WebSocket: ws://localhost:8000/ws

## 项目结构

```
backtrader_web/
├── src/
│   ├── backend/             # FastAPI 后端
│   │   ├── app/
│   │   │   ├── api/        # API 路由 (15+ 模块)
│   │   │   ├── services/   # 业务逻辑
│   │   │   ├── db/         # 数据库层
│   │   │   ├── models/     # ORM 模型
│   │   │   └── schemas/    # Pydantic 模型
│   │   └── strategies/     # 内置策略
│   └── frontend/            # Vue3 前端
│       ├── src/
│       │   ├── api/        # API 调用
│       │   ├── components/ # 组件
│       │   ├── views/      # 页面
│       │   └── stores/     # Pinia 状态
│       └── package.json
├── strategies/              # 118 内置策略模板
├── examples/                # API 调用示例
├── tests/                   # 测试
└── docs/                    # 30+ 篇文档
```

## 核心 API 模块

| 模块 | 端点前缀 | 说明 |
|------|----------|------|
| 认证 | `/api/v1/auth` | JWT 认证、注册、登录 |
| 策略 | `/api/v1/strategy` | 策略 CRUD、模板 |
| 回测 | `/api/v1/backtests` | **推荐** 增强回测端点 |
| 分析 | `/api/v1/analytics` | 回测数据分析 |
| 优化 | `/api/v1/optimization` | 参数优化 |
| 模拟交易 | `/api/v1/paper-trading` | 模拟账户、订单 |
| 实盘交易 | `/api/v1/live-trading` | 实盘账户、订单 |
| 行情数据 | `/api/v1/quote`, `/api/v1/realtime` | 实时行情 |
| 监控告警 | `/api/v1/monitoring` | 告警规则 |
| 工作区 | `/api/v1/workspace` | 工作区管理 |

> ⚠️ **废弃说明**：旧版 `/api/v1/backtest/*` 端点已废弃，请迁移至 `/api/v1/backtests/*`

详细 API 文档请查看 [docs/API.md](docs/API.md)

## 配置说明

环境变量配置 (`.env`):

```bash
# 数据库 (默认SQLite)
DATABASE_TYPE=sqlite
DATABASE_URL=sqlite:///./backtrader.db

# 可选: 使用 PostgreSQL
# DATABASE_TYPE=postgresql
# DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/backtrader

# 可选: 使用 MySQL
# DATABASE_TYPE=mysql
# DATABASE_URL=mysql+aiomysql://user:pass@localhost:3306/backtrader

# JWT 配置
SECRET_KEY=your-secret-key
JWT_EXPIRE_MINUTES=1440

# CORS 配置 (生产环境)
CORS_ORIGINS=https://your-domain.com
```

## 文档

详细文档请查看: [docs/INDEX.md](docs/INDEX.md)

### 核心文档

- **[综合技术文档](docs/TECHNICAL_DOCS.md)** - 系统功能概览、API 模块、数据模型、部署运维
- [安装指南](docs/INSTALLATION.md) - 环境配置和安装
- [快速上手](docs/QUICKSTART.md) - 5分钟完成首次回测
- **[API 文档](docs/API.md)** - RESTful API 接口说明
- [API 使用指南](docs/API_GUIDE.md) - API 调用示例和最佳实践
- [开发指南](docs/DEVELOPMENT.md) - 本地开发环境配置
- [架构设计](docs/ARCHITECTURE.md) - 整体架构设计
- [数据库设计](docs/DATABASE.md) - 数据模型和关系
- [安全指南](docs/SECURITY.md) - 安全最佳实践
- [策略开发](docs/STRATEGY_DEVELOPMENT.md) - 如何编写交易策略
- [更新日志](docs/CHANGELOG.md) - 版本更新记录

### 其他文档

- [代码规范](docs/CODING_STANDARDS.md) - Python/Vue 代码风格
- [测试指南](docs/TESTING.md) - 单元测试、E2E 测试
- [贡献指南](CONTRIBUTING.md) - 开发流程与 PR 规范
- [CI/CD](docs/CI_CD.md) - GitHub Actions 流水线

## 版本计划

### v1.x (当前)

- 稳定版本，持续优化和bug修复
- 部分旧版 API 已标记废弃，但仍保持向后兼容

### v2.0.0 (计划中)

**预计时间**: 2026-Q2

**重大变更**:
- 移除废弃 API 端点：
  - `/api/v1/backtest/*` → 使用 `/api/v1/backtests/*`
  - `/api/v1/live-trading-crypto/*` → 使用 `/api/v1/live-trading/*`
  - `/api/v1/backtests/optimization/grid` → 使用 `/api/v1/optimization/submit`
  - `/api/v1/backtests/optimization/bayesian` → 使用 `/api/v1/optimization/submit`

**迁移建议**: 新项目请直接使用新端点，现有项目请在 v2.0.0 发布前完成迁移。

详见 [API文档](docs/API.md) 的废弃入口清单。

## 参与贡献

请参阅 [CONTRIBUTING.md](CONTRIBUTING.md) 获取完整贡献指南。

## 许可证

[MIT License](LICENSE)
