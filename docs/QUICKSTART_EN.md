# Quick Start: Your First Backtest in 5 Minutes

This guide takes you from zero to running your first strategy backtest.

> **Prerequisites**: Python 3.10+, Node.js 20+, Git

---

## Step 1: Clone & Install (~2 minutes)

```bash
# Clone the project
git clone https://github.com/cloudQuant/backtrader_web.git
cd backtrader_web

# Backend setup
cd src/backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -e ".[dev,backtrader]"

# Create minimal config (SQLite, no external database needed)
cp .env.example .env
```

> Default uses SQLite — no PostgreSQL or MySQL installation required.

```bash
# Frontend setup (new terminal)
cd src/frontend
npm install
```

---

## Step 2: Start Services (~30 seconds)

Open two terminal windows:

**Terminal 1 — Backend:**

```bash
cd src/backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

You'll see `Uvicorn running on http://127.0.0.1:8000` when ready.

**Terminal 2 — Frontend:**

```bash
cd src/frontend
npm run dev
```

You'll see `Local: http://localhost:3000` when ready.

---

## Step 3: Register & Login (~30 seconds)

1. Open http://localhost:3000 in your browser
2. Click "Register", fill in username, email, and password
3. After registration, login with your credentials

---

## Step 4: Run Your First Backtest (~2 minutes)

### Option A: Web Interface (Recommended for Beginners)

1. After login, navigate to "Strategy Management" (策略管理)
2. Browse the "Strategy Templates" tab — 118 built-in strategies available
3. Select a template (e.g., "MA Cross Strategy") and click "Backtest"
4. Fill in parameters:
   - **Symbol**: `000001.SZ` (Ping An Bank)
   - **Date Range**: `2023-01-01` to `2023-12-31`
   - **Initial Capital**: `100000`
   - **Commission Rate**: `0.001`
5. Click "Start Backtest" and wait for completion
6. View results: equity curve, trade records, performance metrics

### Option B: REST API (Recommended for Developers)

```bash
# 1. Register
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "demo", "email": "demo@example.com", "password": "Test12345678"}'

# 2. Login and get token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "demo", "password": "Test12345678"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 3. List available strategy templates
curl -s http://localhost:8000/api/v1/strategy/templates \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# 4. Submit backtest (replace <template_id> with actual ID from step 3)
curl -X POST http://localhost:8000/api/v1/backtests/run \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_id": "<template_id>",
    "symbol": "000001.SZ",
    "start_date": "2023-01-01T00:00:00",
    "end_date": "2023-12-31T00:00:00",
    "initial_cash": 100000,
    "commission": 0.001,
    "params": {}
  }'

# 5. Get result (replace <task_id> with the returned task_id)
curl -s http://localhost:8000/api/v1/backtests/<task_id> \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

### Option C: Docker (Fastest)

```bash
docker compose up -d
# Frontend: http://localhost:3000
# API Docs: http://localhost:8000/docs
```

---

## Verify Success

After the backtest completes, you should see:

- ✅ **Total Return** — Strategy profit/loss percentage
- ✅ **Sharpe Ratio** — Risk-adjusted return metric
- ✅ **Max Drawdown** — Largest peak-to-trough decline
- ✅ **Trade Count** — Number of buy/sell signals generated

In the Web UI you can also view:
- 📈 Equity curve chart
- 📊 K-line chart with trade signal annotations
- 📋 Monthly return heatmap
- 📄 Export reports (HTML/PDF/Excel)

---

## Troubleshooting

### Backend startup error: `ModuleNotFoundError`

Ensure virtual environment is activated and dependencies installed:

```bash
cd src/backend
source venv/bin/activate
pip install -e ".[dev,backtrader]"
```

### Frontend blank page or CORS error

Confirm backend is running on port 8000. Vite automatically proxies `/api` requests.

### Backtest stuck in "pending" status

Check backend terminal for error logs. Common causes:
- Strategy code syntax error
- Data source not configured (built-in templates work without extra data)

### Want to use PostgreSQL/MySQL instead of SQLite?

Edit `src/backend/.env`:

```bash
DATABASE_TYPE=postgresql
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/backtrader
```

---

## What's Next?

| Goal | Documentation |
|------|---------------|
| Write custom strategies | [Strategy Development](STRATEGY_DEVELOPMENT.md) |
| Full API reference | [API Reference (EN)](API_REFERENCE_EN.md) |
| Parameter optimization | [API Reference - Optimization](API_REFERENCE_EN.md#parameter-optimization) |
| Paper trading | [API Reference - Paper Trading](API_REFERENCE_EN.md#paper-trading) |
| AI Strategy Copilot | [AI Strategy Copilot](AI_STRATEGY_COPILOT.md) |
| Local development | [Development Guide](DEVELOPMENT.md) |
| Production deployment | `docker-compose.prod.yml` in project root |
