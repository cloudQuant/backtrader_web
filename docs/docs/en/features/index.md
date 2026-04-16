# Features Overview

Backtrader Web provides comprehensive quantitative trading functionality.

## Core Modules

| Module | Endpoint | Description |
|--------|----------|-------------|
| Authentication | `/api/v1/auth` | JWT auth, register, login |
| Strategy | `/api/v1/strategy` | CRUD, templates |
| Backtest | `/api/v1/backtests` | **Recommended** Enhanced backtest |
| Analytics | `/api/v1/analytics` | Backtest data analysis |
| Optimization | `/api/v1/optimization` | Parameter optimization |
| Paper Trading | `/api/v1/paper-trading` | Simulated accounts, orders |
| Live Trading | `/api/v1/live-trading` | Real accounts, orders |
| Quote Data | `/api/v1/quote`, `/api/v1/realtime` | Real-time quotes |
| Monitoring | `/api/v1/monitoring` | Alert rules |
| Workspace | `/api/v1/workspace` | Workspace management |

## Feature Details

- [Backtesting](./backtesting.md) - Historical data backtesting with fincore metrics
- [Strategy Management](./strategy-management.md) - CRUD, version control, templates
- [Paper Trading](./paper-trading.md) - Simulated trading environment
- [Live Trading](./live-trading.md) - Real broker integration
- [Parameter Optimization](./optimization.md) - Grid search, Bayesian optimization

> ⚠️ **Deprecation Notice**: Legacy `/api/v1/backtest/*` endpoints are deprecated. Please migrate to `/api/v1/backtests/*`
