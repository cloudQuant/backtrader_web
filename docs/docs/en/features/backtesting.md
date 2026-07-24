# Backtests and validation

Backtests run on Backtrader and normalize return, risk, and trade statistics. Their meaning depends on the strategy, data, costs, and date range. They test a research hypothesis; they do not predict future returns.

## Recommended flow

1. Check instrument, timeframe, date range, coverage, and quality in [Market data](./market-data.md).
2. Review the strategy and parameters in [Strategies](./strategy-management.md).
3. Add it to a **research workspace**, configure capital, commission, and data range, then submit the run.
4. Watch status and research output while it runs; retain the task, configuration, and metric snapshot on completion.
5. Use robustness, out-of-sample, or parameter-sensitivity checks for material results.

## Reading results

| Category | Examples |
| --- | --- |
| Return | Total return, annual return, final equity |
| Risk | Maximum drawdown, volatility/risk-adjusted return, drawdown curve |
| Trades | Trade count, win rate, profit/loss ratio, streaks, average holding period |
| Traceability | Strategy version, instrument, timeframe, data range, capital, commission, and run time |

Trade count must come from actual open/close records. Code that overwrites `self.close()` or other trading methods is rejected; use `self.dataclose` for price series as described in the [strategy convention](./strategy-management.md#backtrader-coding-convention).

## API and progress

Research workspaces are the primary UI entry point. The service also exposes `/api/v1/backtests/run` to submit, `/api/v1/backtests/{task_id}/status` for status, `/api/v1/backtests/{task_id}` for results, and `/{task_id}/robustness` to run or retrieve robustness validation. Authentication, request bodies, and optional extensions are defined by `http://localhost:8000/docs`.

## Validation boundaries

- Do not interpret missing data, a failed task, or zero trades as “the strategy is invalid” without checking logs, coverage, and order lifecycle.
- Hold data range, capital, costs, and execution assumptions constant when comparing strategies.
- A successful backtest does not automatically remove live-trading risk constraints; human review and risk approval remain required.
