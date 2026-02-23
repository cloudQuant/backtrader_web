"""
Custom exception classes for consistent error handling across the application.

This module defines a hierarchy of custom exceptions that provide:
- Consistent error types across services
- Structured error information
- Easy error identification and handling
- Better debugging and logging

Usage:
    >>> from app.utils.exceptions import (
    ...     UserNotFoundError,
    ...     AuthenticationError,
    ...     ValidationError,
    ... )
    >>> raise UserNotFoundError(user_id="123")
"""
from typing import Any, Dict, Optional


class BaseAppError(Exception):
    """Base exception class for all application errors.

    All custom exceptions should inherit from this class.

    Attributes:
        message: Human-readable error message.
        details: Additional error details (optional).
        error_code: Unique error code for categorization.
    """

    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None
    ):
        """Initialize the base application error.

        Args:
            message: Human-readable error message.
            details: Additional error details as a dictionary.
            error_code: Unique error code for this error type.
        """
        self.message = message
        self.details = details or {}
        self.error_code = error_code or self.__class__.__name__
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to a dictionary for API responses.

        Returns:
            Dictionary containing error information.
        """
        result = {
            "error": self.error_code,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        return result


# ==================== Authentication Errors ====================

class AuthenticationError(BaseAppError):
    """Base class for authentication-related errors."""

    def __init__(
        self,
        message: str = "Authentication failed",
        details: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None
    ):
        """Initialize authentication error.

        Args:
            message: Human-readable error message.
            details: Additional error details.
            error_code: Optional override for error code.
        """
        super().__init__(
            message,
            details,
            error_code or "AUTHENTICATION_ERROR"
        )


class InvalidCredentialsError(AuthenticationError):
    """Raised when username or password is incorrect."""

    def __init__(self, username: Optional[str] = None):
        """Initialize invalid credentials error.

        Args:
            username: The username that was used (optional).
        """
        details = {}
        if username:
            details["username"] = username
        super().__init__(
            "Invalid username or password",
            details,
            "InvalidCredentialsError"
        )


class UserNotFoundError(AuthenticationError):
    """Raised when a user is not found in the system."""

    def __init__(self, user_id: Optional[str] = None, username: Optional[str] = None):
        """Initialize user not found error.

        Args:
            user_id: The user ID that was not found.
            username: The username that was not found.
        """
        details = {}
        if user_id:
            details["user_id"] = user_id
        if username:
            details["username"] = username
        message = "User not found"
        if user_id:
            message += f" (ID: {user_id})"
        elif username:
            message += f" (username: {username})"
        super().__init__(message, details, "UserNotFoundError")


class UserAlreadyExistsError(AuthenticationError):
    """Raised when trying to create a user that already exists."""

    def __init__(self, username: Optional[str] = None, email: Optional[str] = None):
        """Initialize user already exists error.

        Args:
            username: The conflicting username.
            email: The conflicting email.
        """
        details = {}
        if username:
            details["username"] = username
        if email:
            details["email"] = email

        message = "User already exists"
        if username:
            message += f" (username: {username})"
        elif email:
            message += f" (email: {email})"
        super().__init__(message, details, "UserAlreadyExistsError")


class InvalidTokenError(AuthenticationError):
    """Raised when an authentication token is invalid or expired."""

    def __init__(self, reason: str = "Invalid or expired token"):
        """Initialize invalid token error.

        Args:
            reason: The reason why the token is invalid.
        """
        super().__init__(
            reason,
            {"reason": reason},
            "InvalidTokenError"
        )


class TokenExpiredError(InvalidTokenError):
    """Raised specifically when a token has expired."""

    def __init__(self):
        """Initialize token expired error."""
        super().__init__("Token has expired")


class InsufficientPermissionsError(AuthenticationError):
    """Raised when a user lacks required permissions."""

    def __init__(
        self,
        required_permission: Optional[str] = None,
        resource: Optional[str] = None
    ):
        """Initialize insufficient permissions error.

        Args:
            required_permission: The permission that was required.
            resource: The resource being accessed.
        """
        details = {}
        if required_permission:
            details["required_permission"] = required_permission
        if resource:
            details["resource"] = resource

        message = "Insufficient permissions"
        if required_permission:
            message += f" (requires: {required_permission})"
        super().__init__(message, details, "InsufficientPermissionsError")


class UserInactiveError(AuthenticationError):
    """Raised when trying to authenticate an inactive user account."""

    def __init__(self, user_id: Optional[str] = None, username: Optional[str] = None):
        """Initialize user inactive error.

        Args:
            user_id: The inactive user's ID.
            username: The inactive user's username.
        """
        details = {}
        if user_id:
            details["user_id"] = user_id
        if username:
            details["username"] = username
        super().__init__(
            "User account is inactive",
            details,
            "UserInactiveError"
        )


# ==================== Validation Errors ====================

class ValidationError(BaseAppError):
    """Base class for validation errors."""

    def __init__(
        self,
        message: str = "Validation failed",
        field: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None
    ):
        """Initialize validation error.

        Args:
            message: Human-readable error message.
            field: The field that failed validation.
            details: Additional error details.
            error_code: Optional override for error code.
        """
        full_details = details or {}
        if field:
            full_details["field"] = field
        super().__init__(
            message,
            full_details,
            error_code or "VALIDATION_ERROR"
        )


class InvalidInputError(ValidationError):
    """Raised when input data is invalid."""

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Optional[Any] = None
    ):
        """Initialize invalid input error.

        Args:
            message: Human-readable error message.
            field: The field with invalid input.
            value: The invalid value (will not be logged in production).
        """
        details = {}
        if field:
            details["field"] = field
        if value is not None:
            details["value_type"] = type(value).__name__
        super().__init__(
            message,
            field,
            details,
            "InvalidInputError"
        )


class MissingFieldError(ValidationError):
    """Raised when a required field is missing."""

    def __init__(self, field_name: str):
        """Initialize missing field error.

        Args:
            field_name: The name of the missing field.
        """
        super().__init__(
            f"Required field is missing: {field_name}",
            field=field_name,
            error_code="MissingFieldError"
        )


class PasswordTooWeakError(ValidationError):
    """Raised when a password doesn't meet strength requirements."""

    def __init__(self, reasons: list[str]):
        """Initialize password too weak error.

        Args:
            reasons: List of reasons why the password is weak.
        """
        super().__init__(
            "Password does not meet security requirements",
            details={"requirements": reasons},
            error_code="PasswordTooWeakError"
        )


