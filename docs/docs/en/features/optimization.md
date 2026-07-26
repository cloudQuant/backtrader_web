# Parameter optimization

Parameter optimization compares pre-defined strategy parameter combinations; it is not a mechanism for finding a number that can be deployed automatically. Build it on reproducible data and backtest configuration, then combine it with out-of-sample and robustness checks.

## Principles

1. Fix strategy version, instrument, timeframe, data range, capital, and costs first.
2. Set ranges and steps only for parameters with business meaning; avoid unbounded search.
3. Evaluate return, drawdown, trade count, and stability together—not only the highest Sharpe or return.
4. Re-test candidates in a period that did not participate in the search and retain failures.
5. Store parameters, outputs, and selection rationale in the research workspace.

## Common risks

| Risk | Mitigation |
| --- | --- |
| Overfitting | Constrain the search space and use out-of-sample, rolling-window, and robustness validation. |
| Too few trades | Check order lifecycle, data coverage, and a minimum trade count; do not decide on accidental samples. |
| Non-reproducibility | Fix strategy version, source, dates, costs, and random settings. |
| Metric misreading | Review equity curve, drawdown, trade statistics, and risk constraints together. |

Optimization APIs live under `/api/v1/optimization`; inspect OpenAPI for request models and algorithms enabled in the current environment. See [Backtests and validation](./backtesting.md) for result interpretation.
