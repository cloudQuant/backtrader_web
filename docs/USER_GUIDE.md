# User Guide

This repository contains a full-stack Backtrader-based backtesting web platform.

## Run Locally

### Backend (FastAPI)

```bash
cd src/backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Open:

- API docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

### Example Scripts

After the backend is running, you can try:

- `python examples/backend_api_quickstart.py --base-url http://localhost:8000`
- `python examples/backend_api_enhanced_backtest_demo.py --base-url http://localhost:8000`
- `python examples/backend_api_paper_trading_demo.py --base-url http://localhost:8000`
- `python examples/backend_api_market_data_demo.py --base-url http://localhost:8000`
- `python examples/backend_api_portfolio_demo.py --base-url http://localhost:8000`
- `python examples/backend_api_optimization_demo.py --base-url http://localhost:8000`
- `python examples/backend_api_monitoring_demo.py --base-url http://localhost:8000`

### Frontend (Vue 3)

```bash
cd src/frontend
npm install
npm run dev
```

Open: `http://localhost:5173`

## Typical Workflow

1. Register and login.
2. Browse built-in strategy templates in the Strategy page (or via API).
3. Run a backtest.
4. Watch progress via WebSocket (optional) and view results.
5. Export reports (HTML/PDF/Excel) when enabled.

## WebSocket (Backtest Progress)

The backend exposes:

- `ws://localhost:8000/ws/backtest/{task_id}` (app-level endpoint)
- `ws://localhost:8000/api/v1/backtests/ws/backtest/{task_id}` (enhanced router endpoint)

The exact path depends on which UI/API you use. See the OpenAPI docs for the router you are calling.
