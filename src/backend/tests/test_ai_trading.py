"""Tests for AI Trading service and API.

Tests the natural language trading pipeline including:
- Intent parsing (mocked LLM)
- Risk guard assessment
- API endpoints
- Trade confirmation flow
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.schemas.ai_trading import (
    AITradingRequest,
    OrderType,
    RiskLevel,
    TradeAction,
    TradeStatus,
    TradingIntent,
)
from app.services.ai_trading_service import AITradingService
from app.services.trading_risk_guard import TradingRiskConfig, TradingRiskGuard


class TestTradingRiskGuard:
    """Test the risk guard assessment logic."""

    def setup_method(self):
        self.guard = TradingRiskGuard(
            TradingRiskConfig(
                max_single_trade_amount=10000,
                max_daily_trades=50,
                max_position_ratio=0.3,
                require_confirmation_above=5000,
                min_confidence_threshold=0.3,
                blocked_symbols=["FORBIDDEN"],
            )
        )

    def test_query_always_approved(self):
        intent = TradingIntent(action=TradeAction.QUERY, confidence=0.1)
        result = self.guard.assess(intent)
        assert result.approved is True
        assert result.risk_level == RiskLevel.LOW

    def test_low_confidence_blocked(self):
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="BTCUSDT",
            quantity=1,
            confidence=0.1,
        )
        result = self.guard.assess(intent)
        assert result.approved is False
        assert "置信度过低" in result.blocked_reasons[0]

    def test_missing_symbol_blocked(self):
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol=None,
            quantity=1,
            confidence=0.8,
        )
        result = self.guard.assess(intent)
        assert result.approved is False
        assert "品种未指定" in result.blocked_reasons[0]

    def test_missing_quantity_blocked(self):
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="BTCUSDT",
            quantity=None,
            confidence=0.8,
        )
        result = self.guard.assess(intent)
        assert result.approved is False
        assert "数量未指定" in result.blocked_reasons[0]

    def test_blocked_symbol(self):
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="FORBIDDEN",
            quantity=1,
            confidence=0.8,
        )
        result = self.guard.assess(intent)
        assert result.approved is False
        assert "禁止交易列表" in result.blocked_reasons[0]

    def test_valid_trade_approved(self):
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="BTCUSDT",
            quantity=0.1,
            confidence=0.8,
            risk_level=RiskLevel.LOW,
        )
        result = self.guard.assess(intent)
        assert result.approved is True

    def test_high_value_requires_confirmation(self):
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="BTCUSDT",
            quantity=1,
            price=8000,
            confidence=0.8,
            risk_level=RiskLevel.MEDIUM,
        )
        result = self.guard.assess(intent, account_balance=100000)
        assert result.approved is True
        assert result.requires_confirmation is True

    def test_no_stop_loss_warning(self):
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=1,
            order_type=OrderType.MARKET,
            confidence=0.8,
            risk_level=RiskLevel.LOW,
        )
        result = self.guard.assess(intent)
        assert result.approved is True
        assert any("止损" in w for w in result.warnings)

    def test_daily_trade_limit(self):
        # Set the last reset date to today so it won't reset
        from datetime import datetime, timezone

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.guard._daily_trade_count = 50
        self.guard._last_reset_date = today
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="BTCUSDT",
            quantity=1,
            confidence=0.8,
        )
        result = self.guard.assess(intent)
        assert result.approved is False
        assert "每日最大交易次数" in result.blocked_reasons[0]


class TestAITradingService:
    """Test the AI trading service orchestration."""

    @pytest.fixture
    def service(self):
        return AITradingService()

    async def test_dry_run_execution(self, service):
        """Dry run should return confirmed status without real execution."""
        mock_intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=1,
            confidence=0.9,
            risk_level=RiskLevel.LOW,
            reason="测试买入",
        )

        with (
            patch(
                "app.services.ai_trading_service.parse_trading_intent",
                new_callable=AsyncMock,
                return_value=mock_intent,
            ),
            patch.object(
                service,
                "_resolve_trading_context",
                new_callable=AsyncMock,
                return_value={"account_balance": 100000.0, "current_positions": []},
            ),
        ):
            request = AITradingRequest(message="买入1手螺纹钢", dry_run=True)
            result = await service.process_trading_request("user1", request)

        assert result.status == TradeStatus.CONFIRMED
        assert result.execution_result is not None
        assert result.execution_result.get("dry_run") is True

    async def test_rejected_by_risk_guard(self, service):
        """Low confidence intent should be rejected."""
        mock_intent = TradingIntent(
            action=TradeAction.BUY,
            symbol=None,
            quantity=1,
            confidence=0.1,
            risk_level=RiskLevel.HIGH,
        )

        with (
            patch(
                "app.services.ai_trading_service.parse_trading_intent",
                new_callable=AsyncMock,
                return_value=mock_intent,
            ),
            patch.object(
                service,
                "_resolve_trading_context",
                new_callable=AsyncMock,
                return_value={"account_balance": 100000.0, "current_positions": []},
            ),
        ):
            request = AITradingRequest(message="买点什么", dry_run=True)
            result = await service.process_trading_request("user1", request)

        assert result.status == TradeStatus.REJECTED
        assert "风控拦截" in result.message

    async def test_missing_paper_account_context_raises(self, service):
        """Dry-run execution now requires an explicit paper-trading account context."""
        from app.services.ai_trading_service import MissingGatewayContextError

        mock_intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=1,
            confidence=0.9,
            risk_level=RiskLevel.LOW,
        )

        with patch(
            "app.services.ai_trading_service.parse_trading_intent",
            new_callable=AsyncMock,
            return_value=mock_intent,
        ):
            request = AITradingRequest(message="买入1手螺纹钢", dry_run=True)
            with pytest.raises(MissingGatewayContextError, match="account_id"):
                await service.process_trading_request("user1", request)

    async def test_live_gateway_without_runtime_returns_degraded_response(self, service):
        """A configured but not connected gateway returns a degraded response."""

        class FakeManager:
            def list_connected_gateways(self):
                return [
                    {
                        "gateway_key": "manual:CTP:test",
                        "exchange_type": "CTP",
                        "account_id": "investor-001",
                        "has_runtime": False,
                    }
                ]

        mock_intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=1,
            confidence=0.9,
            risk_level=RiskLevel.LOW,
        )

        with (
            patch(
                "app.services.ai_trading_service.parse_trading_intent",
                new_callable=AsyncMock,
                return_value=mock_intent,
            ),
            patch(
                "app.services.live_trading_manager.get_live_trading_manager",
                return_value=FakeManager(),
            ),
        ):
            request = AITradingRequest(
                message="买入1手螺纹钢",
                dry_run=False,
                gateway_id="manual:CTP:test",
            )
            result = await service.process_trading_request("user1", request)

        assert result.status == TradeStatus.REJECTED
        assert result.degraded is True
        assert result.diagnostic_message is not None
        assert "尚未建立运行时连接" in result.diagnostic_message


class TestAITradingAPI:
    """Test the AI trading API endpoints."""

    @pytest.fixture
    def client(self):
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def test_execute_requires_auth(self, client):
        """Execute endpoint requires authentication."""
        response = await client.post(
            "/api/v1/ai-trading/execute",
            json={
                "message": "买入1手螺纹钢",
            },
        )
        assert response.status_code in (401, 403)

    async def test_config_requires_auth(self, client):
        """Config endpoint requires authentication."""
        response = await client.get("/api/v1/ai-trading/config")
        assert response.status_code in (401, 403)

    async def test_history_requires_auth(self, client):
        """History endpoint requires authentication."""
        response = await client.get("/api/v1/ai-trading/history")
        assert response.status_code in (401, 403)

    async def test_execute_missing_context_returns_422(self, client, auth_headers):
        """Missing paper account context is translated to HTTP 422."""
        mock_intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=1,
            confidence=0.9,
            risk_level=RiskLevel.LOW,
        )

        with patch(
            "app.services.ai_trading_service.parse_trading_intent",
            new_callable=AsyncMock,
            return_value=mock_intent,
        ):
            response = await client.post(
                "/api/v1/ai-trading/execute",
                json={"message": "买入1手螺纹钢", "dry_run": True},
                headers=auth_headers,
            )

        assert response.status_code == 422
        payload = response.json()
        error_message = payload.get("detail") or payload.get("message") or ""
        assert "account_id" in error_message

    async def test_config_exposes_available_context_options(self, client, auth_headers):
        """Config endpoint returns selectable paper and connected account options."""
        with (
            patch.object(
                AITradingService,
                "list_available_gateways",
                return_value=[
                    {
                        "gateway_id": "manual:CTP:test",
                        "exchange_type": "CTP",
                        "account_id": "investor-001",
                        "connected": True,
                    },
                    {
                        "gateway_id": "manual:CTP:stale",
                        "exchange_type": "CTP",
                        "account_id": "investor-stale",
                        "connected": False,
                    }
                ],
            ),
            patch.object(
                AITradingService,
                "list_available_accounts",
                new_callable=AsyncMock,
                return_value=[
                    {
                        "account_id": "paper-001",
                        "name": "主模拟账户",
                        "total_equity": 100000.0,
                        "current_cash": 80000.0,
                        "is_active": True,
                        "source": "paper",
                    }
                ],
            ),
        ):
            response = await client.get("/api/v1/ai-trading/config", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["available_gateways"][0]["gateway_id"] == "manual:CTP:test"
        assert data["available_accounts"][0]["account_id"] == "paper-001"
        assert data["available_accounts"][1] == {
            "account_id": "investor-001",
            "name": "CTP · investor-001",
            "total_equity": None,
            "current_cash": None,
            "is_active": True,
            "source": "gateway",
            "gateway_id": "manual:CTP:test",
            "exchange_type": "CTP",
            "connected": True,
        }
        assert all(item["account_id"] != "investor-stale" for item in data["available_accounts"])


class TestTradingIntentParser:
    """Test the intent parser with mocked LLM responses."""

    async def test_call_llm_uses_observable_ai_chat_entrypoint(self):
        from app.services.trading_intent_parser import _call_llm

        mock_response = (
            '{"action":"query","symbol":null,"exchange":null,"quantity":null,'
            '"price":null,"order_type":"market","stop_loss":null,"take_profit":null,'
            '"reason":"查询","confidence":0.9,"risk_level":"low"}'
        )

        with patch("app.services.trading_intent_parser.AIChatService") as mock_service_class:
            service = mock_service_class.return_value
            service.is_enabled.return_value = True
            service.generate_answer = AsyncMock(
                return_value={
                    "answer": mock_response,
                    "tokens_used": 10,
                    "model_id": "gpt-4o-mini",
                    "strategy_draft": None,
                    "reasoning": None,
                }
            )
            result = await _call_llm("看看持仓", "system prompt")

        assert result == mock_response
        service.generate_answer.assert_awaited_once()

    async def test_parse_buy_intent(self):
        """Parse a simple buy instruction."""
        from app.services.trading_intent_parser import parse_trading_intent

        mock_response = '{"action":"buy","symbol":"rb2501","exchange":"ctp","quantity":1,"price":null,"order_type":"market","stop_loss":null,"take_profit":null,"reason":"用户要求买入螺纹钢","confidence":0.9,"risk_level":"low"}'

        with patch(
            "app.services.trading_intent_parser._call_llm",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            intent = await parse_trading_intent("买入1手螺纹钢主力合约")

        assert intent.action == TradeAction.BUY
        assert intent.symbol == "rb2501"
        assert intent.quantity == 1
        assert intent.order_type == OrderType.MARKET
        assert intent.confidence == 0.9

    async def test_parse_sell_with_price(self):
        """Parse a sell instruction with limit price."""
        from app.services.trading_intent_parser import parse_trading_intent

        mock_response = '{"action":"sell","symbol":"i2501","exchange":"ctp","quantity":2,"price":3500,"order_type":"limit","stop_loss":null,"take_profit":null,"reason":"限价卖出铁矿石","confidence":0.85,"risk_level":"medium"}'

        with patch(
            "app.services.trading_intent_parser._call_llm",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            intent = await parse_trading_intent("以3500限价卖出2手铁矿石")

        assert intent.action == TradeAction.SELL
        assert intent.symbol == "i2501"
        assert intent.quantity == 2
        assert intent.price == 3500
        assert intent.order_type == OrderType.LIMIT

    async def test_parse_crypto_buy(self):
        """Parse a crypto buy instruction."""
        from app.services.trading_intent_parser import parse_trading_intent

        mock_response = '{"action":"buy","symbol":"BTCUSDT","exchange":"binance","quantity":0.1,"price":null,"order_type":"market","stop_loss":null,"take_profit":null,"reason":"在币安买入BTC","confidence":0.88,"risk_level":"medium"}'

        with patch(
            "app.services.trading_intent_parser._call_llm",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            intent = await parse_trading_intent("帮我在币安买入0.1个BTC")

        assert intent.action == TradeAction.BUY
        assert intent.symbol == "BTCUSDT"
        assert intent.exchange == "binance"
        assert intent.quantity == 0.1

    async def test_parse_query_intent(self):
        """Parse a query/position check instruction."""
        from app.services.trading_intent_parser import parse_trading_intent

        mock_response = '{"action":"query","symbol":null,"exchange":null,"quantity":null,"price":null,"order_type":"market","stop_loss":null,"take_profit":null,"reason":"用户查询持仓","confidence":0.95,"risk_level":"low"}'

        with patch(
            "app.services.trading_intent_parser._call_llm",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            intent = await parse_trading_intent("看看我现在的持仓")

        assert intent.action == TradeAction.QUERY
        assert intent.confidence == 0.95

    async def test_parse_ambiguous_input(self):
        """Ambiguous input should have low confidence."""
        from app.services.trading_intent_parser import parse_trading_intent

        mock_response = '{"action":"query","symbol":null,"exchange":null,"quantity":null,"price":null,"order_type":"market","stop_loss":null,"take_profit":null,"reason":"指令不明确","confidence":0.2,"risk_level":"high"}'

        with patch(
            "app.services.trading_intent_parser._call_llm",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            intent = await parse_trading_intent("随便搞点什么")

        assert intent.confidence < 0.5

    async def test_parse_llm_failure_returns_safe_default(self):
        """LLM failure should return a safe query intent with zero confidence."""
        from app.services.trading_intent_parser import parse_trading_intent

        with patch(
            "app.services.trading_intent_parser._call_llm",
            new_callable=AsyncMock,
            side_effect=RuntimeError("AI not configured"),
        ):
            intent = await parse_trading_intent("买入1手螺纹钢")

        assert intent.action == TradeAction.QUERY
        assert intent.confidence == 0.0
        assert intent.risk_level == RiskLevel.HIGH

    async def test_parse_invalid_json_returns_safe_default(self):
        """Invalid JSON from LLM should return safe default."""
        from app.services.trading_intent_parser import parse_trading_intent

        with patch(
            "app.services.trading_intent_parser._call_llm",
            new_callable=AsyncMock,
            return_value="I cannot parse this as JSON, sorry!",
        ):
            intent = await parse_trading_intent("买入1手螺纹钢")

        assert intent.action == TradeAction.QUERY
        assert intent.confidence == 0.0


class TestAITradingServiceConfirmation:
    """Test the trade confirmation flow."""

    @pytest.fixture
    def service(self):
        return AITradingService()

    async def test_pending_confirmation_flow(self, service):
        """High-risk trade should require confirmation."""
        mock_intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="BTCUSDT",
            quantity=0.1,
            price=None,  # market order, no value estimate
            confidence=0.9,
            risk_level=RiskLevel.HIGH,  # HIGH risk triggers confirmation
        )

        with (
            patch(
                "app.services.ai_trading_service.parse_trading_intent",
                new_callable=AsyncMock,
                return_value=mock_intent,
            ),
            patch.object(
                service,
                "_resolve_trading_context",
                new_callable=AsyncMock,
                return_value={"account_balance": 100000.0, "current_positions": []},
            ),
        ):
            request = AITradingRequest(message="买入1个BTC", dry_run=False)
            result = await service.process_trading_request("user1", request)

        assert result.status == TradeStatus.PENDING_CONFIRMATION
        assert result.requires_confirmation is True
        assert result.trade_id

    async def test_confirm_trade_success(self, service):
        """Confirming a pending trade should execute it."""
        from app.schemas.ai_trading import TradeConfirmRequest

        mock_intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=1,
            confidence=0.9,
            risk_level=RiskLevel.HIGH,
        )

        # First create a pending trade
        with (
            patch(
                "app.services.ai_trading_service.parse_trading_intent",
                new_callable=AsyncMock,
                return_value=mock_intent,
            ),
            patch.object(
                service,
                "_resolve_trading_context",
                new_callable=AsyncMock,
                return_value={"account_balance": 100000.0, "current_positions": []},
            ),
        ):
            request = AITradingRequest(message="买入1手螺纹钢", dry_run=False)
            pending_result = await service.process_trading_request("user1", request)

        assert pending_result.status == TradeStatus.PENDING_CONFIRMATION

        # Mock the execution for confirmation
        mock_execution = {"success": True, "type": "paper_trade", "message": "模拟执行成功"}
        with patch.object(
            service, "_execute_trade", new_callable=AsyncMock, return_value=mock_execution
        ):
            confirm_req = TradeConfirmRequest(
                trade_id=pending_result.trade_id,
                confirmed=True,
            )
            confirm_result = await service.confirm_trade("user1", confirm_req)
        assert confirm_result.status == TradeStatus.FILLED

    async def test_reject_trade(self, service):
        """Rejecting a pending trade should cancel it."""
        from app.schemas.ai_trading import TradeConfirmRequest

        mock_intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=1,
            confidence=0.9,
            risk_level=RiskLevel.HIGH,
        )

        with (
            patch(
                "app.services.ai_trading_service.parse_trading_intent",
                new_callable=AsyncMock,
                return_value=mock_intent,
            ),
            patch.object(
                service,
                "_resolve_trading_context",
                new_callable=AsyncMock,
                return_value={"account_balance": 100000.0, "current_positions": []},
            ),
        ):
            request = AITradingRequest(message="买入1手螺纹钢", dry_run=False)
            pending_result = await service.process_trading_request("user1", request)

        confirm_req = TradeConfirmRequest(
            trade_id=pending_result.trade_id,
            confirmed=False,
        )
        confirm_result = await service.confirm_trade("user1", confirm_req)
        assert confirm_result.status == TradeStatus.CANCELLED

    async def test_confirm_nonexistent_trade(self, service):
        """Confirming a non-existent trade should fail."""
        from app.schemas.ai_trading import TradeConfirmRequest

        confirm_req = TradeConfirmRequest(
            trade_id="nonexistent",
            confirmed=True,
        )
        result = await service.confirm_trade("user1", confirm_req)
        assert result.status == TradeStatus.FAILED
        assert "不存在" in result.message

    async def test_confirm_wrong_user(self, service):
        """Confirming another user's trade should fail."""
        from app.schemas.ai_trading import TradeConfirmRequest

        mock_intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=1,
            confidence=0.9,
            risk_level=RiskLevel.HIGH,
        )

        with (
            patch(
                "app.services.ai_trading_service.parse_trading_intent",
                new_callable=AsyncMock,
                return_value=mock_intent,
            ),
            patch.object(
                service,
                "_resolve_trading_context",
                new_callable=AsyncMock,
                return_value={"account_balance": 100000.0, "current_positions": []},
            ),
        ):
            request = AITradingRequest(message="买入1手螺纹钢", dry_run=False)
            pending_result = await service.process_trading_request("user1", request)

        confirm_req = TradeConfirmRequest(
            trade_id=pending_result.trade_id,
            confirmed=True,
        )
        result = await service.confirm_trade("user2", confirm_req)
        assert result.status == TradeStatus.FAILED
        assert "无权" in result.message


