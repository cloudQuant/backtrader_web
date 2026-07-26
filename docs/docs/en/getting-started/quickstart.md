# Quick start

This flow uses the current pages rather than stale fixed API examples, and follows the research-workspace path.

## 1. Sign in and open market data

After starting both services, open `http://localhost:3000` and sign in. Go to **Data → Market Data**, then choose an asset class and instrument.

- Initial loads and instrument changes read the local MySQL market-data warehouse first.
- **Query** is the explicit action that fetches latest data from AkShare. If it fails, the page keeps usable local data and shows a readable warning.
- History is shown newest first. The last instrument is remembered separately for each asset class.

## 2. Optionally build a knowledge base

In **AI → Knowledge Base**, create a knowledge base, upload or add documents, then index them. Open **AI → Chat**, ask a focused question, and inspect the citations.

`not_indexed` means that a document must be indexed or re-indexed. `no_context_found` means the index exists but lacks sufficiently relevant context; it is not a model-outage signal.

## 3. Create or select a strategy

Open **Research → Strategies** and choose a template, an existing strategy, or an AI-generated draft. AI research can use the default research objective or, after confirmation, ask the configured model to improve that objective.

For custom Backtrader strategies, keep price series in a custom property such as `self.dataclose`; preserve `self.close()` as the close-position method and never overwrite it with an attribute.

## 4. Run research and a backtest

Add the strategy to a **research workspace**, set the instrument, timeframe, date range, capital, and commission, then run it. The page streams research output while it runs. On completion, inspect:

- normalized return, annual return, Sharpe, and maximum drawdown;
- trade count, win rate, profit/loss ratio, and holding period;
- equity curve, drawdown, configuration, and data range;
- robustness checks or parameter optimization when needed.

## 5. Move to a trading workspace only after review

Do not treat a single backtest as execution approval. Complete out-of-sample, data-quality, and risk checks, then put a human-reviewed plan into a **trading workspace**. Use **Portfolio** to inspect accounts, positions, trades, cumulative P&L, drawdown, and allocation.

Next, read [Strategies and AI research](../features/strategy-management.md), [Backtests and validation](../features/backtesting.md), and [Trading workspaces](../features/paper-trading.md).
