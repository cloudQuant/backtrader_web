"""
Test Data Factories for Backtrader Web

Provides factory functions for generating test data with sensible defaults
and support for overrides. This reduces boilerplate in tests and ensures
consistent data generation across the test suite.

Usage:
    from tests.factories import UserFactory, StrategyFactory, BacktestRequestFactory

    # Create with defaults
    user = UserFactory.create()

    # Create with overrides
    admin_user = UserFactory.create(username="admin", role="admin")

    # Create multiple
    users = UserFactory.create_batch(3)
"""
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional


class BaseFactory:
    """Base factory class with common functionality."""

    @classmethod
    def _generate_id(cls) -> str:
        """Generate a unique test ID."""
        return str(uuid.uuid4())

    @classmethod
    def _generate_username(cls, prefix: str = "user") -> str:
        """Generate a unique username."""
        return f"{prefix}_{uuid.uuid4().hex[:8]}"

    @classmethod
    def _generate_email(cls, username: Optional[str] = None) -> str:
        """Generate a unique email address."""
        if username:
            return f"{username}@test.example.com"
        return f"{uuid.uuid4().hex[:8]}@test.example.com"


class UserFactory(BaseFactory):
    """Factory for user-related test data."""

    @staticmethod
    def create(**overrides) -> Dict[str, Any]:
        """
        Create user registration data with sensible defaults.

        Args:
            **overrides: Field values to override defaults

        Returns:
            Dictionary with user registration data

        Examples:
            >>> UserFactory.create()
            {'username': 'user_abc123', 'email': 'abc123@test.example.com', 'password': 'Test12345678'}

            >>> UserFactory.create(username="admin", password="AdminPass123!")
            {'username': 'admin', 'email': 'admin@test.example.com', 'password': 'AdminPass123!'}
        """
        username = overrides.get("username") or BaseFactory._generate_username()
        defaults = {
            "username": username,
            "email": overrides.get("email") or f"{username}@test.example.com",
            "password": "Test12345678",  # Meets minimum password requirements
        }
        defaults.update(overrides)
        return defaults

    @staticmethod
    def create_batch(count: int, **common_overrides) -> List[Dict[str, Any]]:
        """
        Create multiple user data objects.

        Args:
            count: Number of users to create
            **common_overrides: Fields to apply to all users

        Returns:
            List of user data dictionaries
        """
        return [UserFactory.create(**common_overrides) for _ in range(count)]


class StrategyFactory(BaseFactory):
    """Factory for strategy-related test data."""

    @staticmethod
    def create(**overrides) -> Dict[str, Any]:
        """
        Create strategy data with sensible defaults.

        Args:
            **overrides: Field values to override defaults

        Returns:
            Dictionary with strategy data
        """
        defaults = {
            "name": f"Test Strategy {uuid.uuid4().hex[:6]}",
            "description": "A test strategy for automated testing",
            "code": "class TestStrategy(bt.Strategy):\n    pass",
            "params": {},
            "category": "custom",
        }
        defaults.update(overrides)
        return defaults


class BacktestRequestFactory(BaseFactory):
    """Factory for backtest request test data."""

    @staticmethod
    def create(**overrides) -> Dict[str, Any]:
        """
        Create backtest request data with sensible defaults.

        Args:
            **overrides: Field values to override defaults

        Returns:
            Dictionary with backtest request data

        Examples:
            >>> BacktestRequestFactory.create()
            {'strategy_id': 'strategy_123', 'symbol': '000001.SZ', ...}

            >>> BacktestRequestFactory.create(symbol='600519.SH', initial_cash=500000)
            {'strategy_id': 'strategy_123', 'symbol': '600519.SH', 'initial_cash': 500000, ...}
        """
        defaults = {
            "strategy_id": f"strategy_{uuid.uuid4().hex[:8]}",
            "symbol": "000001.SZ",
            "start_date": "2024-01-01T00:00:00",
            "end_date": "2024-06-30T00:00:00",
            "initial_cash": 100000,
            "commission": 0.001,
            "params": {},
        }
        defaults.update(overrides)
        return defaults