class TestRiskGuardEdgeCases:
    """Test edge cases in the risk guard."""

    def setup_method(self):
        self.guard = TradingRiskGuard(
            TradingRiskConfig(
                max_single_trade_amount=10000,
                max_daily_trades=50,
                require_confirmation_above=5000,
                min_confidence_threshold=0.3,
                allowed_exchanges=["ctp", "binance", "okx"],
            )
        )

    def test_exchange_not_in_whitelist(self):
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="AAPL",
            exchange="nasdaq",
            quantity=10,
            confidence=0.8,
        )
        result = self.guard.assess(intent)
        assert result.approved is False
        assert "不在允许列表" in result.blocked_reasons[0]

    def test_exchange_in_whitelist(self):
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="BTCUSDT",
            exchange="binance",
            quantity=0.1,
            confidence=0.8,
            risk_level=RiskLevel.LOW,
        )
        result = self.guard.assess(intent)
        assert result.approved is True

    def test_close_action_without_quantity(self):
        """Close action should still work without quantity."""
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="rb2501",
            quantity=None,
            confidence=0.8,
        )
        result = self.guard.assess(intent)
        # Close doesn't require quantity in the same way buy/sell does
        assert result.approved is True

    def test_position_impact_description(self):
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="BTCUSDT",
            quantity=0.5,
            confidence=0.8,
            risk_level=RiskLevel.LOW,
        )
        positions = [{"symbol": "BTCUSDT", "size": 1.0}]
        result = self.guard.assess(intent, current_positions=positions)
        assert result.position_impact is not None
        assert "增加" in result.position_impact

    def test_record_trade_increments_counter(self):
        assert self.guard._daily_trade_count == 0
        self.guard.record_trade(profit_loss=-100)
        assert self.guard._daily_trade_count == 1
        assert self.guard._daily_loss == 100


