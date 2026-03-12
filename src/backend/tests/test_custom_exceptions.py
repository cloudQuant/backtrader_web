"""
Tests for custom exception classes.
"""

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
    """Test suite for BaseAppError class."""

    def test_basic_initialization(self):
        """Test basic error initialization."""
        error = BaseAppError("Something went wrong")
        assert error.message == "Something went wrong"
        assert error.details == {}
        assert error.error_code == "BaseAppError"
        assert str(error) == "Something went wrong"

    def test_error_with_details(self):
        """Test error with details dictionary."""
        details = {"field": "username", "value": "test"}
        error = BaseAppError("Validation failed", details=details)
        assert error.details == details

    def test_error_with_custom_code(self):
        """Test error with custom error code."""
        error = BaseAppError("Custom error", error_code="CUSTOM_001")
        assert error.error_code == "CUSTOM_001"

    def test_to_dict(self):
        """Test conversion to dictionary."""
        error = BaseAppError("Test error", details={"key": "value"})
        result = error.to_dict()
        assert result == {
            "error": "BaseAppError",
            "message": "Test error",
            "details": {"key": "value"},
        }

    def test_to_dict_no_details(self):
        """Test to_dict without details."""
        error = BaseAppError("Test error")
        result = error.to_dict()
        assert result == {"error": "BaseAppError", "message": "Test error"}


class TestAuthenticationErrors:
    """Test suite for authentication-related errors."""

    def test_invalid_credentials_error(self):
        """Test InvalidCredentialsError."""
        error = InvalidCredentialsError(username="testuser")
        assert "Invalid username or password" in error.message
        assert error.details["username"] == "testuser"

    def test_invalid_credentials_no_username(self):
        """Test InvalidCredentialsError without username."""
        error = InvalidCredentialsError()
        assert error.details == {}

    def test_user_not_found_error_with_id(self):
        """Test UserNotFoundError with user ID."""
        error = UserNotFoundError(user_id="123")
        assert "User not found" in error.message
        assert "123" in error.message
        assert error.details["user_id"] == "123"

    def test_user_not_found_error_with_username(self):
        """Test UserNotFoundError with username."""
        error = UserNotFoundError(username="testuser")
        assert "testuser" in error.message
        assert error.details["username"] == "testuser"

    def test_user_already_exists_error(self):
        """Test UserAlreadyExistsError."""
        error = UserAlreadyExistsError(username="existing", email="existing@test.com")
        assert "User already exists" in error.message
        assert error.details["username"] == "existing"
        assert error.details["email"] == "existing@test.com"

    def test_invalid_token_error(self):
        """Test InvalidTokenError."""
        error = InvalidTokenError(reason="Malformed token")
        assert "Malformed token" in error.message
        assert error.details["reason"] == "Malformed token"

    def test_token_expired_error(self):
        """Test TokenExpiredError."""
        error = TokenExpiredError()
        assert "expired" in error.message.lower()

    def test_insufficient_permissions_error(self):
        """Test InsufficientPermissionsError."""
        error = InsufficientPermissionsError(required_permission="write:users", resource="users")
        assert "Insufficient permissions" in error.message
        assert error.details["required_permission"] == "write:users"
        assert error.details["resource"] == "users"

    def test_user_inactive_error(self):
        """Test UserInactiveError."""
        error = UserInactiveError(user_id="123", username="inactive_user")
        assert "inactive" in error.message.lower()
        assert error.details["user_id"] == "123"
        assert error.details["username"] == "inactive_user"


class TestValidationErrors:
    """Test suite for validation-related errors."""

    def test_invalid_input_error(self):
        """Test InvalidInputError."""
        error = InvalidInputError(
            message="Invalid email format", field="email", value="not-an-email"
        )
        assert "Invalid email format" in error.message
        assert error.details["field"] == "email"
        assert error.details["value_type"] == "str"

    def test_missing_field_error(self):
        """Test MissingFieldError."""
        error = MissingFieldError("password")
        assert "password" in error.message
        assert error.details["field"] == "password"

    def test_password_too_weak_error(self):
        """Test PasswordTooWeakError."""
        reasons = ["Too short", "Missing special character"]
        error = PasswordTooWeakError(reasons)
        assert "security requirements" in error.message
        assert error.details["requirements"] == reasons


class TestStrategyErrors:
    """Test suite for strategy-related errors."""

    def test_strategy_not_found_error(self):
        """Test StrategyNotFoundError."""
        error = StrategyNotFoundError(strategy_id="strategy-123")
        assert "Strategy not found" in error.message
        assert error.details["strategy_id"] == "strategy-123"

    def test_invalid_strategy_code_error(self):
        """Test InvalidStrategyCodeError."""
        error = InvalidStrategyCodeError(message="Syntax error", line=42, error="unexpected indent")
        assert "Syntax error" in error.message
        assert error.details["line"] == 42
        assert error.details["error"] == "unexpected indent"


class TestBacktestErrors:
    """Test suite for backtest-related errors."""

    def test_backtest_not_found_error(self):
        """Test BacktestNotFoundError."""
        error = BacktestNotFoundError(task_id="task-123")
        assert "Backtest not found" in error.message
        assert error.details["task_id"] == "task-123"

    def test_backtest_execution_error(self):
        """Test BacktestExecutionError."""
        error = BacktestExecutionError(
            message="Execution failed", task_id="task-123", logs="Error: division by zero"
        )
        assert "Execution failed" in error.message
        assert error.details["task_id"] == "task-123"
        assert "Error: division by zero" in error.details["logs"]

    def test_backtest_timeout_error(self):
        """Test BacktestTimeoutError."""
        error = BacktestTimeoutError(task_id="task-123", timeout_seconds=300)
        assert "timed out" in error.message.lower()
        assert "300" in error.message
        assert error.details["task_id"] == "task-123"

    def test_backtest_execution_error_truncates_long_logs(self):
        """Test that long logs are truncated."""
        long_logs = "Error: " + "x" * 600
        error = BacktestExecutionError(
            message="Execution failed", task_id="task-123", logs=long_logs
        )
        assert len(error.details["logs"]) <= 500 + 10  # Account for "Error: " prefix


