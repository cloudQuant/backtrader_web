"""Tests for TradingRiskGuard service - multi-layer risk control."""

from datetime import datetime, timezone

import pytest

from app.schemas.ai_trading import (
    OrderType,
    RiskLevel,
    TradeAction,
    TradingIntent,
)
from app.services.trading_risk_guard import TradingRiskConfig, TradingRiskGuard


class TestTradingRiskConfig:
    """Test TradingRiskConfig defaults and custom values."""

    def test_default_config(self):
        config = TradingRiskConfig()
        assert config.max_single_trade_amount == 10000.0
        assert config.max_daily_trades == 50
        assert config.max_position_ratio == 0.3
        assert config.require_confirmation_above == 5000.0
        assert config.blocked_symbols == []
        assert config.allowed_exchanges is None
        assert config.max_daily_loss == 5000.0
        assert config.min_confidence_threshold == 0.3

    def test_custom_config(self):
        config = TradingRiskConfig(
            max_single_trade_amount=50000.0,
            max_daily_trades=100,
            max_position_ratio=0.5,
            require_confirmation_above=10000.0,
            blocked_symbols=["ST001", "ST002"],
            allowed_exchanges=["ctp", "binance"],
            max_daily_loss=10000.0,
            min_confidence_threshold=0.5,
        )
        assert config.max_single_trade_amount == 50000.0
        assert config.max_daily_trades == 100
        assert config.blocked_symbols == ["ST001", "ST002"]
        assert config.allowed_exchanges == ["ctp", "binance"]


class TestTradingRiskGuardQueryAction:
    """Test that QUERY actions always pass."""

    def test_query_always_approved(self):
        guard = TradingRiskGuard()
        intent = TradingIntent(
            action=TradeAction.QUERY,
            confidence=0.0,  # Even zero confidence
            risk_level=RiskLevel.CRITICAL,
        )
        result = guard.assess(intent)
        assert result.approved is True
        assert result.risk_level == RiskLevel.LOW
        assert result.warnings == []
        assert result.requires_confirmation is False


class TestTradingRiskGuardHardRules:
    """Test hard rules that block trades."""

    def test_low_confidence_blocks(self):
        guard = TradingRiskGuard(TradingRiskConfig(min_confidence_threshold=0.3))
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=10,
            confidence=0.2,
        )
        result = guard.assess(intent)
        assert result.approved is False
        assert any("置信度过低" in r for r in result.blocked_reasons)

    def test_missing_symbol_blocks(self):
        guard = TradingRiskGuard()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol=None,
            quantity=10,
            confidence=0.8,
        )
        result = guard.assess(intent)
        assert result.approved is False
        assert any("品种未指定" in r for r in result.blocked_reasons)

    def test_missing_quantity_blocks(self):
        guard = TradingRiskGuard()
        intent = TradingIntent(
            action=TradeAction.SELL,
            symbol="rb2501",
            quantity=None,
            confidence=0.8,
        )
        result = guard.assess(intent)
        assert result.approved is False
        assert any("数量未指定" in r for r in result.blocked_reasons)

    def test_blocked_symbol(self):
        config = TradingRiskConfig(blocked_symbols=["ST001", "BADSTOCK"])
        guard = TradingRiskGuard(config)
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="st001",  # case insensitive
            quantity=100,
            confidence=0.9,
        )
        result = guard.assess(intent)
        assert result.approved is False
        assert any("禁止交易列表" in r for r in result.blocked_reasons)

    def test_exchange_not_in_whitelist(self):
        config = TradingRiskConfig(allowed_exchanges=["ctp", "binance"])
        guard = TradingRiskGuard(config)
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="AAPL",
            exchange="ib",
            quantity=10,
            confidence=0.9,
        )
        result = guard.assess(intent)
        assert result.approved is False
        assert any("不在允许列表" in r for r in result.blocked_reasons)

    def test_exchange_in_whitelist_passes(self):
        config = TradingRiskConfig(allowed_exchanges=["ctp", "binance"])
        guard = TradingRiskGuard(config)
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            exchange="CTP",  # case insensitive
            quantity=1,
            price=3500.0,
            confidence=0.9,
        )
        result = guard.assess(intent)
        # Should not be blocked by exchange rule
        assert not any("不在允许列表" in r for r in result.blocked_reasons)

    def test_daily_trade_limit_blocks(self):
        config = TradingRiskConfig(max_daily_trades=2)
        guard = TradingRiskGuard(config)
        # Simulate 2 trades already done
        guard._daily_trade_count = 2
        guard._last_reset_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=1,
            confidence=0.9,
        )
        result = guard.assess(intent)
        assert result.approved is False
        assert any("每日最大交易次数" in r for r in result.blocked_reasons)

    def test_daily_loss_limit_blocks_new_trades(self):
        config = TradingRiskConfig(
            max_daily_loss=500.0,
            max_single_trade_amount=100000.0,
        )
        guard = TradingRiskGuard(config)
        guard._daily_loss = 500.0
        guard._last_reset_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=1,
            price=3500.0,
            confidence=0.9,
        )
        result = guard.assess(intent)

        assert result.approved is False
        assert any("每日最大亏损" in r for r in result.blocked_reasons)

    def test_projected_loss_over_daily_limit_blocks_trade(self):
        config = TradingRiskConfig(
            max_daily_loss=500.0,
            max_single_trade_amount=100000.0,
            require_confirmation_above=100000.0,
        )
        guard = TradingRiskGuard(config)
        guard._daily_loss = 450.0
        guard._last_reset_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=1,
            price=3500.0,
            stop_loss=3400.0,
            confidence=0.9,
        )
        result = guard.assess(intent)

        assert result.approved is False
        assert result.max_loss_estimate == 100.0
        assert any("预计最大亏损" in r for r in result.blocked_reasons)

    def test_single_trade_amount_exceeds_limit(self):
        config = TradingRiskConfig(max_single_trade_amount=5000.0)
        guard = TradingRiskGuard(config)
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=10,
            price=1000.0,  # 10 * 1000 = 10000 > 5000
            confidence=0.9,
        )
        result = guard.assess(intent)
        assert result.approved is False
        assert any("单笔交易金额" in r for r in result.blocked_reasons)


