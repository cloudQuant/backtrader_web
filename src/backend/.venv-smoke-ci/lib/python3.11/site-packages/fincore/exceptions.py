"""Custom exceptions for fincore library.

Provides specific exception classes for better error handling.
"""

from __future__ import annotations

import functools
from typing import Any, Callable, ClassVar

import numpy as np

from fincore.constants import DAILY, MONTHLY, QUARTERLY, WEEKLY, YEARLY

__all__ = [
    "DataAlignmentError",
    "DependencyError",
    "FincoreError",
    "InsufficientDataError",
    "InvalidPeriodError",
    "MissingDataError",
    "NumericalError",
    "UnsupportedFormatError",
    "ValidationError",
    "check_dependencies",
    "ensure_not_nan",
    "handle_numerical_error",
    "safe_divide",
    "safe_sqrt",
]


class FincoreError(Exception):
    """Base exception for all fincore errors."""


class ValidationError(FincoreError):
    """Raised when input validation fails."""

    def __init__(
        self,
        message: str,
        param_name: str | None = None,
        value: Any = None,
    ):
        self.message = message
        self.param_name = param_name
        self.value = value
        super().__init__(message)

    def __str__(self) -> str:
        details = [
            f"Parameter: {self.param_name or 'unknown'}",
            f"Value: {self.value!r}",
            f"Message: {self.message}",
        ]
        return "\n".join(details)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_type": "ValidationError",
            "message": self.message,
            "param_name": self.param_name,
            "value": str(self.value) if self.value is not None else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ValidationError:
        if data.get("error_type") != "ValidationError":
            raise ValueError("Invalid error type for ValidationError")
        return cls(
            message=data["message"],
            param_name=data.get("param_name"),
            value=data.get("value"),
        )


class InsufficientDataError(FincoreError):
    """Raised when there is insufficient data for a calculation."""

    def __init__(
        self,
        message: str,
        required_length: int | None = None,
        actual_length: int | None = None,
    ):
        self.message = message
        self.required_length = required_length
        self.actual_length = actual_length
        super().__init__(message)

    def __str__(self) -> str:
        details = [self.message]
        if self.required_length is not None:
            details.append(f"  required: {self.required_length} observations")
        if self.actual_length is not None:
            details.append(f"  actual: {self.actual_length} observations")
        return "\n".join(details)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_type": "InsufficientDataError",
            "message": self.message,
            "required_length": self.required_length,
            "actual_length": self.actual_length,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InsufficientDataError:
        if data.get("error_type") != "InsufficientDataError":
            raise ValueError("Invalid error type for InsufficientDataError")
        return cls(
            message=data["message"],
            required_length=data.get("required_length"),
            actual_length=data.get("actual_length"),
        )


class InvalidPeriodError(FincoreError):
    """Raised when an invalid period is specified."""

    VALID_PERIODS: ClassVar[list[str]] = [DAILY, WEEKLY, MONTHLY, QUARTERLY, YEARLY]

    def __init__(self, period: str):
        self.period = period
        super().__init__(f"Invalid period: {period!r}. Must be one of: {self.VALID_PERIODS}")

    def __str__(self) -> str:
        return f"InvalidPeriodError({self.period})"

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_type": "InvalidPeriodError",
            "period": self.period,
            "valid_periods": self.VALID_PERIODS,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InvalidPeriodError:
        if data.get("error_type") != "InvalidPeriodError":
            raise ValueError("Invalid error type for InvalidPeriodError")
        return cls(period=data["period"])


class DataAlignmentError(FincoreError):
    """Raised when data alignment fails."""

    def __init__(
        self,
        message: str,
        returns_length: int | None = None,
        factor_length: int | None = None,
    ):
        self.message = message
        self.returns_length = returns_length
        self.factor_length = factor_length
        super().__init__(message)

    def __str__(self) -> str:
        details = [self.message]
        if self.returns_length is not None:
            details.append(f"  returns length: {self.returns_length}")
        if self.factor_length is not None:
            details.append(f"  factor length: {self.factor_length}")
        return "\n".join(details)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_type": "DataAlignmentError",
            "message": self.message,
            "returns_length": self.returns_length,
            "factor_length": self.factor_length,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DataAlignmentError:
        if data.get("error_type") != "DataAlignmentError":
            raise ValueError("Invalid error type for DataAlignmentError")
        return cls(
            message=data["message"],
            returns_length=data.get("returns_length"),
            factor_length=data.get("factor_length"),
        )


class NumericalError(FincoreError):
    """Raised when numerical computation fails."""

    def __init__(
        self,
        message: str,
        operation: str | None = None,
    ):
        self.message = message
        self.operation = operation
        super().__init__(message)

    def __str__(self) -> str:
        details = [self.message]
        if self.operation:
            details.append(f"  operation: {self.operation}")
        return "\n".join(details)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_type": "NumericalError",
            "message": self.message,
            "operation": self.operation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NumericalError:
        if data.get("error_type") != "NumericalError":
            raise ValueError("Invalid error type for NumericalError")
        return cls(
            message=data["message"],
            operation=data.get("operation"),
        )


