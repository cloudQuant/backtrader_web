# Quick Start

Get your first backtest running in 5 minutes!

## Prerequisites

- [Installation](./installation.md) completed
- Services running (backend + frontend)

## Step 1: Access the Platform

Open your browser and navigate to:
- **Frontend**: http://localhost:8080 (development)
- **Backend API Docs**: http://localhost:8000/docs

## Step 2: Register an Account

1. Click "Register" on the frontend
2. Enter username, email, and password
3. Login with your new account

Or use the API directly:

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","email":"test@example.com","password":"testpass123"}'
```

## Step 3: Select a Strategy

Choose from **118 built-in strategy templates** including:

### Trend Following
- Dual Moving Average
- MACD
- Turtle Trading

### Mean Reversion
- Bollinger Bands
- KDJ
- RSI

### Arbitrage
- Spot-Futures Arbitrage
- Calendar Spread

### Options
- VIX Panic Index
- Put-Call Ratio

## Step 4: Configure Backtest

Set the following parameters:

| Parameter | Description | Example |
|-----------|-------------|---------|
| Strategy | Select from templates | Dual MA |
| Symbol | Trading symbol | 000001.SZ |
| Start Date | Backtest start | 2024-01-01 |
| End Date | Backtest end | 2024-12-31 |
| Initial Capital | Starting capital | 100000 |
| Commission | Trading commission | 0.001 |

## Step 5: Run Backtest

Click "Start Backtest" and wait for results (usually < 1 second per year of data).

## Step 6: View Results

### Analytics Dashboard

- **Equity Curve** - Portfolio value over time
- **Drawdown Curve** - Maximum drawdown visualization
- **Monthly Returns Heatmap** - Monthly performance
- **Trade Statistics** - Win rate, profit factor, etc.

### Key Metrics

| Metric | Description |
|--------|-------------|
| Total Return | Overall return percentage |
| Annual Return | Annualized return |
| Sharpe Ratio | Risk-adjusted return |
| Max Drawdown | Maximum peak-to-trough |
| Win Rate | Percentage of profitable trades |
| Profit Factor | Avg win / Avg loss |

## Next Steps

- [Strategy Management](../features/strategy-management.md) - Create and manage your own strategies
- [Parameter Optimization](../features/optimization.md) - Find optimal parameters
- [Paper Trading](../features/paper-trading.md) - Simulated trading with real data
- [Live Trading](../features/live-trading.md) - Connect to real brokers