# ==================== Strategy Errors ====================

class StrategyError(BaseAppError):
    """Base class for strategy-related errors."""

    def __init__(
        self,
        message: str = "Strategy operation failed",
        details: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None
    ):
        """Initialize strategy error.

        Args:
            message: Human-readable error message.
            details: Additional error details.
            error_code: Optional override for error code.
        """
        super().__init__(
            message,
            details,
            error_code or "STRATEGY_ERROR"
        )


class StrategyNotFoundError(StrategyError):
    """Raised when a strategy is not found."""

    def __init__(self, strategy_id: Optional[str] = None):
        """Initialize strategy not found error.

        Args:
            strategy_id: The strategy ID that was not found.
        """
        details = {}
        if strategy_id:
            details["strategy_id"] = strategy_id
        message = "Strategy not found"
        if strategy_id:
            message += f" (ID: {strategy_id})"
        super().__init__(message, details, "StrategyNotFoundError")


class InvalidStrategyCodeError(StrategyError):
    """Raised when strategy code is invalid or cannot be parsed."""

    def __init__(
        self,
        message: str = "Invalid strategy code",
        line: Optional[int] = None,
        error: Optional[str] = None
    ):
        """Initialize invalid strategy code error.

        Args:
            message: Human-readable error message.
            line: The line number where the error occurred.
            error: The actual error message.
        """
        details = {}
        if line:
            details["line"] = line
        if error:
            details["error"] = error
        super().__init__(message, details, "InvalidStrategyCodeError")


# ==================== Backtest Errors ====================

class BacktestError(BaseAppError):
    """Base class for backtest-related errors."""

    def __init__(
        self,
        message: str = "Backtest operation failed",
        details: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None
    ):
        """Initialize backtest error.

        Args:
            message: Human-readable error message.
            details: Additional error details.
            error_code: Optional override for error code.
        """
        super().__init__(
            message,
            details,
            error_code or "BACKTEST_ERROR"
        )


class BacktestNotFoundError(BacktestError):
    """Raised when a backtest result is not found."""

    def __init__(self, task_id: Optional[str] = None):
        """Initialize backtest not found error.

        Args:
            task_id: The task ID that was not found.
        """
        details = {}
        if task_id:
            details["task_id"] = task_id
        message = "Backtest not found"
        if task_id:
            message += f" (task ID: {task_id})"
        super().__init__(message, details, "BacktestNotFoundError")


class BacktestExecutionError(BacktestError):
    """Raised when backtest execution fails."""

    def __init__(
        self,
        message: str,
        task_id: Optional[str] = None,
        logs: Optional[str] = None
    ):
        """Initialize backtest execution error.

        Args:
            message: Human-readable error message.
            task_id: The task ID that failed.
            logs: Error logs or output.
        """
        details = {}
        if task_id:
            details["task_id"] = task_id
        if logs:
            details["logs"] = logs[:500]  # Truncate long logs
        super().__init__(message, details, "BacktestExecutionError")


class BacktestTimeoutError(BacktestExecutionError):
    """Raised when backtest execution times out."""

    def __init__(self, task_id: str, timeout_seconds: int):
        """Initialize backtest timeout error.

        Args:
            task_id: The task ID that timed out.
            timeout_seconds: The timeout duration in seconds.
        """
        super().__init__(
            f"Backtest execution timed out after {timeout_seconds} seconds",
            task_id=task_id
        )


# ==================== Data Errors ====================

