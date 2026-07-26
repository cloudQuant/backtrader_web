# Strategies and AI research

The strategy center manages templates, user strategies, versions, and AI research artifacts. A research objective, strategy code, and backtest result form an auditable research record; they are not an automated trading instruction.

## How to use it

- Create, edit, copy, or select templates in **Research → Strategies**.
- Use AI Chat for knowledge questions, strategy ideation, Backtrader draft generation, or strategy review.
- **Generate research objective** opens a dialog: keep the default template or ask the configured model to improve its wording. If the model is unavailable, the default remains and the reason is shown.
- Choosing a different research profile and running AI research creates corresponding new output. The page updates as the run proceeds instead of reusing a stale result.
- Add a reviewed strategy to a research workspace for backtests and follow-up validation.

## Backtrader coding convention

Keep a price series in a custom property, for example:

```python
def __init__(self):
    self.dataclose = self.datas[0].close
```

`self.close()` is Backtrader’s close-position method. Never write `self.close = ...` or otherwise assign to it. The sandbox rejects overrides of trading methods so generated strategies do not lose close-order behavior and corrupt trade statistics.

## Review checklist

1. State the instrument, timeframe, costs, sizing, and stop assumptions.
2. Verify that code uses allowed APIs and does not overwrite order/close methods.
3. Confirm the date range, adjustment/contract rules, and data-preflight result.
4. Read trade count, equity curve, drawdown, and robustness results—not only one return metric.
5. Require human approval before entering a trading workspace.

See [Backtests and validation](./backtesting.md) and [Parameter optimization](./optimization.md).
