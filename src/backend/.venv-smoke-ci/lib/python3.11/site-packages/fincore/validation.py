"""Input validation utilities for fincore.

Provides decorators and functions for validating inputs to financial metrics.
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Optional, TypeVar

import numpy as np
import pandas as pd

from fincore.constants import DAILY, MONTHLY, QUARTERLY, WEEKLY, YEARLY
from fincore.exceptions import (
    DataAlignmentError,
    InsufficientDataError,
    InvalidPeriodError,
    MissingDataError,
    NumericalError,
    UnsupportedFormatError,
    ValidationError,
)

__all__ = [
    "validate_alignment",
    "validate_input",
    "validate_numeric_array",
    "validate_percentage",
    "validate_period",
    "validate_positive",
    "validate_returns",
    "validate_risk_free",
    "validate_window",
]

F = TypeVar("F", bound=Callable[..., Any])


def validate_input(
    *validators: Callable[[Any], Any | None],
    error_message: str = "Input validation failed",
    raise_on_error: bool = True,
) -> Callable[[F], F]:
    """Decorator to validate function inputs with a list of validators."""

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            args_list = list(args)
            for i, validator in enumerate(validators):
                if i >= len(args_list):
                    break
                try:
                    result = validator(args_list[i])
                    if result is not None:
                        args_list[i] = result
                # Broad except intentional: validators may raise diverse errors
                # (e.g. pandas KeyError, numpy ValueError). Narrowing would risk
                # uncaught exceptions from third-party validators.
                except (TypeError, ValueError, AttributeError, KeyError, RuntimeError, LookupError) as e:
                    if raise_on_error:
                        param_name = func.__code__.co_varnames[i] if i < len(func.__code__.co_varnames) else f"arg{i}"
                        raise ValidationError(
                            f"{error_message}: {e!s}",
                            param_name=param_name,
                            value=args_list[i],
                        ) from e
            return func(*args_list, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def validate_returns(
    returns: Any,
    min_length: int = 1,
    allow_empty: bool = False,
    require_datetime_index: bool = True,
    name: str = "returns",
) -> Any:
    """Validate returns input."""
    if returns is None:
        raise MissingDataError(f"{name} is required", missing_field=name)

    if not isinstance(returns, (np.ndarray, pd.Series, pd.DataFrame, list)):
        raise UnsupportedFormatError(
            f"Expected numpy array, pandas Series/DataFrame, or list, got {type(returns).__name__}",
            expected_format="numpy.ndarray, pandas.Series/DataFrame, or list",
            actual_format=type(returns).__name__,
        )

    if not allow_empty and len(returns) == 0:
        raise InsufficientDataError(
            f"{name} cannot be empty",
            required_length=1,
            actual_length=0,
        )

    if len(returns) < min_length:
        raise InsufficientDataError(
            f"{name} must have at least {min_length} observations",
            required_length=min_length,
            actual_length=len(returns),
        )

    if (
        require_datetime_index
        and isinstance(returns, (pd.Series, pd.DataFrame))
        and not isinstance(returns.index, pd.DatetimeIndex)
    ):
        raise ValidationError(
            f"{name} must have a DatetimeIndex",
            param_name=name,
            value=returns.index,
        )

    if isinstance(returns, list):
        returns = np.array(returns)

    return returns


def validate_period(period: str, _name: str = "period") -> str:
    """Validate period parameter."""
    valid_periods = [DAILY, WEEKLY, MONTHLY, QUARTERLY, YEARLY]
    if period not in valid_periods:
        raise InvalidPeriodError(period)
    return period


def validate_positive(
    value: float,
    min_value: float = 0,
    allow_zero: bool = True,
    name: str = "value",
) -> float:
    """Validate that a value is positive."""
    if allow_zero:
        if value < min_value:
            raise ValidationError(
                f"{name} must be >= {min_value}",
                param_name=name,
                value=value,
            )
    else:
        if value <= min_value:
            raise ValidationError(
                f"{name} must be > {min_value}",
                param_name=name,
                value=value,
            )
    return value


def validate_alignment(
    series1: Any,
    series2: Any,
    name1: str = "series1",
    name2: str = "series2",
) -> tuple[Any, Any]:
    """Validate that two series are aligned."""
    if isinstance(series1, (pd.Series, pd.DataFrame)) and isinstance(series2, (pd.Series, pd.DataFrame)):
        if len(series1) != len(series2):
            raise DataAlignmentError(
                f"{name1} and {name2} must have the same length",
                returns_length=len(series1),
                factor_length=len(series2),
            )

        if (
            isinstance(series1.index, pd.DatetimeIndex)
            and isinstance(series2.index, pd.DatetimeIndex)
            and not series1.index.equals(series2.index)
        ):
            raise DataAlignmentError(
                f"{name1} and {name2} must have the same index",
                returns_length=len(series1),
                factor_length=len(series2),
            )

    return series1, series2


def validate_percentage(value: float, name: str = "value") -> float:
    """Validate that a value is between 0 and 1."""
    if not 0 <= value <= 1:
        raise ValidationError(
            f"{name} must be between 0 and 1, got {value}",
            param_name=name,
            value=value,
        )
    return value


def validate_numeric_array(
    array: Any,
    min_length: int = 1,
    allow_nan: bool = True,
    name: str = "array",
) -> Any:
    """Validate numeric array input."""
    if array is None:
        raise MissingDataError(f"{name} is required", missing_field=name)

    if not isinstance(array, (np.ndarray, list)):
        raise UnsupportedFormatError(
            f"Expected numpy array or list, got {type(array).__name__}",
            expected_format="numpy.ndarray or list",
            actual_format=type(array).__name__,
        )

    if len(array) < min_length:
        raise InsufficientDataError(
            f"{name} must have at least {min_length} elements",
            required_length=min_length,
            actual_length=len(array),
        )

    if isinstance(array, list):
        array = np.array(array)

    if not allow_nan and np.any(np.isnan(array)):
        raise NumericalError(
            f"{name} contains NaN values",
            operation="validation",
        )

    return array


def validate_risk_free(risk_free: float, name: str = "risk_free") -> float:
    """Validate risk-free rate parameter."""
    if not isinstance(risk_free, (int, float)):
        raise ValidationError(
            f"{name} must be a number, got {type(risk_free).__name__}",
            param_name=name,
            value=risk_free,
        )
    return risk_free


def validate_window(
    window: int,
    min_periods: int = 2,
    name: str = "window",
) -> int:
    """Validate rolling window parameter."""
    if window < min_periods:
        raise ValidationError(
            f"{name} must be at least {min_periods}, got {window}",
            param_name=name,
            value=window,
        )
    return window