class DataError(BaseAppError):
    """Base class for data-related errors."""

    def __init__(
        self,
        message: str = "Data operation failed",
        details: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None
    ):
        """Initialize data error.

        Args:
            message: Human-readable error message.
            details: Additional error details.
            error_code: Optional override for error code.
        """
        super().__init__(
            message,
            details,
            error_code or "DATA_ERROR"
        )


class DataNotFoundError(DataError):
    """Raised when requested data is not available."""

    def __init__(
        self,
        symbol: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ):
        """Initialize data not found error.

        Args:
            symbol: The stock symbol.
            start_date: The start date.
            end_date: The end date.
        """
        details = {}
        if symbol:
            details["symbol"] = symbol
        if start_date:
            details["start_date"] = start_date
        if end_date:
            details["end_date"] = end_date

        message = "Market data not available"
        if symbol:
            message += f" for symbol: {symbol}"
        super().__init__(message, details, "DataNotFoundError")


class InvalidDateRangeError(DataError):
    """Raised when date range is invalid."""

    def __init__(
        self,
        reason: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ):
        """Initialize invalid date range error.

        Args:
            reason: Why the date range is invalid.
            start_date: The start date.
            end_date: The end date.
        """
        details = {"reason": reason}
        if start_date:
            details["start_date"] = start_date
        if end_date:
            details["end_date"] = end_date
        super().__init__("Invalid date range", details, "InvalidDateRangeError")


# ==================== Configuration Errors ====================

class ConfigurationError(BaseAppError):
    """Base class for configuration-related errors."""

    def __init__(
        self,
        message: str = "Configuration error",
        setting: Optional[str] = None,
        error_code: Optional[str] = None
    ):
        """Initialize configuration error.

        Args:
            message: Human-readable error message.
            setting: The problematic configuration setting.
            error_code: Optional override for error code.
        """
        details = {}
        if setting:
            details["setting"] = setting
        super().__init__(
            message,
            details if details else None,
            error_code or "CONFIGURATION_ERROR"
        )


class MissingConfigError(ConfigurationError):
    """Raised when a required configuration is missing."""

    def __init__(self, setting: str):
        """Initialize missing config error.

        Args:
            setting: The missing configuration setting.
        """
        super().__init__(
            f"Required configuration setting is missing: {setting}",
            setting=setting,
            error_code="MissingConfigError"
        )


class InvalidConfigError(ConfigurationError):
    """Raised when a configuration value is invalid."""

    def __init__(
        self,
        setting: str,
        value: Optional[Any] = None,
        reason: Optional[str] = None
    ):
        """Initialize invalid config error.

        Args:
            setting: The invalid configuration setting.
            value: The invalid value.
            reason: Why the value is invalid.
        """
        details = {"setting": setting}
        if value is not None:
            details["provided_value_type"] = type(value).__name__
        if reason:
            details["reason"] = reason

        message = f"Invalid configuration value for: {setting}"
        if reason:
            message += f" - {reason}"
        # Call parent's __init__ with message and setting, not details
        super().__init__(
            message,
            setting=setting,
            error_code="InvalidConfigError"
        )
        # Then update details
        self.details.update(details)


# ==================== External Service Errors ====================

class ExternalServiceError(BaseAppError):
    """Base class for external service errors."""

    def __init__(
        self,
        service: str,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None
    ):
        """Initialize external service error.

        Args:
            service: The name of the external service.
            message: Human-readable error message.
            details: Additional error details.
            error_code: Optional override for error code.
        """
        full_message = message or f"External service error: {service}"
        full_details = details or {}
        full_details["service"] = service
        super().__init__(
            full_message,
            full_details,
            error_code or "EXTERNAL_SERVICE_ERROR"
        )


class BrokerConnectionError(ExternalServiceError):
    """Raised when broker connection fails."""

    def __init__(
        self,
        broker: str,
        reason: Optional[str] = None
    ):
        """Initialize broker connection error.

        Args:
            broker: The broker name.
            reason: Why the connection failed.
        """
        details = {}
        if reason:
            details["reason"] = reason
        super().__init__(
            broker,
            message=f"Failed to connect to broker: {broker}",
            details=details,
            error_code="BrokerConnectionError"
        )


class DataProviderError(ExternalServiceError):
    """Raised when data provider fails."""

    def __init__(
        self,
        provider: str,
        reason: Optional[str] = None
    ):
        """Initialize data provider error.

        Args:
            provider: The data provider name.
            reason: Why the request failed.
        """
        details = {}
        if reason:
            details["reason"] = reason
        super().__init__(
            provider,
            message=f"Data provider error: {provider}",
            details=details,
            error_code="DataProviderError"
        )


# ==================== Utility Functions ====================

def format_exception_for_response(exc: Exception) -> Dict[str, Any]:
    """Format any exception for API response.

    Args:
        exc: The exception to format.

    Returns:
        Dictionary with error information suitable for API responses.
    """
    if isinstance(exc, BaseAppError):
        return exc.to_dict()

    # Handle standard Python exceptions
    return {
        "error": type(exc).__name__,
        "message": str(exc) if str(exc) else "An error occurred",
    }
