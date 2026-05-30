"""
Tests for exception classes and alert evaluation logic.

Covers:
- Custom exception hierarchy
- Exception serialization (to_dict)
- format_exception_for_response utility
- Alert trigger evaluation (compare_values, check_trigger)
"""

from unittest.mock import AsyncMock, MagicMock

from app.services.alert_evaluation import (
    _check_cross_trigger,
    _check_rate_trigger,
    _check_threshold_trigger,
    check_trigger,
    compare_values,
)
from app.utils.exceptions import (
    BacktestExecutionError,
    BacktestNotFoundError,
    BacktestTimeoutError,
    BaseAppError,
    BrokerConnectionError,
    DataNotFoundError,
    DataProviderError,
    InsufficientPermissionsError,
    InvalidConfigError,
    InvalidCredentialsError,
    InvalidDateRangeError,
    InvalidInputError,
    InvalidStrategyCodeError,
    InvalidTokenError,
    MissingConfigError,
    MissingFieldError,
    PasswordTooWeakError,
    StrategyNotFoundError,
    TokenExpiredError,
    UserAlreadyExistsError,
    UserInactiveError,
    UserNotFoundError,
    format_exception_for_response,
)

# ============================================================
# Exception Classes Tests
# ============================================================


class TestBaseAppError:
    """Test BaseAppError and its serialization."""

    def test_base_error_has_message(self):
        err = BaseAppError("test error")
        assert str(err) == "test error"
        assert err.message == "test error"

    def test_base_error_has_error_code(self):
        err = BaseAppError("test error", error_code="CUSTOM_CODE")
        assert err.error_code == "CUSTOM_CODE"

    def test_base_error_default_error_code_is_class_name(self):
        err = BaseAppError("test error")
        assert err.error_code == "BaseAppError"

    def test_to_dict(self):
        err = BaseAppError("test error", error_code="VALIDATION", details={"field": "email"})
        d = err.to_dict()
        assert d["message"] == "test error"
        assert d["error"] == "VALIDATION"
        assert d["details"]["field"] == "email"

    def test_to_dict_no_details(self):
        err = BaseAppError("test error")
        d = err.to_dict()
        assert "details" not in d


class TestAuthErrors:
    """Test authentication error classes."""

    def test_invalid_credentials(self):
        err = InvalidCredentialsError(username="john")
        assert (
            "john" in err.message
            or "credentials" in err.message.lower()
            or "password" in err.message.lower()
        )

    def test_invalid_credentials_no_username(self):
        err = InvalidCredentialsError()
        assert err.message  # Should have a default message

    def test_user_not_found(self):
        err = UserNotFoundError(user_id="123")
        assert "123" in err.message

    def test_user_not_found_by_username(self):
        err = UserNotFoundError(username="john")
        assert "john" in err.message

    def test_user_already_exists(self):
        err = UserAlreadyExistsError(username="john")
        assert "john" in err.message

    def test_user_already_exists_by_email(self):
        err = UserAlreadyExistsError(email="john@example.com")
        assert "john@example.com" in err.message

    def test_invalid_token(self):
        err = InvalidTokenError()
        assert err.message

    def test_token_expired(self):
        err = TokenExpiredError()
        assert err.message

    def test_insufficient_permissions(self):
        err = InsufficientPermissionsError(resource="strategy")
        assert "strategy" in err.message.lower() or err.details.get("resource") == "strategy"

    def test_user_inactive(self):
        err = UserInactiveError(username="john")
        assert err.message


class TestValidationErrors:
    """Test validation error classes."""

    def test_invalid_input(self):
        err = InvalidInputError("bad value", field="email")
        assert err.message

    def test_missing_field(self):
        err = MissingFieldError("username")
        assert "username" in err.message

    def test_password_too_weak(self):
        err = PasswordTooWeakError(["too short", "no uppercase"])
        assert err.message


class TestStrategyErrors:
    """Test strategy error classes."""

    def test_strategy_not_found(self):
        err = StrategyNotFoundError(strategy_id="abc123")
        assert "abc123" in err.message

    def test_invalid_strategy_code(self):
        err = InvalidStrategyCodeError("syntax error at line 5")
        assert "syntax" in err.message.lower()


class TestBacktestErrors:
    """Test backtest error classes."""

    def test_backtest_not_found(self):
        err = BacktestNotFoundError(task_id="task-123")
        assert "task-123" in err.message

    def test_backtest_execution_error(self):
        err = BacktestExecutionError("memory overflow", task_id="task-123")
        assert "memory" in err.message.lower()

    def test_backtest_timeout(self):
        err = BacktestTimeoutError(task_id="task-123", timeout_seconds=300)
        assert "300" in err.message


class TestDataErrors:
    """Test data error classes."""

    def test_data_not_found(self):
        err = DataNotFoundError(symbol="000001.SZ")
        assert err.message

    def test_invalid_date_range(self):
        err = InvalidDateRangeError(
            "end before start", start_date="2024-01-01", end_date="2023-01-01"
        )
        assert err.message


class TestConfigErrors:
    """Test configuration error classes."""

    def test_missing_config(self):
        err = MissingConfigError("DATABASE_URL")
        assert "DATABASE_URL" in err.message

    def test_invalid_config(self):
        err = InvalidConfigError("PORT", value="abc", reason="must be integer")
        assert "PORT" in err.message


class TestExternalServiceErrors:
    """Test external service error classes."""

    def test_broker_connection_error(self):
        err = BrokerConnectionError("CTP", reason="timeout")
        assert "CTP" in err.message

    def test_data_provider_error(self):
        err = DataProviderError("AkShare", reason="rate limited")
        assert "AkShare" in err.message


