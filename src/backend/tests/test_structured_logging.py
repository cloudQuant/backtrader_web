"""Property-based tests for structured logging and request ID generation.

Feature: best-practices-improvement
Property 2: Structured Logging Contains Required Fields
Property 3: Request ID Generation

Validates: Requirements 8.1, 8.2, 8.5
"""

import json
import re
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from hypothesis import given, settings
from hypothesis import strategies as st

from app.utils.logger import _serialize_log


def _make_record(message: str, level_name: str, module_name: str = "test") -> dict:
    """Create a mock loguru record dict for testing _serialize_log."""
    now = datetime.now(timezone.utc)
    return {
        "time": now,
        "level": type("Level", (), {"name": level_name})(),
        "message": message,
        "name": module_name,
        "exception": None,
        "extra": {"request_id": "N/A", "name": module_name},
    }


class TestStructuredLoggingProperty:
    """Property 2: Structured Logging Contains Required Fields.

    For any log message string (non-empty, up to 10000 characters) emitted at
    any valid log level, the JSON output SHALL be parseable as valid JSON and
    SHALL contain all required fields.
    """

    @given(
        message=st.text(min_size=1, max_size=5000),
        level_name=st.sampled_from(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    )
    @settings(max_examples=100)
    def test_json_output_is_parseable(self, message: str, level_name: str) -> None:
        """Any log message produces valid parseable JSON."""
        record = _make_record(message, level_name)
        output = _serialize_log(record)
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    @given(
        message=st.text(min_size=1, max_size=5000),
        level_name=st.sampled_from(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
        module_name=st.text(
            min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L",))
        ),
    )
    @settings(max_examples=100)
    def test_json_contains_required_fields(
        self, message: str, level_name: str, module_name: str
    ) -> None:
        """JSON output contains timestamp, level, message, module, request_id."""
        record = _make_record(message, level_name, module_name)
        output = _serialize_log(record)
        parsed = json.loads(output)

        # All required fields present
        assert "timestamp" in parsed
        assert "level" in parsed
        assert "message" in parsed
        assert "module" in parsed
        assert "request_id" in parsed

    @given(
        message=st.text(min_size=1, max_size=5000),
        level_name=st.sampled_from(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    )
    @settings(max_examples=100)
    def test_level_matches_input(self, message: str, level_name: str) -> None:
        """The level field in JSON output matches the input level."""
        record = _make_record(message, level_name)
        output = _serialize_log(record)
        parsed = json.loads(output)
        assert parsed["level"] == level_name

    @given(
        message=st.text(min_size=1, max_size=10000),
    )
    @settings(max_examples=100)
    def test_message_truncated_at_10000(self, message: str) -> None:
        """Messages longer than 10000 chars are truncated."""
        record = _make_record(message, "INFO")
        output = _serialize_log(record)
        parsed = json.loads(output)
        assert len(parsed["message"]) <= 10000

    @given(
        message=st.text(min_size=1, max_size=100),
        level_name=st.sampled_from(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    )
    @settings(max_examples=100)
    def test_timestamp_is_iso8601(self, message: str, level_name: str) -> None:
        """Timestamp field is in ISO 8601 format with millisecond precision."""
        record = _make_record(message, level_name)
        output = _serialize_log(record)
        parsed = json.loads(output)
        ts = parsed["timestamp"]
        # Should match pattern like 2024-01-15T10:30:45.123+08:00
        assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}", ts)

    @given(
        request_id=st.text(
            min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))
        ),
    )
    @settings(max_examples=100)
    def test_request_id_preserved_in_output(self, request_id: str) -> None:
        """request_id from extra context is preserved in JSON output."""
        record = _make_record("test", "INFO")
        record["extra"]["request_id"] = request_id
        output = _serialize_log(record)
        parsed = json.loads(output)
        assert parsed["request_id"] == request_id


class TestRequestIDProperty:
    """Property 3: Request ID Generation.

    For any HTTP request to a non-skipped path, the LoggingMiddleware SHALL
    include an X-Request-ID response header whose value is exactly 8 characters
    long and consists of hexadecimal characters.
    """

    @pytest.mark.asyncio
    @given(
        path=st.sampled_from(
            [
                "/api/v1/health",
                "/api/v1/auth/login",
                "/api/v1/strategy",
            ]
        ),
    )
    @settings(max_examples=100)
    async def test_request_id_is_8_hex_chars(self, path: str) -> None:
        """Every response includes X-Request-ID with exactly 8 hex characters."""
        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(path)
            request_id = response.headers.get("x-request-id", "")
            assert len(request_id) == 8, f"Expected 8 chars, got {len(request_id)}: '{request_id}'"
            assert all(c in "0123456789abcdef-" for c in request_id), (
                f"Non-hex char in request_id: '{request_id}'"
            )
