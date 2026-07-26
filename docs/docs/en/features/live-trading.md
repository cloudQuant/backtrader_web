# Live-trading preparation and gateways

Live capability is designed as a high-risk boundary: configuration, connection diagnostics, instance lifecycle, and runtime state must be auditable. A generated strategy or completed backtest never automatically triggers a real trade.

## Preparation order

1. Complete data, strategy, backtest, and risk validation in a research workspace.
2. Confirm the runtime unit and risk parameters in a trading workspace.
3. An administrator manages gateway connections and diagnostics in **Configuration → Gateways**.
4. Check instance status, start time, logs, and duplicate-runtime-directory warnings during start, list, and query operations.
5. Follow your organization’s approval process, account permissions, and limits for any subsequent action.

## Security requirements

- Keep credentials only in `.env` or a secrets manager—never in strategies, screenshots, knowledge bases, or the repository.
- Use least-privilege accounts and limit instruments, positions, per-order exposure, and intraday risk.
- Validate in simulation or an isolated environment first; stop progression when gateway, data, or risk diagnostics are abnormal.
- Native gateway logs can support diagnosis, but UI/API errors must not expose sensitive database or account details.

Available gateways and configuration vary by deployment. Check the administrator UI and `http://localhost:8000/docs` for your environment instead of relying on a fixed broker list.
