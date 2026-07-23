# AI for Investor

AI 驱动的量化研究、策略生成、回测验证与交易辅助平台

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![Vue](https://img.shields.io/badge/Vue-3.4+-green.svg)](https://vuejs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-teal.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 项目简介

AI for Investor 是一个面向量化交易者和投研团队的 **AI + 量化** 平台，围绕“自然语言研究 → 知识库问答 → 策略生成 → 回测验证 → 工作区与交易执行”的闭环，覆盖策略开发、数据管理、回测分析、参数优化、模拟交易、实盘监控和 AI 辅助研究。

- 🚀 **开箱即用** - 5分钟完成首次回测
- 📊 **专业图表** - Echarts K线图 + 10+ 分析图表
- 🔌 **API优先** - 核心路由 + 可选路由按模块注册，支持可观测降级
- 💾 **多数据库** - 支持 SQLite / PostgreSQL / MySQL
- 🎯 **策略管理** - 策略版本控制 + 代码编辑器 + 118 内置模板
- 🤖 **AI 量化 Copilot** - 知识库问答 + 自然语言策略构思 + Backtrader 策略草案生成 + 保存到策略中心/添加到研究工作区/一键回测/自动报告/自动复盘建议
- 🧠 **知识库/RAG** - 文档管理、自动索引、引用跳转、AI 配置诊断、降级原因提示
- 🗃️ **数据管理与可信度** - AkShare 数据仓、数据覆盖矩阵、质量检查、回测前预检与 MySQL 同步
- 🧪 **模拟交易** - 研究/交易工作区与模拟交易环境
- 🔴 **实盘交易** - 多网关实盘接入、实例生命周期管理与高风险能力边界
- 📈 **组合与风险工作台** - 聚合运行中工作区的账户、持仓、成交、累计 P&L、回撤和资产配置
- 📡 **实时行情** - WebSocket 实时推送
- 🚨 **监控告警** - 实时监控和告警系统

## 当前项目状态

当前项目处于 `v1.x` 持续演进阶段，重点是把投研、市场数据、回测、交易工作区和组合风险视图连接为可验证、可追溯的工作流。

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
  - 市场数据覆盖默认来自 AkShare 数据仓，支持手动刷新本地 CSV 与数据仓覆盖矩阵。
  - 行情历史会校验新鲜度；本地数据缺失或过期时可回退到 AkShare 在线行情并写入缓存。
  - 期货数据质量检查覆盖跨午夜交易日、夜盘缺口、节假日异常 K 线和换月价格跳变。
  - 数据同步支持 `direct_mysql` 默认模式，也保留 `ssh_docker` 兼容模式。
  - `direct_mysql` 模式通过本地 `mysql` / `mysqldump` 客户端直连远程 MySQL，不再强依赖 SSH、Docker 或远程 `.env`。

- **组合、模拟与实盘交易**
  - 投资组合页默认只聚合运行中的交易工作区，并可按工作区查看账户、持仓、成交、资金曲线和资产配置。
  - 持仓估值兼容网关快照、策略日志和资产规格，覆盖多空方向、合约乘数、手续费与共享账户去重。
  - 组合图表展示累计 P&L 和回撤，使用后端统一口径避免混合历史数据造成的错误回撤。
  - 实盘实例会在启动、列表和查询时校正进程状态、启动时间及重复 runtime 目录；网关启动诊断会保留原生 stdout/stderr 日志。

- **知识库运营**
  - 文档切片会将章节标题和正文一起保留，避免标题或元数据单独成为低价值检索结果。
  - 提供可幂等的本地语料导入脚本，可将 HTML 量化文章和 PDF 系统交易资料导入指定知识库。

- **工程质量与稳定性**
  - 可选 API 路由按模块注册，导入失败会记录到 `/api/v1/status/routers`，避免静默缺失。
  - 使用 uv workspace、Ruff、mypy 棘轮、pytest、Vitest 和 Playwright 持续保障跨端质量。

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + TypeScript + Vite + Element Plus + Echarts |
| 后端 | FastAPI + Uvicorn + Pydantic + SQLAlchemy 2.0 |
| 数据库 | SQLite (默认) / PostgreSQL / MySQL |
| 回测引擎 | Backtrader + fincore (标准化指标) |
| AI/RAG | 知识库文档块检索 + OpenAI-compatible `chat/completions` 可选生成层 |
| 数据管理 | AkShare 数据仓、覆盖/质量预检、接口/脚本/任务/执行记录 + MySQL 同步 |
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
./scripts/dev/verify-dev-env.sh --preinstall

# 步骤 2：安装项目依赖
# 后端
cd src/backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
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

容器化部署请参考 [Docker 部署指南](docs/docs/zh/deployment/docker.md)，并在部署前配置生产环境所需的密钥与数据库变量。

### 访问地址

- 前端: http://localhost:3000 (开发) / http://localhost (生产 Docker)
- 后端 API 文档: http://localhost:8000/docs
- WebSocket: ws://localhost:8000/ws

### 建议体验路径

1. 在策略中心创建或选择策略，运行一次增强回测。
2. 在“数据”页面查看目标品种的覆盖范围与质量信息，并在回测前运行数据预检。
3. 将策略加入研究或交易工作区，在模拟环境中观察运行状态、持仓和成交。
4. 打开投资组合页，查看运行中工作区的累计 P&L、回撤和资产配置。
5. 在 AI 助手中使用知识库或策略生成模式，将策略草稿保存到策略中心或研究工作区。

### 本地知识库语料导入（可选）

导入工具会按源文件路径和 SHA-256 去重；先以 `--dry-run` 确认文件范围，再执行正式导入。运行前需激活后端虚拟环境，并为 PDF 语料安装 `pypdf`。

```bash
python scripts/migrate/import_local_knowledge_corpora.py \
  --quant-dir /path/to/quant-articles \
  --system-dir /path/to/system-trading-pdfs \
  --owner-id <user-id> \
  --dry-run
```

移除 `--dry-run` 后会创建或更新默认知识库；可用 `--only quant` 或 `--only system` 只导入一个语料库，其他参数见 `--help`。

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
│   │   └── tests/          # 后端测试
│   └── frontend/            # Vue3 前端
│       ├── src/
│       │   ├── api/        # API 调用
│       │   ├── components/ # 组件
│       │   ├── views/      # 页面
│       │   └── stores/     # Pinia 状态
│       └── package.json
├── strategies/              # 118 内置策略模板
├── scripts/                 # 开发、运维与迁移工具
├── docker/                  # Compose 配置与部署资源
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
| 数据管理 | `/api/v1/data` | AkShare 数据、覆盖/质量预检、脚本、任务、执行、数据表、接口、同步 |
| 数据可信度 | `/api/v1/data/trust` | 资产规格、执行模型、覆盖矩阵、数据仓刷新和回测前预检 |
| 知识库 | `/api/v1/knowledge-base` | 知识库、文档、文件夹、索引状态 |
| RAG | `/api/v1/rag` | 文档索引、检索、问答 |
| KB Chat | `/api/v1/kb-chat` | 知识库会话、历史消息、AI 助手问答 |
| 组合 | `/api/v1/portfolio`, `/api/v1/portfolio-ledger` | 实盘聚合视图、交易记录、资金曲线、资产配置与独立账本 |
| 网关/状态 | `/api/v1/status`, `/api/v1/live-trading/gateways` | 健康检查、可选路由状态、网关状态 |

> ⚠️ **废弃说明**：旧版 `/api/v1/backtest/*` 端点已废弃，请迁移至 `/api/v1/backtests/*`

详细 API 文档请查看 [API 概览](docs/reference/API_OVERVIEW.md) 与 [API 使用指南](docs/guides/API_GUIDE.md)。

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

后端：

```bash
cd src/backend
ruff check app tests
pytest -m "not e2e" -q --tb=short
mypy app
```

前端：

```bash
cd src/frontend
npm run typecheck
npm run lint
npm run test -- --run
npm run test -- --run --coverage
```

## 文档

详细文档请查看: [docs/INDEX.md](docs/INDEX.md)

### 核心文档

- **[综合技术文档](docs/reference/TECHNICAL_DOCS.md)** - 系统功能概览、API 模块、数据模型、部署运维
- [安装指南](docs/guides/INSTALLATION.md) - 环境配置和安装
- [快速上手](docs/guides/QUICKSTART.md) - 完成首次回测
- **[API 概览](docs/reference/API_OVERVIEW.md)** - RESTful API 接口说明
- [API 使用指南](docs/guides/API_GUIDE.md) - API 调用示例和最佳实践
- [开发指南](docs/how-to/DEVELOPMENT.md) - 本地开发环境配置
- [架构设计](docs/explanation/ARCHITECTURE.md) - 整体架构设计
- [数据库设计](docs/reference/DATABASE.md) - 数据模型和关系
- [安全指南](docs/reference/SECURITY.md) - 安全最佳实践
- [AI 策略 Copilot](docs/guides/AI_STRATEGY_COPILOT.md) - AI 助手、自然语言策略生成、工作区接入、回测、自动报告与复盘说明
- [Docker 部署](docs/docs/zh/deployment/docker.md) - 容器化部署和运维
- [投资组合账本](docs/guides/PORTFOLIO_LEDGER.md) - 独立账本与聚合组合视图的边界
- [迭代历史](docs/iterations/README.md) - 当前活跃迭代与历史迭代索引
- [策略开发](docs/guides/STRATEGY_DEVELOPMENT.md) - 如何编写交易策略
- [更新日志](docs/CHANGELOG.md) - 版本更新记录

### 其他文档

- [代码规范](docs/reference/CODING_STANDARDS.md) - Python/Vue 代码风格
- [测试指南](docs/how-to/TESTING.md) - 单元测试、E2E 测试
- [贡献指南](CONTRIBUTING.md) - 开发流程与 PR 规范
- [CI/CD](docs/operations/CI_CD.md) - GitHub Actions 流水线
- [无障碍基线 (Accessibility Baseline)](docs/explanation/accessibility-baseline.md) - WCAG 2.1 AA 基线、Critical_Page_Set 扫描结果与必要豁免（迭代 175 §3）
- [前端 Bundle 体积基线](docs/reference/frontend-bundle-budget.md) - vendor chunk 与 entry chunk gzip 体积基线（迭代 175 §7）
- [数据库迁移 Playbook](docs/how-to/database-migration-playbook.md) - 长锁/全表扫描风险与降级策略（迭代 175 §8）
- [Python Monorepo 选型说明](docs/explanation/python-monorepo.md) - uv workspace 选型与 vendored 包处理（迭代 175 §9）

## 版本计划

### v1.x（当前）

- 持续完善数据可信度、策略与回测、AI 研究工作流、模拟/实盘运行和组合风险视图。
- 部分旧版 API 已标记废弃，但仍保持向后兼容；新集成应优先使用 `/api/v1/backtests/*`、`/api/v1/live-trading/*` 和 `/api/v1/data/trust/*`。
- 路线与当前迭代状态请查看 [迭代历史](docs/iterations/README.md)。

## 参与贡献

请参阅 [CONTRIBUTING.md](CONTRIBUTING.md) 获取完整贡献指南。

## 许可证

[MIT License](LICENSE)
