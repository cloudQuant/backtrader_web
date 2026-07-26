"""Service layer module.

Keep package-level service shortcuts lazy so importing ``app.services`` for a
submodule does not eagerly import the backtest/overfitting stack and create
cycles during application startup or test collection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.auth_service import AuthService
    from app.services.backtest_service import BacktestService
    from app.services.strategy_service import StrategyService

__all__ = ["AuthService", "BacktestService", "StrategyService"]


def __getattr__(name: str):
    if name == "AuthService":
        from app.services.auth_service import AuthService

        return AuthService
    if name == "BacktestService":
        from app.services.backtest_service import BacktestService

        return BacktestService
    if name == "StrategyService":
        from app.services.strategy_service import StrategyService

        return StrategyService
    raise AttributeError(f"module 'app.services' has no attribute {name!r}")
