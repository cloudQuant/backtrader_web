"""Backtest payload sanitisation / normalisation helpers.

These were originally a swarm of staticmethods on ``BacktestService``. They
are pure data transformations (no DB / cache / network), so iteration 174
(C8) extracted them to keep the service class focused on orchestration.

All helpers are exported as module-level functions; ``BacktestService``
keeps its old staticmethod surface as one-line forwarders for backward
compatibility with anything that called e.g.
``BacktestService._sanitize_trades(...)`` directly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def coerce_float(value: Any, default: float = 0.0) -> float:
    """Best-effort coerce ``value`` to ``float``."""
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def coerce_int(value: Any, default: int = 0) -> int:
    """Best-effort coerce ``value`` to ``int``."""
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def normalize_trade_date(value: Any) -> str | None:
    """Coerce many input formats into an ISO-8601 datetime string."""
    if isinstance(value, datetime):
        return value.isoformat()
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    candidate = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(candidate).isoformat()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).isoformat()
        except ValueError:
            continue
    return None


def normalize_trade_type(value: Any) -> str | None:
    """Coerce direction labels to either ``"buy"`` or ``"sell"``."""
    text = str(value or "").strip().lower()
    if text in {"buy", "b", "long", "open", "open_long", "buy_long"}:
        return "buy"
    if text in {"sell", "s", "short", "close", "close_long", "sell_short"}:
        return "sell"
    return None


def sanitize_trades(trades: Any) -> list[dict[str, Any]]:
    """Normalise an arbitrary ``trades`` payload into the response schema."""
    if not isinstance(trades, list):
        return []
    normalized: list[dict[str, Any]] = []
    for trade in trades:
        if not isinstance(trade, dict):
            continue
        date_value = normalize_trade_date(
            trade.get("date")
            or trade.get("datetime")
            or trade.get("dtopen")
            or trade.get("dtclose")
        )
        trade_type = normalize_trade_type(trade.get("type") or trade.get("direction"))
        if not date_value or not trade_type:
            continue
        try:
            price = float(trade.get("price") or 0)
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        size_raw = trade.get("size")
        if size_raw is None:
            size_raw = trade.get("qty")
        if size_raw is None:
            size_raw = trade.get("volume")
        try:
            size = int(abs(float(size_raw or 0)))
        except (TypeError, ValueError):
            continue
        if size <= 0:
            continue
        try:
            value_raw = trade.get("value")
            value = float(value_raw) if value_raw is not None else price * size
        except (TypeError, ValueError):
            value = price * size
        if value <= 0:
            value = price * size
        if value <= 0:
            continue
        pnl_raw = trade.get("pnl")
        try:
            pnl = float(pnl_raw) if pnl_raw is not None else None
        except (TypeError, ValueError):
            pnl = None
        pnlcomm_raw = trade.get("pnlcomm")
        try:
            pnlcomm = float(pnlcomm_raw) if pnlcomm_raw is not None else pnl
        except (TypeError, ValueError):
            pnlcomm = pnl
        commission_raw = trade.get("commission")
        try:
            commission = float(commission_raw) if commission_raw is not None else 0.0
        except (TypeError, ValueError):
            commission = 0.0
        normalized.append(
            {
                "date": date_value,
                "datetime": normalize_trade_date(trade.get("datetime")),
                "dtopen": normalize_trade_date(trade.get("dtopen")),
                "dtclose": normalize_trade_date(trade.get("dtclose")),
                "direction": trade.get("direction"),
                "type": trade_type,
                "price": price,
                "size": size,
                "value": value,
                "commission": commission,
                "pnl": pnl,
                "pnlcomm": pnlcomm,
                "barlen": coerce_int(trade.get("barlen"), 0),
            }
        )
    return normalized


def sanitize_cached_result_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalise a cached result payload to safe numeric defaults + clean trades."""
    normalized = dict(payload)
    normalized["total_return"] = coerce_float(normalized.get("total_return"), 0.0)
    normalized["annual_return"] = coerce_float(normalized.get("annual_return"), 0.0)
    normalized["sharpe_ratio"] = coerce_float(normalized.get("sharpe_ratio"), 0.0)
    normalized["max_drawdown"] = coerce_float(normalized.get("max_drawdown"), 0.0)
    normalized["win_rate"] = coerce_float(normalized.get("win_rate"), 0.0)
    normalized["total_trades"] = coerce_int(normalized.get("total_trades"), 0)
    normalized["profitable_trades"] = coerce_int(normalized.get("profitable_trades"), 0)
    normalized["losing_trades"] = coerce_int(normalized.get("losing_trades"), 0)
    normalized["trades"] = sanitize_trades(normalized.get("trades", []))
    return normalized
