# API Guide

The backend is a FastAPI service. The interactive OpenAPI docs are available at:

- `http://localhost:8000/docs`

All API routes are mounted under:

- `/api/v1`

## Auth

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`

## Strategy

- `GET /api/v1/strategy/templates`
- `GET /api/v1/strategy/templates/{template_id}`
- `GET /api/v1/strategy/templates/{template_id}/readme`
- `GET /api/v1/strategy/templates/{template_id}/config`

## Backtest

There are 2 sets of endpoints:

- Core backtest: `/api/v1/backtest/*`
- Enhanced backtest (includes optimization/report export/WebSocket): `/api/v1/backtests/*`

Prefer using the OpenAPI docs to confirm request/response schemas for your version.

## Enhanced Backtest (Recommended)

- `POST /api/v1/backtests/run`
- `GET /api/v1/backtests/{task_id}`
- `GET /api/v1/backtests/{task_id}/status`
- `GET /api/v1/backtests` (history)
- `GET /api/v1/backtests/{task_id}/report/html`
- `GET /api/v1/backtests/{task_id}/report/pdf`
- `GET /api/v1/backtests/{task_id}/report/excel`
- `WS /api/v1/backtests/ws/backtest/{task_id}`

## Paper Trading

- `POST /api/v1/paper-trading/accounts`
- `GET /api/v1/paper-trading/accounts`
- `POST /api/v1/paper-trading/orders`
- `GET /api/v1/paper-trading/orders`
- `GET /api/v1/paper-trading/positions`
- `GET /api/v1/paper-trading/trades`
- `WS /api/v1/paper-trading/ws/account/{account_id}`

## Market Data

- `GET /api/v1/data/kline`

## Examples

Scripts under `examples/` show end-to-end calls:

- `examples/backend_api_quickstart.py`
- `examples/backend_api_enhanced_backtest_demo.py`
- `examples/backend_api_paper_trading_demo.py`
- `examples/backend_api_market_data_demo.py`
- `examples/backend_api_portfolio_demo.py`
- `examples/backend_api_optimization_demo.py`
- `examples/backend_api_monitoring_demo.py`
