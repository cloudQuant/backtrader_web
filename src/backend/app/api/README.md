# API package map

Iteration 174 groups high-traffic API modules by domain while keeping URL paths and legacy import paths stable.

## Core route registry

`router.py` owns top-level registration. Domain packages expose a `router` from their package root or from a focused submodule.

| Domain | Package | Public path prefix |
|---|---|---|
| AkShare data management | `app.api.akshare` | `/data/*` |
| Market data, governance, topics, realtime | `app.api.data` | `/data`, `/data-governance`, `/data-topics`, `/realtime` |
| Live trading | `app.api.live_trading` | `/live-trading` |
| Portfolio | `app.api.portfolio` | `/portfolio`, `/portfolio-ledger` |
| Strategy | `app.api.strategy` | `/strategy`, `/strategy-versions` |

## Trading entry boundaries

```text
Trading APIs
├── paper_trading      simulated execution lifecycle and paper account state
├── auto_trading       automation control over configured strategies
├── ai_trading         AI-assisted planning and operator workflows
└── live_trading       broker/gateway-backed live instance lifecycle
```

`live_trading` is the runtime gateway-facing API. `paper_trading`, `auto_trading`, and `ai_trading` remain separate entry points because they differ in execution authority and confirmation requirements.

## Compatibility window

Flat modules such as `app.api.live_trading_api`, `app.api.portfolio_api`, `app.api.strategy_score`, and `app.api.data_topics` remain as compatibility shims for one iteration cycle. New imports should target the domain packages directly.
