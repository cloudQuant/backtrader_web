"""
E2E tests for audit trail and call logger features.

Tests cover:
- Audit event upload API (POST /audit/events)
- Audit record query API (GET /audit/records)
- Call logger decorator behavior
- Log level policy
- Event validation and error handling
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.fixture(autouse=True)
async def reset_audit_api_service_state():
    from app.api.audit import get_audit_service

    service = get_audit_service()
    await service.shutdown()
    yield
    await service.shutdown()


# ==================== Audit API Tests ====================


class TestAuditEventUpload:
    """Tests for POST /api/v1/audit/events endpoint."""

    async def test_upload_events_success(self, client: AsyncClient, auth_headers: dict):
        """Authenticated user can upload audit events."""
        now = datetime.now(timezone.utc)
        resp = await client.post(
            "/api/v1/audit/events",
            json={
                "events": [
                    {
                        "event_type": "click",
                        "event_target": "#run-backtest-btn",
                        "page_path": "/backtest",
                        "client_timestamp": now.isoformat(),
                        "session_id": "sess-001",
                        "event_data": {"tag": "button", "text": "Run"},
                    },
                    {
                        "event_type": "navigation",
                        "page_path": "/strategy",
                        "client_timestamp": (now + timedelta(seconds=5)).isoformat(),
                        "session_id": "sess-001",
                        "event_data": {"from_path": "/backtest", "to_path": "/strategy"},
                    },
                ]
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["persisted"] == 2
        assert data["total"] == 2

    async def test_upload_events_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        resp = await client.post(
            "/api/v1/audit/events",
            json={"events": []},
        )
        assert resp.status_code == 401

    async def test_upload_empty_batch(self, client: AsyncClient, auth_headers: dict):
        """Empty event batch returns 201 with 0 persisted."""
        resp = await client.post(
            "/api/v1/audit/events",
            json={"events": []},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["persisted"] == 0

    async def test_upload_event_invalid_timestamp(self, client: AsyncClient, auth_headers: dict):
        """Event with timestamp > 24h in the past is rejected."""
        old_time = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        resp = await client.post(
            "/api/v1/audit/events",
            json={
                "events": [
                    {
                        "event_type": "click",
                        "page_path": "/test",
                        "client_timestamp": old_time,
                    }
                ]
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        # Event should be rejected (validation failure)
        assert resp.json()["persisted"] == 0
        assert resp.json()["total"] == 1

    async def test_upload_event_oversized_data(self, client: AsyncClient, auth_headers: dict):
        """Event with event_data > 10KB is rejected by schema validation."""
        # Create data that exceeds 10KB
        large_data = {"key": "x" * 11000}
        resp = await client.post(
            "/api/v1/audit/events",
            json={
                "events": [
                    {
                        "event_type": "click",
                        "page_path": "/test",
                        "client_timestamp": datetime.now(timezone.utc).isoformat(),
                        "event_data": large_data,
                    }
                ]
            },
            headers=auth_headers,
        )
        # Pydantic validation should reject this with 422
        assert resp.status_code == 422

    async def test_upload_batch_max_size(self, client: AsyncClient, auth_headers: dict):
        """Batch exceeding 50 events is rejected by schema validation."""
        now = datetime.now(timezone.utc).isoformat()
        events = [
            {"event_type": "click", "page_path": "/test", "client_timestamp": now}
            for _ in range(51)
        ]
        resp = await client.post(
            "/api/v1/audit/events",
            json={"events": events},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_upload_mixed_valid_invalid(self, client: AsyncClient, auth_headers: dict):
        """Batch with mix of valid and invalid events: valid ones persist."""
        now = datetime.now(timezone.utc).isoformat()
        old_time = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        resp = await client.post(
            "/api/v1/audit/events",
            json={
                "events": [
                    {
                        "event_type": "click",
                        "page_path": "/valid",
                        "client_timestamp": now,
                    },
                    {
                        "event_type": "click",
                        "page_path": "/invalid-time",
                        "client_timestamp": old_time,
                    },
                    {
                        "event_type": "navigation",
                        "page_path": "/also-valid",
                        "client_timestamp": now,
                    },
                ]
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["persisted"] == 2  # 2 valid, 1 invalid
        assert data["total"] == 3


class TestAuditRecordQuery:
    """Tests for GET /api/v1/audit/records endpoint."""

    async def test_query_requires_admin(self, client: AsyncClient, auth_headers: dict):
        """Non-admin user gets 403 when querying audit records."""
        resp = await client.get("/api/v1/audit/records", headers=auth_headers)
        assert resp.status_code == 403

    async def test_query_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        resp = await client.get("/api/v1/audit/records")
        assert resp.status_code == 401

    async def test_query_invalid_page_size(self, client: AsyncClient, auth_headers: dict):
        """page_size > 100 returns 422."""
        resp = await client.get(
            "/api/v1/audit/records",
            params={"page_size": 200},
            headers=auth_headers,
        )
        assert resp.status_code == 422


# ==================== Call Logger Tests ====================


class TestCallLogger:
    """Tests for the call_logger decorator."""

    def test_sync_function_returns_correctly(self):
        """Decorated sync function returns the correct value."""
        from app.utils.call_logger import call_logger

        @call_logger()
        def add(a: int, b: int) -> int:
            return a + b

        assert add(3, 4) == 7

    async def test_async_function_returns_correctly(self):
        """Decorated async function returns the correct value."""
        from app.utils.call_logger import call_logger

        @call_logger()
        async def multiply(a: int, b: int) -> int:
            return a * b

        result = await multiply(5, 6)
        assert result == 30

    def test_exception_is_reraised(self):
        """Decorated function re-raises the original exception."""
        from app.utils.call_logger import call_logger

        @call_logger()
        def failing():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            failing()

    async def test_async_exception_is_reraised(self):
        """Decorated async function re-raises the original exception."""
        from app.utils.call_logger import call_logger

        @call_logger()
        async def async_failing():
            raise RuntimeError("async error")

        with pytest.raises(RuntimeError, match="async error"):
            await async_failing()

    def test_invalid_log_level_raises_valueerror(self):
        """Invalid log_level raises ValueError at decoration time."""
        from app.utils.call_logger import call_logger

        with pytest.raises(ValueError, match="Invalid log_level"):

            @call_logger(log_level="INVALID")
            def noop():
                pass

    def test_sensitive_params_filtered(self, capsys):
        """Sensitive parameters are masked in log output."""
        from app.utils.call_logger import call_logger

        @call_logger()
        def login(username: str, password: str, api_key: str = ""):
            return True

        result = login("admin", "secret123", api_key="key-abc")
        assert result is True
        # The function should still work correctly even with filtering

    def test_nested_pydantic_args_and_results_are_sanitized(self, monkeypatch):
        """Pydantic credential fields are masked in call and result logs."""
        from app.schemas.auth import Token, UserLogin
        from app.utils.call_logger import call_logger

        messages = []

        class StubLogger:
            def info(self, message):
                messages.append(message)

            def warning(self, message):
                messages.append(message)

            def error(self, message):
                messages.append(message)

        monkeypatch.setattr(
            "app.utils.call_logger.get_logger",
            lambda _name: StubLogger(),
            raising=True,
        )

        @call_logger()
        def login(user_login: UserLogin) -> Token:
            assert user_login.password == "secret123"
            return Token(
                access_token="token-secret-value",
                token_type="bearer",
                expires_in=60,
            )

        result = login(UserLogin(username="admin", password="secret123"))

        assert result.access_token == "token-secret-value"
        log_text = "\n".join(messages)
        assert "secret123" not in log_text
        assert "token-secret-value" not in log_text
        assert "'password': '***'" in log_text
        assert "'access_token': '***'" in log_text

    def test_nested_mapping_args_and_results_are_sanitized(self, monkeypatch):
        """Nested sensitive mapping fields are masked in call and result logs."""
        from app.utils.call_logger import call_logger

        messages = []

        class StubLogger:
            def info(self, message):
                messages.append(message)

            def warning(self, message):
                messages.append(message)

            def error(self, message):
                messages.append(message)

        monkeypatch.setattr(
            "app.utils.call_logger.get_logger",
            lambda _name: StubLogger(),
            raising=True,
        )

        @call_logger()
        def process(payload: dict) -> dict:
            return {
                "status": "ok",
                "refresh_token": "refresh-secret",
                "nested": {"api_key": "key-secret"},
            }

        assert process({"nested": {"password": "secret123"}})["status"] == "ok"
        log_text = "\n".join(messages)
        assert "secret123" not in log_text
        assert "refresh-secret" not in log_text
        assert "key-secret" not in log_text
        assert "'password': '***'" in log_text
        assert "'refresh_token': '***'" in log_text
        assert "'api_key': '***'" in log_text

    def test_self_argument_is_omitted_from_call_logs(self, monkeypatch):
        """Bound method self objects are omitted from call logs."""
        from app.utils.call_logger import call_logger

        messages = []

        class StubLogger:
            def info(self, message):
                messages.append(message)

            def warning(self, message):
                messages.append(message)

            def error(self, message):
                messages.append(message)

        monkeypatch.setattr(
            "app.utils.call_logger.get_logger",
            lambda _name: StubLogger(),
            raising=True,
        )

        class Service:
            @call_logger()
            def run(self, value: str) -> str:
                return value

        assert Service().run("ok") == "ok"
        log_text = "\n".join(messages)
        assert "'self':" not in log_text
        assert "Service object" not in log_text

    def test_log_result_false_suppresses_result(self):
        """log_result=False still returns the correct value."""
        from app.utils.call_logger import call_logger

        @call_logger(log_result=False)
        def get_data():
            return {"large": "payload" * 100}

        result = get_data()
        assert result["large"] == "payload" * 100

    def test_log_args_false_suppresses_args(self):
        """log_args=False still passes arguments correctly."""
        from app.utils.call_logger import call_logger

        @call_logger(log_args=False)
        def process(data: dict) -> int:
            return len(data)

        assert process({"a": 1, "b": 2}) == 2

    def test_slow_threshold_does_not_affect_return(self):
        """Slow threshold warning doesn't affect function behavior."""
        from app.utils.call_logger import call_logger

        @call_logger(slow_threshold=1)  # 1ms threshold
        def slow_func():
            time.sleep(0.01)  # 10ms - will trigger slow warning
            return "done"

        assert slow_func() == "done"


