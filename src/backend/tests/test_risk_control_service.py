"""Tests for risk control service."""

import pytest

from app.services.risk_control_service import (
    RiskAlertLevel,
    RiskAlertType,
    RiskControlConfig,
    RiskControlService,
    get_risk_control_service,
    init_risk_control_service,
)


@pytest.fixture()
def svc() -> RiskControlService:
    return RiskControlService()


@pytest.fixture()
def strict_svc() -> RiskControlService:
    """Service with tight limits for easier testing."""
    return RiskControlService(
        RiskControlConfig(
            max_position_pct=10.0,
            max_total_position_pct=50.0,
            max_daily_loss_pct=3.0,
            stop_loss_pct=2.0,
            take_profit_pct=5.0,
            max_daily_trades=3,
            max_order_size=10000.0,
        )
    )


INSTANCE_ID = "test-instance-001"


class TestPositionLimit:
    async def test_passes_within_limit(self, svc: RiskControlService):
        ok, alert = await svc.check_position_limit(
            INSTANCE_ID, "BTCUSDT", 20000, 100000, {}
        )
        assert ok is True
        assert alert is None

    async def test_rejects_single_position_over_limit(self, strict_svc: RiskControlService):
        ok, alert = await strict_svc.check_position_limit(
            INSTANCE_ID, "BTCUSDT", 15000, 100000, {}
        )
        assert ok is False
        assert alert is not None
        assert alert.alert_type == RiskAlertType.POSITION_LIMIT
        assert alert.level == RiskAlertLevel.WARNING
        assert "BTCUSDT" in alert.message

    async def test_rejects_total_position_over_limit(self, strict_svc: RiskControlService):
        existing = {"ETHUSDT": 30000, "SOLUSDT": 15000}
        ok, alert = await strict_svc.check_position_limit(
            INSTANCE_ID, "BTCUSDT", 8000, 100000, existing
        )
        assert ok is False
        assert alert.details["total_position_pct"] > 50.0

    async def test_skipped_when_disabled(self, svc: RiskControlService):
        svc.config.enable_position_limit = False
        ok, alert = await svc.check_position_limit(
            INSTANCE_ID, "BTCUSDT", 999999, 100000, {}
        )
        assert ok is True
        assert alert is None


class TestDailyLoss:
    async def test_no_alert_within_limit(self, svc: RiskControlService):
        ok, alert = await svc.check_daily_loss(INSTANCE_ID, 98000, 100000)
        assert ok is True
        assert alert is None

    async def test_critical_alert_when_exceeded(self, strict_svc: RiskControlService):
        ok, alert = await strict_svc.check_daily_loss(INSTANCE_ID, 96000, 100000)
        assert ok is False
        assert alert.alert_type == RiskAlertType.DAILY_LOSS
        assert alert.level == RiskAlertLevel.CRITICAL

    async def test_warning_at_80_percent_threshold(self, strict_svc: RiskControlService):
        # 3% limit * 80% = 2.4% → loss of 2.5% should warn
        ok, alert = await strict_svc.check_daily_loss(INSTANCE_ID, 97500, 100000)
        assert ok is True  # Still allowed to trade
        alerts = strict_svc.get_alerts(instance_id=INSTANCE_ID)
        assert len(alerts) == 1
        assert alerts[0].level == RiskAlertLevel.WARNING

    async def test_zero_initial_balance(self, svc: RiskControlService):
        ok, alert = await svc.check_daily_loss(INSTANCE_ID, 0, 0)
        assert ok is True


class TestStopLoss:
    async def test_no_trigger_within_limit(self, svc: RiskControlService):
        alert = await svc.check_stop_loss(INSTANCE_ID, "BTCUSDT", 100, 97, 10)
        assert alert is None

    async def test_trigger_long_position(self, strict_svc: RiskControlService):
        alert = await strict_svc.check_stop_loss(INSTANCE_ID, "BTCUSDT", 100, 97, 10)
        assert alert is not None
        assert alert.alert_type == RiskAlertType.STOP_LOSS
        assert alert.details["action"] == "close_position"

    async def test_trigger_short_position(self, strict_svc: RiskControlService):
        # Short position: price goes UP → loss
        alert = await strict_svc.check_stop_loss(INSTANCE_ID, "BTCUSDT", 100, 103, -10)
        assert alert is not None
        assert alert.alert_type == RiskAlertType.STOP_LOSS

    async def test_skipped_when_disabled(self, svc: RiskControlService):
        svc.config.enable_stop_loss = False
        alert = await svc.check_stop_loss(INSTANCE_ID, "BTCUSDT", 100, 1, 10)
        assert alert is None


