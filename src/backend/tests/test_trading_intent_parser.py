"""Tests for trading_intent_parser - NLP to structured trading intent."""

from unittest.mock import patch

import pytest

from app.schemas.ai_trading import OrderType, RiskLevel, TradeAction
from app.services.trading_intent_parser import (
    _extract_json,
    _parse_action,
    _parse_order_type,
    _parse_risk_level,
    _safe_float,
    parse_trading_intent,
)


class TestExtractJson:
    """Test JSON extraction from various text formats."""

    def test_plain_json(self):
        text = '{"action": "buy", "symbol": "rb2501"}'
        result = _extract_json(text)
        assert result == {"action": "buy", "symbol": "rb2501"}

    def test_json_with_markdown_code_block(self):
        text = '```json\n{"action": "sell", "quantity": 10}\n```'
        result = _extract_json(text)
        assert result == {"action": "sell", "quantity": 10}

    def test_json_embedded_in_text(self):
        text = 'Here is the result: {"action": "query"} end of response'
        result = _extract_json(text)
        assert result == {"action": "query"}

    def test_invalid_json_returns_none(self):
        text = "This is not JSON at all"
        result = _extract_json(text)
        assert result is None

    def test_empty_string(self):
        result = _extract_json("")
        assert result is None

    def test_json_with_whitespace(self):
        text = '  \n  {"action": "close"}  \n  '
        result = _extract_json(text)
        assert result == {"action": "close"}

    def test_nested_json(self):
        text = '{"action": "buy", "params": {"period": 20}}'
        result = _extract_json(text)
        assert result["params"]["period"] == 20

    def test_json_with_code_block_no_lang(self):
        text = '```\n{"action": "buy"}\n```'
        result = _extract_json(text)
        assert result == {"action": "buy"}

    def test_malformed_json_returns_none(self):
        text = '{"action": "buy", "symbol": }'
        result = _extract_json(text)
        assert result is None


class TestParseAction:
    """Test action string parsing."""

    def test_buy(self):
        assert _parse_action("buy") == TradeAction.BUY

    def test_sell(self):
        assert _parse_action("sell") == TradeAction.SELL

    def test_close(self):
        assert _parse_action("close") == TradeAction.CLOSE

    def test_cancel(self):
        assert _parse_action("cancel") == TradeAction.CANCEL

    def test_query(self):
        assert _parse_action("query") == TradeAction.QUERY

    def test_modify(self):
        assert _parse_action("modify") == TradeAction.MODIFY

    def test_unknown_defaults_to_query(self):
        assert _parse_action("unknown") == TradeAction.QUERY

    def test_case_insensitive(self):
        assert _parse_action("BUY") == TradeAction.BUY
        assert _parse_action("Sell") == TradeAction.SELL


class TestParseOrderType:
    """Test order type string parsing."""

    def test_market(self):
        assert _parse_order_type("market") == OrderType.MARKET

    def test_limit(self):
        assert _parse_order_type("limit") == OrderType.LIMIT

    def test_stop(self):
        assert _parse_order_type("stop") == OrderType.STOP

    def test_stop_limit(self):
        assert _parse_order_type("stop_limit") == OrderType.STOP_LIMIT

    def test_unknown_defaults_to_market(self):
        assert _parse_order_type("unknown") == OrderType.MARKET

    def test_case_insensitive(self):
        assert _parse_order_type("LIMIT") == OrderType.LIMIT


class TestParseRiskLevel:
    """Test risk level string parsing."""

    def test_low(self):
        assert _parse_risk_level("low") == RiskLevel.LOW

    def test_medium(self):
        assert _parse_risk_level("medium") == RiskLevel.MEDIUM

    def test_high(self):
        assert _parse_risk_level("high") == RiskLevel.HIGH

    def test_critical(self):
        assert _parse_risk_level("critical") == RiskLevel.CRITICAL

    def test_unknown_defaults_to_medium(self):
        assert _parse_risk_level("unknown") == RiskLevel.MEDIUM


class TestSafeFloat:
    """Test safe float conversion."""

    def test_valid_float(self):
        assert _safe_float(3.14) == 3.14

    def test_valid_int(self):
        assert _safe_float(10) == 10.0

    def test_valid_string(self):
        assert _safe_float("3.14") == 3.14

    def test_none_returns_none(self):
        assert _safe_float(None) is None

    def test_zero_returns_none(self):
        assert _safe_float(0) is None

    def test_negative_returns_none(self):
        assert _safe_float(-5) is None

    def test_invalid_string_returns_none(self):
        assert _safe_float("abc") is None

    def test_empty_string_returns_none(self):
        assert _safe_float("") is None

    def test_list_returns_none(self):
        assert _safe_float([1, 2]) is None


