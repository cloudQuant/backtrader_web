# Paper Trading

## Overview

Paper trading provides a simulated trading environment with real market data, allowing you to test strategies without risking real capital.

## Features

- **Account Management** - Multiple paper trading accounts
- **Order Types** - Market, limit, stop-loss, take-profit
- **Position Tracking** - Real-time positions and P&L
- **Trade History** - Complete audit trail
- **WebSocket Updates** - Real-time order/position updates

## API Endpoints

### Create Session

```http
POST /api/v1/paper-trading/sessions
Content-Type: application/json

{
  "name": "My Paper Account",
  "initial_cash": 100000,
  "commission": 0.001
}
```

### List Sessions

```http
GET /api/v1/paper-trading/sessions
```

### Start Session

```http
POST /api/v1/paper-trading/sessions/{id}/start
```

### Stop Session

```http
POST /api/v1/paper-trading/sessions/{id}/stop
```

### Place Order

```http
POST /api/v1/paper-trading/orders
Content-Type: application/json

{
  "session_id": 1,
  "symbol": "000001.SZ",
  "direction": "long",  # long / short
  "order_type": "market",  # market / limit
  "quantity": 100,
  "price": null  # for market orders
}
```

### Get Positions

```http
GET /api/v1/paper-trading/sessions/{id}/positions
```

### Get Trades

```http
GET /api/v1/paper-trading/sessions/{id}/trades
```

## WebSocket for Real-time Updates

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/paper-trading/{session_id}');
ws.onmessage = (event) => {
  const update = JSON.parse(event.data);
  // Handle: order_update, position_update, trade_update
};
```
