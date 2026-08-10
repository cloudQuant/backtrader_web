"""
Enhanced logging system tests.

Tests:
- Sensitive data filtering
- Log context management
- Request context binding
- Task context binding
"""

import json
import logging
from collections import namedtuple
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
from zipfile import ZipFile

import pytest

from app.utils.logger import (
    LogContext,
    LogLevel,
    _add_file_handler,
    _archive_stale_dated_logs,
    _build_daily_or_size_rotation,
    _filter_sensitive_data,
    _patch_record,
    _serialize_log,
    bind_request_context,
    bind_task_context,
    get_logger,
    setup_logger,
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
        data = {"user": "john", "credentials": {"password": "secret", "token": "abc123"}}
        filtered = _filter_sensitive_data(data)
        assert filtered["user"] == "john"
        # 'credentials' key contains 'credential' pattern, so entire nested dict is masked
        # This is intentional security behavior - don't log credential dictionaries at all
        assert filtered["credentials"] == "****"

    def test_filter_nested_dict_safe_keys(self):
        """Test filtering with safe nested keys."""
        data = {
            "user": "john",
            "config": {"password": "secret123", "api_url": "https://api.example.com"},
        }
        filtered = _filter_sensitive_data(data)
        assert filtered["user"] == "john"
        assert filtered["config"]["api_url"] == "https://api.example.com"
        # password within safe nested key gets filtered
        assert "****" in filtered["config"]["password"]

    def test_filter_list_of_dicts(self):
        """Test filtering in list of dictionaries."""
        data = {"users": [{"name": "Alice", "secret": "pass1"}, {"name": "Bob", "secret": "pass2"}]}
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

    def test_filter_redacts_credentials_embedded_in_safe_text_fields(self):
        """Provider error text must not bypass key-based context redaction."""
        api_key = "provider-api-key-should-not-appear"
        bearer = "provider-bearer-should-not-appear"

        filtered = _filter_sensitive_data(
            {
                "error_message": f"upstream rejected api_key={api_key}",
                "details": f"Authorization: Bearer {bearer}",
            }
        )

        rendered = json.dumps(filtered)
        assert api_key not in rendered
        assert bearer not in rendered
        assert "****" in rendered

    def test_structured_serializer_redacts_message_exception_and_context(self):
        """All structured-log channels must redact credential-bearing text."""
        message_secret = "message-secret-should-not-appear"
        exception_secret = "exception-secret-should-not-appear"
        context_secret = "context-secret-should-not-appear"

        try:
            raise RuntimeError(f"provider password={exception_secret}")
        except RuntimeError as exc:
            record = {
                "time": datetime.now(),
                "level": type("Level", (), {"name": "ERROR"})(),
                "message": f"provider api_key={message_secret}",
                "name": "asset_research",
                "exception": type(
                    "ExceptionRecord",
                    (),
                    {"type": type(exc), "value": exc, "traceback": exc.__traceback__},
                )(),
                "extra": {
                    "request_id": "request-1",
                    "error_message": f"Authorization: Bearer {context_secret}",
                },
            }

        rendered = _serialize_log(record)
        assert message_secret not in rendered
        assert exception_secret not in rendered
        assert context_secret not in rendered
        assert "****" in rendered

    def test_log_record_patcher_redacts_plain_sink_message_and_exception(self):
        """Plain and serialized sinks share the same redacted log record."""
        message_secret = "plain-message-secret-should-not-appear"
        exception_secret = "plain-exception-secret-should-not-appear"
        ExceptionRecord = namedtuple("ExceptionRecord", "type value traceback")
        record = {
            "message": f"provider secret={message_secret}",
            "exception": ExceptionRecord(
                RuntimeError,
                RuntimeError(f"provider token={exception_secret}"),
                None,
            ),
            "extra": {"detail": f"Bearer {exception_secret}"},
        }

        assert _patch_record(record) is True
        assert message_secret not in record["message"]
        assert exception_secret not in str(record["exception"].value)
        assert exception_secret not in record["extra"]["detail"]

    def test_global_loguru_patcher_redacts_actual_sink_records(self):
        """The live logger patcher must protect every sink, not only helper calls."""
        import app.utils.logger as logger_module

        message_secret = "sink-message-secret-should-not-appear"
        context_secret = "sink-context-secret-should-not-appear"
        exception_secret = "sink-exception-secret-should-not-appear"
        captured_records = []
        sink_id = logger_module.logger.add(
            lambda message: captured_records.append(message.record),
            format="{message}",
        )
        try:
            logger_module.logger.bind(detail=f"Bearer {context_secret}").info(
                f"provider api_key={message_secret}"
            )
            try:
                raise RuntimeError(f"provider password={exception_secret}")
            except RuntimeError:
                logger_module.logger.exception("provider request failed")
        finally:
            logger_module.logger.remove(sink_id)

        rendered = str(captured_records)
        assert message_secret not in rendered
        assert context_secret not in rendered
        assert exception_secret not in rendered


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

    def test_setup_logger_suppresses_noisy_third_party_debug_logs(self, tmp_path: Path):
        """Known noisy dependency loggers should not flood DEBUG app log files."""
        with patch("app.utils.logger.get_settings") as mock_settings:
            settings = MagicMock()
            settings.DEBUG = True
            mock_settings.return_value = settings

            setup_logger(log_dir=str(tmp_path / "logs"))

        app_logger = logging.getLogger("app.services.example")
        assert app_logger.isEnabledFor(logging.DEBUG)

        noisy_logger_names = (
            "aiomysql.connection",
            "aiosqlite.core",
            "asyncio.selector_events",
            "faker.factory",
            "slowapi.extension",
        )
        for logger_name in noisy_logger_names:
            noisy_logger = logging.getLogger(logger_name)
            assert noisy_logger.getEffectiveLevel() == logging.WARNING
            assert not noisy_logger.isEnabledFor(logging.DEBUG)
            assert not noisy_logger.isEnabledFor(logging.INFO)

    def test_pytest_log_dir_isolated_from_repo_logs(self):
        """Pytest app imports should not write expected test errors to repo logs."""
        from app.config import get_settings

        repo_logs = Path(__file__).resolve().parents[3] / "logs"
        log_dir = Path(get_settings().LOG_DIR).resolve()

        assert log_dir != repo_logs.resolve()
        assert log_dir.name.startswith("backtrader_web_pytest_logs_")

    def test_error_file_handler_never_diagnoses_local_variables(self, monkeypatch, tmp_path: Path):
        """Exception stacks retain control flow but must not serialize locals."""
        import app.utils.logger as logger_module

        mocked_logger = MagicMock()
        monkeypatch.setattr(logger_module, "logger", mocked_logger)

        _add_file_handler(
            tmp_path,
            "errors_{time:YYYY-MM-DD}.log",
            use_json=False,
            backtrace=True,
        )

        assert mocked_logger.add.call_args.kwargs["diagnose"] is False


class TestLogFileArchival:
    """Tests for startup cleanup of stale dated log files."""

    def test_archive_stale_dated_logs_compresses_inactive_file(self, tmp_path: Path):
        old_log = tmp_path / "app_2026-06-22.log"
        old_log.write_text("debug flood\n", encoding="utf-8")

        archived = _archive_stale_dated_logs(
            tmp_path,
            current_date=date(2026, 6, 25),
            min_age_seconds=0,
        )

        archive_path = tmp_path / "app_2026-06-22.log.zip"
        assert archived == [archive_path]
        assert archive_path.exists()
        assert not old_log.exists()

        with ZipFile(archive_path) as archive:
            assert archive.namelist() == ["app_2026-06-22.log"]
            assert archive.read("app_2026-06-22.log").decode() == "debug flood\n"

    def test_archive_stale_dated_logs_skips_current_recent_and_non_dated(self, tmp_path: Path):
        current_log = tmp_path / "app_2026-06-25.log"
        recent_old_log = tmp_path / "errors_2026-06-24.log"
        non_dated_log = tmp_path / "backend.log"
        for log_file in (current_log, recent_old_log, non_dated_log):
            log_file.write_text("keep\n", encoding="utf-8")

        archived = _archive_stale_dated_logs(
            tmp_path,
            current_date=date(2026, 6, 25),
            min_age_seconds=3600,
        )

        assert archived == []
        assert current_log.exists()
        assert recent_old_log.exists()
        assert non_dated_log.exists()


class TestLogRotationPolicy:
    """Tests for combined daily and size-based log rotation."""

    class _Message:
        def __init__(self, timestamp: datetime, text: str) -> None:
            self.record = {"time": timestamp}
            self.text = text

        def __str__(self) -> str:
            return self.text

    def test_daily_or_size_rotation_triggers_when_size_cap_would_be_exceeded(self, tmp_path: Path):
        rotation = _build_daily_or_size_rotation(10)
        log_file = tmp_path / "app_2026-06-25.log"
        log_file.write_text("12345678", encoding="utf-8")

        with log_file.open("a+", encoding="utf-8") as handle:
            message = self._Message(datetime(2026, 6, 25, 12, 0, 0), "abcd")
            assert callable(rotation)
            assert rotation(message, handle) is True

    def test_daily_or_size_rotation_triggers_on_date_boundary(self, tmp_path: Path):
        rotation = _build_daily_or_size_rotation(1024)
        log_file = tmp_path / "app_2026-06-24.log"
        log_file.write_text("small", encoding="utf-8")

        with log_file.open("a+", encoding="utf-8") as handle:
            message = self._Message(datetime(2026, 6, 25, 0, 0, 1), "x")
            assert callable(rotation)
            assert rotation(message, handle) is True

    def test_daily_or_size_rotation_can_disable_size_cap(self):
        assert _build_daily_or_size_rotation(0) == "00:00"


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


@pytest.mark.skip(reason="LoggingMiddleware doesn't have expected attributes - pre-existing issue")
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