class TestDirectOrderServiceLive:
    """Test the live trading execution path (mocked ZMQ)."""

    async def test_live_trade_no_gateway_returns_error(self):
        """Without a gateway, live trade should return clear error."""
        from app.services.direct_order_service import DirectOrderService

        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=1,
            confidence=0.9,
            risk_level=RiskLevel.LOW,
        )
        result = await service.execute_live_trade(intent, user_id="user1", gateway_id=None)
        assert result["success"] is False
        assert "no_gateway" in result.get("error", "") or "未找到" in result.get("message", "")

    async def test_live_trade_gateway_not_found(self):
        """With invalid gateway_id, should return gateway_not_found."""
        from app.services.direct_order_service import DirectOrderService

        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=1,
            confidence=0.9,
        )
        result = await service.execute_live_trade(
            intent, user_id="user1", gateway_id="nonexistent_gateway"
        )
        assert result["success"] is False
        assert "not_found" in result.get("error", "") or "不可用" in result.get("message", "")

    async def test_build_order_payload_market(self):
        """Market order payload should have price=0."""
        from app.services.direct_order_service import DirectOrderService

        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=2,
            order_type=OrderType.MARKET,
            confidence=0.9,
        )
        payload = service._build_order_payload(intent)
        assert payload["symbol"] == "rb2501"
        assert payload["side"] == "buy"
        assert payload["size"] == 2
        assert payload["price"] == 0
        assert payload["offset"] == "open"
        assert payload["strategy_id"] == "ai_trading"

    async def test_build_order_payload_limit(self):
        """Limit order payload should have the specified price."""
        from app.services.direct_order_service import DirectOrderService

        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.SELL,
            symbol="i2501",
            quantity=3,
            price=850.5,
            order_type=OrderType.LIMIT,
            confidence=0.9,
        )
        payload = service._build_order_payload(intent)
        assert payload["symbol"] == "i2501"
        assert payload["side"] == "sell"
        assert payload["size"] == 3
        assert payload["price"] == 850.5
        assert payload["offset"] == "open"

    async def test_build_order_payload_close(self):
        """Close action should set offset=close."""
        from app.services.direct_order_service import DirectOrderService

        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="rb2501",
            quantity=1,
            confidence=0.9,
        )
        payload = service._build_order_payload(intent)
        assert payload["offset"] == "close"

    async def test_live_trade_with_mocked_zmq_success(self):
        """Successful ZMQ response should return success."""
        from app.services.direct_order_service import DirectOrderService

        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=1,
            confidence=0.9,
        )

        # Mock the gateway lookup and ZMQ call
        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://127.0.0.1:9999"
            ),
            patch.object(
                service,
                "_send_gateway_command",
                return_value={"order_id": "12345", "status": "submitted"},
            ),
        ):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="manual:CTP:test"
            )

        assert result["success"] is True
        assert result["type"] == "live_trade"
        assert result["symbol"] == "rb2501"
        assert "已提交" in result["message"]

    async def test_live_trade_with_mocked_zmq_failure(self):
        """Failed ZMQ response (None) should return failure."""
        from app.services.direct_order_service import DirectOrderService

        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=1,
            confidence=0.9,
        )

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://127.0.0.1:9999"
            ),
            patch.object(service, "_send_gateway_command", return_value=None),
        ):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="manual:CTP:test"
            )

        assert result["success"] is False
        assert "失败" in result["message"]

    async def test_live_query_positions(self):
        """Query positions via mocked gateway."""
        from app.services.direct_order_service import DirectOrderService

        service = DirectOrderService()
        intent = TradingIntent(action=TradeAction.QUERY, confidence=0.9)

        mock_positions = [
            {"symbol": "rb2501", "volume": 2, "direction": "long"},
            {"symbol": "i2501", "volume": 1, "direction": "short"},
        ]

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://127.0.0.1:9999"
            ),
            patch.object(service, "_send_gateway_command", return_value=mock_positions),
        ):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="manual:CTP:test"
            )

        assert result["success"] is True
        assert result["type"] == "live_query"
        assert len(result["positions"]) == 2