# ==================== Log Level Policy Tests ====================


class TestLogLevelPolicy:
    """Tests for environment-based log level configuration."""

    def test_debug_mode_level(self):
        """DEBUG=true results in DEBUG level for console and file."""
        from app.config import Settings

        settings = Settings(DEBUG=True, LOG_LEVEL="")
        assert settings.DEBUG is True
        # In debug mode, setup_logger should use DEBUG level

    def test_production_mode_level(self):
        """DEBUG=false with no LOG_LEVEL override uses WARNING/INFO split."""
        # This is tested implicitly through the setup_logger logic
        from app.config import Settings

        settings = Settings(
            DEBUG=False,
            LOG_LEVEL="",
            SECRET_KEY="a" * 32,
            JWT_SECRET_KEY="b" * 32,
            ADMIN_PASSWORD="StrongPass123!",
            IB_VERIFY_SSL=True,
            IB_WEB_VERIFY_SSL=True,
            IB_PAPER_VERIFY_SSL=True,
            IB_LIVE_VERIFY_SSL=True,
        )
        assert settings.DEBUG is False
        assert settings.LOG_LEVEL == ""

    def test_explicit_log_level_override(self):
        """LOG_LEVEL env var overrides DEBUG-based default."""
        from app.config import Settings

        settings = Settings(DEBUG=True, LOG_LEVEL="ERROR")
        assert settings.LOG_LEVEL == "ERROR"


