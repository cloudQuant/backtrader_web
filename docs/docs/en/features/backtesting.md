# Backtesting

## Overview

Backtrader Web's backtesting engine is built on **Backtrader** with **fincore** for standardized financial metrics.

## Key Features

- **Async Execution** - Non-blocking backtest runs
- **Progress Streaming** - Real-time progress via WebSocket
- **Multiple Data Sources** - AkShare, CSV, database
- **Standardized Metrics** - fincore-powered analytics
- **Report Export** - HTML/PDF/Excel reports

## API Endpoints

### Run Backtest

```http
POST /api/v1/backtests/run
Content-Type: application/json

{
  "strategy_id": 1,
  "symbol": "000001.SZ",
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "initial_cash": 100000,
  "commission": 0.001
}
```

### Get Backtest Result

```http
GET /api/v1/backtests/{task_id}
```

### List Backtest History

```http
GET /api/v1/backtests?page=1&page_size=20
```

## Financial Metrics

### Return Metrics
- Total Return
- Annual Return
- Excess Return

### Risk Metrics
- Maximum Drawdown
- Volatility
- Downside Risk

### Risk-Adjusted Returns
- Sharpe Ratio
- Sortino Ratio
- Calmar Ratio

### Trade Statistics
- Win Rate
- Profit Factor
- Average Holding Period

## WebSocket for Progress

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/backtest/{task_id}');
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(`Progress: ${data.progress}%`);
};
```

## Report Export

Export backtest results in multiple formats:

- **HTML** - Interactive charts
- **PDF** - Print-friendly report
- **Excel** - Raw data for analysis
