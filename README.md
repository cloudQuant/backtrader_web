# AI for Investor

AI 驱动的量化研究、策略生成、回测验证与交易辅助平台

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![Vue](https://img.shields.io/badge/Vue-3.4+-green.svg)](https://vuejs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-teal.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 项目简介

AI for Investor 是一个面向量化交易者和投研团队的 **AI + 量化** MVP 产品，围绕“自然语言研究 → 知识库问答 → 策略生成 → 回测验证 → 工作区沉淀”的闭环，提供从策略开发、数据管理、回测分析、参数优化到模拟交易、实盘监控和 AI 辅助研究的全流程解决方案：

- 🚀 **开箱即用** - 5分钟完成首次回测
- 📊 **专业图表** - Echarts K线图 + 10+ 分析图表
- 🔌 **API优先** - 核心路由 + 可选路由按模块注册，支持可观测降级
- 💾 **多数据库** - 支持 SQLite / PostgreSQL / MySQL
- 🎯 **策略管理** - 策略版本控制 + 代码编辑器 + 118 内置模板
- 🤖 **AI 量化 Copilot** - 知识库问答 + 自然语言策略构思 + Backtrader 策略草案生成 + 保存到策略中心/添加到研究工作区/一键回测/自动报告/自动复盘建议
- 🧠 **知识库/RAG** - 文档管理、自动索引、引用跳转、AI 配置诊断、降级原因提示
- 🗃️ **数据管理** - Akshare 接口、脚本、任务、执行记录、数据表浏览与 MySQL 同步
-  **模拟交易** - 研究/交易工作区与模拟交易环境
- 🔴 **实盘交易** - 多券商实盘对接 (CTP/CCXT)，默认保持高风险能力边界
- 📡 **实时行情** - WebSocket 实时推送
- 🚨 **监控告警** - 实时监控和告警系统

## 当前项目状态

当前项目处于 `v1.x` 持续优化阶段，近期重点是**知识库 + AI 问答 + 策略 Copilot + 工作区报告闭环**的稳定性打磨。

已完成或已具备的关键能力：

- **知识库与 AI 问答**
  - 支持知识库、文档、文档块、RAG 搜索和 KB Chat 会话。
  - 空白问题会被后端校验拒绝，空文档索引会返回 `not_indexed`。
  - RAG/KB Chat 会返回兼容字段 `reason_code` / `diagnostic_message`，用于区分 `no_context_found`、`ai_not_configured`、`ai_provider_failed`。
  - AIChat 页面会展示诊断提示、引用 fallback、未索引文档说明和重建索引入口。

- **AI 策略 Copilot**
  - 支持 `知识问答`、`策略构思`、`Backtrader策略生成`、`策略审查` 四种模式。
  - `strategy_draft` 可保存到策略中心、添加到研究工作区、触发回测并生成报告摘要/复盘建议。
  - 策略草稿缺字段时，前端会禁用相关动作并提示原因。

- **数据管理与同步**
  - `/data` 已拆分为市场数据、脚本、任务、执行、数据表、接口和同步等子页面。
  - 数据同步支持 `direct_mysql` 默认模式，也保留 `ssh_docker` 兼容模式。
  - `direct_mysql` 模式通过本地 `mysql` / `mysqldump` 客户端直连远程 MySQL，不再强依赖 SSH、Docker 或远程 `.env`。

- **工程稳定性**
  - 可选 API 路由按模块注册，导入失败会记录到 `/api/v1/status/routers`，避免静默缺失。
  - 数据库兼容、自启动、错误提示、空状态和前端测试覆盖仍在迭代 163 中持续优化。

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + TypeScript + Vite + Element Plus + Echarts |
| 后端 | FastAPI + Uvicorn + Pydantic + SQLAlchemy 2.0 |
| 数据库 | SQLite (默认) / PostgreSQL / MySQL |
| 回测引擎 | Backtrader + fincore (标准化指标) |
| AI/RAG | 知识库文档块检索 + OpenAI-compatible `chat/completions` 可选生成层 |
| 数据管理 | Akshare 接口/脚本/任务/执行记录 + MySQL 同步 |
| 测试 | pytest + Playwright (E2E) + Vitest (前端) |

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 20+
- Docker (可选，用于容器化部署)

### 安装步骤

```bash
# 克隆项目
git clone https://github.com/cloudQuant/ai-for-investor.git
cd ai-for-investor

# 步骤 1：安装前环境检查
./scripts/dev/verify-dev-env.sh --preinstall

# 步骤 2：安装项目依赖
# 后端
cd src/backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e ".[dev,backtrader]"
cp .env.example .env

# 安装后环境检查
cd ../..
./scripts/dev/verify-dev-env.sh --postinstall

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
docker compose -f docker-compose.yml -f docker/compose/prod.yml up -d
```

### 访问地址

- 前端: http://localhost:3000 (开发) / http://localhost (生产 Docker)
- 后端 API 文档: http://localhost:8000/docs
- WebSocket: ws://localhost:8000/ws

### v0.2.0 RC1 演示路径

当前 RC1 可完整体验已交付的 AI 可信度能力：

1. 在策略中心创建或选择策略，运行一次回测。
2. 打开回测结果页，查看策略评分卡、过拟合检测和策略解释面板。
3. 在 AI 助手中选择知识库或策略生成模式，生成策略草稿并保存到策略中心/添加到研究工作区。
4. 运行 `cd src/backend && pytest tests/perf/ -q --tb=short` 查看 API 与回测任务吞吐基线。
5. 运行 `cd src/frontend && npm run test -- --run --coverage` 验证前端覆盖率阈值。

AI 调用可观测、多模型路由、VaR/CVaR、因子分析、绩效归因和市场状态识别属于 v0.2.x 后续迭代目标；当前 RC1 已在 [发布说明](docs/RELEASE_NOTES_V0.2.0.md) 中标注其路线边界。

## 项目结构

```
ai-for-investor/
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
| 数据管理 | `/api/v1/data` | Akshare 数据、脚本、任务、执行、数据表、接口、同步 |
| 知识库 | `/api/v1/knowledge-base` | 知识库、文档、文件夹、索引状态 |
| RAG | `/api/v1/rag` | 文档索引、检索、问答 |
| KB Chat | `/api/v1/kb-chat` | 知识库会话、历史消息、AI 助手问答 |
| 网关/状态 | `/api/v1/status`, `/api/v1/live-trading/gateways` | 健康检查、可选路由状态、网关状态 |

> ⚠️ **废弃说明**：旧版 `/api/v1/backtest/*` 端点已废弃，请迁移至 `/api/v1/backtests/*`

详细 API 文档请查看 [docs/API.md](docs/API.md)

## 配置说明

环境变量配置 (`.env`):

```bash
# 数据库 (默认SQLite)
DATABASE_TYPE=sqlite
DATABASE_URL=sqlite+aiosqlite:///../../data/dev/backtrader.db

# 可选: 使用 PostgreSQL
# DATABASE_TYPE=postgresql
# DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/backtrader

# 可选: 使用 MySQL
# DATABASE_TYPE=mysql
# DATABASE_URL=mysql+aiomysql://user:pass@localhost:3306/backtrader

# JWT 配置
SECRET_KEY=your-secret-key
JWT_SECRET_KEY=your-jwt-secret
JWT_EXPIRE_MINUTES=1440

# CORS 配置 (生产环境)
CORS_ORIGINS=https://your-domain.com

# 可选: 生成式 AI / 知识库问答
AI_CHAT_ENABLED=false
AI_CHAT_BASE_URL=
AI_CHAT_API_KEY=
AI_CHAT_MODEL=
AI_CHAT_TIMEOUT=60
AI_CHAT_TEMPERATURE=0.2

# 可选: 数据库兼容自举
DB_AUTO_CREATE_SCHEMA=false
DB_AUTO_CREATE_DEFAULT_ADMIN=false

# 可选: 数据同步默认本地 MySQL
SYNC_LOCAL_MYSQL_HOST=127.0.0.1
SYNC_LOCAL_MYSQL_PORT=3306
SYNC_LOCAL_MYSQL_USER=root
SYNC_LOCAL_MYSQL_PASSWORD=
```

> 生产环境必须替换 `SECRET_KEY` / `JWT_SECRET_KEY` / 管理员密码等默认占位值；不要把真实密钥提交到仓库。

## 常用验证命令

前端覆盖率按实测基线渐进收紧：

| 阶段 | lines/statements | functions | branches |
|------|------------------|-----------|----------|
| 迭代163 基线 | 29% | 35% | 40% |
| 迭代169 / v0.2.0 RC | 34% | 40% | 45% |
| 后续目标 | 每轮 +5，直至 60%+ 稳定门槛 | 每轮 +5，直至 60%+ 稳定门槛 | 每轮 +5，直至 60%+ 稳定门槛 |

后端：

```bash
cd src/backend
ruff check app tests
pytest tests/test_iteration129_knowledge_base_api.py tests/test_iteration129_rag_api.py tests/test_iteration129_kb_chat_api.py -q --tb=short
mypy app/utils app/schemas
```

前端：

```bash
cd src/frontend
npm run typecheck
npm run test -- src/test/views/AIChatPage.test.ts src/test/stores/kbChat.test.ts --run
npm run test -- --run --coverage
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
- [AI策略 Copilot](docs/AI_STRATEGY_COPILOT.md) - AI 助手、自然语言策略生成、工作区接入、回测、自动报告与复盘说明
- [v0.2.0 RC 发布说明](docs/RELEASE_NOTES_V0.2.0.md) - RC1 交付内容、验证命令和已知边界
- [迭代历史](docs/iterations/README.md) - 当前活跃迭代与历史迭代索引
- [迭代163 Goal 夜间项目完善](docs/iterations/迭代163-Goal夜间项目完善/index.md) - 当前稳定性、测试覆盖和文档一致性优化任务书
- [策略开发](docs/STRATEGY_DEVELOPMENT.md) - 如何编写交易策略
- [更新日志](docs/CHANGELOG.md) - 版本更新记录

### 其他文档

- [代码规范](docs/CODING_STANDARDS.md) - Python/Vue 代码风格
- [测试指南](docs/TESTING.md) - 单元测试、E2E 测试
- [贡献指南](CONTRIBUTING.md) - 开发流程与 PR 规范
- [CI/CD](docs/CI_CD.md) - GitHub Actions 流水线
- [无障碍基线 (Accessibility Baseline)](docs/explanation/accessibility-baseline.md) - WCAG 2.1 AA 基线、Critical_Page_Set 扫描结果与必要豁免（迭代 175 §3）
- [前端 Bundle 体积基线](docs/reference/frontend-bundle-budget.md) - vendor chunk 与 entry chunk gzip 体积基线（迭代 175 §7）
- [数据库迁移 Playbook](docs/how-to/database-migration-playbook.md) - 长锁/全表扫描风险与降级策略（迭代 175 §8）
- [Python Monorepo 选型说明](docs/explanation/python-monorepo.md) - uv workspace 选型与 vendored 包处理（迭代 175 §9）

## 版本计划

### v1.x (当前)

- 稳定版本，持续优化和bug修复
- 部分旧版 API 已标记废弃，但仍保持向后兼容
- 当前重点：知识库/RAG/AI Copilot、工作区报告闭环、数据管理同步、数据库兼容与前端错误隔离

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
