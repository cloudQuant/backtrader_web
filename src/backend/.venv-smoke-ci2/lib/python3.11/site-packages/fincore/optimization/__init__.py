"""Portfolio optimization module.

Provides tools for:
- Efficient frontier computation
- Risk parity (equal risk contribution) portfolios
- Constrained optimization (max Sharpe, min variance, target return)

Example::

    from fincore.optimization import efficient_frontier, risk_parity, optimize

    # Efficient frontier
    ef = efficient_frontier(returns, n_points=50)

    # Risk parity
    weights = risk_parity(returns)

    # Max-Sharpe portfolio
    result = optimize(returns, objective="max_sharpe")
"""

from __future__ import annotations

from fincore.optimization._utils import OptimizationError
from fincore.optimization.frontier import efficient_frontier
from fincore.optimization.objectives import optimize
from fincore.optimization.risk_parity import risk_parity

__all__ = [
    "OptimizationError",
    "efficient_frontier",
    "optimize",
    "risk_parity",
]
