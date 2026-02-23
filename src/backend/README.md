# Backtrader Web Backend

FastAPI-based backend service for the Backtrader Web quantitative backtesting platform.

## Features

- **Authentication** — JWT tokens + bcrypt password hashing
- **Backtest Engine** — Async backtest execution with result persistence
- **Strategy Management** — CRUD, 100+ built-in templates, YAML config auto-scan
- **Strategy Version Control** — Branching, comparison, rollback (Git-like workflow)
- **Paper Trading** — Simulated live trading sessions
- **Parameter Optimization** — Grid search and genetic algorithm support
- **Portfolio Management** — Multi-strategy portfolio construction
- **Real-time Data** — Market data feeds and subscriptions
- **Strategy Comparison** — Side-by-side performance analysis
- **Analytics & Reports** — HTML/PDF/Excel report generation
- **System Monitoring** — Health checks, metrics, alerts
- **Database Abstraction** — SQLite/PostgreSQL/MySQL via env config
- **Caching** — Optional Redis cache layer
- **Sandbox** — Secure execution of user-uploaded strategy code

## Quick Start

### 1. Install Dependencies

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env to configure database, JWT secret, etc.
```

### 3. Start the Server

```bash
# Development mode (auto-reload)
uvicorn app.main:app --reload --port 8000

# Or run directly
python -m app.main
```

### 4. API Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Project Structure

```
backend/
├── app/
│   ├── api/                        # API routes
│   │   ├── auth.py                 # Authentication
│   │   ├── backtest.py             # Basic backtest
│   │   ├── backtest_enhanced.py    # Enhanced backtest with analyzers
│   │   ├── strategy.py             # Strategy CRUD + templates
│   │   ├── strategy_version.py     # Version control + branches
│   │   ├── comparison.py           # Strategy comparison
│   │   ├── paper_trading.py        # Paper trading
│   │   ├── optimization_api.py     # Parameter optimization
│   │   ├── portfolio_api.py        # Portfolio management
│   │   ├── realtime_data.py        # Real-time data feeds
│   │   ├── monitoring.py           # System monitoring
│   │   ├── analytics.py            # Analytics dashboards
│   │   ├── data.py                 # Market data (AkShare)
│   │   ├── live_trading_api.py     # Live trading
│   │   ├── deps.py                 # Dependency injection
│   │   └── router.py               # Route registry
│   ├── db/                         # Database layer
│   │   ├── base.py                 # Repository interface
│   │   ├── database.py             # Engine + session factory
│   │   ├── sql_repository.py       # SQL implementation
│   │   ├── factory.py              # Repository factory
│   │   └── cache.py                # Cache abstraction
│   ├── models/                     # SQLAlchemy ORM models
│   ├── schemas/                    # Pydantic request/response schemas
│   ├── services/                   # Business logic
│   │   ├── auth_service.py
│   │   ├── backtest_service.py
│   │   ├── strategy_service.py
│   │   ├── strategy_version_service.py
│   │   ├── comparison_service.py
│   │   ├── paper_trading_service.py
│   │   ├── optimization_service.py
│   │   ├── monitoring_service.py
│   │   ├── report_service.py
│   │   └── ...
│   ├── utils/                      # Utilities
│   │   ├── sandbox.py              # Strategy code sandbox
│   │   ├── security.py             # JWT + password utils
│   │   └── logger.py               # Logging config
│   ├── config.py                   # Settings (pydantic-settings)
│   └── main.py                     # FastAPI app entry point
├── tests/                          # 1200+ tests, 100% coverage
├── requirements.txt
├── pyproject.toml
└── .env.example
```

## API Endpoints

All endpoints require JWT authentication unless noted.

### Authentication (public)

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

### Strategy

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
| POST | `/api/v1/strategy-versions/versions/compare` | Compare versions |
| POST | `/api/v1/strategy-versions/versions/rollback` | Rollback |
| POST | `/api/v1/strategy-versions/branches` | Create branch |

### Paper Trading

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/paper-trading/sessions` | Create session |
| GET | `/api/v1/paper-trading/sessions` | List sessions |
| POST | `/api/v1/paper-trading/sessions/{id}/start` | Start |
| POST | `/api/v1/paper-trading/sessions/{id}/stop` | Stop |

### Optimization

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/optimization/tasks` | Create task |
| GET | `/api/v1/optimization/tasks` | List tasks |
| GET | `/api/v1/optimization/tasks/{id}` | Get result |

### Portfolio

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/portfolio/` | Create portfolio |
| GET | `/api/v1/portfolio/` | List portfolios |

### Monitoring

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/monitoring/health` | Health check |
| GET | `/api/v1/monitoring/metrics` | Metrics |

## Testing

```bash
# Run all tests
pytest tests/

# With coverage
pytest tests/ --cov=app --cov-report=term-missing

# Single file
pytest tests/test_auth.py -v
```

**Status: 1218 tests, 100% code coverage.**

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_TYPE` | `sqlite` | Database type (sqlite/postgresql/mysql) |
| `DATABASE_URL` | `sqlite+aiosqlite:///./backtrader.db` | Connection URL |
| `JWT_SECRET_KEY` | (auto) | JWT signing secret |
| `JWT_EXPIRE_MINUTES` | `1440` | Token TTL in minutes |
| `DEBUG` | `true` | Debug mode |
| `SQL_ECHO` | `false` | SQLAlchemy query logging |

## License

MIT
