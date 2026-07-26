# Getting started

This section walks through a minimal, verifiable research loop: start the services, choose data, create a strategy, run a backtest, and inspect the result.

## Prerequisites

- Python 3.10+, Node.js 20+, and Git.
- Install the `backtrader` extra to run backtests, the `data` extra for online AkShare data, and the `rag` extra for semantic retrieval.
- SQLite is suitable for the default application database; PostgreSQL or MySQL is recommended for production or team environments.

## Recommended path

1. [Installation](./installation.md): create the backend environment, install the frontend, and configure `.env`.
2. [Quick start](./quickstart.md): complete a first backtest from market data through a research workspace.
3. [Knowledge base](../features/knowledge-base.md): import, index, and ask cited questions.
4. [Market data](../features/market-data.md): understand MySQL-first reads and explicit AkShare refreshes.

## Preflight checks

The repository contains a development-environment verifier. Run it before and after dependency installation:

```bash
./scripts/dev/verify-dev-env.sh --preinstall
./scripts/dev/verify-dev-env.sh --postinstall
```

The running OpenAPI contract at `http://localhost:8000/docs` is authoritative. Both pages and APIs require authentication; administrative configuration pages also require admin access.