class TestFormatExceptionForResponse:
    """Test format_exception_for_response utility."""

    def test_format_app_error(self):
        err = InvalidCredentialsError(username="john")
        result = format_exception_for_response(err)
        assert "message" in result

    def test_format_generic_exception(self):
        err = ValueError("something went wrong")
        result = format_exception_for_response(err)
        assert "message" in result


# ============================================================
# Alert Evaluation Tests
# ============================================================


class TestCompareValues:
    """Test compare_values function."""

    def test_gt_true(self):
        assert compare_values(10.0, 5.0, "gt") is True

    def test_gt_false(self):
        assert compare_values(3.0, 5.0, "gt") is False

    def test_lt_true(self):
        assert compare_values(3.0, 5.0, "lt") is True

    def test_lt_false(self):
        assert compare_values(10.0, 5.0, "lt") is False

    def test_eq_true(self):
        assert compare_values(5.0, 5.0, "eq") is True

    def test_eq_false(self):
        assert compare_values(5.1, 5.0, "eq") is False

    def test_default_is_lt(self):
        assert compare_values(3.0, 5.0, None) is True
        assert compare_values(10.0, 5.0, None) is False


class TestCheckThresholdTrigger:
    """Test threshold trigger evaluation."""

    async def test_threshold_trigger_fires(self):
        rule = MagicMock()
        config = {"threshold": 100.0, "condition": "gt"}
        get_metric = AsyncMock(return_value=150.0)

        result = await _check_threshold_trigger(rule, config, get_metric)
        assert result is True

    async def test_threshold_trigger_not_fires(self):
        rule = MagicMock()
        config = {"threshold": 100.0, "condition": "gt"}
        get_metric = AsyncMock(return_value=50.0)

        result = await _check_threshold_trigger(rule, config, get_metric)
        assert result is False

    async def test_threshold_no_threshold_config(self):
        rule = MagicMock()
        config = {}
        get_metric = AsyncMock(return_value=50.0)

        result = await _check_threshold_trigger(rule, config, get_metric)
        assert result is False

    async def test_threshold_metric_none(self):
        rule = MagicMock()
        config = {"threshold": 100.0, "condition": "gt"}
        get_metric = AsyncMock(return_value=None)

        result = await _check_threshold_trigger(rule, config, get_metric)
        assert result is False


class TestCheckRateTrigger:
    """Test rate-of-change trigger evaluation."""

    async def test_rate_trigger_first_call_returns_false(self):
        rule = MagicMock()
        rule.id = "rule-1"
        config = {"threshold": 0.1, "condition": "gt", "mode": "pct"}
        state = {}
        get_metric = AsyncMock(return_value=100.0)

        result = await _check_rate_trigger(rule, config, state, get_metric)
        assert result is False  # No previous value

    async def test_rate_trigger_fires_on_increase(self):
        rule = MagicMock()
        rule.id = "rule-1"
        config = {"threshold": 0.1, "condition": "gt", "mode": "pct"}
        state = {"rate:rule-1": 100.0}
        get_metric = AsyncMock(return_value=120.0)  # 20% increase

        result = await _check_rate_trigger(rule, config, state, get_metric)
        assert result is True

    async def test_rate_trigger_abs_mode(self):
        rule = MagicMock()
        rule.id = "rule-2"
        config = {"threshold": 5.0, "condition": "gt", "mode": "abs"}
        state = {"rate:rule-2": 100.0}
        get_metric = AsyncMock(return_value=110.0)  # +10 absolute

        result = await _check_rate_trigger(rule, config, state, get_metric)
        assert result is True


class TestCheckCrossTrigger:
    """Test cross-over trigger evaluation."""

    async def test_cross_up_trigger(self):
        rule = MagicMock()
        rule.id = "rule-1"
        config = {"value1": 10.0, "value2": 5.0, "direction": "up"}
        state = {"cross:rule-1": -1.0}  # Was below

        result = await _check_cross_trigger(rule, config, state)
        assert result is True  # Now above → cross up

    async def test_cross_down_trigger(self):
        rule = MagicMock()
        rule.id = "rule-2"
        config = {"value1": 3.0, "value2": 5.0, "direction": "down"}
        state = {"cross:rule-2": 1.0}  # Was above

        result = await _check_cross_trigger(rule, config, state)
        assert result is True  # Now below → cross down

    async def test_cross_no_previous_state(self):
        rule = MagicMock()
        rule.id = "rule-3"
        config = {"value1": 10.0, "value2": 5.0, "direction": "up"}
        state = {}

        result = await _check_cross_trigger(rule, config, state)
        assert result is False  # No previous state


class TestCheckTrigger:
    """Test the main check_trigger dispatcher."""

    async def test_manual_trigger_always_false(self):
        rule = MagicMock()
        rule.trigger_type = "manual"
        rule.trigger_config = {}

        result = await check_trigger(rule, {}, AsyncMock())
        assert result is False

    async def test_unknown_trigger_type_returns_false(self):
        rule = MagicMock()
        rule.trigger_type = "unknown_type"
        rule.trigger_config = {}

        result = await check_trigger(rule, {}, AsyncMock())
        assert result is False

    async def test_threshold_trigger_dispatches(self):
        rule = MagicMock()
        rule.trigger_type = "threshold"
        rule.trigger_config = {"threshold": 50.0, "condition": "gt"}
        get_metric = AsyncMock(return_value=100.0)

        result = await check_trigger(rule, {}, get_metric)
        assert result is True
