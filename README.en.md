# AI for Investor

**An AI + quant platform that takes traders from research questions to strategy drafts, backtests, and trading workflows.**

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB.svg?logo=python&logoColor=white)](https://python.org)
[![Vue 3](https://img.shields.io/badge/Vue-3.4+-4FC08D.svg?logo=vuedotjs&logoColor=white)](https://vuejs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/cloudQuant/backtrader_web/ci.yml?branch=master&label=CI&logo=githubactions&logoColor=white)](https://github.com/cloudQuant/backtrader_web/actions)

[中文文档](README.md) | **English**

[中文文档](https://cloudquant.github.io/backtrader_web/) · [English docs](https://cloudquant.github.io/backtrader_web/en/) · [Local API docs](http://localhost:8000/docs)

---

AI for Investor is an AI + quantitative trading MVP for developers, traders, and small research teams who want to turn market knowledge and natural-language strategy ideas into executable research workflows. Strategy development, backtesting, parameter optimization, paper trading, live trading, knowledge-base Q&A, and AI-assisted research are integrated in one product.

## Highlights

- 🚀 **5-Minute Quick Start** — Clone, install, run your first backtest
- 🤖 **AI Quant Copilot** — Knowledge Q&A → natural language strategy idea → strategy code → auto-backtest → performance report
- 📊 **Professional Charts** — ECharts K-line charts with 10+ analytical visualizations
- 🎯 **118 Built-in Strategies** — Ready-to-use templates covering momentum, mean-reversion, ML, and more
- 🔌 **API-First Design** — Every feature accessible via REST API; modular route registration with observable degradation
- 💾 **Multi-Database** — SQLite (zero-config default), PostgreSQL, or MySQL
- 🔴 **Research to Production** — Seamless path from backtest → paper trading → live trading (CTP/CCXT)
- 🧠 **Knowledge Base & RAG** — Document management, auto-indexing, citation navigation, AI-powered Q&A

## Key Features

### Strategy & Backtesting

- Strategy CRUD with built-in code editor and version control
- Subprocess-isolated backtest execution with multi-dimensional analysis
- Parameter optimization (grid search + Bayesian optimization)
- Strategy comparison and performance attribution
- 118 built-in strategy templates as starting points

### AI & Knowledge

- AI Strategy Copilot: knowledge Q&A, strategy ideation, code generation, strategy review
- RAG-powered knowledge base with document chunking and semantic search
- Strategy drafts can be saved, added to workspace, backtested, and auto-reviewed
- OpenAI-compatible API integration (works with any LLM provider)

### Trading

- Paper trading with simulated accounts and order management
- Live trading via CTP (futures) and CCXT (crypto: Binance, OKX, etc.)
- Real-time market data via WebSocket
- Monitoring and alerting system

### Data Management

- Akshare data interface integration
- Data scripts, scheduled tasks, and execution history
- Data table browser with MySQL sync support
- Direct MySQL mode (no SSH/Docker dependency)

### Platform

- JWT authentication with role-based access
- Workspace management (research & trading environments)
- Modular API with graceful degradation — failed optional modules don't crash the system
- Health checks and router status endpoint (`/api/v1/status/routers`)

## Quick Start (5 Minutes)

### Prerequisites

- Python 3.10+
- Node.js 20+
- Git

### Setup

```bash
# Clone
git clone https://github.com/cloudQuant/backtrader_web.git
cd backtrader_web

# Backend
cd src/backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e ".[dev,backtrader]"
cp .env.example .env

# Frontend (new terminal)
cd src/frontend
npm install
```

### Run

```bash
# Terminal 1 — Backend
cd src/backend
uvicorn app.main:app --reload --port 8000

# Terminal 2 — Frontend
cd src/frontend
npm run dev
```

### Access

| Service | URL |
| ------- | --- |
| Frontend | http://localhost:3000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| API Docs (ReDoc) | http://localhost:8000/redoc |
| WebSocket | ws://localhost:8000/ws |

### v0.2.0 RC1 Demo Path

RC1 lets you validate the shipped AI trust capabilities end to end:

1. Create or select a strategy, then run a backtest.
2. Open the backtest result page and inspect the strategy score card, overfitting diagnostics, and strategy explanation panel.
3. Use AI Assistant knowledge or strategy-generation mode to create a draft, save it to Strategy Center, or add it to a research workspace.
4. Run `cd src/backend && pytest tests/perf/ -q --tb=short` to inspect API and backtest-task throughput baselines.
5. Run `cd src/frontend && npm run test -- --run --coverage` to verify frontend coverage thresholds.

AI observability, multi-model routing, VaR/CVaR, factor analytics, performance attribution, and market-regime detection remain v0.2.x roadmap items. RC1 boundaries are documented in [v0.2.0 release notes](docs/explanation/RELEASE_NOTES_V0.2.0.md).

### Docker (Alternative)

```bash
docker compose -f docker-compose.yml -f docker/compose/prod.yml up -d
# Frontend: http://localhost | API: http://localhost:8000/docs
```

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Vue 3 Frontend                     │
│         TypeScript · Vite · Element Plus · ECharts   │
└──────────────────────┬──────────────────────────────┘
                       │ REST / WebSocket
┌──────────────────────▼──────────────────────────────┐
│                  FastAPI Backend                      │
│    Pydantic · SQLAlchemy 2.0 · Async · JWT Auth      │
├──────────────┬───────────────┬───────────────────────┤
│  API Layer   │ Service Layer │   Backtrader Engine    │
│  (15+ modules)│ (Business Logic)│ (Subprocess Isolation)│
└──────┬───────┴───────┬───────┴───────────┬───────────┘
       │               │                   │
┌──────▼───────┐ ┌─────▼──────┐  ┌────────▼──────────┐
│   Database   │ │  AI / RAG  │  │  Broker Gateways   │
│ SQLite/PG/MY │ │ OpenAI API │  │  CTP · CCXT · MT5  │
└──────────────┘ └────────────┘  └────────────────────┘
```

## API Modules

| Module | Endpoint Prefix | Description |
| ------ | --------------- | ----------- |
| Auth | `/api/v1/auth` | JWT registration, login, user management |
| Strategy | `/api/v1/strategy` | Strategy CRUD, templates, code editor |
| Backtests | `/api/v1/backtests` | Enhanced backtest execution and results |
| Analytics | `/api/v1/analytics` | Backtest data analysis and metrics |
| Optimization | `/api/v1/optimization` | Grid search and Bayesian parameter optimization |
| Paper Trading | `/api/v1/paper-trading` | Simulated accounts and orders |
| Live Trading | `/api/v1/live-trading` | Multi-broker live execution (CTP/CCXT) |
| Market Data | `/api/v1/quote`, `/api/v1/realtime` | Real-time and historical quotes |
| Monitoring | `/api/v1/monitoring` | Health checks, metrics, alert rules |
| Workspace | `/api/v1/workspace` | Research and trading workspace management |
| Data | `/api/v1/data` | Akshare data, scripts, tasks, sync |
| Knowledge Base | `/api/v1/knowledge-base` | Documents, folders, indexing status |
| RAG | `/api/v1/rag` | Document indexing, retrieval, Q&A |
| KB Chat | `/api/v1/kb-chat` | Knowledge base conversations and AI assistant |
| Status | `/api/v1/status` | System health, optional router status |

Full API documentation: [docs/guides/API_GUIDE.md](docs/guides/API_GUIDE.md)

## Technology Stack

| Layer | Technology |
| ----- | ---------- |
| Frontend | Vue 3 + TypeScript + Vite + Element Plus + ECharts |
| Backend | FastAPI + Uvicorn + Pydantic + SQLAlchemy 2.0 (async) |
| Database | SQLite (default) / PostgreSQL / MySQL |
| Backtest Engine | Backtrader + fincore (standardized metrics) |
| AI / RAG | Knowledge base chunking + OpenAI-compatible chat/completions |
| Data Sources | Akshare + custom scripts + MySQL sync |
| Auth | JWT + bcrypt |
| Testing | pytest + Playwright (E2E) + Vitest (frontend) |
| CI/CD | GitHub Actions (lint, test, build, deploy) |
| Code Quality | Ruff + pre-commit + conventional commits |

## Configuration

Copy `.env.example` to `.env` and customize:

```bash
# Database (default: SQLite, zero-config)
DATABASE_TYPE=sqlite
DATABASE_URL=sqlite+aiosqlite:///../../data/dev/backtrader.db

# PostgreSQL alternative
# DATABASE_TYPE=postgresql
# DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/backtrader

# JWT (MUST change in production)
SECRET_KEY=your-secret-key
JWT_SECRET_KEY=your-jwt-secret
JWT_EXPIRE_MINUTES=1440

# AI Strategy Copilot (optional)
AI_CHAT_ENABLED=false
AI_CHAT_BASE_URL=https://api.openai.com/v1
AI_CHAT_API_KEY=sk-...
AI_CHAT_MODEL=gpt-4o

# CORS (production)
CORS_ORIGINS=https://your-domain.com
```

> ⚠️ **Security**: Never commit real secrets. Replace all placeholder values before deploying to production.

## Testing

```bash
# Backend
cd src/backend
pytest                              # All tests
pytest --cov=app --cov-report=term  # With coverage
pytest tests/test_auth.py -v        # Single file

# Frontend
cd src/frontend
npm run test                        # Unit tests (Vitest)
npm run test -- --run --coverage    # Unit tests with coverage thresholds
npm run typecheck                   # TypeScript validation
npm run test:e2e                    # E2E tests (Playwright)
```

Frontend coverage thresholds are tightened gradually from measured baselines:

| Stage | lines/statements | functions | branches |
| ----- | ---------------- | --------- | -------- |
| Iteration 163 baseline | 29% | 35% | 40% |
| Iteration 169 / v0.2.0 RC | 34% | 40% | 45% |
| Future target | +5 per iteration until 60%+ | +5 per iteration until 60%+ | +5 per iteration until 60%+ |

## Project Structure

```
backtrader_web/
├── src/
│   ├── backend/              # FastAPI backend
│   │   ├── app/
│   │   │   ├── api/         # API routes (15+ modules)
│   │   │   ├── services/    # Business logic
│   │   │   ├── db/          # Database repositories
│   │   │   ├── models/      # SQLAlchemy ORM models
│   │   │   ├── schemas/     # Pydantic DTOs
│   │   │   └── middleware/  # Logging, security
│   │   └── strategies/      # Built-in strategy files
│   └── frontend/             # Vue 3 SPA
│       └── src/
│           ├── api/          # API client layer
│           ├── components/   # Reusable UI components
│           ├── views/        # Page views
│           └── stores/       # Pinia state management
├── strategies/               # 118 built-in strategy templates
├── examples/                 # API usage examples
├── tests/                    # Integration tests
├── docs/                     # 30+ documentation pages
└── scripts/                  # Dev and deployment scripts
```

## Contributing

We welcome contributions from the community. See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide.

**Quick version:**

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Follow [conventional commits](https://www.conventionalcommits.org/): `feat(backtest): add cancel endpoint`
4. Write tests for your changes
5. Submit a Pull Request

**Development tools:**

```bash
pip install pre-commit && pre-commit install  # Auto-lint on commit
ruff check src/backend                        # Python linting
npm run lint                                  # Frontend linting
```

## Roadmap

The project is in active development:

- **v0.1.0 (Current)**: Initial public release — clean API surface, 118 strategy templates, AI Copilot, full trading pipeline
- **v0.2 (2026 Q3)**: UI/UX overhaul, 85%+ test coverage, i18n, Docker Hub official image
- **v0.3 (2026 Q4)**: AI deep integration, smart risk control, natural language trading
- **Future**: Strategy marketplace, plugin system, multi-tenant, cloud-native deployment

See [docs/explanation/STRATEGIC_ROADMAP.md](docs/explanation/STRATEGIC_ROADMAP.md) for the full strategic plan.

## Documentation

| Document | Description |
| -------- | ----------- |
| [Published docs (English)](https://cloudquant.github.io/backtrader_web/en/) | Online documentation site (GitHub Pages) |
| [Published docs (中文)](https://cloudquant.github.io/backtrader_web/) | Online documentation site (GitHub Pages) |
| [Installation Guide](docs/guides/INSTALLATION.md) | Environment setup and installation |
| [Quick Start](docs/guides/QUICKSTART.md) | 5-minute first backtest tutorial |
| [API Usage Guide](docs/guides/API_GUIDE.md) | REST API examples and best practices |
| [Architecture](docs/explanation/ARCHITECTURE.md) | System design and decisions |
| [Development Guide](docs/how-to/DEVELOPMENT.md) | Local dev environment setup |
| [AI Strategy Copilot](docs/guides/AI_STRATEGY_COPILOT.md) | AI assistant and NL strategy generation |
| [Strategy Development](docs/guides/STRATEGY_DEVELOPMENT.md) | Writing custom trading strategies |
| [Database Design](docs/reference/DATABASE.md) | Data models and relationships |
| [Security Guide](docs/reference/SECURITY.md) | Security best practices |
| [v0.2.0 RC Release Notes](docs/explanation/RELEASE_NOTES_V0.2.0.md) | RC1 scope, validation commands, and known boundaries |
| [Testing Guide](docs/how-to/TESTING.md) | Unit, integration, and E2E testing |
| [Coding Standards](docs/reference/CODING_STANDARDS.md) | Python and Vue code style |
| [CI/CD](docs/operations/CI_CD.md) | GitHub Actions pipeline |
| [Accessibility Baseline](docs/explanation/accessibility-baseline.md) | WCAG 2.1 AA baseline, Critical_Page_Set scan results, exemptions (iter 175 §3) |
| [Frontend Bundle Budget](docs/reference/frontend-bundle-budget.md) | Vendor and entry chunk gzip budgets (iter 175 §7) |
| [Database Migration Playbook](docs/how-to/database-migration-playbook.md) | Long-lock / full-scan risks and downgrade strategy (iter 175 §8) |
| [Python Monorepo Choice](docs/explanation/python-monorepo.md) | uv workspace rationale and vendored-package handling (iter 175 §9) |
| [Changelog](CHANGELOG.md) | Version history |

## Related Projects

Other resources in the cloudQuant quant ecosystem:

| Project | Description |
| --- | --- |
| [backtrader](https://github.com/cloudQuant/backtrader) | Professional Python algorithmic trading framework (backtesting + live trading); the core fork powering this repo's strategy research engine. |
| [backtrader-skills](https://github.com/cloudQuant/backtrader-skills) | Offline, independently installable strategy author/review/test product: turns local datasets and StrategySpec v1 into pytest strategies or three-file bundles, statically reviewed and validated in isolated child processes. |
| [backtrader-mcp](https://github.com/cloudQuant/backtrader-mcp) | Local-first MCP server: CSVs become immutable datasets, typed strategy intent becomes private drafts, and reviewed drafts run in bounded subprocesses with durable status and reports (offline, backtest-only). |
| [backtrader_web](https://github.com/cloudQuant/backtrader_web) | This repository: a web-based full-cycle Backtrader strategy management tool covering backtesting analysis, paper trading, live execution, and data management. |
| [backtrader-agent](https://github.com/cloudQuant/backtrader-agent) | Offline-first strategy-authoring agent runtime: content-addressed storage, strategy-spec validation, 14 scaffolds, static review, hash-bound approvals, fixed child-process execution, and session provenance. |
| [fincore](https://github.com/cloudQuant/fincore) | Unified Python toolkit integrating financial metrics, performance analysis, backtesting, AI-driven insights, and multi-database/data source support for quantitative finance workflows. |

## License

[MIT License](LICENSE) — Use it freely for personal, commercial, or educational purposes.

---

<p align="center">
  Built with ❤️ for the quantitative trading community<br>
  <a href="https://github.com/cloudQuant/backtrader_web">GitHub</a> ·
  <a href="https://github.com/cloudQuant/backtrader_web/issues">Issues</a> ·
  <a href="https://github.com/cloudQuant/backtrader_web/discussions">Discussions</a>
</p>