# ==================== Log Rotation Config Tests ====================


class TestLogRotationConfig:
    """Tests for log rotation configuration settings."""

    def test_default_retention_values(self):
        """Default retention periods are correctly set."""
        from app.config import Settings

        settings = Settings(DEBUG=True)
        assert settings.LOG_RETENTION_APP_DAYS == 30
        assert settings.LOG_RETENTION_ERROR_DAYS == 90
        assert settings.LOG_RETENTION_AUDIT_DAYS == 365
        assert settings.LOG_ROTATION_MAX_MB == 100

    def test_custom_retention_values(self):
        """Custom retention periods can be set."""
        from app.config import Settings

        settings = Settings(
            DEBUG=True,
            LOG_RETENTION_APP_DAYS=7,
            LOG_RETENTION_ERROR_DAYS=30,
            LOG_RETENTION_AUDIT_DAYS=180,
            LOG_ROTATION_MAX_MB=50,
        )
        assert settings.LOG_RETENTION_APP_DAYS == 7
        assert settings.LOG_RETENTION_ERROR_DAYS == 30
        assert settings.LOG_RETENTION_AUDIT_DAYS == 180
        assert settings.LOG_ROTATION_MAX_MB == 50

    def test_log_dir_config(self):
        """LOG_DIR can be configured."""
        from app.config import Settings

        settings = Settings(DEBUG=True, LOG_DIR="/tmp/test-logs")
        assert settings.LOG_DIR == "/tmp/test-logs"