class MissingDataError(FincoreError):
    """Raised when required data is missing."""

    def __init__(
        self,
        message: str,
        missing_field: str | None = None,
    ):
        self.message = message
        self.missing_field = missing_field
        super().__init__(message)

    def __str__(self) -> str:
        details = [self.message]
        if self.missing_field:
            details.append(f"  missing field: {self.missing_field}")
        return "\n".join(details)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_type": "MissingDataError",
            "message": self.message,
            "missing_field": self.missing_field,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MissingDataError:
        if data.get("error_type") != "MissingDataError":
            raise ValueError("Invalid error type for MissingDataError")
        return cls(
            message=data["message"],
            missing_field=data.get("missing_field"),
        )


class UnsupportedFormatError(FincoreError):
    """Raised when an unsupported data format is encountered."""

    def __init__(
        self,
        message: str,
        expected_format: str | None = None,
        actual_format: str | None = None,
    ):
        self.message = message
        self.expected_format = expected_format
        self.actual_format = actual_format
        super().__init__(message)

    def __str__(self) -> str:
        details = [self.message]
        if self.expected_format:
            details.append(f"  expected: {self.expected_format}")
        if self.actual_format:
            details.append(f"  actual: {self.actual_format}")
        return "\n".join(details)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_type": "UnsupportedFormatError",
            "message": self.message,
            "expected_format": self.expected_format,
            "actual_format": self.actual_format,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UnsupportedFormatError:
        if data.get("error_type") != "UnsupportedFormatError":
            raise ValueError("Invalid error type for UnsupportedFormatError")
        return cls(
            message=data["message"],
            expected_format=data.get("expected_format"),
            actual_format=data.get("actual_format"),
        )


class DependencyError(FincoreError):
    """Raised when a required dependency is not available."""

    def __init__(
        self,
        message: str,
        dependency: str | None = None,
    ):
        self.message = message
        self.dependency = dependency
        super().__init__(message)

    def __str__(self) -> str:
        details = [self.message]
        if self.dependency:
            details.append(f"  dependency: {self.dependency}")
        return "\n".join(details)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_type": "DependencyError",
            "message": self.message,
            "dependency": self.dependency,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DependencyError:
        if data.get("error_type") != "DependencyError":
            raise ValueError("Invalid error type for DependencyError")
        return cls(
            message=data["message"],
            dependency=data.get("dependency"),
        )


# ---------------------------------------------------------------------------
# Error-handling utilities
# ---------------------------------------------------------------------------


def handle_numerical_error(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to handle numerical errors gracefully."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except (ZeroDivisionError, FloatingPointError, OverflowError) as e:
            raise NumericalError(
                f"Numerical error in {func.__name__}: {e!s}",
                operation=type(e).__name__,
            ) from e
        except (ValueError, TypeError) as e:
            raise NumericalError(
                f"Numerical error in {func.__name__}: {e!s}",
                operation=type(e).__name__,
            ) from e

    return wrapper


def check_dependencies(*dependencies: str) -> None:
    """Check if optional dependencies are available."""
    missing = []
    for dep in dependencies:
        try:
            __import__(dep)
        except ImportError:
            missing.append(dep)

    if missing:
        raise DependencyError(
            f"Missing required dependencies: {', '.join(missing)}",
            dependency=", ".join(missing),
        )


def ensure_not_nan(
    value: Any,
    param_name: str,
    replace_with: float | None = None,
) -> Any:
    """Ensure a value is not NaN."""
    is_nan = isinstance(value, float) and np.isnan(value)
    if is_nan:
        if replace_with is not None:
            return replace_with
        raise ValidationError(
            f"{param_name} cannot be NaN",
            param_name=param_name,
            value=value,
        )
    return value


def safe_divide(
    numerator: Any,
    denominator: Any,
    default: Any = np.nan,
) -> Any:
    """Safely divide two values, returning default if denominator is zero."""
    with np.errstate(divide="ignore", invalid="ignore"):
        if isinstance(denominator, (int, float)) and denominator == 0:
            return default
        if isinstance(numerator, np.ndarray) and isinstance(denominator, np.ndarray):
            return np.where(denominator != 0, np.divide(numerator, denominator), default)
        return numerator / denominator


def safe_sqrt(value: Any, default: Any = np.nan) -> Any:
    """Safely compute square root, returning default if negative."""
    with np.errstate(invalid="ignore"):
        if isinstance(value, (int, float)) and value < 0:
            return default
        if isinstance(value, np.ndarray):
            return np.sqrt(value)
        return np.sqrt(value)
