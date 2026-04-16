# API Reference

## Core API Modules

| Module | Endpoint Prefix | Description |
|--------|----------------|-------------|
| Authentication | `/api/v1/auth` | JWT auth, register, login |
| Strategy | `/api/v1/strategy` | CRUD, templates |
| Backtest | `/api/v1/backtests` | **Recommended** Enhanced backtest |
| Analytics | `/api/v1/analytics` | Backtest data analysis |
| Optimization | `/api/v1/optimization` | Parameter optimization |
| Paper Trading | `/api/v1/paper-trading` | Simulated accounts |
| Live Trading | `/api/v1/live-trading` | Real accounts |
| Quote Data | `/api/v1/quote`, `/api/v1/realtime` | Market data |
| Monitoring | `/api/v1/monitoring` | Alert rules |
| Workspace | `/api/v1/workspace` | Workspace management |

## Authentication

All endpoints require JWT authentication unless marked as public.

### Public Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/register` | Register new user |
| POST | `/api/v1/auth/login` | Login and get token |

### Protected Endpoints

Include `Authorization: Bearer <token>` header.

## WebSocket Endpoints

| Endpoint | Description |
|----------|-------------|
| `/ws/backtest/{task_id}` | Backtest progress |
| `/ws/paper-trading/{session_id}` | Paper trading updates |
| `/ws/live-trading/{session_id}` | Live trading updates |
| `/ws/realtime/{symbol}` | Real-time quotes |

## Deprecation Notice

> ⚠️ Legacy endpoints are deprecated. Please migrate to recommended endpoints:

| Legacy | Recommended |
|--------|-------------|
| `/api/v1/backtest/*` | `/api/v1/backtests/*` |
| `/api/v1/live-trading-crypto/*` | `/api/v1/live-trading/*` |

## Rate Limiting

Default rate limits:
- **Authenticated users**: 100 requests/minute
- **Public endpoints**: 20 requests/minute

## Error Responses

```json
{
  "detail": "Error message",
  "code": "ERROR_CODE"
}
```

| Status | Description |
|--------|-------------|
| 400 | Bad Request |
| 401 | Unauthorized |
| 403 | Forbidden |
| 404 | Not Found |
| 422 | Validation Error |
| 429 | Rate Limited |
| 500 | Internal Server Error |
