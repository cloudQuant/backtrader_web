# Live Trading

## Overview

Connect to real brokers for live trading with Backtrader Web.

## Supported Brokers

| Broker | Type | Region |
|--------|------|--------|
| CTP | Futures | China |
| CCXT | Crypto Exchange | Global |

## Features

- **Multi-Account** - Support multiple broker accounts
- **Gateway Management** - Configurable connection parameters
- **Real-time Data** - Live market data streaming
- **Order Execution** - Market and limit orders
- **Risk Control** - Position limits, daily limits

## API Endpoints

### Gateway Management

```http
# List gateways
GET /api/v1/live-trading/gateways

# Add gateway
POST /api/v1/live-trading/gateways
{
  "broker": "ctp",
  "name": "My CTP Gateway",
  "config": {
    "front": "tcp://127.0.0.1:41205",
    "broker_id": "9999",
    "user_id": "your_user_id"
  }
}
```

### Live Trading Sessions

```http
# Create session
POST /api/v1/live-trading/sessions
{
  "gateway_id": 1,
  "strategy_id": 1,
  "symbols": ["rb2405"]
}

# Start session
POST /api/v1/live-trading/sessions/{id}/start

# Stop session
POST /api/v1/live-trading/sessions/{id}/stop
```

### Monitor Status

```http
GET /api/v1/live-trading/sessions/{id}/status
```

## Risk Controls

| Control | Description |
|---------|-------------|
| Single Trade Limit | Max quantity per order |
| Daily Trade Limit | Max orders per day |
| Max Position | Max position percentage |
| Auto Stop Loss | Automatic stop-loss execution |

## ⚠️ Important Notes

1. **Use with caution** - Live trading involves real capital
2. **Test first** - Always test thoroughly in paper trading
3. **Risk management** - Set appropriate risk controls
4. **Monitor closely** - Watch live trading sessions
