"""Monte Carlo simulation and stress testing for financial analytics.

This module provides tools for:
- Monte Carlo path simulation (GBM, jump diffusion)
- Value at Risk (VaR) and Expected Shortfall (CVaR) via simulation
- Bootstrap statistical inference
- Stress testing scenarios

Example::

    from fincore.simulation import MonteCarlo, bootstrap

    # Path simulation
    mc = MonteCarlo.simulate(returns, n_paths=1000, horizon=252)

    # Bootstrap confidence intervals
    ci = bootstrap(returns, n_samples=10000, alpha=0.05)

    # Stress testing
    scenarios = MonteCarlo.stress_test(returns, scenarios=["crash", "spike"])
"""

from __future__ import annotations

from fincore.simulation.bootstrap import bootstrap, bootstrap_ci
from fincore.simulation.monte_carlo import MonteCarlo

__all__ = [
    "MonteCarlo",
    "bootstrap",
    "bootstrap_ci",
]
