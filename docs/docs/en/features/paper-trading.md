# Trading workspaces and simulation

Trading workspaces carry forward reviewed strategy units and keep runtime state separate from research workspaces. They support simulated operation, account/order observation, and traceable context for later gateway integration.

## Research versus trading workspaces

| Type | Goal | Typical entry |
| --- | --- | --- |
| Research workspace | Strategy hypotheses, backtests, reports, optimization, and validation | `/research/workspaces` |
| Trading workspace | Reviewed runtime units, accounts/positions/trades, and runtime state | `/trading` |

Do not treat research output as an execution instruction. Before moving to a trading workspace, confirm strategy version, data range, costs, risk parameters, human approval, and gateway state.

## Portfolio observation

**Portfolio** aggregates confirmable runtime workspace state and shows:

- accounts, positions, trades, and allocation;
- cumulative P&L, equity curve, and drawdown;
- valuation after long/short direction, contract multiplier, fees, and shared-account de-duplication;
- a distinction between a fast first-screen summary and detailed runtime state.

The summary improves page-open time. Trading decisions must still use process-verified runtime state, simulation snapshots, and strategy logs.

## Operating principles

1. Preserve validation evidence in the research workspace first.
2. After creating or changing a trading unit, verify that account, data, risk, and strategy version agree.
3. Cross-check runtime state using gateway diagnostics, strategy logs, and Portfolio.
4. Preserve audit records before stopping or changing a run; do not rely on cached page data alone.

See [Live-trading preparation and gateways](./live-trading.md) before live use.
