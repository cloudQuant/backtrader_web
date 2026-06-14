"""Business-span helpers for Iteration 175 §5 OTel coverage.

This module wraps :mod:`opentelemetry.trace` so service-layer code can create
spans with consistent naming conventions and business attributes without
worrying about whether OTel itself is enabled.

Usage::

    from app.utils.tracing import business_span

    async def create_backtest(self, user_id: int, payload: ...) -> Backtest:
        with business_span(
            "backtrader.backtest.create",
            user_id=user_id,
        ):
            # core implementation
            return bt

The span name namespace is one of:

  * ``backtrader.backtest.<phase>``   — phase ∈ {create, submit, execute, collect, finalize}
  * ``backtrader.strategy.<phase>``   — phase ∈ {submit, version_create}
  * ``backtrader.ai.<phase>``         — phase ∈ {intent_parse, llm_call, response_format}
  * ``backtrader.live.<phase>``       — phase ∈ {place_order, cancel_order, on_fill}

Business attributes are written under the ``bt.`` prefix so they can be
filtered uniformly in Jaeger/Tempo. The helper supports any combination of
``user_id`` / ``strategy_id`` / ``backtest_id`` / ``symbol`` / ``order_id``;
unknown keys are passed through prefixed with ``bt.``.

Iteration 175 §5.10 — exceptions raised inside the ``with`` block are caught
just long enough to mark the span as ERROR and call ``record_exception``,
then re-raised. The span lifetime is closed by the context manager regardless
of error path (Property 3 — span completeness).

Iteration 175 §5.11 — when OTel is disabled the helper degrades to a true
no-op (no NoOpSpan creation either). This keeps the cold-path cost equivalent
to "OTel was never imported" outside of the one boolean check below.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

_TRUTHY = frozenset({"true", "1", "yes", "on"})


def _otel_enabled() -> bool:
    val = os.environ.get("OTEL_ENABLED", "")
    return val.strip().lower() in _TRUTHY


_TRACER = trace.get_tracer("ai-for-trader")

# Map readable kwarg names to the formal OTel attribute key.
_KNOWN_ATTRS: dict[str, str] = {
    "user_id": "bt.user_id",
    "strategy_id": "bt.strategy_id",
    "backtest_id": "bt.backtest_id",
    "symbol": "bt.symbol",
    "order_id": "bt.order_id",
}


def _normalise_value(v: Any) -> Any:
    """OTel SDK only accepts primitive types as attribute values.

    Coerce common business-id types (UUID, ints, str-coercible objects) to a
    string while preserving str/int/float/bool as-is.
    """
    if isinstance(v, (str, int, float, bool)):
        return v
    return str(v)


@contextmanager
def business_span(name: str, **attrs: Any) -> Iterator[Any]:
    """Create a business-level OTel span.

    Args:
        name: span name; should follow ``backtrader.<domain>.<phase>``.
        **attrs: business attributes. Known keys (user_id / strategy_id /
            backtest_id / symbol / order_id) are mapped to ``bt.*`` keys
            automatically. Unknown keys get the ``bt.`` prefix as well.

    Yields:
        The span object (or a no-op object when OTel is disabled).

    Raises:
        Re-raises any exception thrown inside the ``with`` block after marking
        the span ERROR and recording the exception event.
    """
    if not _otel_enabled():
        # Cold-path no-op: avoid even allocating a NoOpSpan.
        with nullcontext() as ctx:
            yield ctx
        return

    with _TRACER.start_as_current_span(name) as span:
        for key, raw_value in attrs.items():
            if raw_value is None:
                # Surface that the caller is missing a business object so we
                # do not silently drop attributes that *should* have a value.
                # 175 §5.5 — when an expected attribute is absent we record
                # a single sentinel event rather than skipping silently.
                span.add_event(
                    "bt.attr_missing",
                    attributes={"missing_key": key},
                )
                continue
            attr_key = _KNOWN_ATTRS.get(key, f"bt.{key}")
            span.set_attribute(attr_key, _normalise_value(raw_value))

        try:
            yield span
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, str(exc)[:200]))
            span.record_exception(exc)
            raise