class TestParseTradingIntent:
    """Test the main parse_trading_intent function."""

    @pytest.mark.asyncio
    async def test_ai_disabled_returns_low_confidence(self):
        """When AI is not enabled, returns a fallback intent."""
        with patch("app.services.trading_intent_parser._call_llm") as mock_llm:
            mock_llm.side_effect = RuntimeError("AI chat is not enabled")
            result = await parse_trading_intent("买入10手螺纹钢")
            assert result.action == TradeAction.QUERY
            assert result.confidence == 0.0
            assert result.risk_level == RiskLevel.HIGH
            assert "买入10手螺纹钢" in result.raw_input

    @pytest.mark.asyncio
    async def test_successful_parse(self):
        """When AI returns valid JSON, intent is properly constructed."""
        mock_response = '{"action": "buy", "symbol": "rb2501", "exchange": "ctp", "quantity": 10, "price": 3500.0, "order_type": "limit", "stop_loss": 3400.0, "take_profit": 3700.0, "reason": "趋势突破", "confidence": 0.85, "risk_level": "medium"}'
        with patch("app.services.trading_intent_parser._call_llm") as mock_llm:
            mock_llm.return_value = mock_response
            result = await parse_trading_intent("买入10手螺纹钢rb2501，限价3500")
            assert result.action == TradeAction.BUY
            assert result.symbol == "rb2501"
            assert result.exchange == "ctp"
            assert result.quantity == 10
            assert result.price == 3500.0
            assert result.order_type == OrderType.LIMIT
            assert result.stop_loss == 3400.0
            assert result.take_profit == 3700.0
            assert result.confidence == 0.85
            assert result.risk_level == RiskLevel.MEDIUM

    @pytest.mark.asyncio
    async def test_invalid_json_response(self):
        """When AI returns non-JSON, returns fallback intent."""
        with patch("app.services.trading_intent_parser._call_llm") as mock_llm:
            mock_llm.return_value = "I don't understand your request"
            result = await parse_trading_intent("随便说点什么")
            assert result.action == TradeAction.QUERY
            assert result.confidence == 0.0
            assert result.risk_level == RiskLevel.HIGH

    @pytest.mark.asyncio
    async def test_partial_json_response(self):
        """When AI returns partial JSON, fills in defaults."""
        mock_response = '{"action": "query", "confidence": 0.9}'
        with patch("app.services.trading_intent_parser._call_llm") as mock_llm:
            mock_llm.return_value = mock_response
            result = await parse_trading_intent("查看持仓")
            assert result.action == TradeAction.QUERY
            assert result.confidence == 0.9
            assert result.symbol is None
            assert result.quantity is None

    @pytest.mark.asyncio
    async def test_confidence_clamped_to_range(self):
        """Confidence is clamped between 0.0 and 1.0."""
        mock_response = '{"action": "buy", "symbol": "rb2501", "quantity": 1, "confidence": 1.5}'
        with patch("app.services.trading_intent_parser._call_llm") as mock_llm:
            mock_llm.return_value = mock_response
            result = await parse_trading_intent("买入")
            assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_negative_confidence_clamped(self):
        """Negative confidence is clamped to 0.0."""
        mock_response = '{"action": "buy", "symbol": "rb2501", "quantity": 1, "confidence": -0.5}'
        with patch("app.services.trading_intent_parser._call_llm") as mock_llm:
            mock_llm.return_value = mock_response
            result = await parse_trading_intent("买入")
            assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_additional_params_captured(self):
        """Extra fields in JSON are captured in additional_params."""
        mock_response = '{"action": "buy", "symbol": "rb2501", "quantity": 1, "confidence": 0.8, "custom_field": "hello", "extra": 42}'
        with patch("app.services.trading_intent_parser._call_llm") as mock_llm:
            mock_llm.return_value = mock_response
            result = await parse_trading_intent("买入")
            assert result.additional_params.get("custom_field") == "hello"
            assert result.additional_params.get("extra") == 42

    @pytest.mark.asyncio
    async def test_market_context_passed(self):
        """Market context is passed to the LLM call."""
        mock_response = '{"action": "query", "confidence": 0.9}'
        with patch("app.services.trading_intent_parser._call_llm") as mock_llm:
            mock_llm.return_value = mock_response
            await parse_trading_intent("查看持仓", market_context="螺纹钢主力合约3500")
            # Verify the system prompt was built with market context
            call_args = mock_llm.call_args
            assert "螺纹钢主力合约3500" in call_args[1][
                "system_prompt"
            ] or "螺纹钢主力合约3500" in str(call_args)
