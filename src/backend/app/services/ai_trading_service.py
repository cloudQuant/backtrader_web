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
    TradeConfirmRequest,
    TradeConfirmResponse,
    TradeStatus,
    TradingIntent,
)
from app.services.ai_trading.conditional_orders import (
    ConditionalOrderManager,
    _conditional_orders,
    get_conditional_order_manager,
)
from app.services.ai_trading.messages import (
    build_confirmation_message as _build_confirmation_message,
)
from app.services.ai_trading.messages import (
    build_dry_run_message as _build_dry_run_message,
)
from app.services.ai_trading.messages import (
    build_execution_message as _build_execution_message,
)
from app.services.ai_trading.messages import (
    build_market_context as _build_market_context,
)
from app.services.ai_trading.messages import (
    build_rejection_message as _build_rejection_message,
)
from app.services.ai_trading.messages import (
    build_suggestions as _build_suggestions,
)
from app.services.trading_asset_info_service import (
    gateway_position_symbol,
    query_local_asset_spec,
    signed_gateway_size,
)
from app.services.trading_intent_parser import parse_trading_intent
from app.services.trading_risk_guard import TradingRiskConfig, TradingRiskGuard

logger = logging.getLogger(__name__)

# In-memory store for pending trades (production should use DB)
_pending_trades: dict[str, dict[str, Any]] = {}
PENDING_TRADE_TTL_SECONDS = 300

# Global risk guard instance
_risk_guard: TradingRiskGuard | None = None


