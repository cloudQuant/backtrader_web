"""Quantitative finance risk and performance analytics library.

Lazy-loading facade: Empyrical, Pyfolio, analyze(), create_strategy_report(),
and flat API functions (sharpe_ratio, max_drawdown, etc.) load on first access.
"""

from __future__ import annotations

__version__ = "0.3.0"

__all__ = [
    # Core classes
    "Empyrical",
    "Pyfolio",
    "aggregate_returns",
    "alpha",
    "alpha_beta",
    "analyze",
    "annual_return",
    "annual_volatility",
    "beta",
    "calmar_ratio",
    "capture",
    "create_strategy_report",
    "cum_returns",
    "cum_returns_final",
    "downside_risk",
    "information_ratio",
    "max_drawdown",
    "omega_ratio",
    # Commonly-used metric functions (flat API)
    "sharpe_ratio",
    "simple_returns",
    "sortino_ratio",
    "stability_of_timeseries",
    "tail_ratio",
    "value_at_risk",
]

# ---------------------------------------------------------------------------
# Lazy imports — defer heavy submodules until first attribute access.
# ``from fincore import empyrical`` still works because Python resolves
# sub-module names before calling ``__getattr__``.
# ---------------------------------------------------------------------------

# Maps commonly-used function names to (module_path, attr_name)
_FLAT_API = {
    "sharpe_ratio": ("fincore.metrics.ratios", "sharpe_ratio"),
    "sortino_ratio": ("fincore.metrics.ratios", "sortino_ratio"),
    "calmar_ratio": ("fincore.metrics.ratios", "calmar_ratio"),
    "omega_ratio": ("fincore.metrics.ratios", "omega_ratio"),
    "information_ratio": ("fincore.metrics.ratios", "information_ratio"),
    "stability_of_timeseries": ("fincore.metrics.ratios", "stability_of_timeseries"),
    "capture": ("fincore.metrics.ratios", "capture"),
    "max_drawdown": ("fincore.metrics.drawdown", "max_drawdown"),
    "annual_return": ("fincore.metrics.yearly", "annual_return"),
    "annual_volatility": ("fincore.metrics.risk", "annual_volatility"),
    "downside_risk": ("fincore.metrics.risk", "downside_risk"),
    "value_at_risk": ("fincore.metrics.risk", "value_at_risk"),
    "tail_ratio": ("fincore.metrics.risk", "tail_ratio"),
    "cum_returns": ("fincore.metrics.returns", "cum_returns"),
    "cum_returns_final": ("fincore.metrics.returns", "cum_returns_final"),
    "simple_returns": ("fincore.metrics.returns", "simple_returns"),
    "aggregate_returns": ("fincore.metrics.returns", "aggregate_returns"),
    "alpha": ("fincore.metrics.alpha_beta", "alpha"),
    "beta": ("fincore.metrics.alpha_beta", "beta"),
    "alpha_beta": ("fincore.metrics.alpha_beta", "alpha_beta"),
}


def __getattr__(name: str):
    if name == "Empyrical":
        from .empyrical import Empyrical

        globals()["Empyrical"] = Empyrical
        return Empyrical
    if name == "Pyfolio":
        from .pyfolio import Pyfolio

        globals()["Pyfolio"] = Pyfolio
        return Pyfolio
    if name == "analyze":
        from .core.context import analyze

        globals()["analyze"] = analyze
        return analyze
    if name == "create_strategy_report":
        from .report import create_strategy_report

        globals()["create_strategy_report"] = create_strategy_report
        return create_strategy_report

    # Flat metric function API
    entry = _FLAT_API.get(name)
    if entry is not None:
        import importlib

        mod_path, attr_name = entry
        mod = importlib.import_module(mod_path)
        func = getattr(mod, attr_name)
        globals()[name] = func
        return func

    raise AttributeError(f"module 'fincore' has no attribute {name!r}")
