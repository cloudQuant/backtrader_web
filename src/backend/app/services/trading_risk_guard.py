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
        if intent.action in (TradeAction.BUY, TradeAction.SELL) and not intent.symbol:
            blocked_reasons.append("交易品种未指定，无法执行")

        # Rule 4: Quantity must be specified
        if intent.action in (TradeAction.BUY, TradeAction.SELL) and not intent.quantity:
            blocked_reasons.append("交易数量未指定，无法执行")

        # Rule 5: Blocked symbols
        if intent.symbol and intent.symbol.upper() in [s.upper() for s in self.config.blocked_symbols]:
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
            blocked_reasons.append(
                f"已达到每日最大交易次数 ({self.config.max_daily_trades})"
            )

        # === Soft Rules (warnings + confirmation) ===

        # Estimate trade value
        trade_value = self._estimate_trade_value(intent, account_balance)

        # Rule 8: Single trade amount limit
        if trade_value and trade_value > self.config.max_single_trade_amount:
            blocked_reasons.append(
                f"单笔交易金额 ({trade_value:.0f}) 超过限制 ({self.config.max_single_trade_amount:.0f})"
            )

        # Rule 9: Confirmation threshold
        if trade_value and trade_value > self.config.require_confirmation_above:
            requires_confirmation = True
            warnings.append(
                f"交易金额 ({trade_value:.0f}) 超过自动执行阈值 "
                f"({self.config.require_confirmation_above:.0f})，需要确认"
            )

        # Rule 10: Position ratio check
        if account_balance > 0 and trade_value:
            position_ratio = trade_value / account_balance
            if position_ratio > self.config.max_position_ratio:
                warnings.append(
                    f"本次交易占账户比例 ({position_ratio:.1%}) "
                    f"超过建议上限 ({self.config.max_position_ratio:.1%})"
                )
                requires_confirmation = True

        # Rule 11: High risk level from AI
        if intent.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            warnings.append(f"AI 评估风险等级为 {intent.risk_level.value}")
            requires_confirmation = True

        # Rule 12: Market order without stop loss
        if (
            intent.action in (TradeAction.BUY, TradeAction.SELL)
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
            max_loss_estimate=self._estimate_max_loss(intent, trade_value),
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

    def _estimate_trade_value(
        self, intent: TradingIntent, account_balance: float
    ) -> float | None:
        """Estimate the monetary value of a trade."""
        if intent.quantity is None:
            return None
        if intent.price:
            return intent.quantity * intent.price
        # For market orders without price, we can't estimate precisely
        return None

    def _estimate_max_loss(
        self, intent: TradingIntent, trade_value: float | None
    ) -> float | None:
        """Estimate maximum potential loss."""
        if trade_value is None:
            return None
        if intent.stop_loss and intent.price:
            loss_per_unit = abs(intent.price - intent.stop_loss)
            return loss_per_unit * (intent.quantity or 1)
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
            if pos.get("symbol", "").upper() == intent.symbol.upper():
                current_size = pos.get("size", 0)
                if intent.action == TradeAction.BUY:
                    return f"当前持仓 {current_size}，买入后将增加 {intent.quantity or 0}"
                elif intent.action == TradeAction.SELL:
                    return f"当前持仓 {current_size}，卖出后将减少 {intent.quantity or 0}"
                elif intent.action == TradeAction.CLOSE:
                    return f"当前持仓 {current_size}，平仓后将清零"

        if intent.action in (TradeAction.BUY, TradeAction.SELL):
            return f"新建 {intent.symbol} 仓位"
        return None