class TestTakeProfit:
    async def test_no_trigger_within_limit(self, svc: RiskControlService):
        alert = await svc.check_take_profit(INSTANCE_ID, "BTCUSDT", 100, 110, 10)
        assert alert is None

    async def test_trigger_long_position(self, strict_svc: RiskControlService):
        alert = await strict_svc.check_take_profit(INSTANCE_ID, "BTCUSDT", 100, 106, 10)
        assert alert is not None
        assert alert.alert_type == RiskAlertType.TAKE_PROFIT
        assert alert.level == RiskAlertLevel.INFO

    async def test_trigger_short_position(self, strict_svc: RiskControlService):
        alert = await strict_svc.check_take_profit(INSTANCE_ID, "BTCUSDT", 100, 94, -10)
        assert alert is not None

    async def test_skipped_when_disabled(self, svc: RiskControlService):
        svc.config.enable_take_profit = False
        alert = await svc.check_take_profit(INSTANCE_ID, "BTCUSDT", 100, 999, 10)
        assert alert is None


class TestOrderSize:
    async def test_passes_within_limit(self, svc: RiskControlService):
        ok, alert = await svc.check_order_size(INSTANCE_ID, 50000)
        assert ok is True

    async def test_rejects_over_limit(self, strict_svc: RiskControlService):
        ok, alert = await strict_svc.check_order_size(INSTANCE_ID, 15000)
        assert ok is False
        assert alert.alert_type == RiskAlertType.ABNORMAL_TRADING


class TestTradeCount:
    async def test_within_limit(self, strict_svc: RiskControlService):
        for _ in range(3):
            ok, _ = await strict_svc.increment_trade_count(INSTANCE_ID)
            assert ok is True

    async def test_exceeds_limit(self, strict_svc: RiskControlService):
        for _ in range(3):
            await strict_svc.increment_trade_count(INSTANCE_ID)
        ok, alert = await strict_svc.increment_trade_count(INSTANCE_ID)
        assert ok is False
        assert alert.details["trade_count"] == 4


class TestAlertManagement:
    async def test_get_alerts_empty(self, svc: RiskControlService):
        assert svc.get_alerts() == []

    async def test_get_alerts_filtered_by_instance(self, strict_svc: RiskControlService):
        await strict_svc.check_order_size("inst-a", 99999)
        await strict_svc.check_order_size("inst-b", 99999)
        alerts_a = strict_svc.get_alerts(instance_id="inst-a")
        assert len(alerts_a) == 1
        assert alerts_a[0].instance_id == "inst-a"

    async def test_get_alerts_filtered_by_level(self, strict_svc: RiskControlService):
        await strict_svc.check_daily_loss(INSTANCE_ID, 96000, 100000)  # CRITICAL
        await strict_svc.check_order_size(INSTANCE_ID, 99999)  # WARNING
        critical = strict_svc.get_alerts(level=RiskAlertLevel.CRITICAL)
        assert all(a.level == RiskAlertLevel.CRITICAL for a in critical)

    async def test_clear_alerts_all(self, strict_svc: RiskControlService):
        await strict_svc.check_order_size(INSTANCE_ID, 99999)
        count = strict_svc.clear_alerts()
        assert count == 1
        assert strict_svc.get_alerts() == []

    async def test_clear_alerts_by_instance(self, strict_svc: RiskControlService):
        await strict_svc.check_order_size("inst-a", 99999)
        await strict_svc.check_order_size("inst-b", 99999)
        count = strict_svc.clear_alerts(instance_id="inst-a")
        assert count == 1
        assert len(strict_svc.get_alerts()) == 1

    def test_reset_daily_counters(self, svc: RiskControlService):
        svc._daily_trades["a"] = 10
        svc._daily_pnl["a"] = -500
        svc._daily_trades["b"] = 5
        svc.reset_daily_counters(instance_id="a")
        assert "a" not in svc._daily_trades
        assert "b" in svc._daily_trades

    def test_reset_all_counters(self, svc: RiskControlService):
        svc._daily_trades["a"] = 10
        svc._daily_pnl["a"] = -500
        svc.reset_daily_counters()
        assert len(svc._daily_trades) == 0
        assert len(svc._daily_pnl) == 0


class TestConfigUpdate:
    def test_update_config(self, svc: RiskControlService):
        new_config = RiskControlConfig(max_position_pct=50.0)
        svc.update_config(new_config)
        assert svc.config.max_position_pct == 50.0


class TestGlobalInstance:
    def test_get_returns_singleton(self):
        svc1 = get_risk_control_service()
        svc2 = get_risk_control_service()
        assert svc1 is svc2

    def test_init_replaces_global(self):
        custom = RiskControlConfig(max_daily_trades=1)
        svc = init_risk_control_service(custom)
        assert svc.config.max_daily_trades == 1
        assert get_risk_control_service() is svc
