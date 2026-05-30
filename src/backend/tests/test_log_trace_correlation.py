"""Tests for iteration 176 §H — logs↔traces correlation.

The structured JSON log serializer must stamp the active OpenTelemetry
``trace_id`` / ``span_id`` onto each line when (and only when) there is a valid
recording span in context. When OTel is disabled the fields must be absent and
the serializer must not raise.
"""

import json
from datetime import datetime, timezone
from unittest.mock import patch

from app.utils import logger as logger_mod
from app.utils.logger import _get_trace_context, _serialize_log


def _make_record(message: str = "hello", level_name: str = "INFO") -> dict:
    now = datetime.now(timezone.utc)
    return {
        "time": now,
        "level": type("Level", (), {"name": level_name})(),
        "message": message,
        "name": "test",
        "exception": None,
        "extra": {"request_id": "N/A", "name": "test"},
    }


class TestGetTraceContext:
    def test_empty_when_no_span(self):
        # No active span in a bare test context → empty dict, no exception.
        ctx = _get_trace_context()
        assert ctx == {} or set(ctx) == {"trace_id", "span_id"}

    def test_empty_on_invalid_span_context(self):
        fake_ctx = type("Ctx", (), {"is_valid": False, "trace_id": 0, "span_id": 0})()
        fake_span = type("Span", (), {"get_span_context": lambda self: fake_ctx})()
        with patch("opentelemetry.trace.get_current_span", return_value=fake_span):
            assert _get_trace_context() == {}

    def test_formats_ids_as_hex_when_valid(self):
        fake_ctx = type(
            "Ctx",
            (),
            {"is_valid": True, "trace_id": 0x1234, "span_id": 0xABCD},
        )()
        fake_span = type("Span", (), {"get_span_context": lambda self: fake_ctx})()
        with patch("opentelemetry.trace.get_current_span", return_value=fake_span):
            ctx = _get_trace_context()
        assert ctx["trace_id"] == format(0x1234, "032x")
        assert ctx["span_id"] == format(0xABCD, "016x")
        assert len(ctx["trace_id"]) == 32
        assert len(ctx["span_id"]) == 16

    def test_swallows_exceptions(self):
        with patch("opentelemetry.trace.get_current_span", side_effect=RuntimeError("boom")):
            assert _get_trace_context() == {}


class TestSerializerCorrelation:
    def test_no_trace_fields_when_context_empty(self):
        with patch.object(logger_mod, "_get_trace_context", return_value={}):
            out = json.loads(_serialize_log(_make_record()))
        assert "trace_id" not in out
        assert "span_id" not in out

    def test_trace_fields_present_when_context_available(self):
        fake = {"trace_id": "a" * 32, "span_id": "b" * 16}
        with patch.object(logger_mod, "_get_trace_context", return_value=fake):
            out = json.loads(_serialize_log(_make_record()))
        assert out["trace_id"] == "a" * 32
        assert out["span_id"] == "b" * 16
        # correlation fields must not clobber the existing required fields
        assert out["level"] == "INFO"
        assert out["message"] == "hello"

    def test_serializer_does_not_raise_without_otel(self):
        # Default path (no span). Must produce valid parseable JSON.
        out = json.loads(_serialize_log(_make_record("plain", "WARNING")))
        assert out["level"] == "WARNING"
