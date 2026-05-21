"""Tests for alert_evaluation - trigger evaluation and metric resolution."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.alert_evaluation import (
    _check_cross_trigger,
    _check_rate_trigger,
    _check_threshold_trigger,
    check_trigger,
    compare_values,
    get_current_metric_value,
)


class TestCompareValues:
    """Test compare_values function."""

    def test_gt_true(self):
        assert compare_values(10.0, 5.0, "gt") is True

    def test_gt_false(self):
        assert compare_values(3.0, 5.0, "gt") is False

    def test_gt_equal_is_false(self):
        assert compare_values(5.0, 5.0, "gt") is False

    def test_lt_true(self):
        assert compare_values(3.0, 5.0, "lt") is True

    def test_lt_false(self):
        assert compare_values(10.0, 5.0, "lt") is False

    def test_eq_true(self):
        assert compare_values(5.0, 5.0, "eq") is True

    def test_eq_false(self):
        assert compare_values(5.1, 5.0, "eq") is False

    def test_default_is_lt(self):
        assert compare_values(3.0, 5.0, "unknown") is True
        assert compare_values(10.0, 5.0, "unknown") is False

    def test_none_condition_defaults_to_lt(self):
        assert compare_values(3.0, 5.0, None) is True


class TestCheckThresholdTrigger:
    """Test threshold trigger evaluation."""

    @pytest.mark.asyncio
    async def test_threshold_met(self):
        rule = MagicMock()
        config = {"threshold": 5.0, "condition": "gt"}
        get_metric_fn = AsyncMock(return_value=10.0)

        result = await _check_threshold_trigger(rule, config, get_metric_fn)
        assert result is True

    @pytest.mark.asyncio
    async def test_threshold_not_met(self):
        rule = MagicMock()
        config = {"threshold": 5.0, "condition": "gt"}
        get_metric_fn = AsyncMock(return_value=3.0)

        result = await _check_threshold_trigger(rule, config, get_metric_fn)
        assert result is False

    @pytest.mark.asyncio
    async def test_no_threshold_returns_false(self):
        rule = MagicMock()
        config = {}
        get_metric_fn = AsyncMock(return_value=10.0)

        result = await _check_threshold_trigger(rule, config, get_metric_fn)
        assert result is False

    @pytest.mark.asyncio
    async def test_metric_none_returns_false(self):
        rule = MagicMock()
        config = {"threshold": 5.0, "condition": "gt"}
        get_metric_fn = AsyncMock(return_value=None)

        result = await _check_threshold_trigger(rule, config, get_metric_fn)
        assert result is False


class TestCheckRateTrigger:
    """Test rate-of-change trigger evaluation."""

    @pytest.mark.asyncio
    async def test_first_call_returns_false(self):
        """First call has no previous value, should return False."""
        rule = MagicMock()
        rule.id = "rule1"
        config = {"threshold": 0.1, "condition": "gt", "mode": "pct"}
        trigger_state = {}
        get_metric_fn = AsyncMock(return_value=100.0)

        result = await _check_rate_trigger(rule, config, trigger_state, get_metric_fn)
        assert result is False
        assert trigger_state["rate:rule1"] == 100.0

    @pytest.mark.asyncio
    async def test_pct_change_triggers(self):
        """Percentage change exceeds threshold."""
        rule = MagicMock()
        rule.id = "rule1"
        config = {"threshold": 0.1, "condition": "gt", "mode": "pct"}
        trigger_state = {"rate:rule1": 100.0}
        get_metric_fn = AsyncMock(return_value=120.0)  # 20% change

        result = await _check_rate_trigger(rule, config, trigger_state, get_metric_fn)
        assert result is True

    @pytest.mark.asyncio
    async def test_pct_change_below_threshold(self):
        """Percentage change below threshold."""
        rule = MagicMock()
        rule.id = "rule1"
        config = {"threshold": 0.5, "condition": "gt", "mode": "pct"}
        trigger_state = {"rate:rule1": 100.0}
        get_metric_fn = AsyncMock(return_value=105.0)  # 5% change

        result = await _check_rate_trigger(rule, config, trigger_state, get_metric_fn)
        assert result is False

    @pytest.mark.asyncio
    async def test_abs_change_triggers(self):
        """Absolute change exceeds threshold."""
        rule = MagicMock()
        rule.id = "rule1"
        config = {"threshold": 10.0, "condition": "gt", "mode": "abs"}
        trigger_state = {"rate:rule1": 100.0}
        get_metric_fn = AsyncMock(return_value=115.0)  # 15 abs change

        result = await _check_rate_trigger(rule, config, trigger_state, get_metric_fn)
        assert result is True

    @pytest.mark.asyncio
    async def test_no_rule_id_returns_false(self):
        """Rule without id returns False."""
        rule = MagicMock(spec=[])  # No id attribute
        del rule.id
        config = {"threshold": 0.1, "condition": "gt"}
        trigger_state = {}
        get_metric_fn = AsyncMock(return_value=100.0)

        result = await _check_rate_trigger(rule, config, trigger_state, get_metric_fn)
        assert result is False

    @pytest.mark.asyncio
    async def test_prev_zero_pct_mode(self):
        """Previous value is zero in pct mode."""
        rule = MagicMock()
        rule.id = "rule1"
        config = {"threshold": 0.1, "condition": "gt", "mode": "pct"}
        trigger_state = {"rate:rule1": 0.0}
        get_metric_fn = AsyncMock(return_value=10.0)

        result = await _check_rate_trigger(rule, config, trigger_state, get_metric_fn)
        # inf > 0.1 should be True
        assert result is True

    @pytest.mark.asyncio
    async def test_metric_none_returns_false(self):
        rule = MagicMock()
        rule.id = "rule1"
        config = {"threshold": 0.1}
        trigger_state = {}
        get_metric_fn = AsyncMock(return_value=None)

        result = await _check_rate_trigger(rule, config, trigger_state, get_metric_fn)
        assert result is False


class TestCheckCrossTrigger:
    """Test cross-over trigger evaluation."""

    @pytest.mark.asyncio
    async def test_first_call_returns_false(self):
        """First call has no previous diff, should return False."""
        rule = MagicMock()
        rule.id = "rule1"
        config = {"value1": 10.0, "value2": 5.0, "direction": "up"}
        trigger_state = {}

        result = await _check_cross_trigger(rule, config, trigger_state)
        assert result is False
        assert trigger_state["cross:rule1"] == 5.0

    @pytest.mark.asyncio
    async def test_cross_up_triggers(self):
        """Cross up: prev_diff <= 0 and current diff > 0."""
        rule = MagicMock()
        rule.id = "rule1"
        config = {"value1": 10.0, "value2": 5.0, "direction": "up"}
        trigger_state = {"cross:rule1": -1.0}  # Was below

        result = await _check_cross_trigger(rule, config, trigger_state)
        assert result is True

    @pytest.mark.asyncio
    async def test_cross_up_no_trigger(self):
        """No cross up: prev_diff > 0 and current diff > 0."""
        rule = MagicMock()
        rule.id = "rule1"
        config = {"value1": 10.0, "value2": 5.0, "direction": "up"}
        trigger_state = {"cross:rule1": 2.0}  # Was already above

        result = await _check_cross_trigger(rule, config, trigger_state)
        assert result is False

    @pytest.mark.asyncio
    async def test_cross_down_triggers(self):
        """Cross down: prev_diff >= 0 and current diff < 0."""
        rule = MagicMock()
        rule.id = "rule1"
        config = {"value1": 3.0, "value2": 5.0, "direction": "down"}
        trigger_state = {"cross:rule1": 1.0}  # Was above

        result = await _check_cross_trigger(rule, config, trigger_state)
        assert result is True

    @pytest.mark.asyncio
    async def test_cross_down_no_trigger(self):
        """No cross down: prev_diff < 0 and current diff < 0."""
        rule = MagicMock()
        rule.id = "rule1"
        config = {"value1": 3.0, "value2": 5.0, "direction": "down"}
        trigger_state = {"cross:rule1": -2.0}  # Was already below

        result = await _check_cross_trigger(rule, config, trigger_state)
        assert result is False

    @pytest.mark.asyncio
    async def test_invalid_values_returns_false(self):
        """Invalid values return False."""
        rule = MagicMock()
        rule.id = "rule1"
        config = {"value1": "abc", "value2": 5.0}
        trigger_state = {}

        result = await _check_cross_trigger(rule, config, trigger_state)
        assert result is False


class TestCheckTrigger:
    """Test the main check_trigger dispatcher."""

    @pytest.mark.asyncio
    async def test_threshold_type(self):
        rule = MagicMock()
        rule.trigger_type = "threshold"
        rule.trigger_config = {"threshold": 5.0, "condition": "gt"}
        get_metric_fn = AsyncMock(return_value=10.0)

        result = await check_trigger(rule, {}, get_metric_fn)
        assert result is True

    @pytest.mark.asyncio
    async def test_manual_type_always_false(self):
        rule = MagicMock()
        rule.trigger_type = "manual"
        rule.trigger_config = {}

        result = await check_trigger(rule, {}, AsyncMock())
        assert result is False

    @pytest.mark.asyncio
    async def test_unknown_type_returns_false(self):
        rule = MagicMock()
        rule.trigger_type = "unknown_type"
        rule.trigger_config = {}

        result = await check_trigger(rule, {}, AsyncMock())
        assert result is False

    @pytest.mark.asyncio
    async def test_rate_type(self):
        rule = MagicMock()
        rule.id = "rule1"
        rule.trigger_type = "rate"
        rule.trigger_config = {"threshold": 0.1, "condition": "gt", "mode": "pct"}
        trigger_state = {"rate:rule1": 100.0}
        get_metric_fn = AsyncMock(return_value=120.0)

        result = await check_trigger(rule, trigger_state, get_metric_fn)
        assert result is True

    @pytest.mark.asyncio
    async def test_cross_type(self):
        rule = MagicMock()
        rule.id = "rule1"
        rule.trigger_type = "cross"
        rule.trigger_config = {"value1": 10.0, "value2": 5.0, "direction": "up"}
        trigger_state = {"cross:rule1": -1.0}

        result = await check_trigger(rule, trigger_state, AsyncMock())
        assert result is True


class TestGetCurrentMetricValue:
    """Test metric value resolution."""

    @pytest.mark.asyncio
    async def test_current_value_in_config(self):
        """When current_value is in config, use it directly."""
        rule = MagicMock()
        rule.alert_type = "account"
        config = {"current_value": 42.5}

        result = await get_current_metric_value(rule, config, None, None, None)
        assert result == 42.5

    @pytest.mark.asyncio
    async def test_current_value_invalid(self):
        """When current_value is invalid, return None."""
        rule = MagicMock()
        rule.alert_type = "account"
        config = {"current_value": "not_a_number"}

        result = await get_current_metric_value(rule, config, None, None, None)
        assert result is None

    @pytest.mark.asyncio
    async def test_account_metric_cash(self):
        """Resolve account cash metric from paper trading."""
        rule = MagicMock()
        rule.alert_type = "account"
        rule.user_id = "user1"

        mock_account = MagicMock()
        mock_account.current_cash = 50000.0
        mock_paper = AsyncMock()
        mock_paper.get_account = AsyncMock(return_value=mock_account)

        config = {"metric": "cash", "account_id": "acc1"}
        result = await get_current_metric_value(rule, config, mock_paper, None, None)
        assert result == 50000.0

    @pytest.mark.asyncio
    async def test_account_metric_equity(self):
        """Resolve account equity metric."""
        rule = MagicMock()
        rule.alert_type = "account"
        rule.user_id = "user1"

        mock_account = MagicMock()
        mock_account.total_equity = 120000.0
        mock_paper = AsyncMock()
        mock_paper.get_account = AsyncMock(return_value=mock_account)

        config = {"metric": "equity", "account_id": "acc1"}
        result = await get_current_metric_value(rule, config, mock_paper, None, None)
        assert result == 120000.0

    @pytest.mark.asyncio
    async def test_account_not_found(self):
        """Return None when account not found."""
        rule = MagicMock()
        rule.alert_type = "account"

        mock_paper = AsyncMock()
        mock_paper.get_account = AsyncMock(return_value=None)

        config = {"metric": "cash", "account_id": "nonexistent"}
        result = await get_current_metric_value(rule, config, mock_paper, None, None)
        assert result is None

    @pytest.mark.asyncio
    async def test_position_metric_unrealized_pnl(self):
        """Resolve position unrealized PnL metric."""
        rule = MagicMock()
        rule.alert_type = "position"
        rule.user_id = "user1"

        mock_pos = MagicMock()
        mock_pos.unrealized_pnl = 1500.0
        mock_paper = AsyncMock()
        mock_paper.list_positions = AsyncMock(return_value=([mock_pos], 1))

        config = {"metric": "unrealized_pnl", "symbol": "rb2501", "account_id": "acc1"}
        result = await get_current_metric_value(rule, config, mock_paper, None, None)
        assert result == 1500.0

    @pytest.mark.asyncio
    async def test_position_no_symbol_returns_none(self):
        """Return None when no symbol specified."""
        rule = MagicMock()
        rule.alert_type = "position"

        config = {"metric": "unrealized_pnl"}
        result = await get_current_metric_value(rule, config, None, None, None)
        assert result is None

    @pytest.mark.asyncio
    async def test_strategy_metric_sharpe(self):
        """Resolve strategy sharpe ratio metric."""
        rule = MagicMock()
        rule.alert_type = "strategy"
        rule.user_id = "user1"

        mock_result = MagicMock()
        mock_result.sharpe_ratio = 1.85
        mock_backtest = AsyncMock()
        mock_backtest.get_result = AsyncMock(return_value=mock_result)

        config = {"metric": "sharpe_ratio", "backtest_task_id": "task1"}
        result = await get_current_metric_value(rule, config, None, None, mock_backtest)
        assert result == 1.85

    @pytest.mark.asyncio
    async def test_strategy_metric_no_task_id(self):
        """Return None when no backtest_task_id."""
        rule = MagicMock()
        rule.alert_type = "strategy"

        config = {"metric": "sharpe_ratio"}
        result = await get_current_metric_value(rule, config, None, None, None)
        assert result is None

    @pytest.mark.asyncio
    async def test_live_account_metric(self):
        """Resolve live trading account metric."""
        rule = MagicMock()
        rule.alert_type = "account"
        rule.user_id = "user1"

        mock_live = AsyncMock()
        mock_live.get_task_status = AsyncMock(return_value={"cash": 80000.0, "value": 95000.0})

        config = {"metric": "cash", "live_task_id": "live1"}
        result = await get_current_metric_value(rule, config, None, mock_live, None)
        assert result == 80000.0
