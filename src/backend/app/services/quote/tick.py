"""QuoteTick payload assembly and tick value/time normalisation.

Iteration 174 (C4) extracted these out of QuoteService so the assembly
logic that maps a raw GatewayTick (from ZMQ or a snapshot fetcher) onto
the front-end-visible QuoteTick schema lives next to the rest of the
quote stack.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any


def opt_float(v: Any) -> float | None:
    """Convert ``v`` to ``float``; return ``None`` on missing / invalid input."""
    if v is None:
        return None
    try:
        number = float(v)
    except (ValueError, TypeError):
        return None
    if not math.isfinite(number) or abs(number) >= 1e308:
        return None
    return number


def normalize_tick_date_part(value: Any) -> str | None:
    """Normalise a date-like field into ``YYYY-MM-DD`` form."""
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return text
    return None


def normalize_tick_update_time(value: Any, raw: dict[str, Any], now: str) -> str | None:
    """Coalesce a tick's update_time into an ISO-8601 string.

    Accepts:
    - already ISO-8601 strings (returned normalised),
    - ``HH:MM:SS`` time strings (combined with the trading day from ``raw``),
    - other strings (returned as-is).
    """
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.isoformat()
    except ValueError:
        pass

    time_part = text
    if text.count(":") >= 2:
        date_part = (
            normalize_tick_date_part(raw.get("trading_day"))
            or normalize_tick_date_part(raw.get("action_day"))
            or normalize_tick_date_part(raw.get("date"))
            or now.split("T", 1)[0]
        )
        return f"{date_part}T{time_part}"

    return text


def build_tick(
    source: str,
    label: str,
    symbol: str,
    meta: dict[str, str],
    raw: dict[str, Any] | None,
    now: str,
) -> dict[str, Any]:
    """Map a raw GatewayTick payload onto the front-end QuoteTick schema.

    ``raw`` is a cached GatewayTick payload (dict) from the ZMQ receiver,
    or ``None`` if no data has been received yet (the resulting tick will
    have ``status='missing'``).
    """
    tick: dict[str, Any] = {
        "source": source,
        "source_label": label,
        "symbol": symbol,
        "name": meta.get("name", ""),
        "exchange": meta.get("exchange", ""),
        "category": meta.get("category", ""),
        "last_price": None,
        "change": None,
        "change_pct": None,
        "bid_price": None,
        "ask_price": None,
        "high_price": None,
        "low_price": None,
        "open_price": None,
        "prev_close": None,
        "volume": None,
        "turnover": None,
        "open_interest": None,
        "update_time": None,
        "status": "normal",
        "error_message": None,
    }

    if raw is None:
        tick["status"] = "missing"
        return tick

    price = raw.get("price")
    bid_price = opt_float(raw.get("bid_price"))
    ask_price = opt_float(raw.get("ask_price"))
    if price is not None and price != 0:
        tick["last_price"] = float(price)
    elif bid_price is not None and ask_price is not None:
        tick["last_price"] = (bid_price + ask_price) / 2.0
    elif bid_price is not None:
        tick["last_price"] = bid_price
    elif ask_price is not None:
        tick["last_price"] = ask_price
    tick["bid_price"] = bid_price
    tick["ask_price"] = ask_price
    tick["volume"] = opt_float(raw.get("volume"))
    tick["turnover"] = opt_float(raw.get("turnover"))
    tick["open_interest"] = opt_float(raw.get("openinterest"))

    tick["high_price"] = opt_float(raw.get("high_price"))
    tick["low_price"] = opt_float(raw.get("low_price"))
    tick["open_price"] = opt_float(raw.get("open_price"))
    tick["prev_close"] = opt_float(raw.get("prev_close"))

    last = tick["last_price"]
    if last is not None:
        ref = tick["prev_close"] or tick["open_price"]
        if ref is not None and ref != 0:
            tick["change"] = last - ref
            tick["change_pct"] = (last - ref) / ref * 100.0

    if raw.get("exchange"):
        tick["exchange"] = raw["exchange"]

    if raw.get("update_time"):
        tick["update_time"] = normalize_tick_update_time(raw.get("update_time"), raw, now)
    elif raw.get("datetime"):
        tick["update_time"] = normalize_tick_update_time(raw.get("datetime"), raw, now)
    elif raw.get("timestamp"):
        try:
            tick["update_time"] = datetime.fromtimestamp(
                float(raw["timestamp"]), tz=timezone.utc
            ).isoformat()
        except (ValueError, TypeError, OSError):
            tick["update_time"] = now

    return tick
