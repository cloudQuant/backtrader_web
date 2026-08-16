# AI for Investor

AI 驱动的量化研究、策略生成、回测验证与交易辅助平台。

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![Vue](https://img.shields.io/badge/Vue-3-green.svg)](https://vuejs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-teal.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[中文文档](https://cloudquant.github.io/backtrader_web/) · [English docs](https://cloudquant.github.io/backtrader_web/en/) · [本地 API 文档](http://localhost:8000/docs)

## 项目定位

AI for Investor 面向量化交易者与投研团队，将自然语言研究、知识库检索、策略开发、数据预检、回测验证、交易工作区和组合风险观察连接成可追溯的工作流。它帮助研究人员更快形成和验证假设，但不替代数据校验、风险控制或人工交易决策。

## 从问题到可验证结果

| 阶段 | 在平台中完成什么 | 主要入口 |
| --- | --- | --- |
| 研究依据 | 检索团队规范、数据说明和历史复盘，并查看引用来源 | `/ai/chat`、`/ai/knowledge-base` |
| 策略形成 | 创建、审查或生成 Backtrader 策略草案及研究目标 | `/investment/strategies` |
| 数据确认 | 选择标的、检查覆盖与质量，必要时主动刷新在线行情 | `/data/market` |
| 验证与迭代 | 运行回测、阅读指标/交易统计、执行稳健性或参数优化 | `/research/workspaces`、`/backtest` |
| 运行与风险观察 | 管理经审核的运行单元，查看账户、持仓、P&L 与回撤 | `/trading`、`/portfolio` |

## 核心能力

| 领域 | 能力 |
| --- | --- |
| AI 与知识 | 知识库、文档索引、引用型问答、词法检索、可选语义检索、策略构思与审查、AI 投研 |
| 数据可信度 | MySQL 行情仓本地优先、AkShare 显式刷新、覆盖矩阵、质量检查、历史补齐缓存与回测前预检 |
| 策略与回测 | Backtrader、策略版本、内置模板、统一指标、回测报告、研究工作区、稳健性验证与参数优化 |
| 交易与组合 | 研究/交易工作区、模拟运行、网关状态、账户/持仓/成交、累计 P&L、回撤和资产配置 |
| 工程化 | FastAPI、Vue 3、SQLAlchemy、SQLite/PostgreSQL/MySQL、pytest、Vitest、Playwright 与 OpenTelemetry |

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 20+
- Git
- Docker Compose v2（可选）

### 本地开发

```bash
git clone https://github.com/cloudQuant/backtrader_web.git
cd backtrader_web

./scripts/dev/verify-dev-env.sh --preinstall

# 后端
cd src/backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev,backtrader]"
# 需要在线 AkShare 查询时：pip install -e ".[dev,backtrader,data]"
# 需要语义向量检索时：pip install -e ".[dev,backtrader,rag]"
cp .env.example .env

# 前端
cd ../frontend
npm install

cd ../..
./scripts/dev/verify-dev-env.sh --postinstall
```

分别启动后端和前端：

```bash
cd src/backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000
```

```bash
cd src/frontend && npm run dev
```

- 前端：<http://localhost:3000>
- API / Swagger：<http://localhost:8000/docs>
- 健康检查：<http://localhost:8000/health>

### Docker

Compose 基础文件位于 `docker/docker-compose.yml`，需配合环境覆盖文件使用：

```bash
# 开发环境
docker compose -f docker/docker-compose.yml -f docker/compose/dev.yml up

# 生产环境（先配置受保护的环境变量）
docker compose -f docker/docker-compose.yml -f docker/compose/prod.yml up -d
```

生产环境的密钥、数据库密码、CORS 与备份要求见 [部署文档](docs/docs/zh/deployment/production.md)。

## 首次体验建议

1. 在 **数据 → 市场数据**选择资产类别和标的，检查数据覆盖和质量。
2. 需要最新行情时点击**查询**；这才会请求 AkShare，普通页面打开与标的切换优先读取本地 MySQL 行情仓。
3. 在 **投研 → 策略**选择模板、已有策略或 AI 草案，并审查标的、周期、成本与风险假设。
4. 将策略加入**研究工作区**，运行回测并查看交易次数、资金曲线、回撤和稳健性结果。
5. 只有经过人工审核后，才将方案放入**交易工作区**；再通过组合页核对账户、持仓、成交和风险视图。

## 重要边界

- **知识库不是整库喂给模型。** 系统先在选定知识库的已索引文档块中检索，再由可选模型组织回答。`not_indexed`、`no_context_found`、`ai_not_configured` 和 `ai_provider_failed` 都有明确诊断含义。
- **行情页本地优先。** 在线 AkShare 请求失败、无数据或不覆盖所选区间时，系统保留可用 MySQL 数据，并返回脱敏、可操作的提示。
- **AI 策略必须复核。** “生成研究目标”允许选择默认方案或由当前模型优化；模型不可用时保留默认方案。策略代码在受限环境中运行，禁止覆盖 `self.close()` 等交易方法；价格序列应使用 `self.dataclose` 等自定义属性保存。
- **回测不是实盘许可。** 回测指标、RAG 回答和 AI 输出都需要人工复核；真实网关与账户权限属于高风险边界。

## 项目结构

```text
backtrader_web/
├── src/
│   ├── backend/             # FastAPI、SQLAlchemy、Backtrader 与领域服务
│   └── frontend/            # Vue 3、TypeScript、Pinia 与 ECharts
├── strategies/              # 内置策略模板与示例
├── scripts/                 # 开发、运维、迁移与 CI 工具
├── docker/                  # Compose 基础文件与环境覆盖文件
├── tests/                   # 端到端与辅助测试资源
└── docs/                    # 发布文档、工程手册、迭代记录与历史归档
```

## API 与配置

所有业务 API 位于 `/api/v1`。当前运行环境中可用的端点、认证要求和请求/响应模型以 Swagger 为准：<http://localhost:8000/docs>。常用领域包括：

| 领域 | 前缀 |
| --- | --- |
| 认证与状态 | `/auth`、`/status` |
| 策略、回测与优化 | `/strategy`、`/backtests`、`/analytics`、`/optimization` |
| 工作区、运行与组合 | `/workspace`、`/paper-runtimes`、`/live-trading`、`/portfolio` |
| 数据与可信度 | `/data`、`/data/trust`、`/quote` |
| 知识库与 AI | `/knowledge-base`、`/rag`、`/kb-chat` |

关键环境变量保存在 `src/backend/.env` 或受保护的部署环境中：

| 配置 | 用途 |
| --- | --- |
| `DATABASE_TYPE`、`DATABASE_URL` | 应用数据库（SQLite / PostgreSQL / MySQL） |
| `AKSHARE_DATA_DATABASE_URL` | 独立的 MySQL 行情数据仓 |
| `AI_CHAT_*` | OpenAI-compatible 生成模型接入 |
| `RAG_VECTOR_*` | 可选语义检索的模型、集合和批处理设置 |
| `SECRET_KEY`、`JWT_SECRET_KEY` | 加密与 JWT 签名；生产环境必须使用不同的高熵值 |

不要提交 `.env`、数据库导出、证书、网关或模型凭据。

## 验证命令

```bash
# 后端
cd src/backend
ruff check app tests
pytest -m "not e2e" -q --tb=short
mypy app

# 前端
cd src/frontend
npm run typecheck
npm run lint
npm run test -- --run
npm run build

# 文档（仓库根目录）
python -m mkdocs build -f docs/mkdocs.yml --strict
python scripts/ci/check_doc_links.py
```

## 文档与贡献

| 目标 | 入口 |
| --- | --- |
| 在线文档（中文） | <https://cloudquant.github.io/backtrader_web/> |
| 在线文档（English） | <https://cloudquant.github.io/backtrader_web/en/> |
| 产品概览与投研流程 | [项目介绍](docs/project-introduction/ai-for-investor-project-introduction.md) / [中文文档首页源码](docs/docs/zh/index.md) |
| 安装、知识库、市场数据、策略与回测 | [快速开始与功能文档](docs/docs/zh/getting-started/index.md) |
| 架构、API、数据库与配置 | [开发文档](docs/docs/zh/development/index.md) |
| Docker 与生产运维 | [部署文档](docs/docs/zh/deployment/index.md) |
| 文档分层与归档策略 | [文档导航](docs/INDEX.md) |
| 贡献规范 | [CONTRIBUTING.md](CONTRIBUTING.md) |

当前处于 `v1.x` 持续演进阶段。旧迭代、已完成方案和专项报告位于 `docs/iterations/`、`docs/archive/` 和 `docs/reports/archive/`，仅用于追溯，不应替代当前操作文档。

## 相关项目

与 backtrader_web 同属 cloudQuant 量化体系的相关资源：

| 项目 | 简介 |
| --- | --- |
| [backtrader](https://github.com/cloudQuant/backtrader) | 专业 Python 算法交易框架（回测 + 实盘），本仓库策略研究引擎的基础 fork。 |
| [backtrader-skills](https://github.com/cloudQuant/backtrader-skills) | 离线可独立安装的策略"作者/评审/测试"产品：把本地数据集与 StrategySpec v1 转成 pytest 策略或三文件包，静态评审后在独立子进程中验证。 |
| [backtrader-mcp](https://github.com/cloudQuant/backtrader-mcp) | 本地优先的 MCP 服务器：CSV 固化为不可变数据集，类型化策略意图转为私有草稿，经评审后在受限子进程中运行并产出状态与报告（离线、仅回测）。 |
| [backtrader_web](https://github.com/cloudQuant/backtrader_web) | 本仓库：基于 Web 的 Backtrader 全周期策略管理工具，覆盖回测分析、模拟交易、实盘执行与数据管理。 |
| [backtrader-agent](https://github.com/cloudQuant/backtrader-agent) | 离线优先的策略编写 agent 运行时：内容寻址存储、策略规范校验、14 种脚手架、静态评审、哈希绑定审批、固定子进程执行与会话溯源。 |
| [fincore](https://github.com/cloudQuant/fincore) | 统一 Python 工具集：金融指标、绩效分析、回测、AI 洞察与多数据库/多数据源支持，服务量化金融工作流。 |

## 许可证

[MIT License](LICENSE)