class TestTradingRiskGuardSoftRules:
    """Test soft rules that generate warnings and require confirmation."""

    def test_confirmation_threshold(self):
        config = TradingRiskConfig(
            require_confirmation_above=3000.0,
            max_single_trade_amount=100000.0,
        )
        guard = TradingRiskGuard(config)
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=5,
            price=1000.0,  # 5000 > 3000
            confidence=0.9,
        )
        result = guard.assess(intent)
        assert result.requires_confirmation is True
        assert any("需要确认" in w for w in result.warnings)

    def test_position_ratio_warning(self):
        config = TradingRiskConfig(
            max_position_ratio=0.2,
            max_single_trade_amount=100000.0,
            require_confirmation_above=100000.0,
        )
        guard = TradingRiskGuard(config)
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=10,
            price=5000.0,  # 50000 / 100000 = 50% > 20%
            confidence=0.9,
        )
        result = guard.assess(intent, account_balance=100000.0)
        assert result.requires_confirmation is True
        assert any("占账户比例" in w for w in result.warnings)

    def test_high_risk_level_warning(self):
        config = TradingRiskConfig(max_single_trade_amount=100000.0)
        guard = TradingRiskGuard(config)
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=1,
            price=100.0,
            confidence=0.9,
            risk_level=RiskLevel.HIGH,
        )
        result = guard.assess(intent)
        assert result.requires_confirmation is True
        assert any("风险等级" in w for w in result.warnings)

    def test_market_order_without_stop_loss_warning(self):
        config = TradingRiskConfig(max_single_trade_amount=100000.0)
        guard = TradingRiskGuard(config)
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=1,
            confidence=0.9,
            order_type=OrderType.MARKET,
            stop_loss=None,
        )
        result = guard.assess(intent)
        assert any("止损" in w for w in result.warnings)


class TestTradingRiskGuardRiskLevel:
    """Test risk level determination."""

    def test_critical_when_blocked(self):
        guard = TradingRiskGuard()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol=None,  # Will be blocked
            quantity=10,
            confidence=0.9,
        )
        result = guard.assess(intent)
        assert result.risk_level == RiskLevel.CRITICAL

    def test_high_with_many_warnings(self):
        config = TradingRiskConfig(
            max_position_ratio=0.01,
            require_confirmation_above=1.0,
            max_single_trade_amount=100000.0,
        )
        guard = TradingRiskGuard(config)
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=10,
            price=5000.0,
            confidence=0.9,
            risk_level=RiskLevel.HIGH,
            order_type=OrderType.MARKET,
            stop_loss=None,
        )
        result = guard.assess(intent, account_balance=100000.0)
        # Should have 3+ warnings: confirmation, position ratio, risk level, stop loss
        assert result.risk_level == RiskLevel.HIGH

    def test_low_risk_clean_trade(self):
        config = TradingRiskConfig(max_single_trade_amount=100000.0)
        guard = TradingRiskGuard(config)
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=1,
            price=100.0,
            confidence=0.9,
            risk_level=RiskLevel.LOW,
            order_type=OrderType.LIMIT,
            stop_loss=90.0,
        )
        result = guard.assess(intent, account_balance=1000000.0)
        assert result.approved is True
        assert result.risk_level == RiskLevel.LOW


class TestTradingRiskGuardDailyCounters:
    """Test daily counter reset logic."""

    def test_record_trade_increments_count(self):
        guard = TradingRiskGuard()
        guard.record_trade(profit_loss=100.0)
        assert guard._daily_trade_count == 1
        assert guard._daily_loss == 0.0

    def test_record_trade_tracks_loss(self):
        guard = TradingRiskGuard()
        guard.record_trade(profit_loss=-500.0)
        assert guard._daily_trade_count == 1
        assert guard._daily_loss == 500.0

    def test_daily_reset_on_new_day(self):
        guard = TradingRiskGuard()
        guard._daily_trade_count = 10
        guard._daily_loss = 1000.0
        guard._last_reset_date = "2020-01-01"  # Old date

        # Calling assess should trigger reset
        intent = TradingIntent(action=TradeAction.QUERY, confidence=0.9)
        guard.assess(intent)
        assert guard._daily_trade_count == 0
        assert guard._daily_loss == 0.0


