# Backtrader Web — Project Context

> LLM-optimized project context for AI agent consistency.
> Last updated: 2026-05-20

## Identity

**Name**: Backtrader Web
**Type**: Full-stack quantitative trading platform (open-source)
**License**: MIT
**Repo**: github.com/cloudQuant/backtrader_web
**Stage**: v0.1.0 (initial public release)

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Backend | Python + FastAPI + SQLAlchemy 2.0 (async) | Python 3.10+ |
| Frontend | Vue 3 + TypeScript + Vite + Element Plus | Node 20+ |
| Database | SQLite (default) / PostgreSQL / MySQL | Multi-driver |
| Backtest Engine | Backtrader + fincore (metrics) | 1.9.78+ |
| AI/RAG | OpenAI-compatible chat/completions + vector search | Optional |
| Data | Akshare + MySQL sync | 1.12+ |
| Observability | OpenTelemetry (traces + metrics) | 1.20+ |
| Testing | pytest (backend) + Vitest + Playwright (frontend) | Latest |
| CI/CD | GitHub Actions (lint, test, security, Lighthouse) | Multi-job |

## Architecture Overview

```text
Browser (Vue 3 SPA)
    │ HTTP / WebSocket
    ▼
Nginx / Vite Dev Server
    │
    ▼
FastAPI + Uvicorn (async)
    ├── Middleware: exception handling, security headers, logging, rate limiting
    ├── API Layer: 15+ core routers + 18 optional routers (graceful degradation)
    ├── Service Layer: 60+ services (business logic)
    ├── DB Layer: Repository pattern + factory (SQLite/PG/MySQL)
    └── External: Akshare (data), CCXT/CTP (trading), OpenAI-compatible (AI)
```

## Key Modules

| Module | Backend Routes | Frontend Pages | Status |
|--------|---------------|----------------|--------|
| Auth (JWT) | `/api/v1/auth` | Login, Register | Stable |
| Strategy | `/api/v1/strategy` | StrategyPage | Stable |
| Backtest | `/api/v1/backtests` | Workspace (research) | Stable |
| Analytics | `/api/v1/analytics` | BacktestResult | Stable |
| Optimization | `/api/v1/optimization` | Workspace detail | Stable |
| Live Trading | `/api/v1/live-trading` | Workspace (trading) | Stable |
| Paper Trading | `/api/v1/paper-trading` | Workspace (trading) | Stable |
| Data Management | `/api/v1/data` | Data (8 sub-pages) | Stable |
| Knowledge Base | `/api/v1/knowledge-base` | KnowledgeBasePage | Stable |
| RAG / KB Chat | `/api/v1/rag`, `/api/v1/kb-chat` | AIChatPage | Stable |
| AI Trading | `/api/v1/ai-trading` | AITradingPage | Beta |
| Portfolio | `/api/v1/portfolio` | PortfolioPage | Stable |
| Monitoring | `/api/v1/monitoring` | (alerts) | Stable |
| Quote / Realtime | `/api/v1/quote`, `/api/v1/realtime` | QuotePage | Stable |
| Risk Control | `/api/v1/risk-control` | (integrated) | Beta |

## Strategies

- **118 backtest templates** (strategies/backtest/000-118): MA, MACD, Bollinger, RSI, Turtle, Pairs, Ichimoku, Supertrend, etc.
- **5 live MT5 strategies** (strategies/live/mt5_001-005)
- **27 simulation strategies** (strategies/simulate/)
- **60+ user-generated** (UUID-named, config.yaml + strategy_generated.py)

## Engineering Standards

- **Lint**: Ruff (E, F, I, W, B, UP, C4), line-length 100
- **Type checking**: Mypy (strict on api/ and schemas/)
- **Test coverage**: Backend 70%+ (CI enforced), diff-cover 60% on PRs
- **Security**: Bandit scanning, safety checks, parameterized queries
- **CI gates**: Generated artifact check, doc link validation, deps sync, OpenAPI validation, migration check
- **ADRs**: 10 documented (Element Plus auto-import, PyJWT, caching, graceful shutdown, OpenTelemetry, multi-theme, responsive layout, deprecated API removal, Alembic chain, Docker quick-start)

## Current Focus (Phase 1: 基础加固)

1. v0.1.0 release preparation (deprecated APIs removed ✅, migration chain unified ✅, version bumped ✅)
2. Test coverage improvement (portfolio 93% ✅, knowledge_base 94% ✅, paper_trading 82% ✅)
3. Documentation internationalization (English README ✅)
4. UI consistency and design system
5. Docker Hub official image

## File Structure (Key Paths)

```text
src/backend/
├── app/api/          # 40+ route modules
├── app/services/     # 60+ service files
├── app/models/       # 14 ORM models
├── app/schemas/      # 22 Pydantic DTOs
├── app/db/           # Repository + factory
├── app/middleware/    # 5 middleware modules
└── app/config.py     # Settings (Pydantic)

src/frontend/
├── src/views/        # 15+ pages
├── src/stores/       # 10 Pinia stores
├── src/api/          # 16 typed API modules
├── src/components/   # Organized by domain
├── src/composables/  # 5 composables
└── src/i18n/         # Internationalization

strategies/           # 118+ templates
docs/                 # 30+ documents
tests/                # 120+ test files
```

## Conventions

- **API routes**: kebab-case (`/live-trading`)
- **Python files**: snake_case
- **Vue components**: PascalCase.vue
- **Commits**: Conventional Commits (`feat(backtest): add cancel endpoint`)
- **Branches**: feature/*, fix/*, docs/*
- **Services**: One class per file, `@lru_cache` for singletons, async methods
- **Error handling**: Service returns None/False for expected failures; API converts to HTTPException
