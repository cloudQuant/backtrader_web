"""Backtest execution model normalization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.schemas.market_data_trust import ExecutionModelResponse


@dataclass(frozen=True)
class ExecutionModel:
    """Normalized execution assumptions used by backtests and paper handoff."""

    asset_type: str
    symbol: str
    commission_rate: float = 0.0
    commission_fixed: float = 0.0
    slippage_bps: float = 0.0
    min_order_size: float = 1.0
    lot_size: float = 1.0
    contract_multiplier: float = 1.0
    margin_rate: float | None = None
    volume_limit_ratio: float | None = None
    price_limit_policy: str = "placeholder"
    suspended_policy: str = "placeholder"
    source: str = ""

    @classmethod
    def from_asset_spec(
        cls,
        asset_spec: dict[str, Any],
        *,
        overrides: dict[str, Any] | None = None,
    ) -> ExecutionModel:
        """Build an execution model from normalized asset specs and overrides."""
        merged = {**dict(asset_spec or {}), **dict(overrides or {})}
        asset_type = str(merged.get("asset_type") or "stock")
        return cls(
            asset_type=asset_type,
            symbol=str(merged.get("symbol") or ""),
            commission_rate=_float(merged.get("commission_rate"), 0.0),
            commission_fixed=_float(
                merged.get("commission_fixed") or merged.get("commission_amount"),
                0.0,
            ),
            slippage_bps=_float(merged.get("slippage_bps") or merged.get("slippage"), 0.0),
            min_order_size=max(_float(merged.get("min_order_size"), 1.0), 0.0),
            lot_size=max(_float(merged.get("lot_size") or merged.get("order_size_step"), 1.0), 0.0),
            contract_multiplier=max(
                _float(merged.get("contract_multiplier") or merged.get("multiplier"), 1.0),
                0.0,
            ),
            margin_rate=_optional_float(merged.get("margin_rate") or merged.get("margin")),
            volume_limit_ratio=_optional_float(merged.get("volume_limit_ratio")),
            price_limit_policy=str(
                merged.get("price_limit_policy")
                or ("stock_limit_placeholder" if asset_type == "stock" else "placeholder")
            ),
            suspended_policy=str(
                merged.get("suspended_policy")
                or ("stock_suspension_placeholder" if asset_type == "stock" else "placeholder")
            ),
            source=str(merged.get("source") or "asset_spec"),
        )

    def to_response(self) -> ExecutionModelResponse:
        """Return the API schema for this execution model."""
        return ExecutionModelResponse(**self.__dict__)

    def to_backtest_config(self) -> dict[str, Any]:
        """Return fields that can be merged into strategy/unit runtime config."""
        return {
            "commission": self.commission_rate,
            "commission_fixed": self.commission_fixed,
            "slippage_bps": self.slippage_bps,
            "min_order_size": self.min_order_size,
            "lot_size": self.lot_size,
            "multiplier": self.contract_multiplier,
            "margin": self.margin_rate,
            "volume_limit_ratio": self.volume_limit_ratio,
            "price_limit_policy": self.price_limit_policy,
            "suspended_policy": self.suspended_policy,
            "asset_spec_source": self.source,
        }


def _float(value: Any, default: float) -> float:
    parsed = _optional_float(value)
    return default if parsed is None else parsed


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
