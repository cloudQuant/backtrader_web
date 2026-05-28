"""Background ZMQ subscriber that caches the latest tick per symbol.

One :class:`ZmqTickReceiver` is created per active gateway. It subscribes
to the GatewayRuntime's ``market_socket`` (PUB) and drains tick messages
into an in-memory map keyed by symbol so that REST callers can fetch the
latest snapshot without a round-trip to the gateway.

Iteration 174 (C4) extracted this class out of
:mod:`app.services.quote_service` into its own module — the receiver only
depends on stdlib ``threading`` plus an optional ``pyzmq`` import, so it
can live in isolation from QuoteService and be unit-tested directly.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)


class ZmqTickReceiver:
    """Background thread that SUBs a GatewayRuntime's market_endpoint."""

    def __init__(self, source: str, market_endpoint: str) -> None:
        self.source = source
        self.market_endpoint = market_endpoint
        self._tick_cache: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._recv_loop,
            daemon=True,
            name=f"quote-zmq-{self.source}",
        )
        self._thread.start()
        logger.info(
            "ZMQ tick receiver started for %s @ %s",
            self.source,
            self.market_endpoint,
        )

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("ZMQ tick receiver stopped for %s", self.source)

    @property
    def is_alive(self) -> bool:
        return (
            self._running
            and self._thread is not None
            and self._thread.is_alive()
        )

    # -- data access -------------------------------------------------------

    def get_tick(self, symbol: str) -> dict[str, Any] | None:
        with self._lock:
            return self._tick_cache.get(symbol)

    def get_all_ticks(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return dict(self._tick_cache)

    def seed_tick(self, symbol: str, payload: dict[str, Any]) -> None:
        """Pre-populate the cache (used when a gateway returns a snapshot before pub)."""
        normalized = dict(payload)
        if symbol:
            normalized["symbol"] = normalized.get("symbol") or symbol
        key = str(normalized.get("symbol") or symbol or "").strip()
        if not key:
            return
        with self._lock:
            self._tick_cache[key] = normalized
            instrument_id = str(normalized.get("instrument_id") or "").strip()
            if instrument_id and instrument_id != key:
                self._tick_cache[instrument_id] = normalized

    # -- internal ----------------------------------------------------------

    def _recv_loop(self) -> None:
        """Connect ZMQ SUB and drain ticks into the cache."""
        try:
            import zmq
        except ImportError:
            logger.warning(
                "pyzmq not installed; ZMQ tick receiver disabled for %s",
                self.source,
            )
            self._running = False
            return

        ctx = zmq.Context.instance()
        sock = ctx.socket(zmq.SUB)
        sock.setsockopt(zmq.SUBSCRIBE, b"")
        # 500 ms recv timeout so the loop can check ``_running`` periodically.
        sock.setsockopt(zmq.RCVTIMEO, 500)
        try:
            sock.connect(self.market_endpoint)
        except zmq.ZMQError as exc:
            logger.error(
                "Cannot connect ZMQ SUB to %s: %s",
                self.market_endpoint,
                exc,
            )
            self._running = False
            sock.close()
            return

        logger.info(
            "ZMQ SUB connected to %s for %s",
            self.market_endpoint,
            self.source,
        )
        try:
            while self._running:
                try:
                    raw = sock.recv()
                except zmq.Again:
                    continue
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                symbol = payload.get("symbol") or payload.get("instrument_id") or ""
                if not symbol:
                    continue
                with self._lock:
                    self._tick_cache[symbol] = payload
        finally:
            sock.close()
            self._running = False
