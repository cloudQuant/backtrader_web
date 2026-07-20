from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path
from typing import Any

from app.utils.backend_data_paths import get_backend_data_path

logger = logging.getLogger(__name__)
_DATA_DIR = get_backend_data_path()
_CUSTOM_SYMBOLS_FILE = _DATA_DIR / "quote_custom_symbols.json"
_HIDDEN_SUBSCRIPTIONS_FILE = _DATA_DIR / "quote_hidden_subscriptions.json"


def load_custom_symbols(
    file_path: Path = _CUSTOM_SYMBOLS_FILE,
) -> dict[str, dict[str, list[str]]]:
    try:
        if file_path.exists():
            data = json.loads(file_path.read_text("utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        logger.exception("Failed to load custom symbols from %s", file_path)
    return {}


def save_custom_symbols(
    data: dict[str, dict[str, list[str]]],
    file_path: Path = _CUSTOM_SYMBOLS_FILE,
) -> None:
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            "utf-8",
        )
    except Exception:
        logger.exception("Failed to save custom symbols to %s", file_path)


def load_hidden_subscriptions(
    file_path: Path = _HIDDEN_SUBSCRIPTIONS_FILE,
) -> dict[str, dict[str, list[str]]]:
    """Load user-disabled non-workspace subscriptions from durable local storage."""
    return load_custom_symbols(file_path)


def save_hidden_subscriptions(
    data: dict[str, dict[str, list[str]]],
    file_path: Path = _HIDDEN_SUBSCRIPTIONS_FILE,
) -> None:
    """Persist user-disabled non-workspace subscriptions."""
    save_custom_symbols(data, file_path)


def get_cached_tick_metrics(receivers: dict[str, Any], source: str) -> dict[str, Any]:
    normalized = str(source or "").strip().upper()
    if not normalized:
        return {"tick_count": 0, "last_tick_time": None}
    relevant_receivers = [
        receiver
        for receiver_key, receiver in receivers.items()
        if str(receiver_key).upper() == normalized
        or str(getattr(receiver, "source", "")).upper() == normalized
    ]
    if not relevant_receivers:
        return {"tick_count": 0, "last_tick_time": None}
    last_tick_time: int | None = None
    tick_count = 0
    for receiver in relevant_receivers:
        cached_ticks = receiver.get_all_ticks()
        tick_count += len(cached_ticks)
        for payload in cached_ticks.values():
            if not isinstance(payload, dict):
                continue
            raw_timestamp = payload.get("timestamp")
            if raw_timestamp in (None, ""):
                continue
            if not isinstance(raw_timestamp, str | bytes | int | float):
                continue
            try:
                timestamp = float(raw_timestamp)
            except (TypeError, ValueError, OverflowError):
                continue
            if math.isnan(timestamp) or math.isinf(timestamp):
                continue
            normalized_timestamp = int(timestamp / 1000.0) if timestamp > 1e12 else int(timestamp)
            if last_tick_time is None or normalized_timestamp > last_tick_time:
                last_tick_time = normalized_timestamp
    return {
        "tick_count": tick_count,
        "last_tick_time": last_tick_time,
    }


def wait_for_initial_ticks(
    receiver: Any | None,
    symbols: list[str],
    timeout_sec: float = 1.5,
) -> dict[str, dict[str, Any]]:
    if receiver is None or not receiver.is_alive:
        return {}
    cached = receiver.get_all_ticks()
    if not symbols or any(sym in cached for sym in symbols):
        return cached
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        time.sleep(0.2)
        cached = receiver.get_all_ticks()
        if any(sym in cached for sym in symbols):
            return cached
    return cached


def match_cached_tick(
    cached_ticks: dict[str, dict[str, Any]],
    symbol: str,
) -> dict[str, Any] | None:
    raw = cached_ticks.get(symbol)
    if raw is not None:
        return raw
    target = symbol.upper()
    for key, payload in cached_ticks.items():
        candidates = [
            str(key or ""),
            str(payload.get("symbol") or ""),
            str(payload.get("instrument_id") or ""),
        ]
        normalized = [candidate.upper() for candidate in candidates if candidate]
        if target in normalized:
            return payload
        if any(value.startswith(target) for value in normalized):
            return payload
    return None
