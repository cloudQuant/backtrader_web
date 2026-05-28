"""Snapshot tick fetchers for the various gateway feeds.

These pull a single best-effort tick out of a gateway adapter's ``feed``
when no live tick has yet flowed through the ZMQ subscriber. Each gateway
family has its own raw-tick shape, so the helpers normalise them onto the
common :class:`bt_api_py.gateway.GatewayTick`-style dict that QuoteService
consumes.

Iteration 174 (C4) extracted these out of QuoteService so the service
class is easier to read.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.services.quote.registry import first_present
from app.services.quote.tick import opt_float

logger = logging.getLogger(__name__)


def fetch_gateway_snapshot_tick(
    source: str, feed: Any, symbol: str
) -> dict[str, Any] | None:
    """Dispatch to the source-specific snapshot fetcher."""
    if source == "IB_WEB":
        return fetch_ib_web_snapshot_tick(feed, symbol)
    return fetch_standard_snapshot_tick(source, feed, symbol)


def fetch_ib_web_snapshot_tick(feed: Any, symbol: str) -> dict[str, Any] | None:
    """Pull a single tick from IB Web's snapshot feed.

    IB Web returns a flat dict keyed by IB field IDs (``31``, ``84``, ...).
    """
    try:
        snapshot = feed.get_tick(symbol)
    except Exception as exc:  # noqa: BLE001 - tolerate any gateway error
        logger.warning(
            "Failed to fetch IB_WEB snapshot for %s: %s: %s",
            symbol,
            type(exc).__name__,
            exc,
        )
        return None
    if not isinstance(snapshot, dict) or not snapshot:
        return None

    price = opt_float(
        snapshot.get("31") or snapshot.get("last") or snapshot.get("lastPrice")
    )
    bid_price = opt_float(
        snapshot.get("84") or snapshot.get("bid") or snapshot.get("bidPrice")
    )
    ask_price = opt_float(
        snapshot.get("86") or snapshot.get("ask") or snapshot.get("askPrice")
    )
    volume = opt_float(
        snapshot.get("87") or snapshot.get("volume") or snapshot.get("lastSize")
    )
    if price is None and bid_price is None and ask_price is None and volume is None:
        return None

    raw: dict[str, Any] = {
        "timestamp": time.time(),
        "symbol": symbol,
        "exchange": "IB_WEB",
        "instrument_id": str(snapshot.get("conid") or snapshot.get("conidEx") or ""),
        "exchange_id": str(
            snapshot.get("listingExchange") or snapshot.get("exchange") or ""
        ),
    }
    if price is not None:
        raw["price"] = price
    if bid_price is not None:
        raw["bid_price"] = bid_price
    if ask_price is not None:
        raw["ask_price"] = ask_price
    if volume is not None:
        raw["volume"] = volume
    return raw


def fetch_standard_snapshot_tick(
    source: str, feed: Any, symbol: str
) -> dict[str, Any] | None:
    """Pull a single tick from a non-IB feed (CTP / MT5 / BINANCE / OKX)."""
    try:
        snapshot = feed.get_tick(symbol)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to fetch %s snapshot for %s: %s: %s",
            source,
            symbol,
            type(exc).__name__,
            exc,
        )
        return None

    data = snapshot.get_data() if hasattr(snapshot, "get_data") else snapshot
    if isinstance(data, list):
        item = data[0] if data else None
    elif isinstance(data, dict):
        item = data
    else:
        item = None
    if item is None:
        return None

    payload = item.get_all_data() if hasattr(item, "get_all_data") else item
    if not isinstance(payload, dict) or not payload:
        return None

    bid_price = opt_float(first_present(payload, "bid_price"))
    ask_price = opt_float(first_present(payload, "ask_price"))
    price = opt_float(first_present(payload, "last_price", "price"))
    if price is None and bid_price is not None and ask_price is not None:
        price = (bid_price + ask_price) / 2.0
    volume = opt_float(first_present(payload, "volume_24h", "vol_24h", "volume"))
    turnover = opt_float(
        first_present(payload, "turnover_24h", "vol_ccy_24h", "turnover")
    )
    high_price = opt_float(first_present(payload, "high_price", "high_24h"))
    low_price = opt_float(first_present(payload, "low_price", "low_24h"))
    open_price = opt_float(first_present(payload, "open_price", "open_24h"))
    prev_close = opt_float(first_present(payload, "prev_close"))
    bid_volume = opt_float(first_present(payload, "bid_volume"))
    ask_volume = opt_float(first_present(payload, "ask_volume"))
    if all(
        value is None
        for value in (
            price,
            bid_price,
            ask_price,
            volume,
            turnover,
            high_price,
            low_price,
            open_price,
            prev_close,
        )
    ):
        return None

    server_time = opt_float(first_present(payload, "server_time"))
    if server_time is None:
        timestamp = time.time()
    else:
        timestamp = server_time / 1000.0 if server_time > 1e12 else server_time

    raw: dict[str, Any] = {
        "timestamp": timestamp,
        "symbol": str(
            first_present(payload, "ticker_symbol_name", "symbol_name") or symbol
        ),
        "exchange": source,
    }
    if price is not None:
        raw["price"] = price
    if bid_price is not None:
        raw["bid_price"] = bid_price
    if ask_price is not None:
        raw["ask_price"] = ask_price
    if bid_volume is not None:
        raw["bid_volume"] = bid_volume
    if ask_volume is not None:
        raw["ask_volume"] = ask_volume
    if volume is not None:
        raw["volume"] = volume
    if turnover is not None:
        raw["turnover"] = turnover
    if high_price is not None:
        raw["high_price"] = high_price
    if low_price is not None:
        raw["low_price"] = low_price
    if open_price is not None:
        raw["open_price"] = open_price
    if prev_close is not None:
        raw["prev_close"] = prev_close
    return raw
