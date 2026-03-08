# Backtrader Web

A modern, full-featured web backtesting platform built on [Backtrader](https://www.backtrader.com/).

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![Vue](https://img.shields.io/badge/Vue-3.4+-green.svg)](https://vuejs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-teal.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Features

- **Backtest Engine** — Run backtests on 100+ built-in strategy templates or your own custom strategies
- **Financial Metrics** — Standardized metrics via [fincore](https://github.com/quantopian/fincore) library
- **Strategy Version Control** — Branch, compare, and rollback strategy versions like Git
- **Paper Trading** — Simulate live trading with real-time market data
- **Parameter Optimization** — Grid search and genetic algorithm optimization
- **Portfolio Management** — Multi-strategy portfolio construction and monitoring
- **Real-time Data** — Live market data feeds and subscriptions
- **Strategy Comparison** — Side-by-side comparison of multiple strategies
- **Analytics & Reports** — HTML/PDF/Excel report generation with 10+ chart types
- **System Monitoring** — Health checks, performance metrics, and alerts
- **REST API** — Programmatic access to implemented platform modules

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Vue 3 + TypeScript + Vite + Element Plus + ECharts |
| Backend | FastAPI + Uvicorn + Pydantic + SQLAlchemy 2.0 |
| Database | SQLite (default) / PostgreSQL / MySQL |
| Backtest Engine | Backtrader |
| Financial Metrics | fincore (industry-standard calculations) |
| Auth | JWT + bcrypt |

## Quick Start

### Requirements

- Python 3.10+
- Node.js 20 LTS

### Installation

```bash
git clone https://gitee.com/xxx/backtrader_web.git
cd backtrader_web
./scripts/verify-dev-env.sh --preinstall

# Backend
cd src/backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -e ".[dev,backtrader]"
cp .env.example .env
python scripts/init_db.py --init-all
cd ../..
./scripts/verify-dev-env.sh --postinstall

cd src/backend
uvicorn app.main:app --reload --port 8000

# Frontend (new terminal)
cd src/frontend
npm ci
npm run dev
```

If the preinstall check fails, fix the reported Node or Python mismatch first. If
the postinstall check fails, reinstall backend dependencies and verify that the
installed `backtrader` package exposes `Analyzer`.

### Access

- **Frontend**: http://localhost:3000
- **Swagger API Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Project Structure

```
backtrader_web/
 ├── src/
 │   ├── backend/                # FastAPI backend
 │   │   ├── app/
 │   │   │   ├── api/            # API routes (auth, backtest, strategy, etc.)
 │   │   │   ├── services/       # Business logic layer
 │   │   │   ├── db/             # Database abstraction (SQLite/PostgreSQL/MySQL)
 │   │   │   ├── models/         # SQLAlchemy ORM models
 │   │   │   ├── schemas/        # Pydantic request/response schemas
 │   │   │   └── utils/          # Utilities (sandbox, security, logging)
 │   │   └── tests/              # Backend tests (pytest unit tests + coverage)
 │   └── frontend/               # Vue 3 frontend
 │       └── src/
 │           ├── api/            # API client
 │           ├── components/     # Reusable components
 │           ├── views/          # Page views
 │           └── stores/         # Pinia state management
 ├── strategies/                 # 100+ built-in strategy templates
 ├── examples/                   # Usage examples
 └── docs/                       # Documentation
```

## API Reference

All endpoints require JWT authentication (except `/api/v1/auth/register` and `/api/v1/auth/login`).

### Authentication

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/register` | Register a new user |
| POST | `/api/v1/auth/login` | Login and get JWT token |
| GET | `/api/v1/auth/me` | Get current user info |

### Backtest

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/backtest/run` | Run a backtest |
| GET | `/api/v1/backtest/{id}` | Get backtest result |
| GET | `/api/v1/backtest/` | List backtest history |
| DELETE | `/api/v1/backtest/{id}` | Delete a backtest |

### Strategy Management

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/strategy/` | Create user strategy |
| GET | `/api/v1/strategy/` | List user strategies |
| GET | `/api/v1/strategy/{id}` | Get strategy detail |
| PUT | `/api/v1/strategy/{id}` | Update strategy |
| DELETE | `/api/v1/strategy/{id}` | Delete strategy |
| GET | `/api/v1/strategy/templates` | List built-in templates |

### Strategy Version Control

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/strategy-versions/versions` | Create version |
| GET | `/api/v1/strategy-versions/strategies/{id}/versions` | List versions |
| GET | `/api/v1/strategy-versions/versions/{id}` | Get version detail |
| PUT | `/api/v1/strategy-versions/versions/{id}` | Update version |
| POST | `/api/v1/strategy-versions/versions/compare` | Compare two versions |
| POST | `/api/v1/strategy-versions/versions/rollback` | Rollback to version |
| POST | `/api/v1/strategy-versions/branches` | Create branch |
| GET | `/api/v1/strategy-versions/strategies/{id}/branches` | List branches |

### Paper Trading

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/paper-trading/sessions` | Create paper trading session |
| GET | `/api/v1/paper-trading/sessions` | List sessions |
| POST | `/api/v1/paper-trading/sessions/{id}/start` | Start session |
| POST | `/api/v1/paper-trading/sessions/{id}/stop` | Stop session |

### Parameter Optimization

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/optimization/tasks` | Create optimization task |
| GET | `/api/v1/optimization/tasks` | List tasks |
| GET | `/api/v1/optimization/tasks/{id}` | Get task result |

### Portfolio Management

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/portfolio/` | Create portfolio |
| GET | `/api/v1/portfolio/` | List portfolios |
| POST | `/api/v1/portfolio/{id}/strategies` | Add strategy to portfolio |

### Monitoring

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/monitoring/health` | System health check |
| GET | `/api/v1/monitoring/metrics` | Performance metrics |
| GET | `/api/v1/monitoring/alerts` | Active alerts |

## Examples

| Example | Description |
|---------|-------------|
| `backend_api_quickstart.py` | Register, login, fetch strategy templates |
| `backend_api_enhanced_backtest_demo.py` | Run enhanced backtest with analyzers |
| `backend_api_market_data_demo.py` | Fetch A-share kline data via AkShare |
| `backend_api_monitoring_demo.py` | System monitoring and health checks |
| `backend_api_optimization_demo.py` | Parameter grid search optimization |
| `backend_api_paper_trading_demo.py` | Paper trading session management |
| `backend_api_portfolio_demo.py` | Portfolio construction and management |
| `backend_api_strategy_version_demo.py` | Version control, branching, rollback |
| `backend_api_comparison_demo.py` | Side-by-side strategy comparison |
| `backend_api_realtime_data_demo.py` | Real-time data subscriptions |
| `demo_custom_strategy.py` | Custom strategy with Backtrader + WebServer |
| `demo_webserver.py` | Minimal WebServer demo |

Run any example:

```bash
python examples/backend_api_quickstart.py --base-url http://localhost:8000
```

## Configuration

Environment variables (`.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_TYPE` | `sqlite` | Database type (sqlite/postgresql/mysql) |
| `DATABASE_URL` | `sqlite+aiosqlite:///./backtrader.db` | Database connection URL |
| `JWT_SECRET_KEY` | (auto-generated) | JWT signing secret |
| `JWT_EXPIRE_MINUTES` | `1440` | Token expiration (minutes) |
| `DEBUG` | `true` | Debug mode |
| `SQL_ECHO` | `false` | SQLAlchemy query logging |

## Testing

```bash
cd src/backend

# Run all tests
pytest tests/

# With coverage report
pytest tests/ --cov=app --cov-report=term-missing

# Run a specific test file
pytest tests/test_auth.py -v
```

Current status: **1218+ tests, 100% code coverage**.

## Documentation

- **[Installation Guide](docs/INSTALLATION.md)** — Quick start and setup
- **[Deployment Guide](docs/DEPLOYMENT.md)** — Production deployment
- **[Operations Guide](docs/OPERATIONS.md)** — System administration
- **[Backend README](src/backend/README.md)** — Backend architecture
- **[Fincore Migration Guide](src/backend/FINCORE_MIGRATION.md)** — Metrics integration

## Development

### Adding a New API Endpoint

1. Define schemas in `app/schemas/`
2. Implement service logic in `app/services/`
3. Create route in `app/api/`
4. Register route in `app/api/router.py`
5. Add tests in `tests/`

### Code Style

- Python: [Ruff](https://docs.astral.sh/ruff/) for linting and formatting
- Docstrings: Google style (English)
- Type hints: required for all public functions

## Contributing

1. Fork the repository
2. Create a feature branch (`feature/my-feature`)
3. Write tests for your changes
4. Submit a Pull Request

## License

[MIT License](LICENSE)