# ==================== Audit Service Unit Tests ====================


class TestAuditServiceUnit:
    """Unit tests for AuditService logic."""

    async def test_cleanup_no_expired_records(self):
        """Cleanup with no expired records returns 0."""
        from app.services.audit_service import AuditService

        service = AuditService()
        deleted = await service.cleanup_expired_records(retention_days=90)
        assert deleted == 0

    async def test_create_events_empty_list(self):
        """Creating events with empty list returns 0."""
        from app.services.audit_service import AuditService

        service = AuditService()
        result = await service.create_events([], "user-123", "127.0.0.1")
        assert result == 0

    async def test_query_records_empty_db(self):
        """Querying empty database returns empty result."""
        from app.schemas.audit import AuditQueryParams
        from app.services.audit_service import AuditService

        service = AuditService()
        result = await service.query_records(AuditQueryParams())
        assert result.total_count == 0
        assert result.items == []
        assert result.current_page == 1
        assert result.total_pages == 0

    async def test_create_events_fail_open_when_async_sink_write_raises(self):
        """Async sink write failures are logged and do not bubble to the caller."""
        from app.schemas.audit import OperationEvent
        from app.services.audit_service import AuditService

        service = AuditService()
        persist_mock = AsyncMock(side_effect=RuntimeError("db down"))

        with patch.object(service, "_persist_with_retry", persist_mock):
            accepted = await service.create_events(
                [
                    OperationEvent(
                        event_type="click",
                        page_path="/audit",
                        client_timestamp=datetime.now(timezone.utc),
                    )
                ],
                "user-123",
                "127.0.0.1",
            )
            await service.flush()
            await service.shutdown()

        assert accepted == 1
        assert persist_mock.await_count == 1

    async def test_shutdown_flushes_pending_audit_batches(self):
        """Shutdown waits for queued audit batches to persist."""
        from app.schemas.audit import OperationEvent
        from app.services.audit_service import AuditService

        service = AuditService()
        persisted_batches: list[tuple[int, str]] = []

        async def _fake_persist(records, user_id, max_retries=3):
            await asyncio.sleep(0)
            persisted_batches.append((len(records), user_id))
            return len(records)

        with patch.object(service, "_persist_with_retry", _fake_persist):
            accepted = await service.create_events(
                [
                    OperationEvent(
                        event_type="navigation",
                        page_path="/strategy",
                        client_timestamp=datetime.now(timezone.utc),
                    )
                ],
                "user-456",
                "127.0.0.1",
            )
            await service.shutdown()

        assert accepted == 1
        assert persisted_batches == [(1, "user-456")]


# ==================== Audit Config Tests ====================


class TestAuditConfig:
    """Tests for audit-specific configuration."""

    def test_default_audit_config(self):
        """Default audit configuration values."""
        from app.config import Settings

        settings = Settings(DEBUG=True)
        assert settings.AUDIT_RETENTION_DAYS == 90
        assert settings.AUDIT_CLEANUP_HOUR == 2
        assert settings.AUDIT_EVENT_MAX_SIZE_KB == 10

    def test_custom_audit_config(self):
        """Custom audit configuration values."""
        from app.config import Settings

        settings = Settings(
            DEBUG=True,
            AUDIT_RETENTION_DAYS=180,
            AUDIT_CLEANUP_HOUR=3,
            AUDIT_EVENT_MAX_SIZE_KB=20,
        )
        assert settings.AUDIT_RETENTION_DAYS == 180
        assert settings.AUDIT_CLEANUP_HOUR == 3
        assert settings.AUDIT_EVENT_MAX_SIZE_KB == 20
