"""Tests for custom exception classes."""


from app.utils.exceptions import (
    AuthenticationError,
    BacktestError,
    BacktestExecutionError,
    BacktestNotFoundError,
    BacktestTimeoutError,
    BaseAppError,
    BrokerConnectionError,
    ConfigurationError,
    DataError,
    DataNotFoundError,
    DataProviderError,
    ExternalServiceError,
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
    StrategyError,
    StrategyNotFoundError,
    TokenExpiredError,
    UserAlreadyExistsError,
    UserInactiveError,
    UserNotFoundError,
    ValidationError,
    format_exception_for_response,
)


class TestBaseAppError:
    """Tests for BaseAppError."""

    def test_init_with_message_only(self):
        """Test initialization with message only."""
        exc = BaseAppError("Test error")
        assert exc.message == "Test error"
        assert exc.details == {}
        assert exc.error_code == "BaseAppError"

    def test_init_with_all_params(self):
        """Test initialization with all parameters."""
        exc = BaseAppError("Test error", details={"key": "value"}, error_code="CUSTOM_CODE")
        assert exc.message == "Test error"
        assert exc.details == {"key": "value"}
        assert exc.error_code == "CUSTOM_CODE"

    def test_to_dict_without_details(self):
        """Test to_dict without details."""
        exc = BaseAppError("Test error")
        result = exc.to_dict()
        assert result == {"error": "BaseAppError", "message": "Test error"}

    def test_to_dict_with_details(self):
        """Test to_dict with details."""
        exc = BaseAppError("Test error", details={"key": "value"})
        result = exc.to_dict()
        assert result == {"error": "BaseAppError", "message": "Test error", "details": {"key": "value"}}


class TestAuthenticationErrors:
    """Tests for authentication-related errors."""

    def test_authentication_error_default(self):
        """Test AuthenticationError with default values."""
        exc = AuthenticationError()
        assert exc.message == "Authentication failed"
        assert exc.error_code == "AUTHENTICATION_ERROR"

    def test_invalid_credentials_error(self):
        """Test InvalidCredentialsError."""
        exc = InvalidCredentialsError(username="testuser")
        assert exc.message == "Invalid username or password"
        assert exc.details == {"username": "testuser"}
        assert exc.error_code == "InvalidCredentialsError"

    def test_invalid_credentials_error_without_username(self):
        """Test InvalidCredentialsError without username."""
        exc = InvalidCredentialsError()
        assert exc.message == "Invalid username or password"
        assert exc.details == {}

    def test_user_not_found_error_with_id(self):
        """Test UserNotFoundError with user_id."""
        exc = UserNotFoundError(user_id="123")
        assert exc.message == "User not found (ID: 123)"
        assert exc.details == {"user_id": "123"}

    def test_user_not_found_error_with_username(self):
        """Test UserNotFoundError with username."""
        exc = UserNotFoundError(username="testuser")
        assert exc.message == "User not found (username: testuser)"
        assert exc.details == {"username": "testuser"}

    def test_user_already_exists_error(self):
        """Test UserAlreadyExistsError."""
        exc = UserAlreadyExistsError(username="testuser", email="test@example.com")
        assert exc.message == "User already exists (username: testuser)"
        assert exc.details == {"username": "testuser", "email": "test@example.com"}

    def test_invalid_token_error(self):
        """Test InvalidTokenError."""
        exc = InvalidTokenError(reason="Token malformed")
        assert exc.message == "Token malformed"
        assert exc.details == {"reason": "Token malformed"}

    def test_token_expired_error(self):
        """Test TokenExpiredError."""
        exc = TokenExpiredError()
        assert exc.message == "Token has expired"
        assert exc.error_code == "InvalidTokenError"

    def test_insufficient_permissions_error(self):
        """Test InsufficientPermissionsError."""
        exc = InsufficientPermissionsError(required_permission="admin", resource="/api/admin")
        assert exc.message == "Insufficient permissions (requires: admin)"
        assert exc.details == {"required_permission": "admin", "resource": "/api/admin"}

    def test_user_inactive_error(self):
        """Test UserInactiveError."""
        exc = UserInactiveError(user_id="123")
        assert exc.message == "User account is inactive"
        assert exc.details == {"user_id": "123"}


class TestValidationErrors:
    """Tests for validation-related errors."""

    def test_validation_error_default(self):
        """Test ValidationError with default values."""
        exc = ValidationError()
        assert exc.message == "Validation failed"
        assert exc.error_code == "VALIDATION_ERROR"

    def test_validation_error_with_field(self):
        """Test ValidationError with field."""
        exc = ValidationError(message="Invalid value", field="email")
        assert exc.details == {"field": "email"}

    def test_invalid_input_error(self):
        """Test InvalidInputError."""
        exc = InvalidInputError("Invalid email format", field="email", value="invalid")
        assert exc.message == "Invalid email format"
        assert exc.details == {"field": "email", "value_type": "str"}

    def test_missing_field_error(self):
        """Test MissingFieldError."""
        exc = MissingFieldError("email")
        assert exc.message == "Required field is missing: email"
        assert exc.error_code == "MissingFieldError"

    def test_password_too_weak_error(self):
        """Test PasswordTooWeakError."""
        exc = PasswordTooWeakError(["Too short", "No uppercase"])
        assert exc.message == "Password does not meet security requirements"
        assert exc.details == {"requirements": ["Too short", "No uppercase"]}


