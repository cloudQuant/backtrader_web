"""OTel ``business_span`` overhead benchmark (REFACTORING_BACKLOG.md §F).

175 deferred the OTel ON/OFF performance comparison because no equivalent
perf baseline existed. The perf baseline now exists (this directory), so this
module establishes the ON-vs-OFF overhead comparison the backlog asked for.

Strategy:
- Measure the per-call cost of ``business_span`` in both modes by toggling the
  ``OTEL_ENABLED`` env var that ``tracing._otel_enabled()`` reads.
- Assert two things:
    1. The OFF path is genuinely near-zero (no-op ``nullcontext``).
    2. The ON path's per-call cost stays within an absolute ceiling, so a
       regression that makes spans expensive (e.g. accidental exporter flush
       on the hot path) is caught.

We use wall-clock micro-timing rather than pytest-benchmark's statistical
machinery so the test is deterministic and dependency-light; the absolute
ceilings are generous (microseconds) to avoid CI flakiness while still
catching order-of-magnitude regressions.
"""

from __future__ import annotations

import importlib
import os
import time
from collections.abc import Iterator

import pytest

pytestmark = pytest.mark.performance

_ITERATIONS = 5000


def _time_business_span(enabled: bool) -> float:
    """Return mean seconds per ``business_span`` enter/exit for the given mode.

    Reloads the tracing module under the desired ``OTEL_ENABLED`` value so the
    module-level tracer/state matches the mode under test.
    """
    prev = os.environ.get("OTEL_ENABLED")
    os.environ["OTEL_ENABLED"] = "true" if enabled else "false"
    try:
        import app.utils.tracing as tracing

        tracing = importlib.reload(tracing)
        assert tracing._otel_enabled() is enabled

        business_span = tracing.business_span

        # Warm up (import-time lazy initialisation, tracer provider, etc.)
        for _ in range(100):
            with business_span("backtrader.backtest.execute", symbol="000001.SZ"):
                pass

        start = time.perf_counter()
        for _ in range(_ITERATIONS):
            with business_span("backtrader.backtest.execute", symbol="000001.SZ"):
                pass
        elapsed = time.perf_counter() - start
        return elapsed / _ITERATIONS
    finally:
        if prev is None:
            os.environ.pop("OTEL_ENABLED", None)
        else:
            os.environ["OTEL_ENABLED"] = prev
        # Restore module to the ambient env state for other tests.
        import app.utils.tracing as tracing

        importlib.reload(tracing)


@pytest.fixture(autouse=True)
def _restore_tracing_module() -> Iterator[None]:
    """Ensure the tracing module is reloaded to ambient state after each test."""
    yield
    import app.utils.tracing as tracing

    importlib.reload(tracing)


def test_business_span_off_is_near_zero() -> None:
    """When OTel is disabled the span must be a cheap no-op."""
    per_call = _time_business_span(enabled=False)
    # No-op nullcontext should be well under 5µs/call even on slow CI.
    assert per_call < 5e-6, f"OTel-OFF business_span too slow: {per_call * 1e6:.2f}µs/call"


def test_business_span_on_overhead_bounded() -> None:
    """When OTel is enabled the span overhead must stay bounded (no hot-path export)."""
    per_call = _time_business_span(enabled=True)
    # A real (default no-export) span should be on the order of single-digit µs.
    # Ceiling of 200µs/call catches accidental synchronous exporter flushes
    # (which would be milliseconds) without being flaky on shared CI runners.
    assert per_call < 2e-4, f"OTel-ON business_span overhead too high: {per_call * 1e6:.2f}µs/call"


def test_otel_on_off_relative_overhead() -> None:
    """The absolute ON-vs-OFF delta per call must stay within a small budget.

    This is the §F "ON/OFF comparison" gate: enabling tracing must not add more
    than a small fixed cost per business span on the hot path.
    """
    off = _time_business_span(enabled=False)
    on = _time_business_span(enabled=True)
    delta = on - off
    # Enabling tracing should add < 200µs/span. Expressed as an absolute budget
    # because the OFF baseline is near-zero, making a ratio meaningless.
    assert delta < 2e-4, (
        f"OTel ON adds too much per span: off={off * 1e6:.2f}µs "
        f"on={on * 1e6:.2f}µs delta={delta * 1e6:.2f}µs"
    )