class MissingGatewayContextError(ValueError):
    """Raised when AI trading execution lacks a valid account or gateway context."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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

        context = await self._resolve_trading_context(user_id=user_id, request=request)
        if context.get("degraded"):
            diagnostic_message = str(context.get("diagnostic_message") or "交易上下文不可用")
            degraded_risk = self._build_degraded_risk_assessment(diagnostic_message)
            return AITradingResponse(
                trade_id=trade_id,
                intent=intent,
                risk_assessment=degraded_risk,
                status=TradeStatus.REJECTED,
                message=f"⚠️ 交易上下文不可用，已停止自动交易: {diagnostic_message}",
                ai_reasoning=intent.reason,
                suggestions=[
                    "请先在交易页面补齐可用账户或已连接网关后再重试",
                    *self._build_suggestions(intent, degraded_risk),
                ],
                degraded=True,
                diagnostic_message=diagnostic_message,
            )

        self._enrich_intent_with_asset_spec(intent, request)

        # Step 2: Risk assessment
        risk_assessment = self.risk_guard.assess(
            intent=intent,
            account_balance=float(context.get("account_balance") or 0.0),
            current_positions=context.get("current_positions"),
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
            created_at = _utc_now()
            expires_at = created_at + timedelta(seconds=PENDING_TRADE_TTL_SECONDS)
            _pending_trades[trade_id] = {
                "user_id": user_id,
                "intent": intent.model_dump(),
                "risk_assessment": risk_assessment.model_dump(),
                "request": request.model_dump(),
                "created_at": created_at.isoformat(),
                "expires_at": expires_at.isoformat(),
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
        execution_result = await self._execute_trade(user_id, intent, request)
        status = TradeStatus.FILLED if execution_result.get("success") else TradeStatus.FAILED

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

        if not request.confirmed:
            del _pending_trades[request.trade_id]
            return TradeConfirmResponse(
                trade_id=request.trade_id,
                status=TradeStatus.CANCELLED,
                message="交易已取消",
            )

        intent = TradingIntent(**pending["intent"])
        original_request = AITradingRequest(**pending["request"])
        if self._pending_trade_expired(pending):
            del _pending_trades[request.trade_id]
            return TradeConfirmResponse(
                trade_id=request.trade_id,
                status=TradeStatus.FAILED,
                message="确认已过期，请重新提交交易请求。",
                execution_result={
                    "success": False,
                    "error": "confirmation_expired",
                    "expires_at": pending.get("expires_at"),
                },
            )

        try:
            current_risk = await self._reassess_confirmed_trade(
                user_id=user_id,
                intent=intent,
                request=original_request,
            )
        except MissingGatewayContextError as exc:
            del _pending_trades[request.trade_id]
            diagnostic_message = str(exc)
            return TradeConfirmResponse(
                trade_id=request.trade_id,
                status=TradeStatus.REJECTED,
                message=f"交易上下文不可用，已取消确认执行: {diagnostic_message}",
                execution_result={
                    "success": False,
                    "error": "context_unavailable",
                    "message": diagnostic_message,
                },
            )

        if not current_risk.approved:
            del _pending_trades[request.trade_id]
            return TradeConfirmResponse(
                trade_id=request.trade_id,
                status=TradeStatus.REJECTED,
                message=self._build_rejection_message(current_risk),
                execution_result={
                    "success": False,
                    "error": "risk_recheck_failed",
                    "risk_assessment": current_risk.model_dump(),
                },
            )

        # Remove from pending immediately before execution to prevent double-submit.
        del _pending_trades[request.trade_id]

        execution_result = await self._execute_trade(user_id, intent, original_request)
        status = TradeStatus.FILLED if execution_result.get("success") else TradeStatus.FAILED

        return TradeConfirmResponse(
            trade_id=request.trade_id,
            status=status,
            message=self._build_execution_message(intent, execution_result),
            execution_result=execution_result,
        )

    def _pending_trade_expired(self, pending: dict[str, Any]) -> bool:
        expires_at = _parse_datetime(pending.get("expires_at"))
        if expires_at is None:
            created_at = _parse_datetime(pending.get("created_at"))
            if created_at is None:
                return True
            expires_at = created_at + timedelta(seconds=PENDING_TRADE_TTL_SECONDS)
        return _utc_now() >= expires_at

    async def _reassess_confirmed_trade(
        self,
        *,
        user_id: str,
        intent: TradingIntent,
        request: AITradingRequest,
    ) -> RiskAssessment:
        context = await self._resolve_trading_context(user_id=user_id, request=request)
        if context.get("degraded"):
            diagnostic_message = str(context.get("diagnostic_message") or "交易上下文不可用")
            raise MissingGatewayContextError(diagnostic_message)

        self._enrich_intent_with_asset_spec(intent, request)
        return self.risk_guard.assess(
            intent=intent,
            account_balance=float(context.get("account_balance") or 0.0),
            current_positions=context.get("current_positions"),
        )

    async def _execute_trade(
        self,
        user_id: str,
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
                    user_id=user_id,
                    account_id=request.account_id,
                )
            else:
                # Attempt live trading
                return await order_service.execute_live_trade(
                    intent=intent,
                    user_id=user_id,
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

    async def _resolve_trading_context(
        self,
        user_id: str,
        request: AITradingRequest,
    ) -> dict[str, Any]:
        """Resolve account or gateway context for risk assessment.

        Returns a context dictionary with real account balance and positions.
        When live gateway data is unavailable but a gateway is selected, returns a
        degraded context instead of silently falling back to fake values.
        """
        if request.dry_run:
            return await self._resolve_paper_trading_context(
                user_id=user_id,
                account_id=request.account_id,
            )
        return self._resolve_live_trading_context(gateway_id=request.gateway_id)

    async def _resolve_paper_trading_context(
        self,
        user_id: str,
        account_id: str | None,
    ) -> dict[str, Any]:
        """Load real paper-trading account balance and positions."""
        if not account_id:
            raise MissingGatewayContextError(
                "模拟交易必须提供有效的 paper trading 账户 account_id。"
            )

        from app.services.paper_trading_service import PaperTradingService

        service = PaperTradingService()
        account = await service.get_account(account_id)
        if account is None or account.user_id != user_id or not account.is_active:
            raise MissingGatewayContextError(
                "未找到当前用户可用的模拟交易账户，请先选择有效的 account_id。"
            )

        positions, _ = await service.list_positions(
            filters={"account_id": account.id},
            limit=200,
            offset=0,
        )
        return {
            "account_balance": float(account.total_equity),
            "current_positions": [
                {"symbol": position.symbol, "size": position.size} for position in positions
            ],
        }

    def _resolve_live_trading_context(self, gateway_id: str | None) -> dict[str, Any]:
        """Load live-gateway context or return a degraded response."""
        if not gateway_id:
            raise MissingGatewayContextError("实盘交易必须提供已连接的 gateway_id。")

        from app.services.live_trading_manager import get_live_trading_manager

        manager = get_live_trading_manager()
        gateway = next(
            (
                item
                for item in manager.list_connected_gateways()
                if str(item.get("gateway_key") or "") == gateway_id
            ),
            None,
        )
        if gateway is None:
            raise MissingGatewayContextError(
                "未找到有效的网关上下文，请先在实盘交易页面连接并选择可用 gateway。"
            )
        if not gateway.get("has_runtime"):
            return self._build_degraded_context(
                "所选网关已配置但尚未建立运行时连接，请先完成连接后再试。"
            )

        account_snapshot = manager.query_gateway_account(gateway_id)
        if not account_snapshot:
            return self._build_degraded_context(
                "网关已连接，但当前无法读取账户快照，已停止自动交易。"
            )

        gateway_state = str(account_snapshot.get("state") or "").strip().lower()
        trade_connection = str(account_snapshot.get("trade_connection") or "").strip().lower()
        if gateway_state in {"error", "stopped"} or (
            trade_connection and trade_connection not in {"connected", "ready", "ok"}
        ):
            return self._build_degraded_context("网关交易连接尚未就绪，已停止自动交易。")

        account_balance = self._extract_account_balance(account_snapshot)
        if account_balance is None:
            return self._build_degraded_context(
                "当前网关未返回账户权益或余额，AI 交易已降级为仅解析意图。"
            )

        try:
            raw_positions = manager.query_gateway_positions(gateway_id, strict=True)
        except RuntimeError as exc:
            return self._build_degraded_context(
                f"网关持仓查询失败，已停止自动交易：{exc}"
            )

        return {
            "account_balance": account_balance,
            "current_positions": self._normalize_positions(raw_positions),
        }

    def _build_degraded_context(self, diagnostic_message: str) -> dict[str, Any]:
        """Return a degraded context marker with a diagnostic message."""
        return {
            "degraded": True,
            "diagnostic_message": diagnostic_message,
        }

    def _build_degraded_risk_assessment(self, diagnostic_message: str) -> RiskAssessment:
        """Build a rejected risk assessment for degraded responses."""
        return RiskAssessment(
            approved=False,
            risk_level=RiskLevel.HIGH,
            warnings=[diagnostic_message],
            blocked_reasons=[diagnostic_message],
            requires_confirmation=False,
        )

    def _extract_account_balance(self, account_snapshot: dict[str, Any]) -> float | None:
        """Extract a usable account balance from a gateway snapshot."""
        balance_keys = (
            "value",
            "total_equity",
            "totalEquity",
            "equity",
            "Equity",
            "balance",
            "Balance",
            "current_cash",
            "account_value",
            "accountValue",
            "available_balance",
            "availableBalance",
            "net_liquidation",
            "NetLiquidation",
            "netliquidation",
            "NetLiquidationValue",
            "total_margin_balance",
            "totalMarginBalance",
            "margin_balance",
            "marginBalance",
            "total_wallet_balance",
            "totalWalletBalance",
            "wallet_balance",
            "walletBalance",
        )
        for key in balance_keys:
            value = self._coerce_optional_float(account_snapshot.get(key))
            if value is not None:
                return value
        return None

    def _normalize_positions(self, positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Normalize gateway positions into the schema expected by the risk guard."""
        normalized_positions: list[dict[str, Any]] = []
        for position in positions:
            if not isinstance(position, dict):
                continue
            symbol = gateway_position_symbol(position)
            size = signed_gateway_size(position)
            if not symbol or abs(size) <= 1e-12:
                continue

            normalized_positions.append({"symbol": symbol, "size": size})
        return normalized_positions

    def _enrich_intent_with_asset_spec(
        self,
        intent: TradingIntent,
        request: AITradingRequest,
    ) -> None:
        """Attach asset specs before risk checks use notional values."""
        if not intent.symbol:
            return
        if request.dry_run:
            try:
                asset_spec = query_local_asset_spec(intent.symbol)
            except Exception as exc:
                logger.debug("Failed to enrich AI paper intent with local asset spec: %s", exc)
                return
        else:
            if not request.gateway_id:
                return
            try:
                from app.services.direct_order_service import DirectOrderService

                asset_spec = DirectOrderService()._gateway_asset_spec(
                    request.gateway_id,
                    intent.symbol,
                )
            except Exception as exc:
                logger.debug("Failed to enrich AI live intent with gateway asset spec: %s", exc)
                return
        if not isinstance(asset_spec, dict) or not asset_spec:
            return

        params = dict(intent.additional_params or {})
        for key, value in asset_spec.items():
            if value in (None, ""):
                continue
            params[key] = value
        intent.additional_params = params

    def _enrich_intent_with_live_asset_spec(
        self,
        intent: TradingIntent,
        request: AITradingRequest,
    ) -> None:
        """Backward-compatible wrapper for live-only callers."""
        self._enrich_intent_with_asset_spec(intent, request)

    def _coerce_optional_float(self, value: Any) -> float | None:
        """Safely coerce a value to float."""
        if value is None or value == "":
            return None
        if isinstance(value, dict):
            for key in ("amount", "value", "balance", "total"):
                parsed = self._coerce_optional_float(value.get(key))
                if parsed is not None:
                    return parsed
            return None
        try:
            return float(str(value).strip().replace(",", ""))
        except (TypeError, ValueError):
            return None

    def list_available_gateways(self) -> list[dict[str, Any]]:
        """List live gateways that can be selected from the AI trading page."""
        try:
            from app.services.live_trading_manager import get_live_trading_manager

            manager = get_live_trading_manager()
            return [
                {
                    "gateway_id": str(item.get("gateway_key") or ""),
                    "exchange_type": str(item.get("exchange_type") or ""),
                    "account_id": str(item.get("account_id") or ""),
                    "connected": bool(item.get("has_runtime")),
                }
                for item in manager.list_connected_gateways()
                if item.get("gateway_key")
            ]
        except Exception as exc:
            logger.debug("Failed to list available gateways: %s", exc)
            return []

    async def list_available_accounts(self, user_id: str) -> list[dict[str, Any]]:
        """List selectable paper-trading accounts for the current user."""
        try:
            from app.services.paper_trading_service import PaperTradingService

            service = PaperTradingService()
            accounts, _ = await service.list_accounts(user_id=user_id, limit=100, offset=0)
            return [
                {
                    "account_id": account.id,
                    "name": account.name,
                    "total_equity": float(account.total_equity),
                    "current_cash": float(account.current_cash),
                    "is_active": bool(account.is_active),
                    "source": "paper",
                }
                for account in accounts
            ]
        except Exception as exc:
            logger.debug("Failed to list available paper-trading accounts: %s", exc)
            return []

    def _build_market_context(self, request: AITradingRequest) -> str:
        """Build market context string for intent parsing."""
        return _build_market_context(request)

    def _build_rejection_message(self, risk: RiskAssessment) -> str:
        """Build user-friendly rejection message."""
        return _build_rejection_message(risk)

    def _build_confirmation_message(self, intent: TradingIntent, risk: RiskAssessment) -> str:
        """Build confirmation request message."""
        return _build_confirmation_message(intent, risk)

    def _build_dry_run_message(self, intent: TradingIntent) -> str:
        """Build dry run result message."""
        return _build_dry_run_message(intent)

    def _build_execution_message(self, intent: TradingIntent, result: dict[str, Any]) -> str:
        """Build execution result message."""
        return _build_execution_message(intent, result)

    def _build_suggestions(self, intent: TradingIntent, risk: RiskAssessment) -> list[str]:
        """Build actionable suggestions for the user."""
        return _build_suggestions(intent, risk)

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
                    f"AI 交易需要确认: {intent.action.value} {intent.quantity} {intent.symbol}"
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


# ─── Backward-compatible re-exports ──────────────────────────────────────────
# These names used to live in this module; iteration 174 (C9) moved them to
# ``app.services.ai_trading.conditional_orders`` but tests still import them
# from here, so we keep them visible.
__all__ = [
    "AITradingService",
    "ConditionalOrderManager",
    "MissingGatewayContextError",
    "_conditional_orders",
    "_pending_trades",
    "get_conditional_order_manager",
    "get_risk_guard",
]