class TestDataErrors:
    """Test suite for data-related errors."""

    def test_data_not_found_error(self):
        """Test DataNotFoundError."""
        error = DataNotFoundError(symbol="INVALID", start_date="2024-01-01")
        assert "Market data not available" in error.message
        assert error.details["symbol"] == "INVALID"
        assert error.details["start_date"] == "2024-01-01"

    def test_invalid_date_range_error(self):
        """Test InvalidDateRangeError."""
        error = InvalidDateRangeError(
            reason="End date before start date", start_date="2024-12-31", end_date="2024-01-01"
        )
        assert "Invalid date range" in error.message
        assert error.details["reason"] == "End date before start date"


class TestConfigurationErrors:
    """Test suite for configuration-related errors."""

    def test_missing_config_error(self):
        """Test MissingConfigError."""
        error = MissingConfigError("DATABASE_URL")
        assert "DATABASE_URL" in error.message
        assert error.details["setting"] == "DATABASE_URL"

    def test_invalid_config_error(self):
        """Test InvalidConfigError."""
        error = InvalidConfigError(
            setting="LOG_LEVEL", value="INVALID", reason="Must be DEBUG, INFO, WARNING, or ERROR"
        )
        assert "LOG_LEVEL" in error.message
        assert error.details["setting"] == "LOG_LEVEL"
        assert error.details["provided_value_type"] == "str"
        assert error.details["reason"] == "Must be DEBUG, INFO, WARNING, or ERROR"


class TestExternalServiceErrors:
    """Test suite for external service errors."""

    def test_broker_connection_error(self):
        """Test BrokerConnectionError."""
        error = BrokerConnectionError(broker="Binance", reason="Connection timeout")
        assert "Binance" in error.message
        assert error.details["service"] == "Binance"
        assert error.details["reason"] == "Connection timeout"

    def test_data_provider_error(self):
        """Test DataProviderError."""
        error = DataProviderError(provider="AkShare", reason="Service unavailable")
        assert "AkShare" in error.message
        assert error.details["service"] == "AkShare"
        assert error.details["reason"] == "Service unavailable"


class TestUtilityFunctions:
    """Test suite for utility functions."""

    def test_format_exception_for_response_custom_error(self):
        """Test format_exception_for_response with custom error."""
        error = UserNotFoundError(user_id="123")
        result = format_exception_for_response(error)
        assert result["error"] == "UserNotFoundError"
        assert "123" in result["message"]

    def test_format_exception_for_response_standard_error(self):
        """Test format_exception_for_response with standard error."""
        error = ValueError("Invalid value")
        result = format_exception_for_response(error)
        assert result["error"] == "ValueError"
        assert result["message"] == "Invalid value"

    def test_format_exception_for_response_empty_message(self):
        """Test format_exception_for_response with error without message."""
        error = ValueError()  # No message
        result = format_exception_for_response(error)
        assert result["error"] == "ValueError"
        assert result["message"] == "An error occurred"


class TestExceptionHierarchy:
    """Test suite for exception inheritance."""

    def test_authentication_errors_inherit_from_base(self):
        """Test that all auth errors inherit from AuthenticationError."""
        assert issubclass(InvalidCredentialsError, AuthenticationError)
        assert issubclass(UserNotFoundError, AuthenticationError)
        assert issubclass(UserAlreadyExistsError, AuthenticationError)
        assert issubclass(InvalidTokenError, AuthenticationError)
        assert issubclass(TokenExpiredError, InvalidTokenError)
        assert issubclass(InsufficientPermissionsError, AuthenticationError)
        assert issubclass(UserInactiveError, AuthenticationError)

    def test_validation_errors_inherit_from_base(self):
        """Test that all validation errors inherit from ValidationError."""
        assert issubclass(InvalidInputError, ValidationError)
        assert issubclass(MissingFieldError, ValidationError)
        assert issubclass(PasswordTooWeakError, ValidationError)

    def test_all_custom_errors_inherit_from_base(self):
        """Test that all custom errors inherit from BaseAppError."""
        custom_errors = [
            AuthenticationError,
            InvalidCredentialsError,
            UserNotFoundError,
            UserAlreadyExistsError,
            InvalidTokenError,
            TokenExpiredError,
            InsufficientPermissionsError,
            UserInactiveError,
            ValidationError,
            InvalidInputError,
            MissingFieldError,
            PasswordTooWeakError,
            StrategyError,
            StrategyNotFoundError,
            InvalidStrategyCodeError,
            BacktestError,
            BacktestNotFoundError,
            BacktestExecutionError,
            BacktestTimeoutError,
            DataError,
            DataNotFoundError,
            InvalidDateRangeError,
            ConfigurationError,
            MissingConfigError,
            InvalidConfigError,
            ExternalServiceError,
            BrokerConnectionError,
            DataProviderError,
        ]
        for error_class in custom_errors:
            assert issubclass(error_class, BaseAppError), (
                f"{error_class} should inherit from BaseAppError"
            )
