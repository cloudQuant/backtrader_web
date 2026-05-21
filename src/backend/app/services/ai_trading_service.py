"""AI Trading Service: orchestrates natural language trading execution.

This is the main entry point for the natural language trading feature.
It coordinates intent parsing, risk assessment, and order execution.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.db.database import async_session_maker
from app.models.ai_trading import AITradingLog
from app.schemas.ai_trading import (
    AITradingRequest,
    AITradingResponse,
    RiskAssessment,
    RiskLevel,
    TradeAction,
    TradeConfirmRequest,
    TradeConfirmResponse,
    TradeStatus,
    TradingIntent,
)
from app.services.trading_intent_parser import parse_trading_intent
from app.services.trading_risk_guard import TradingRiskConfig, TradingRiskGuard

logger = logging.getLogger(__name__)

# In-memory store for pending trades (production should use DB)
_pending_trades: dict[str, dict[str, Any]] = {}

# Global risk guard instance
_risk_guard: TradingRiskGuard | None = None


def get_risk_guard() -> TradingRiskGuard:
    """Get or create the global risk guard instance."""
    global _risk_guard
    if _risk_guard is None:
        _risk_guard = TradingRiskGuard(TradingRiskConfig())
    return _risk_guard


class AITradingService:
    """Orchestrates the natural language → trade execution pipeline."""

    def __init__(self) -> None:
        self.risk_guard = get_risk_guard()

    async def process_trading_request(
        self,
        user_id: str,
        request: AITradingRequest,
    ) -> AITradingResponse:
        """Process a natural language trading request.

        Pipeline:
        1. Parse natural language → TradingIntent
        2. Enrich with market context
        3. Risk assessment
        4. Execute or queue for confirmation

        Args:
            user_id: The authenticated user's ID.
            request: The trading request with natural language message.

        Returns:
            AITradingResponse with intent, risk assessment, and status.
        """
        trade_id = str(uuid.uuid4())[:12]

        # Step 1: Parse intent
        intent = await parse_trading_intent(
            user_input=request.message,
            market_context=self._build_market_context(request),
        )

        # Step 2: Risk assessment
        risk_assessment = self.risk_guard.assess(
            intent=intent,
            account_balance=0.0,  # TODO: fetch from gateway
            current_positions=None,  # TODO: fetch from gateway
        )

        # Step 3: Determine action based on risk assessment
        if not risk_assessment.approved:
            return AITradingResponse(
                trade_id=trade_id,
                intent=intent,
                risk_assessment=risk_assessment,
                status=TradeStatus.REJECTED,
                message=self._build_rejection_message(risk_assessment),
                ai_reasoning=intent.reason,
                suggestions=self._build_suggestions(intent, risk_assessment),
            )

        # Step 4: Check if confirmation is needed
        if risk_assessment.requires_confirmation and not request.auto_confirm:
            # Store pending trade for later confirmation
            _pending_trades[trade_id] = {
                "user_id": user_id,
                "intent": intent.model_dump(),
                "risk_assessment": risk_assessment.model_dump(),
                "request": request.model_dump(),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            # Push WebSocket notification for real-time confirmation
            await self._notify_confirmation_needed(trade_id, intent, risk_assessment)

            return AITradingResponse(
                trade_id=trade_id,
                intent=intent,
                risk_assessment=risk_assessment,
                status=TradeStatus.PENDING_CONFIRMATION,
                message=self._build_confirmation_message(intent, risk_assessment),
                ai_reasoning=intent.reason,
                requires_confirmation=True,
                suggestions=self._build_suggestions(intent, risk_assessment),
            )

        # Step 5: Execute trade
        if request.dry_run:
            return AITradingResponse(
                trade_id=trade_id,
                intent=intent,
                risk_assessment=risk_assessment,
                status=TradeStatus.CONFIRMED,
                message=self._build_dry_run_message(intent),
                ai_reasoning=intent.reason,
                execution_result={"dry_run": True, "would_execute": intent.model_dump()},
                suggestions=self._build_suggestions(intent, risk_assessment),
            )

        # Real execution
        execution_result = await self._execute_trade(intent, request)
        status = (
            TradeStatus.FILLED
            if execution_result.get("success")
            else TradeStatus.FAILED
        )

        return AITradingResponse(
            trade_id=trade_id,
            intent=intent,
            risk_assessment=risk_assessment,
            status=status,
            message=self._build_execution_message(intent, execution_result),
            ai_reasoning=intent.reason,
            execution_result=execution_result,
            suggestions=self._build_suggestions(intent, risk_assessment),
        )

    async def confirm_trade(
        self,
        user_id: str,
        request: TradeConfirmRequest,
    ) -> TradeConfirmResponse:
        """Confirm or reject a pending trade.

        Args:
            user_id: The authenticated user's ID.
            request: Confirmation request with trade_id and decision.

        Returns:
            TradeConfirmResponse with execution result.
        """
        pending = _pending_trades.get(request.trade_id)
        if not pending:
            return TradeConfirmResponse(
                trade_id=request.trade_id,
                status=TradeStatus.FAILED,
                message="交易不存在或已过期",
            )

        if pending["user_id"] != user_id:
            return TradeConfirmResponse(
                trade_id=request.trade_id,
                status=TradeStatus.FAILED,
                message="无权操作此交易",
            )

        # Remove from pending
        del _pending_trades[request.trade_id]

        if not request.confirmed:
            return TradeConfirmResponse(
                trade_id=request.trade_id,
                status=TradeStatus.CANCELLED,
                message="交易已取消",
            )

        # Execute the confirmed trade
        intent = TradingIntent(**pending["intent"])
        original_request = AITradingRequest(**pending["request"])

        execution_result = await self._execute_trade(intent, original_request)
        status = (
            TradeStatus.FILLED
            if execution_result.get("success")
            else TradeStatus.FAILED
        )

        return TradeConfirmResponse(
            trade_id=request.trade_id,
            status=status,
            message=self._build_execution_message(intent, execution_result),
            execution_result=execution_result,
        )

    async def _execute_trade(
        self,
        intent: TradingIntent,
        request: AITradingRequest,
    ) -> dict[str, Any]:
        """Execute a trade through the appropriate execution channel.

        Routes to paper trading or live trading based on dry_run flag.
        """
        from app.services.direct_order_service import DirectOrderService

        order_service = DirectOrderService()

        try:
            if request.dry_run:
                # Use paper trading system
                return await order_service.execute_paper_trade(
                    intent=intent,
                    user_id="",  # Will be set by caller context
                    account_id=request.account_id,
                )
            else:
                # Attempt live trading
                return await order_service.execute_live_trade(
                    intent=intent,
                    user_id="",
                    gateway_id=request.gateway_id,
                )
        except Exception as e:
            logger.error("Trade execution failed: %s", e, exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "message": f"交易执行失败: {e}",
            }

    async def _persist_trade_log(
        self,
        trade_id: str,
        user_id: str,
        request: AITradingRequest,
        intent: TradingIntent,
        risk_assessment: RiskAssessment,
        status: TradeStatus,
        execution_result: dict[str, Any] | None = None,
    ) -> None:
        """Persist a trade log entry to the database."""
        try:
            async with async_session_maker() as session:
                log_entry = AITradingLog(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    trade_id=trade_id,
                    user_input=request.message,
                    action=intent.action.value,
                    symbol=intent.symbol,
                    exchange=intent.exchange,
                    quantity=intent.quantity,
                    price=intent.price,
                    order_type=intent.order_type.value,
                    stop_loss=intent.stop_loss,
                    take_profit=intent.take_profit,
                    confidence=intent.confidence,
                    risk_level=intent.risk_level.value,
                    risk_approved=risk_assessment.approved,
                    risk_warnings=risk_assessment.warnings,
                    risk_blocked_reasons=risk_assessment.blocked_reasons,
                    requires_confirmation=risk_assessment.requires_confirmation,
                    status=status.value,
                    execution_result=execution_result,
                    gateway_id=request.gateway_id,
                    dry_run=request.dry_run,
                    ai_reasoning=intent.reason,
                )
                session.add(log_entry)
                await session.commit()
        except Exception as e:
            logger.warning("Failed to persist trade log: %s", e)

    def _build_market_context(self, request: AITradingRequest) -> str:
        """Build market context string for intent parsing."""
        parts = []
        if request.gateway_id:
            parts.append(f"网关: {request.gateway_id}")
        if request.account_id:
            parts.append(f"账户: {request.account_id}")
        if request.dry_run:
            parts.append("模式: 模拟交易")
        return "; ".join(parts) if parts else "无额外市场上下文"

    def _build_rejection_message(self, risk: RiskAssessment) -> str:
        """Build user-friendly rejection message."""
        reasons = "; ".join(risk.blocked_reasons)
        return f"⚠️ 交易被风控拦截: {reasons}"

    def _build_confirmation_message(
        self, intent: TradingIntent, risk: RiskAssessment
    ) -> str:
        """Build confirmation request message."""
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

    def _build_dry_run_message(self, intent: TradingIntent) -> str:
        """Build dry run result message."""
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

    def _build_execution_message(
        self, intent: TradingIntent, result: dict[str, Any]
    ) -> str:
        """Build execution result message."""
        if result.get("success"):
            return f"✅ 交易执行成功: {result.get('message', '')}"
        return f"❌ 交易执行失败: {result.get('message', result.get('error', '未知错误'))}"

    def _build_suggestions(
        self, intent: TradingIntent, risk: RiskAssessment
    ) -> list[str]:
        """Build actionable suggestions for the user."""
        suggestions = []

        if intent.confidence < 0.5:
            suggestions.append("建议更明确地描述交易品种和数量")

        if not intent.stop_loss and intent.action in (TradeAction.BUY, TradeAction.SELL):
            suggestions.append("建议设置止损价格以控制风险")

        if risk.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            suggestions.append("当前交易风险较高，建议减小仓位或等待更好的入场时机")

        if intent.action == TradeAction.QUERY:
            suggestions.append("您可以说'买入1手螺纹钢'来执行交易")

        return suggestions

    async def _notify_confirmation_needed(
        self,
        trade_id: str,
        intent: TradingIntent,
        risk_assessment: RiskAssessment,
    ) -> None:
        """Push WebSocket notification when a trade requires confirmation."""
        try:
            from app.websocket_manager import manager as ws_manager

            message = {
                "type": "ai_trading_confirmation",
                "trade_id": trade_id,
                "action": intent.action.value,
                "symbol": intent.symbol,
                "quantity": intent.quantity,
                "price": intent.price,
                "risk_level": risk_assessment.risk_level.value,
                "warnings": risk_assessment.warnings,
                "message": (
                    f"AI 交易需要确认: {intent.action.value} "
                    f"{intent.quantity} {intent.symbol}"
                ),
            }
            await ws_manager.broadcast(message)
        except Exception as e:
            logger.debug("WebSocket notification failed (non-critical): %s", e)

    async def get_history(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Get trading history for a user.

        Args:
            user_id: The user's ID.
            limit: Maximum number of records.

        Returns:
            List of trade log entries as dicts.
        """
        try:
            from sqlalchemy import select

            async with async_session_maker() as session:
                result = await session.execute(
                    select(AITradingLog)
                    .where(AITradingLog.user_id == user_id)
                    .order_by(AITradingLog.created_at.desc())
                    .limit(limit)
                )
                logs = result.scalars().all()
                return [
                    {
                        "trade_id": log.trade_id,
                        "user_input": log.user_input,
                        "action": log.action,
                        "symbol": log.symbol,
                        "quantity": log.quantity,
                        "price": log.price,
                        "status": log.status,
                        "confidence": log.confidence,
                        "risk_level": log.risk_level,
                        "ai_reasoning": log.ai_reasoning,
                        "dry_run": log.dry_run,
                        "created_at": log.created_at.isoformat() if log.created_at else None,
                        "executed_at": log.executed_at.isoformat() if log.executed_at else None,
                    }
                    for log in logs
                ]
        except Exception as e:
            logger.warning("Failed to fetch trading history: %s", e)
            return []

    async def generate_reflection(
        self,
        trade_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        """Generate AI reflection on a completed trade.

        Analyzes the trade decision, execution result, and provides
        lessons learned for future improvement.

        Args:
            trade_id: The trade to reflect on.
            user_id: The user's ID.

        Returns:
            Reflection result with analysis and suggestions.
        """
        try:
            from sqlalchemy import select

            async with async_session_maker() as session:
                result = await session.execute(
                    select(AITradingLog).where(
                        AITradingLog.trade_id == trade_id,
                        AITradingLog.user_id == user_id,
                    )
                )
                log = result.scalar_one_or_none()
                if not log:
                    return {"success": False, "message": "交易记录不存在"}

                # Build reflection prompt (for future LLM-based reflection)
                # reflection_context includes trade details for AI analysis
                reflection_text = self._generate_simple_reflection(log)

                # Persist reflection
                log.reflection = reflection_text
                await session.commit()

                return {
                    "success": True,
                    "trade_id": trade_id,
                    "reflection": reflection_text,
                }
        except Exception as e:
            logger.warning("Failed to generate reflection: %s", e)
            return {"success": False, "message": f"反思生成失败: {e}"}

    def _generate_simple_reflection(self, log: AITradingLog) -> str:
        """Generate a simple rule-based reflection without LLM."""
        parts = []

        if log.status == "filled":
            parts.append("✅ 交易已成功执行。")
        elif log.status == "rejected":
            parts.append("⚠️ 交易被风控拦截。")
            if log.risk_blocked_reasons:
                parts.append(f"拦截原因: {', '.join(log.risk_blocked_reasons)}")
        elif log.status == "cancelled":
            parts.append("ℹ️ 交易被用户取消。")

        if log.confidence and log.confidence < 0.5:
            parts.append("建议: 下次尝试更明确地描述交易意图以提高解析准确度。")

        if log.action in ("buy", "sell") and not log.stop_loss:
            parts.append("建议: 考虑设置止损以控制下行风险。")

        return " ".join(parts) if parts else "交易已记录。"

    def build_conversation_context(
        self,
        user_id: str,
        recent_messages: list[dict[str, str]],
    ) -> str:
        """Build conversation context for multi-turn trading dialogue.

        Extracts relevant context from recent messages to help the LLM
        understand follow-up instructions like "再买1手" or "把止损改到3400".

        Args:
            user_id: The user's ID.
            recent_messages: Recent conversation messages.

        Returns:
            Context string to prepend to the intent parsing prompt.
        """
        if not recent_messages:
            return ""

        context_parts = []
        for msg in recent_messages[-5:]:  # Last 5 messages
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                context_parts.append(f"用户: {content}")
            elif role == "assistant":
                # Extract key info from assistant response
                if "买入" in content or "卖出" in content:
                    context_parts.append(f"AI: {content[:100]}")

        if context_parts:
            return "对话上下文:\n" + "\n".join(context_parts) + "\n\n"
        return ""


# ─── Conditional Orders ──────────────────────────────────────────────────────

# In-memory store for conditional orders (production should use DB)
_conditional_orders: dict[str, dict[str, Any]] = {}


class ConditionalOrderManager:
    """Manages conditional (trigger) orders.

    Conditional orders are stored and periodically checked against
    market conditions. When the condition is met, the order is executed.

    Example conditions:
    - "如果BTC跌到60000就买入0.1个"
    - "螺纹钢涨到4000就卖出"
    - "如果持仓亏损超过5%就平仓"
    """

    def create_conditional_order(
        self,
        user_id: str,
        condition: str,
        action_message: str,
        gateway_id: str | None = None,
        dry_run: bool = True,
        expiry_hours: float = 24.0,
    ) -> dict[str, Any]:
        """Create a new conditional order.

        Args:
            user_id: The user's ID.
            condition: Natural language condition description.
            action_message: The trade action to execute when triggered.
            gateway_id: Optional gateway for execution.
            dry_run: Whether to use paper trading.
            expiry_hours: Hours until the order expires.

        Returns:
            The created conditional order details.
        """
        order_id = str(uuid.uuid4())[:12]
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=expiry_hours)

        order_data = {
            "id": order_id,
            "user_id": user_id,
            "condition": condition,
            "action_message": action_message,
            "gateway_id": gateway_id,
            "dry_run": dry_run,
            "status": "active",
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "triggered_at": None,
        }

        _conditional_orders[order_id] = order_data
        logger.info("Created conditional order %s: %s → %s", order_id, condition, action_message)

        return order_data

    def list_conditional_orders(self, user_id: str) -> list[dict[str, Any]]:
        """List all conditional orders for a user."""
        self._expire_old_orders()
        return [
            order
            for order in _conditional_orders.values()
            if order["user_id"] == user_id
        ]

    def cancel_conditional_order(self, order_id: str, user_id: str) -> bool:
        """Cancel a conditional order."""
        order = _conditional_orders.get(order_id)
        if not order or order["user_id"] != user_id:
            return False
        order["status"] = "cancelled"
        return True

    def _expire_old_orders(self) -> None:
        """Mark expired orders."""
        now = datetime.now(timezone.utc)
        for order in _conditional_orders.values():
            if order["status"] == "active":
                expires_at = datetime.fromisoformat(order["expires_at"])
                if now > expires_at:
                    order["status"] = "expired"


# Global instance
_conditional_order_manager: ConditionalOrderManager | None = None


def get_conditional_order_manager() -> ConditionalOrderManager:
    """Get or create the conditional order manager."""
    global _conditional_order_manager
    if _conditional_order_manager is None:
        _conditional_order_manager = ConditionalOrderManager()
    return _conditional_order_manager
