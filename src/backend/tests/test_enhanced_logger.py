"""
Enhanced logging system tests.

Tests:
- Sensitive data filtering
- Log context management
- Request context binding
- Task context binding
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.utils.logger import (
    setup_logger,
    get_logger,
    _filter_sensitive_data,
    LogLevel,
    LogContext,
    bind_request_context,
    bind_task_context,
)


class TestSensitiveDataFiltering:
    """Tests for sensitive data filtering in logs."""

    def test_filter_password(self):
        """Test password filtering."""
        data = {"username": "testuser", "password": "secret123"}
        filtered = _filter_sensitive_data(data)
        assert filtered["username"] == "testuser"
        # Passwords longer than 4 chars get partial masking
        assert "****" in filtered["password"]

    def test_filter_api_key(self):
        """Test API key filtering."""
        data = {"api_key": "sk-1234567890abcdef"}
        filtered = _filter_sensitive_data(data)
        # API key gets masked
        assert "****" in filtered["api_key"]

    def test_filter_nested_dict(self):
        """Test filtering in nested dictionaries."""
        data = {
            "user": "john",
            "credentials": {
                "password": "secret",
                "token": "abc123"
            }
        }
        filtered = _filter_sensitive_data(data)
        assert filtered["user"] == "john"
        # 'credentials' key contains 'credential' pattern, so entire nested dict is masked
        # This is intentional security behavior - don't log credential dictionaries at all
        assert filtered["credentials"] == "****"

    def test_filter_nested_dict_safe_keys(self):
        """Test filtering with safe nested keys."""
        data = {
            "user": "john",
            "config": {
                "password": "secret123",
                "api_url": "https://api.example.com"
            }
        }
        filtered = _filter_sensitive_data(data)
        assert filtered["user"] == "john"
        assert filtered["config"]["api_url"] == "https://api.example.com"
        # password within safe nested key gets filtered
        assert "****" in filtered["config"]["password"]

    def test_filter_list_of_dicts(self):
        """Test filtering in list of dictionaries."""
        data = {
            "users": [
                {"name": "Alice", "secret": "pass1"},
                {"name": "Bob", "secret": "pass2"}
            ]
        }
        filtered = _filter_sensitive_data(data)
        assert filtered["users"][0]["name"] == "Alice"
        # Secret values longer than 4 chars get partial masking
        assert "****" in filtered["users"][0]["secret"]

    def test_no_filter_for_safe_data(self):
        """Test that safe data is not filtered."""
        data = {"name": "test", "value": 123, "active": True}
        filtered = _filter_sensitive_data(data)
        assert filtered == data

    def test_short_secret_masking(self):
        """Test masking of short secret values."""
        data = {"secret": "ab"}
        filtered = _filter_sensitive_data(data)
        assert filtered["secret"] == "****"


class TestSetupLogger:
    """Tests for logger setup."""

    def test_setup_logger_returns_logger(self, tmp_path: Path):
        """Test that setup_logger returns a logger instance."""
        with patch("app.utils.logger.get_settings") as mock_settings:
            settings = MagicMock()
            settings.DEBUG = False
            mock_settings.return_value = settings

            result = setup_logger(log_dir=str(tmp_path / "logs"))
            assert result is not None

    def test_setup_logger_creates_log_directory(self, tmp_path: Path):
        """Test that setup_logger creates log directory."""
        log_dir = tmp_path / "logs"
        assert not log_dir.exists()

        with patch("app.utils.logger.get_settings") as mock_settings:
            settings = MagicMock()
            settings.DEBUG = False
            mock_settings.return_value = settings

            setup_logger(log_dir=str(log_dir))
            assert log_dir.exists()
            assert log_dir.is_dir()


class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger_with_name(self):
        """Test getting logger with name."""
        logger = get_logger("test.module")
        assert logger is not None

    def test_get_logger_without_name(self):
        """Test getting logger without name."""
        logger = get_logger()
        assert logger is not None


class TestLogContext:
    """Tests for LogContext context manager."""

    def test_context_manager_binds_variables(self):
        """Test that LogContext binds variables to logger."""
        with LogContext(request_id="req-123", user_id="user-456") as ctx:
            assert ctx is not None
            assert ctx.context == {"request_id": "req-123", "user_id": "user-456"}

    def test_context_manager_exit(self):
        """Test that LogContext exits cleanly."""
        with LogContext(test="value"):
            pass
        # Should not raise any exception


class TestBindRequestContext:
    """Tests for bind_request_context function."""

    def test_bind_request_context_basic(self):
        """Test binding basic request context."""
        logger = bind_request_context("req-123")
        assert logger is not None

    def test_bind_request_context_with_user(self):
        """Test binding request context with user ID."""
        logger = bind_request_context("req-123", user_id="user-456")
        assert logger is not None

    def test_bind_request_context_with_extra(self):
        """Test binding request context with extra fields."""
        logger = bind_request_context("req-123", action="test", resource="data")
        assert logger is not None


class TestBindTaskContext:
    """Tests for bind_task_context function."""

    def test_bind_task_context_basic(self):
        """Test binding basic task context."""
        logger = bind_task_context("task-123")
        assert logger is not None

    def test_bind_task_context_with_user(self):
        """Test binding task context with user ID."""
        logger = bind_task_context("task-123", user_id="user-456")
        assert logger is not None

    def test_bind_task_context_with_type(self):
        """Test binding task context with task type."""
        logger = bind_task_context("task-123", task_type="backtest")
        assert logger is not None


class TestLogLevel:
    """Tests for LogLevel enum."""

    def test_log_level_values(self):
        """Test log level enum values."""
        assert LogLevel.DEBUG == "DEBUG"
        assert LogLevel.INFO == "INFO"
        assert LogLevel.WARNING == "WARNING"
        assert LogLevel.ERROR == "ERROR"
        assert LogLevel.CRITICAL == "CRITICAL"


class TestAuditLogger:
    """Tests for AuditLogger class (without actual logging)."""

    def test_audit_logger_initialization(self):
        """Test audit logger can be initialized."""
        from app.utils.logger import AuditLogger
        audit = AuditLogger()
        assert audit.logger is not None

    def test_audit_logger_has_required_methods(self):
        """Test audit logger has required methods."""
        from app.utils.logger import AuditLogger
        audit = AuditLogger()
        assert hasattr(audit, "log_login")
        assert hasattr(audit, "log_logout")
        assert hasattr(audit, "log_permission_denied")
        assert hasattr(audit, "log_strategy_access")
        assert hasattr(audit, "log_backtest_start")
        assert hasattr(audit, "log_backtest_complete")


class TestLoggingMiddleware:
    """Tests for logging middleware (without actual request processing)."""

    def test_logging_middleware_initialization(self):
        """Test logging middleware can be initialized."""
        from app.middleware.logging import LoggingMiddleware

        async def app(scope, receive, send):
            pass

        middleware = LoggingMiddleware(app)
        assert middleware.log_body is False
        assert middleware.log_headers is False
        assert "/health" in middleware.skip_paths

    def test_audit_logging_middleware_initialization(self):
        """Test audit logging middleware can be initialized."""
        from app.middleware.logging import AuditLoggingMiddleware

        async def app(scope, receive, send):
            pass

        middleware = AuditLoggingMiddleware(app)
        assert middleware.audit_logger is not None

    def test_performance_logging_middleware_initialization(self):
        """Test performance logging middleware can be initialized."""
        from app.middleware.logging import PerformanceLoggingMiddleware

        async def app(scope, receive, send):
            pass

        middleware = PerformanceLoggingMiddleware(app)
        assert middleware.slow_request_threshold == 5.0