class TestStrategyErrors:
    """Tests for strategy-related errors."""

    def test_strategy_error_default(self):
        """Test StrategyError with default values."""
        exc = StrategyError()
        assert exc.message == "Strategy operation failed"
        assert exc.error_code == "STRATEGY_ERROR"

    def test_strategy_not_found_error(self):
        """Test StrategyNotFoundError."""
        exc = StrategyNotFoundError(strategy_id="strat-123")
        assert exc.message == "Strategy not found (ID: strat-123)"
        assert exc.details == {"strategy_id": "strat-123"}

    def test_invalid_strategy_code_error(self):
        """Test InvalidStrategyCodeError."""
        exc = InvalidStrategyCodeError(message="Syntax error", line=42, error="Invalid syntax")
        assert exc.message == "Syntax error"
        assert exc.details == {"line": 42, "error": "Invalid syntax"}


class TestBacktestErrors:
    """Tests for backtest-related errors."""

    def test_backtest_error_default(self):
        """Test BacktestError with default values."""
        exc = BacktestError()
        assert exc.message == "Backtest operation failed"
        assert exc.error_code == "BACKTEST_ERROR"

    def test_backtest_not_found_error(self):
        """Test BacktestNotFoundError."""
        exc = BacktestNotFoundError(task_id="task-123")
        assert exc.message == "Backtest not found (task ID: task-123)"
        assert exc.details == {"task_id": "task-123"}

    def test_backtest_execution_error(self):
        """Test BacktestExecutionError."""
        exc = BacktestExecutionError("Execution failed", task_id="task-123", logs="Error log")
        assert exc.message == "Execution failed"
        assert exc.details == {"task_id": "task-123", "logs": "Error log"}

    def test_backtest_execution_error_truncates_logs(self):
        """Test BacktestExecutionError truncates long logs."""
        long_log = "x" * 1000
        exc = BacktestExecutionError("Failed", logs=long_log)
        assert len(exc.details["logs"]) == 500

    def test_backtest_timeout_error(self):
        """Test BacktestTimeoutError."""
        exc = BacktestTimeoutError(task_id="task-123", timeout_seconds=300)
        assert exc.message == "Backtest execution timed out after 300 seconds"
        assert exc.details == {"task_id": "task-123"}


class TestDataErrors:
    """Tests for data-related errors."""

    def test_data_error_default(self):
        """Test DataError with default values."""
        exc = DataError()
        assert exc.message == "Data operation failed"
        assert exc.error_code == "DATA_ERROR"

    def test_data_not_found_error(self):
        """Test DataNotFoundError."""
        exc = DataNotFoundError(symbol="AAPL", start_date="2024-01-01", end_date="2024-12-31")
        assert exc.message == "Market data not available for symbol: AAPL"
        assert exc.details == {"symbol": "AAPL", "start_date": "2024-01-01", "end_date": "2024-12-31"}

    def test_invalid_date_range_error(self):
        """Test InvalidDateRangeError."""
        exc = InvalidDateRangeError("Start after end", start_date="2024-12-01", end_date="2024-01-01")
        assert exc.message == "Invalid date range"
        assert exc.details == {"reason": "Start after end", "start_date": "2024-12-01", "end_date": "2024-01-01"}


class TestConfigurationErrors:
    """Tests for configuration-related errors."""

    def test_configuration_error_default(self):
        """Test ConfigurationError with default values."""
        exc = ConfigurationError()
        assert exc.message == "Configuration error"
        assert exc.error_code == "CONFIGURATION_ERROR"

    def test_configuration_error_with_setting(self):
        """Test ConfigurationError with setting."""
        exc = ConfigurationError(message="Invalid setting", setting="DATABASE_URL")
        assert exc.details == {"setting": "DATABASE_URL"}

    def test_missing_config_error(self):
        """Test MissingConfigError."""
        exc = MissingConfigError("API_KEY")
        assert exc.message == "Required configuration setting is missing: API_KEY"
        assert exc.error_code == "MissingConfigError"

    def test_invalid_config_error(self):
        """Test InvalidConfigError."""
        exc = InvalidConfigError("PORT", value="abc", reason="Must be integer")
        assert exc.message == "Invalid configuration value for: PORT - Must be integer"
        assert exc.details["setting"] == "PORT"
        assert exc.details["provided_value_type"] == "str"
        assert exc.details["reason"] == "Must be integer"


class TestExternalServiceErrors:
    """Tests for external service errors."""

    def test_external_service_error(self):
        """Test ExternalServiceError."""
        exc = ExternalServiceError("broker")
        assert exc.message == "External service error: broker"
        assert exc.details == {"service": "broker"}

    def test_broker_connection_error(self):
        """Test BrokerConnectionError."""
        exc = BrokerConnectionError("IB", reason="Connection refused")
        assert exc.message == "Failed to connect to broker: IB"
        assert exc.details == {"service": "IB", "reason": "Connection refused"}

    def test_data_provider_error(self):
        """Test DataProviderError."""
        exc = DataProviderError("Yahoo", reason="Rate limited")
        assert exc.message == "Data provider error: Yahoo"
        assert exc.details == {"service": "Yahoo", "reason": "Rate limited"}


class TestFormatExceptionForResponse:
    """Tests for format_exception_for_response function."""

    def test_format_base_app_error(self):
        """Test formatting BaseAppError."""
        exc = UserNotFoundError(user_id="123")
        result = format_exception_for_response(exc)
        assert result == {"error": "UserNotFoundError", "message": "User not found (ID: 123)", "details": {"user_id": "123"}}

    def test_format_standard_exception(self):
        """Test formatting standard Python exception."""
        exc = ValueError("Invalid value")
        result = format_exception_for_response(exc)
        assert result == {"error": "ValueError", "message": "Invalid value"}

    def test_format_exception_without_message(self):
        """Test formatting exception without message."""
        exc = RuntimeError()
        result = format_exception_for_response(exc)
        assert result == {"error": "RuntimeError", "message": "An error occurred"}
