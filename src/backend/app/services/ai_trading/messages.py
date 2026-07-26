"""Pure message-formatting helpers used by AITradingService.

These helpers do not depend on any service state (network, DB, gateway), so
they live as module-level functions that are unit-testable in isolation.
"""

from __future__ import annotations

from typing import Any

from app.schemas.ai_trading import (
    AITradingRequest,
    RiskAssessment,
    RiskLevel,
    TradeAction,
    TradingIntent,
)


def build_market_context(request: AITradingRequest) -> str:
    """Build a short market-context string for intent parsing prompts."""
    parts = []
    if request.gateway_id:
        parts.append(f"网关: {request.gateway_id}")
    if request.account_id:
        parts.append(f"账户: {request.account_id}")
    if request.dry_run:
        parts.append("模式: 模拟交易")
    return "; ".join(parts) if parts else "无额外市场上下文"


def build_rejection_message(risk: RiskAssessment) -> str:
    """User-facing message when risk control rejects the trade."""
    reasons = "; ".join(risk.blocked_reasons)
    return f"⚠️ 交易被风控拦截: {reasons}"


def build_confirmation_message(intent: TradingIntent, risk: RiskAssessment) -> str:
    """User-facing prompt asking the user to confirm a borderline trade."""
    action_desc = {
        TradeAction.BUY: "买入",
        TradeAction.SELL: "卖出",
        TradeAction.CLOSE: "平仓",
    }.get(intent.action, intent.action.value)

    msg = f"请确认交易: {action_desc} {intent.quantity or '?'} {intent.symbol or '?'}"
    if intent.price:
        msg += f" @ {intent.price}"
    if risk.warnings:
        msg += f"\n⚠️ 注意: {'; '.join(risk.warnings)}"
    return msg


def build_dry_run_message(intent: TradingIntent) -> str:
    """User-facing message after a successful dry-run."""
    action_desc = {
        TradeAction.BUY: "买入",
        TradeAction.SELL: "卖出",
        TradeAction.CLOSE: "平仓",
        TradeAction.QUERY: "查询",
    }.get(intent.action, intent.action.value)

    return (
        f"🔍 模拟模式: 将{action_desc} {intent.quantity or '?'} "
        f"{intent.symbol or '?'} @ {intent.price or '市价'}"
    )


def build_execution_message(intent: TradingIntent, result: dict[str, Any]) -> str:
    """User-facing message summarising an execution result."""
    if result.get("success"):
        return f"✅ 交易执行成功: {result.get('message', '')}"
    return f"❌ 交易执行失败: {result.get('message', result.get('error', '未知错误'))}"


def build_suggestions(intent: TradingIntent, risk: RiskAssessment) -> list[str]:
    """Generate actionable suggestions to surface in the response."""
    suggestions: list[str] = []

    if intent.confidence < 0.5:
        suggestions.append("建议更明确地描述交易品种和数量")

    if not intent.stop_loss and intent.action in (TradeAction.BUY, TradeAction.SELL):
        suggestions.append("建议设置止损价格以控制风险")

    if risk.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
        suggestions.append("当前交易风险较高，建议减小仓位或等待更好的入场时机")

    if intent.action == TradeAction.QUERY:
        suggestions.append("您可以说'买入1手螺纹钢'来执行交易")

    return suggestions
