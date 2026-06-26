"""Trading risk guard: validates trading intents against safety rules.

Implements a multi-layer risk control system:
1. Hard rules (cannot be bypassed)
2. Soft rules (configurable confirmation requirements)
3. AI-based risk assessment (optional)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.schemas.ai_trading import (
    OrderType,
    RiskAssessment,
    RiskLevel,
    TradeAction,
    TradingIntent,
)
from app.services.trading_asset_info_service import symbol_aliases

logger = logging.getLogger(__name__)


class TradingRiskConfig:
    """Configuration for trading risk limits."""

    def __init__(
        self,
        max_single_trade_amount: float = 10000.0,
        max_daily_trades: int = 50,
        max_position_ratio: float = 0.3,
        require_confirmation_above: float = 5000.0,
        blocked_symbols: list[str] | None = None,
        allowed_exchanges: list[str] | None = None,
        max_daily_loss: float = 5000.0,
        min_confidence_threshold: float = 0.3,
    ):
        self.max_single_trade_amount = max_single_trade_amount
        self.max_daily_trades = max_daily_trades
        self.max_position_ratio = max_position_ratio
        self.require_confirmation_above = require_confirmation_above
        self.blocked_symbols = blocked_symbols or []
        self.allowed_exchanges = allowed_exchanges
        self.max_daily_loss = max_daily_loss
        self.min_confidence_threshold = min_confidence_threshold


class TradingRiskGuard:
    """Multi-layer risk control for AI trading."""

    def __init__(self, config: TradingRiskConfig | None = None):
        self.config = config or TradingRiskConfig()
        self._daily_trade_count: int = 0
        self._daily_loss: float = 0.0
        self._last_reset_date: str = ""

    def assess(
        self,
        intent: TradingIntent,
        account_balance: float = 0.0,
        current_positions: list[dict[str, Any]] | None = None,
    ) -> RiskAssessment:
        """Assess the risk of a trading intent.

        Args:
            intent: The parsed trading intent.
            account_balance: Current account balance.
            current_positions: List of current positions.

        Returns:
            RiskAssessment with approval status and details.
        """
        self._maybe_reset_daily_counters()

        warnings: list[str] = []
        blocked_reasons: list[str] = []
        requires_confirmation = False
        is_execution_action = intent.action in (TradeAction.BUY, TradeAction.SELL)

        # === Hard Rules (cannot be bypassed) ===

        # Rule 1: Query actions always pass
        if intent.action == TradeAction.QUERY:
            return RiskAssessment(
                approved=True,
                risk_level=RiskLevel.LOW,
                warnings=[],
                requires_confirmation=False,
            )

        # Rule 2: Confidence threshold
        if intent.confidence < self.config.min_confidence_threshold:
            blocked_reasons.append(
                f"AI 解析置信度过低 ({intent.confidence:.1%})，"
                f"最低要求 {self.config.min_confidence_threshold:.1%}"
            )

        # Rule 3: Symbol must be specified for execution actions
        if is_execution_action and not intent.symbol:
            blocked_reasons.append("交易品种未指定，无法执行")

        # Rule 4: Quantity must be specified
        if is_execution_action and not intent.quantity:
            blocked_reasons.append("交易数量未指定，无法执行")

        # Rule 5: Blocked symbols
        if intent.symbol and any(
            self._symbols_match(intent.symbol, blocked_symbol)
            for blocked_symbol in self.config.blocked_symbols
        ):
            blocked_reasons.append(f"品种 {intent.symbol} 在禁止交易列表中")

        # Rule 6: Exchange whitelist
        if (
            self.config.allowed_exchanges
            and intent.exchange
            and intent.exchange.lower() not in [e.lower() for e in self.config.allowed_exchanges]
        ):
            blocked_reasons.append(
                f"交易所 {intent.exchange} 不在允许列表中: {self.config.allowed_exchanges}"
            )

        # Rule 7: Daily trade count limit
        if self._daily_trade_count >= self.config.max_daily_trades:
            blocked_reasons.append(f"已达到每日最大交易次数 ({self.config.max_daily_trades})")

        # Estimate trade value and potential loss before amount/loss rules.
        trade_value = self._estimate_trade_value(intent, account_balance)
        max_loss_estimate = self._estimate_max_loss(intent, trade_value)

        # Rule 8: Daily loss limit
        if is_execution_action and self.config.max_daily_loss > 0:
            if self._daily_loss >= self.config.max_daily_loss:
                blocked_reasons.append(
                    "已达到每日最大亏损限制 "
                    f"({self._daily_loss:.0f}/{self.config.max_daily_loss:.0f})"
                )
            elif max_loss_estimate is not None:
                projected_daily_loss = self._daily_loss + max_loss_estimate
                if projected_daily_loss > self.config.max_daily_loss:
                    blocked_reasons.append(
                        f"预计最大亏损 ({max_loss_estimate:.0f}) 将使当日累计亏损达到 "
                        f"{projected_daily_loss:.0f}，超过每日最大亏损限制 "
                        f"({self.config.max_daily_loss:.0f})"
                    )

        # === Soft Rules (warnings + confirmation) ===

        if (
            is_execution_action
            and intent.quantity is not None
            and account_balance > 0
            and trade_value is None
        ):
            blocked_reasons.append(
                "缺少价格或最新价，无法校验单笔金额和账户仓位比例，禁止自动执行"
            )

        # Rule 9: Single trade amount limit
        if trade_value and trade_value > self.config.max_single_trade_amount:
            blocked_reasons.append(
                f"单笔交易金额 ({trade_value:.0f}) 超过限制 ({self.config.max_single_trade_amount:.0f})"
            )

        # Rule 10: Confirmation threshold
        if trade_value and trade_value > self.config.require_confirmation_above:
            requires_confirmation = True
            warnings.append(
                f"交易金额 ({trade_value:.0f}) 超过自动执行阈值 "
                f"({self.config.require_confirmation_above:.0f})，需要确认"
            )

        # Rule 11: Position ratio check
        if account_balance > 0 and trade_value:
            position_ratio = trade_value / account_balance
            if position_ratio > self.config.max_position_ratio:
                warnings.append(
                    f"本次交易占账户比例 ({position_ratio:.1%}) "
                    f"超过建议上限 ({self.config.max_position_ratio:.1%})"
                )
                requires_confirmation = True

        # Rule 12: High risk level from AI
        if intent.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            warnings.append(f"AI 评估风险等级为 {intent.risk_level.value}")
            requires_confirmation = True

        # Rule 13: Market order without stop loss
        if (
            is_execution_action
            and intent.order_type == OrderType.MARKET
            and intent.stop_loss is None
        ):
            warnings.append("市价单未设置止损，建议添加止损保护")

        # Determine overall risk level
        risk_level = self._determine_risk_level(intent, warnings, blocked_reasons)

        return RiskAssessment(
            approved=len(blocked_reasons) == 0,
            risk_level=risk_level,
            warnings=warnings,
            blocked_reasons=blocked_reasons,
            requires_confirmation=requires_confirmation,
            max_loss_estimate=max_loss_estimate,
            position_impact=self._describe_position_impact(intent, current_positions),
        )

    def record_trade(self, profit_loss: float = 0.0) -> None:
        """Record a completed trade for daily tracking."""
        self._maybe_reset_daily_counters()
        self._daily_trade_count += 1
        if profit_loss < 0:
            self._daily_loss += abs(profit_loss)

    def _maybe_reset_daily_counters(self) -> None:
        """Reset daily counters if date has changed."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self._last_reset_date:
            self._daily_trade_count = 0
            self._daily_loss = 0.0
            self._last_reset_date = today

    def _estimate_trade_value(self, intent: TradingIntent, account_balance: float) -> float | None:
        """Estimate the monetary value of a trade."""
        if intent.quantity is None:
            return None
        multiplier = self._contract_multiplier(intent)
        if self._is_inverse_contract(intent):
            return abs(intent.quantity) * multiplier
        reference_price = self._reference_price(intent)
        if reference_price and reference_price > 0:
            return abs(intent.quantity) * reference_price * multiplier
        return None

    def _estimate_max_loss(self, intent: TradingIntent, trade_value: float | None) -> float | None:
        """Estimate maximum potential loss."""
        if trade_value is None:
            return None
        reference_price = self._reference_price(intent)
        if intent.stop_loss and reference_price:
            multiplier = self._contract_multiplier(intent)
            if self._is_inverse_contract(intent):
                return (
                    abs(intent.quantity or 1)
                    * multiplier
                    * abs((intent.stop_loss / reference_price) - 1.0)
                )
            loss_per_unit = abs(reference_price - intent.stop_loss)
            return loss_per_unit * abs(intent.quantity or 1) * multiplier
        # Without stop loss, estimate 5% max loss
        return trade_value * 0.05

    def _determine_risk_level(
        self,
        intent: TradingIntent,
        warnings: list[str],
        blocked_reasons: list[str],
    ) -> RiskLevel:
        """Determine overall risk level."""
        if blocked_reasons:
            return RiskLevel.CRITICAL
        if len(warnings) >= 3:
            return RiskLevel.HIGH
        if len(warnings) >= 1:
            return RiskLevel.MEDIUM
        return intent.risk_level

    def _describe_position_impact(
        self,
        intent: TradingIntent,
        current_positions: list[dict[str, Any]] | None,
    ) -> str | None:
        """Describe how this trade would impact current positions."""
        if not current_positions or not intent.symbol:
            return None

        for pos in current_positions:
            symbol = str(pos.get("symbol") or pos.get("data_name") or "").strip()
            if self._symbols_match(symbol, intent.symbol):
                current_size = self._coerce_float(pos.get("size"), 0.0)
                if abs(current_size) <= 1e-12:
                    continue
                if intent.action == TradeAction.BUY:
                    return f"当前持仓 {current_size}，买入后将增加 {intent.quantity or 0}"
                elif intent.action == TradeAction.SELL:
                    return f"当前持仓 {current_size}，卖出后将减少 {intent.quantity or 0}"
                elif intent.action == TradeAction.CLOSE:
                    return f"当前持仓 {current_size}，平仓后将清零"

        if intent.action in (TradeAction.BUY, TradeAction.SELL):
            return f"新建 {intent.symbol} 仓位"
        return None

    @staticmethod
    def _symbols_match(left: Any, right: Any) -> bool:
        left_aliases = {alias.upper() for alias in symbol_aliases(left)}
        right_aliases = {alias.upper() for alias in symbol_aliases(right)}
        return bool(left_aliases and right_aliases and left_aliases & right_aliases)

    @staticmethod
    def _coerce_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _reference_price(cls, intent: TradingIntent) -> float | None:
        price = cls._coerce_optional_float(intent.price)
        if price and price > 0:
            return price
        params = intent.additional_params if isinstance(intent.additional_params, dict) else {}
        for key in (
            "reference_price",
            "current_price",
            "latest_price",
            "last_price",
            "mark_price",
            "market_price",
            "estimated_price",
        ):
            price = cls._coerce_optional_float(params.get(key))
            if price and price > 0:
                return price
        return None

    @classmethod
    def _contract_multiplier(cls, intent: TradingIntent) -> float:
        params = intent.additional_params if isinstance(intent.additional_params, dict) else {}
        keys = (
            (
                "contract_value",
                "contractValue",
                "contract_value_amount",
                "contractValueAmount",
                "contract_notional_value",
                "okx_contract_value",
                "ctVal",
                "multiplier",
                "mult",
                "contract_multiplier",
                "contract_size",
                "trade_contract_size",
                "ctMult",
                "VolumeMultiple",
                "CONTRACT_MULTIPLIER",
            )
            if cls._is_inverse_contract(intent)
            else (
                "multiplier",
                "mult",
                "contract_multiplier",
                "contract_size",
                "trade_contract_size",
                "contract_notional_value",
                "okx_contract_value",
                "ctVal",
                "ctMult",
                "VolumeMultiple",
                "CONTRACT_MULTIPLIER",
            )
        )
        for key in keys:
            multiplier = cls._coerce_optional_float(params.get(key))
            if multiplier and multiplier > 0:
                return multiplier
        return 1.0

    @classmethod
    def _is_inverse_contract(cls, intent: TradingIntent) -> bool:
        params = intent.additional_params if isinstance(intent.additional_params, dict) else {}
        explicit = cls._explicit_inverse_flag(params)
        if explicit is not None:
            return explicit
        contract_type = str(
            params.get("contract_type") or params.get("ctType") or ""
        ).strip().lower()
        if "inverse" in contract_type:
            return True
        if "linear" in contract_type:
            return False

        contract_ccy = cls._currency_code(
            params.get("contract_value_currency")
            or params.get("contract_value_ccy")
            or params.get("ctValCcy")
            or params.get("contractValueCurrency")
        )
        if not contract_ccy:
            return False
        base_ccy = cls._currency_code(params.get("base_asset") or params.get("baseCcy"))
        quote_ccy = cls._currency_code(params.get("quote_asset") or params.get("quoteCcy"))
        settle_ccy = cls._currency_code(
            params.get("settle_currency")
            or params.get("settleCcy")
            or params.get("fee_currency")
            or params.get("feeCcy")
        )
        if quote_ccy and contract_ccy == quote_ccy and contract_ccy != base_ccy:
            return True
        return bool(base_ccy and settle_ccy == base_ccy and contract_ccy != base_ccy)

    @staticmethod
    def _explicit_inverse_flag(params: dict[str, Any]) -> bool | None:
        for key in (
            "inverse",
            "is_inverse",
            "isInverse",
            "inverse_contract",
            "inverseContract",
        ):
            value = params.get(key)
            if value in (None, ""):
                continue
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return value != 0
            text = str(value).strip().lower()
            if text in {"1", "true", "yes", "y", "inverse", "coin_margined"}:
                return True
            if text in {"0", "false", "no", "n", "linear"}:
                return False
        return None

    @staticmethod
    def _currency_code(value: Any) -> str:
        return "".join(ch for ch in str(value or "").strip().upper() if ch.isalnum())

    @staticmethod
    def _coerce_optional_float(value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
