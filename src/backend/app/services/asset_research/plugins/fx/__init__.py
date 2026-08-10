"""Deterministic foreign-exchange research primitives."""

from app.services.asset_research.plugins.fx.quotes import (
    FxExecutionInput,
    calculate_fx_execution_return,
)

__all__ = ["FxExecutionInput", "calculate_fx_execution_return"]
