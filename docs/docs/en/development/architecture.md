# System Architecture

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (Vue 3)                         │
│  Strategy Management | Backtest Analysis | Paper/Live Trading    │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTP/WebSocket
┌───────────────────────────┴─────────────────────────────────────┐
│                      API Gateway Layer (FastAPI)                  │
├─────────────────────────────────────────────────────────────────┤
│  Auth Middleware | Permission Middleware | Rate Limit | Logging  │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────┴─────────────────────────────────────┐
│                          Service Layer                            │
├──────────┬──────────┬──────────┬──────────┬──────────┬─────────┤
│ Strategy │ Backtest │  Paper   │  Live    │ Monitor  │  Data   │
│ Service  │ Service  │ Trading  │ Trading  │ Service  │ Service │
└──────────┴──────────┴──────────┴──────────┴──────────┴─────────┘
                            │
┌───────────────────────────┴─────────────────────────────────────┐
│                            Data Layer                             │
├────────────────────┬────────────────────┬────────────────────────┤
│  SQLite/PG/MySQL  │  Backtrader Engine │  Strategy Templates   │
│  (Users/Strategies)│  (Backtest/Live)   │  (118 built-in)      │
└────────────────────┴────────────────────┴────────────────────────┘
```

## Backend Architecture

### Layered Architecture

```
API Layer (app/api/)
    ↓
Service Layer (app/services/)
    ↓
Database Layer (app/db/)
    ↓
ORM Models (app/models/)
```

### Key Components

| Component | Path | Description |
|-----------|------|-------------|
| API Router | `app/api/router.py` | Aggregates all sub-routers |
| Auth Service | `app/services/auth_service.py` | JWT authentication |
| Backtest Service | `app/services/backtest_service.py` | Backtest orchestration |
| Strategy Service | `app/services/strategy_service.py` | Strategy CRUD |
| Live Trading | `app/services/live_trading_service.py` | Live trading coordination |

## Frontend Architecture

### Component Structure

```
src/
├── api/              # API client functions
├── components/       # Reusable Vue components
├── views/            # Page components
├── stores/           # Pinia state management
├── router/           # Vue Router configuration
└── utils/            # Utility functions
```

### State Management (Pinia)

| Store | Description |
|-------|-------------|
| `auth` | User authentication state |
| `strategy` | Strategy list and current strategy |
| `backtest` | Backtest tasks and results |
| `websocket` | WebSocket connection management |

## Database Design

### Key Tables

| Table | Description |
|-------|-------------|
| `users` | User accounts and profiles |
| `strategies` | User strategy definitions |
| `strategy_versions` | Strategy version history |
| `backtest_tasks` | Backtest task records |
| `optimization_tasks` | Optimization task records |
| `paper_trading_sessions` | Paper trading sessions |
| `live_trading_sessions` | Live trading sessions |

See [Database](./database.md) for detailed schema.
