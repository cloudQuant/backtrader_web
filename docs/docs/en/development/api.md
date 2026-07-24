# API reference

The running Swagger UI (`/docs`) and OpenAPI document (`/openapi.json`) are the only authoritative endpoint inventory. Some modules are registered conditionally by installed dependencies or deployment configuration.

## Conventions

- API prefix: `/api/v1`.
- Pages and most APIs require JWT; administrative configuration routes also require admin identity.
- Pydantic validates requests and responses; invalid input returns 422.
- The API maps expected business failures to HTTP errors and never includes sensitive database, account, or secret material in error messages.
- Long-running work is submitted before status/result retrieval; the frontend updates through the relevant event stream or polling.

## Primary domains

| Domain | Common prefix | Purpose |
| --- | --- | --- |
| Authentication and status | `/auth`, `/status` | Login, tokens, health, and optional-router state |
| Strategies and backtests | `/strategy`, `/backtests`, `/analytics`, `/optimization` | Strategies, versions, runs, analysis, and optimization |
| Workspaces and trading | `/workspace`, `/live-trading`, `/portfolio`, `/portfolio-ledger` | Research/trading workspaces, gateways, portfolios, and ledger |
| Data | `/data`, `/data/trust`, `/quote` | Market data, coverage, preflight quality, data administration, and quotes |
| AI and knowledge | `/knowledge-base`, `/rag`, `/kb-chat` | Documents, indexing, retrieval, chat, and diagnostics |

## Example: health

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/health
```

Before submitting a backtest, reading a result, or configuring a gateway, inspect Swagger for schemas, authentication, and responses enabled in your environment. Do not copy requests from legacy `/api/v1/backtest/*` or historical session endpoints.
