# API Reference (English)

> Version: 0.1.0 | Base URL: `/api/v1`

Interactive API documentation is available at runtime:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Postman Collection: `GET /api/v1/docs/postman`

---

## Authentication

All endpoints (except login/register) require a JWT token in the `Authorization: Bearer <token>` header.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/register` | Register a new user |
| POST | `/auth/login` | Login and receive JWT token |
| POST | `/auth/refresh` | Refresh access token |
| POST | `/auth/logout` | Logout (invalidate token) |
| PUT | `/auth/change-password` | Change password |
| GET | `/auth/me` | Get current user profile |

---

## Strategy Management

| Method | Path | Description |
|--------|------|-------------|
| POST | `/strategy/` | Create a custom strategy |
| GET | `/strategy/` | List user's strategies |
| GET | `/strategy/{id}` | Get strategy details |
| PUT | `/strategy/{id}` | Update strategy |
| DELETE | `/strategy/{id}` | Delete strategy |
| GET | `/strategy/templates` | List built-in strategy templates (118+) |
| GET | `/strategy/templates/{id}` | Get template details |
| GET | `/strategy/templates/{id}/readme` | Get template documentation |
| GET | `/strategy/templates/{id}/config` | Get template parameter config |

---

## Backtesting

| Method | Path | Description |
|--------|------|-------------|
| POST | `/backtests/run` | Submit a backtest task |
| GET | `/backtests/` | List backtest history (paginated, sortable) |
| GET | `/backtests/{task_id}` | Get backtest result |
| GET | `/backtests/{task_id}/status` | Get task status |
| GET | `/backtests/{task_id}/trades` | Get paginated trade records |
| POST | `/backtests/{task_id}/cancel` | Cancel a running task |
| DELETE | `/backtests/{task_id}` | Delete backtest result |
| GET | `/backtests/{task_id}/report/html` | Export HTML report |
| GET | `/backtests/{task_id}/report/pdf` | Export PDF report |
| GET | `/backtests/{task_id}/report/excel` | Export Excel report |
| WS | `/ws/backtest/{task_id}` | Real-time progress updates |

---

## Analytics

| Method | Path | Description |
|--------|------|-------------|
| GET | `/analytics/{task_id}/detail` | Full backtest analysis (metrics, equity, trades) |
| GET | `/analytics/{task_id}/kline` | K-line data with trading signals |
| GET | `/analytics/{task_id}/monthly-returns` | Monthly return breakdown |
| GET | `/analytics/{task_id}/export` | Export results (CSV/JSON) |

---

## Parameter Optimization

| Method | Path | Description |
|--------|------|-------------|
| POST | `/optimization/submit` | Submit optimization task (grid/bayesian) |
| GET | `/optimization/` | List optimization tasks |
| GET | `/optimization/{task_id}` | Get optimization result |
| GET | `/optimization/{task_id}/status` | Get task status |
| POST | `/optimization/{task_id}/cancel` | Cancel optimization |

---

## Paper Trading

| Method | Path | Description |
|--------|------|-------------|
| POST | `/paper-trading/accounts` | Create paper trading account |
| GET | `/paper-trading/accounts` | List accounts |
| GET | `/paper-trading/accounts/{id}` | Get account details |
| DELETE | `/paper-trading/accounts/{id}` | Delete account |
| POST | `/paper-trading/orders` | Submit order |
| GET | `/paper-trading/orders` | List orders (filterable) |
| GET | `/paper-trading/orders/{id}` | Get order details |
| DELETE | `/paper-trading/orders/{id}` | Cancel order |
| GET | `/paper-trading/positions` | List positions |
| GET | `/paper-trading/positions/{id}` | Get position details |
| GET | `/paper-trading/trades` | List trade history |
| WS | `/paper-trading/ws/account/{id}` | Real-time account updates |

---

## Live Trading

| Method | Path | Description |
|--------|------|-------------|
| GET | `/live-trading/` | List live trading instances |
| POST | `/live-trading/` | Create instance |
| GET | `/live-trading/{id}` | Get instance details |
| DELETE | `/live-trading/{id}` | Delete instance |
| POST | `/live-trading/{id}/start` | Start instance |
| POST | `/live-trading/{id}/stop` | Stop instance |
| POST | `/live-trading/start-all` | Start all instances |
| POST | `/live-trading/stop-all` | Stop all instances |
| GET | `/live-trading/{id}/detail` | Get trading analysis |
| GET | `/live-trading/{id}/kline` | Get K-line with signals |
| GET | `/live-trading/presets` | List gateway presets |
| GET | `/live-trading/gateways/health` | Gateway health status |
| POST | `/live-trading/gateways/connect` | Connect gateway |
| POST | `/live-trading/gateways/disconnect` | Disconnect gateway |
| GET | `/live-trading/gateways/connected` | List connected gateways |

---

## Portfolio

| Method | Path | Description |
|--------|------|-------------|
| GET | `/portfolio/overview` | Portfolio overview (aggregated metrics) |
| GET | `/portfolio/positions` | Aggregated positions across strategies |
| GET | `/portfolio/trades` | Aggregated trade history |
| GET | `/portfolio/equity` | Portfolio equity curve |
| GET | `/portfolio/allocation` | Strategy asset allocation |
| GET | `/portfolio/simulation/*` | Same endpoints for simulation trading |

---

## Knowledge Base

| Method | Path | Description |
|--------|------|-------------|
| GET | `/knowledge-base/` | List knowledge bases |
| POST | `/knowledge-base/` | Create knowledge base |
| GET | `/knowledge-base/{kb_id}` | Get knowledge base |
| PUT | `/knowledge-base/{kb_id}` | Update knowledge base |
| DELETE | `/knowledge-base/{kb_id}` | Delete knowledge base |
| GET | `/knowledge-base/{kb_id}/documents/` | List documents |
| POST | `/knowledge-base/{kb_id}/documents/` | Create document |
| GET | `/knowledge-base/{kb_id}/documents/{doc_id}` | Get document |
| PUT | `/knowledge-base/{kb_id}/documents/{doc_id}` | Update document |
| DELETE | `/knowledge-base/{kb_id}/documents/{doc_id}` | Delete document |

---

## RAG & AI Chat

| Method | Path | Description |
|--------|------|-------------|
| POST | `/rag/index` | Index documents for retrieval |
| POST | `/rag/search` | Semantic search in knowledge base |
| POST | `/kb-chat/` | Send message to AI assistant |
| GET | `/kb-chat/conversations` | List conversations |
| GET | `/kb-chat/conversations/{id}` | Get conversation history |

---

## Market Data

| Method | Path | Description |
|--------|------|-------------|
| GET | `/quote/` | Get real-time quotes |
| GET | `/quote/symbols` | List available symbols |
| GET | `/realtime/subscribe` | Subscribe to real-time data |
| GET | `/data/scripts` | List data fetch scripts |
| POST | `/data/scripts/{id}/run` | Execute data script |
| GET | `/data/tables` | List data tables |

---

## Monitoring & System

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/status/routers` | Optional router availability |
| GET | `/status/cache` | Cache statistics |
| GET | `/monitoring/alerts` | List alert rules |
| POST | `/monitoring/alerts` | Create alert rule |

---

## Common Response Patterns

### Success Response
```json
{
  "task_id": "abc123",
  "status": "completed",
  "data": { ... }
}
```

### Error Response
```json
{
  "detail": "Resource not found"
}
```

### Paginated Response
```json
{
  "total": 100,
  "items": [ ... ],
  "skip": 0,
  "limit": 20
}
```

---

## Rate Limiting

API responses include rate limit headers:
- `X-RateLimit-Limit`: Maximum requests per window
- `X-RateLimit-Remaining`: Remaining requests
- `X-RateLimit-Reset`: Window reset timestamp

When rate limited (HTTP 429), the `Retry-After` header indicates seconds to wait.

---

## WebSocket Authentication

WebSocket connections use the `Sec-WebSocket-Protocol` header for authentication:

```
Sec-WebSocket-Protocol: access-token, <your-jwt-token>
```

---

## Caching

Cached endpoints include `X-Cache: HIT` or `X-Cache: MISS` headers.
Write operations automatically invalidate related caches.