class TestConditionalOrders:
    """Test conditional order management."""

    def test_create_conditional_order(self):
        from app.services.ai_trading_service import ConditionalOrderManager

        manager = ConditionalOrderManager()
        result = manager.create_conditional_order(
            user_id="user1",
            condition="BTC跌到60000",
            action_message="买入0.1个BTC",
            dry_run=True,
            expiry_hours=24.0,
        )
        assert result["id"]
        assert result["status"] == "active"
        assert result["condition"] == "BTC跌到60000"
        assert result["action_message"] == "买入0.1个BTC"

    def test_list_conditional_orders(self):
        from app.services.ai_trading_service import ConditionalOrderManager, _conditional_orders

        _conditional_orders.clear()
        manager = ConditionalOrderManager()

        manager.create_conditional_order("user1", "条件A", "动作A")
        manager.create_conditional_order("user1", "条件B", "动作B")
        manager.create_conditional_order("user2", "条件C", "动作C")

        user1_orders = manager.list_conditional_orders("user1")
        assert len(user1_orders) == 2

        user2_orders = manager.list_conditional_orders("user2")
        assert len(user2_orders) == 1

    def test_cancel_conditional_order(self):
        from app.services.ai_trading_service import ConditionalOrderManager, _conditional_orders

        _conditional_orders.clear()
        manager = ConditionalOrderManager()

        result = manager.create_conditional_order("user1", "条件", "动作")
        order_id = result["id"]

        # Cancel by owner
        assert manager.cancel_conditional_order(order_id, "user1") is True
        orders = manager.list_conditional_orders("user1")
        assert orders[0]["status"] == "cancelled"

    def test_cancel_wrong_user(self):
        from app.services.ai_trading_service import ConditionalOrderManager, _conditional_orders

        _conditional_orders.clear()
        manager = ConditionalOrderManager()

        result = manager.create_conditional_order("user1", "条件", "动作")
        order_id = result["id"]

        # Cannot cancel another user's order
        assert manager.cancel_conditional_order(order_id, "user2") is False

    def test_expire_old_orders(self):
        from app.services.ai_trading_service import ConditionalOrderManager, _conditional_orders

        _conditional_orders.clear()
        manager = ConditionalOrderManager()

        # Create an order that's already expired
        manager.create_conditional_order("user1", "条件", "动作", expiry_hours=0.0)

        # Listing should mark it as expired
        import time

        time.sleep(0.01)  # Ensure time passes
        orders = manager.list_conditional_orders("user1")
        assert orders[0]["status"] == "expired"