class TestTradingRiskGuardHelpers:
    """Test helper methods."""

    def test_estimate_trade_value_with_price(self):
        guard = TradingRiskGuard()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=10,
            price=3500.0,
            confidence=0.9,
        )
        value = guard._estimate_trade_value(intent, account_balance=100000.0)
        assert value == 35000.0

    def test_estimate_trade_value_for_inverse_contract_uses_contract_value(self):
        guard = TradingRiskGuard()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="BTC-USD-SWAP",
            exchange="okx",
            quantity=100,
            price=50000.0,
            stop_loss=45000.0,
            confidence=0.9,
            additional_params={
                "contract_type": "inverse",
                "ctVal": 100,
                "ctValCcy": "USD",
                "baseCcy": "BTC",
                "quoteCcy": "USD",
                "settleCcy": "BTC",
            },
        )

        trade_value = guard._estimate_trade_value(intent, account_balance=100000.0)
        max_loss = guard._estimate_max_loss(intent, trade_value=trade_value)

        assert trade_value == 10000.0
        assert max_loss == pytest.approx(1000.0)

    def test_explicit_inverse_flag_prefers_ctval_over_multiplier_aliases(self):
        guard = TradingRiskGuard()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="BTCUSD",
            exchange="okx",
            quantity=100,
            price=50000.0,
            stop_loss=45000.0,
            confidence=0.9,
            additional_params={
                "inverse": True,
                "multiplier": 1,
                "ctMult": 1,
                "ctVal": 100,
            },
        )

        trade_value = guard._estimate_trade_value(intent, account_balance=100000.0)
        max_loss = guard._estimate_max_loss(intent, trade_value=trade_value)

        assert trade_value == pytest.approx(10000.0)
        assert max_loss == pytest.approx(1000.0)

    def test_estimate_trade_value_no_price(self):
        guard = TradingRiskGuard()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=10,
            price=None,
            confidence=0.9,
        )
        value = guard._estimate_trade_value(intent, account_balance=100000.0)
        assert value is None

    def test_estimate_trade_value_no_quantity(self):
        guard = TradingRiskGuard()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=None,
            price=3500.0,
            confidence=0.9,
        )
        value = guard._estimate_trade_value(intent, account_balance=100000.0)
        assert value is None

    def test_estimate_max_loss_with_stop_loss(self):
        guard = TradingRiskGuard()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=10,
            price=3500.0,
            stop_loss=3400.0,
            confidence=0.9,
        )
        loss = guard._estimate_max_loss(intent, trade_value=35000.0)
        assert loss == 1000.0  # (3500 - 3400) * 10

    def test_estimate_max_loss_without_stop_loss(self):
        guard = TradingRiskGuard()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=10,
            price=3500.0,
            stop_loss=None,
            confidence=0.9,
        )
        loss = guard._estimate_max_loss(intent, trade_value=35000.0)
        assert loss == 1750.0  # 35000 * 0.05

    def test_estimate_max_loss_none_trade_value(self):
        guard = TradingRiskGuard()
        intent = TradingIntent(action=TradeAction.BUY, confidence=0.9)
        loss = guard._estimate_max_loss(intent, trade_value=None)
        assert loss is None

    def test_position_impact_buy_existing(self):
        guard = TradingRiskGuard()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=5,
            confidence=0.9,
        )
        positions = [{"symbol": "RB2501", "size": 10}]
        impact = guard._describe_position_impact(intent, positions)
        assert "当前持仓 10" in impact
        assert "增加 5" in impact

    def test_position_impact_sell_existing(self):
        guard = TradingRiskGuard()
        intent = TradingIntent(
            action=TradeAction.SELL,
            symbol="rb2501",
            quantity=3,
            confidence=0.9,
        )
        positions = [{"symbol": "RB2501", "size": 10}]
        impact = guard._describe_position_impact(intent, positions)
        assert "减少 3" in impact

    def test_position_impact_close_existing(self):
        guard = TradingRiskGuard()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="rb2501",
            confidence=0.9,
        )
        positions = [{"symbol": "RB2501", "size": 10}]
        impact = guard._describe_position_impact(intent, positions)
        assert "清零" in impact

    def test_position_impact_new_position(self):
        guard = TradingRiskGuard()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="i2501",
            quantity=5,
            confidence=0.9,
        )
        positions = [{"symbol": "RB2501", "size": 10}]
        impact = guard._describe_position_impact(intent, positions)
        assert "新建" in impact
        assert "i2501" in impact

    def test_position_impact_no_positions(self):
        guard = TradingRiskGuard()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            confidence=0.9,
        )
        impact = guard._describe_position_impact(intent, None)
        assert impact is None

    def test_position_impact_no_symbol(self):
        guard = TradingRiskGuard()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol=None,
            confidence=0.9,
        )
        positions = [{"symbol": "RB2501", "size": 10}]
        impact = guard._describe_position_impact(intent, positions)
        assert impact is None
