# Features

The product is organized around an evidence-to-execution path: research evidence, strategy and validation, trading preparation, and risk observation. Pages are the primary entry point; the running OpenAPI contract is authoritative for API details.

## Feature map

| Workflow | Page entry | Boundary |
| --- | --- | --- |
| Knowledge and AI | `/ai/chat`, `/ai/knowledge-base` | Index before asking; answers include context or a readable diagnostic |
| Market data | `/data/market` | MySQL-first reads; AkShare is called only by an explicit query |
| Strategies and AI research | `/investment/strategies` | Review code, objectives, and results before use |
| Backtests and validation | `/research/workspaces`, `/backtest` | Metrics reflect the chosen data/configuration, not a return promise |
| Trading workspaces | `/trading` | Research state and trading runtime state are managed separately |
| Portfolio and risk | `/portfolio` | Aggregates accounts, positions, trades, P&L, drawdown, and allocation |
| Administration | `/config/data`, `/config/ai`, `/config/gateways` | Admin access; secrets stay in environment or a secrets service |

## Read next

- [Knowledge base and AI chat](./knowledge-base.md)
- [Market data and trust](./market-data.md)
- [Strategies and AI research](./strategy-management.md)
- [Backtests and validation](./backtesting.md)
- [Trading workspaces and simulation](./paper-trading.md)
- [Live-trading preparation and gateways](./live-trading.md)
- [Parameter optimization](./optimization.md)

## API convention

Core APIs live under `/api/v1`. Common domains include `/strategy`, `/backtests`, `/workspace`, `/data`, `/data/trust`, `/knowledge-base`, `/rag`, `/kb-chat`, `/portfolio`, and `/live-trading`. Some modules are registered conditionally based on installed dependencies and configuration, so do not rely on stale endpoint inventories. Inspect `http://localhost:8000/docs` for the contract actually available in your environment.