class AccountFactory(BaseFactory):
    """Factory for paper trading account test data."""

    @staticmethod
    def create(**overrides) -> Dict[str, Any]:
        """
        Create paper trading account data with sensible defaults.

        Args:
            **overrides: Field values to override defaults

        Returns:
            Dictionary with account data
        """
        defaults = {
            "name": f"Test Account {uuid.uuid4().hex[:6]}",
            "initial_cash": 100000,
            "commission_rate": 0.001,
            "slippage_rate": 0.001,
        }
        defaults.update(overrides)
        return defaults


class AlertRuleFactory(BaseFactory):
    """Factory for alert rule test data."""

    @staticmethod
    def create(**overrides) -> Dict[str, Any]:
        """
        Create alert rule data with sensible defaults.

        Args:
            **overrides: Field values to override defaults

        Returns:
            Dictionary with alert rule data
        """
        defaults = {
            "alert_type": "threshold",
            "severity": "warning",
            "name": f"Test Rule {uuid.uuid4().hex[:6]}",
            "description": "A test alert rule",
            "trigger_type": "greater_than",
            "trigger_config": {"threshold": 0.05},
            "notification_enabled": True,
            "is_active": True,
        }
        defaults.update(overrides)
        return defaults


class ComparisonFactory(BaseFactory):
    """Factory for comparison test data."""

    @staticmethod
    def create(**overrides) -> Dict[str, Any]:
        """
        Create comparison data with sensible defaults.

        Args:
            **overrides: Field values to override defaults

        Returns:
            Dictionary with comparison data
        """
        defaults = {
            "name": f"Comparison {uuid.uuid4().hex[:6]}",
            "description": "Test comparison",
            "type": "metrics",
            "backtest_task_ids": [f"task_{uuid.uuid4().hex[:8]}", f"task_{uuid.uuid4().hex[:8]}"],
        }
        defaults.update(overrides)
        return defaults


# HTTP Status Code Constants for Assertions
class HTTP:
    """HTTP status code constants for clearer assertions."""

    OK = 200
    CREATED = 201
    NO_CONTENT = 204
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    CONFLICT = 409
    UNPROCESSABLE_ENTITY = 422
    INTERNAL_SERVER_ERROR = 500


# Assertion Helpers
def assert_response_status(
    response,
    expected_status: int,
    message: Optional[str] = None
) -> None:
    """
    Assert HTTP response status with detailed error message.

    Args:
        response: HTTP response object
        expected_status: Expected status code
        message: Optional additional context

    Raises:
        AssertionError: If status doesn't match
    """
    actual_status = response.status_code
    if actual_status != expected_status:
        error_msg = f"Expected status {expected_status}, got {actual_status}"
        if message:
            error_msg = f"{message}: {error_msg}"
        error_msg += f"\nResponse: {response.text[:200]}"
        raise AssertionError(error_msg)


def assert_response_has_fields(response, *fields: str) -> None:
    """
    Assert response JSON contains required fields.

    Args:
        response: HTTP response object
        *fields: Field names that must be present

    Raises:
        AssertionError: If any field is missing
    """
    data = response.json()
    missing = [f for f in fields if f not in data]
    if missing:
        raise AssertionError(f"Response missing fields: {missing}\nGot: {list(data.keys())}")


def assert_validation_error(response, expected_field: Optional[str] = None) -> None:
    """
    Assert response is a validation error (422) with optional field check.

    Args:
        response: HTTP response object
        expected_field: Optional field name that should be in error location

    Raises:
        AssertionError: If not a validation error or field mismatch
    """
    assert response.status_code == HTTP.UNPROCESSABLE_ENTITY, \
        f"Expected 422, got {response.status_code}: {response.text}"

    if expected_field:
        detail = response.json().get("detail", [])
        if isinstance(detail, list) and len(detail) > 0:
            locations = detail[0].get("loc", [])
            assert expected_field in str(locations), \
                f"Expected field '{expected_field}' in error location, got {locations}"
