"""
Log parsing service.

Parses backtest logs under a strategy `logs/` directory.

Supported log files:
- value.log: daily equity/cash curve (dt, value, cash)
- trade.log: trade records
- order.log: order records
- data.log: OHLCV + indicators
- position.log: position records
- run_info.json: run metadata
- current_position.json: final positions
- current_position.yaml: final positions
"""

import json
import logging
import math
from pathlib import Path
from typing import Any

import numpy as np

from app.services import strategy_runtime_support

logger = logging.getLogger(__name__)


def find_latest_log_dir(strategy_dir: Path) -> Path | None:
    """Find the latest log directory under the strategy directory.

    Supports two layouts:
    1. logs/<subdir>/ (e.g. backtest runs) - returns the latest subdir by name.
    2. logs/ (flat, no subdirs) - returns logs_dir when it contains log files.
       Used by simulate strategies that write directly to logs/.

    Args:
        strategy_dir: The strategy directory path.

    Returns:
        The path to the latest log directory, or None if no logs directory exists.
    """
    latest_log_dir = strategy_runtime_support.find_latest_log_dir(strategy_dir)
    return Path(latest_log_dir) if latest_log_dir is not None else None


def _parse_tsv(filepath: Path) -> list[dict[str, str]]:
    """Parse a tab-separated log file and return a list of dictionaries.

    Args:
        filepath: Path to the TSV file.

    Returns:
        A list of dictionaries where each dictionary represents a row
        with column headers as keys.
    """
    if not filepath.is_file():
        return []

    rows = []
    with open(filepath, encoding="utf-8") as f:
        header_line = f.readline().strip()
        if not header_line:
            return []
        if header_line.startswith("{") or header_line.startswith("["):
            return []
        if "\t" not in header_line:
            return []
        headers = header_line.split("\t")

        for line in f:
            line = line.strip()
            if not line:
                continue
            values = line.split("\t")
            row = {}
            for i, h in enumerate(headers):
                row[h] = values[i] if i < len(values) else ""
            rows.append(row)

    return rows


def _parse_json_lines(filepath: Path) -> list[dict[str, Any]]:
    if not filepath.is_file():
        return []

    rows: list[dict[str, Any]] = []
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                return []
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def _parse_pipe_lines(filepath: Path) -> list[dict[str, str]]:
    if not filepath.is_file():
        return []

    rows: list[dict[str, str]] = []
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            text = line.strip()
            if not text or "|" not in text:
                continue
            parts = [part.strip() for part in text.split("|")]
            if len(parts) < 2:
                continue
            row: dict[str, str] = {"datetime": parts[0], "event": parts[1]}
            for part in parts[2:]:
                if not part or "=" not in part:
                    continue
                key, value = part.split("=", 1)
                row[key.strip().lower()] = value.strip()
            rows.append(row)
    return rows


def _parse_pipe_key_value_lines(filepath: Path) -> list[dict[str, str]]:
    if not filepath.is_file():
        return []

    rows: list[dict[str, str]] = []
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            text = line.strip()
            if not text or "|" not in text:
                continue
            parts = [part.strip() for part in text.split("|")]
            if len(parts) < 2:
                continue
            row: dict[str, str] = {"log_time": parts[0]}
            unlabeled: list[str] = []
            for part in parts[1:]:
                if not part:
                    continue
                if "=" in part:
                    key, value = part.split("=", 1)
                    row[key.strip()] = value.strip()
                    continue
                unlabeled.append(part)
            if unlabeled:
                row["event"] = unlabeled[0]
            rows.append(row)
    return rows


def _normalize_dt_text(value: Any) -> str:
    text = str(value or "").strip()
    return text


def _normalize_date_text(value: Any) -> str:
    text = _normalize_dt_text(value)
    if " " in text:
        return text.split(" ")[0]
    if "T" in text:
        return text.split("T")[0]
    return text


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _extract_indicator_values(row: dict[str, Any]) -> dict[str, float]:
    ignored = {
        "log_time",
        "datetime",
        "strategy_name",
        "data_name",
        "event_type",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "openinterest",
    }
    ignored_suffixes = (
        "_open",
        "_high",
        "_low",
        "_close",
        "_volume",
        "_openinterest",
        "_datetime",
    )
    values: dict[str, float] = {}
    for key, value in row.items():
        if key in ignored:
            continue
        if key.endswith(ignored_suffixes):
            continue
        if isinstance(value, (int, float, str)):
            numeric_value = _safe_float(value, default=math.nan)
            if not math.isnan(numeric_value):
                values[key] = numeric_value
    return values


def _load_strategy_config(strategy_dir: Path) -> dict[str, Any]:
    config_path = strategy_dir / "config.yaml"
    if not config_path.is_file():
        return {}
    try:
        import yaml

        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError) as e:
        logger.warning("Failed to load strategy config from %s: %s", config_path, e)
        return {}


def _initial_cash_for_strategy(strategy_dir: Path, run_info: dict[str, Any] | None = None) -> float:
    run_info = run_info or {}
    for key in ("initial_cash", "starting_cash", "initial_capital"):
        value = run_info.get(key)
        if value is not None:
            cash = _safe_float(value, 0.0)
            if cash > 0:
                return cash

    config = _load_strategy_config(strategy_dir)
    for section in ("simulate", "backtest"):
        value = (config.get(section) or {}).get("initial_cash")
        cash = _safe_float(value, 0.0)
        if cash > 0:
            return cash
    return 100000.0


def _synthesize_value_curve(
    strategy_dir: Path,
    kline_data: dict[str, Any],
    position_rows: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    run_info: dict[str, Any],
) -> dict[str, Any]:
    initial_cash = _initial_cash_for_strategy(strategy_dir, run_info)
    realized_by_date: dict[str, float] = {}
    for trade in trades:
        close_dt = _normalize_dt_text(trade.get("dtclose") or trade.get("datetime"))
        if not close_dt:
            continue
        realized_by_date[close_dt] = realized_by_date.get(close_dt, 0.0) + _safe_float(
            trade.get("pnlcomm", trade.get("pnl", 0.0)),
            0.0,
        )

    position_by_date: dict[str, dict[str, Any]] = {}
    for row in position_rows:
        dt = _normalize_dt_text(row.get("datetime") or row.get("dt"))
        if dt:
            position_by_date[dt] = row

    ordered_dates: list[str] = []
    seen_dates: set[str] = set()
    for dt in kline_data.get("dates", []):
        if dt and dt not in seen_dates:
            ordered_dates.append(dt)
            seen_dates.add(dt)
    for dt in sorted(position_by_date):
        if dt not in seen_dates:
            ordered_dates.append(dt)
            seen_dates.add(dt)
    for dt in sorted(realized_by_date):
        if dt not in seen_dates:
            ordered_dates.append(dt)
            seen_dates.add(dt)

    if not ordered_dates:
        return {"dates": [], "equity_curve": [], "cash_curve": [], "drawdown_curve": []}

    realized = 0.0
    equity: list[float] = []
    cash_curve: list[float] = []
    peak = initial_cash
    drawdown_curve: list[float] = []
    for dt in ordered_dates:
        realized += realized_by_date.get(dt, 0.0)
        pos = position_by_date.get(dt, {})
        size = _safe_float(pos.get("size", 0.0), 0.0)
        avg_price = _safe_float(pos.get("price", 0.0), 0.0)
        market_value = _safe_float(pos.get("value", pos.get("market_value", 0.0)), 0.0)
        cost_basis = size * avg_price
        unrealized = market_value - cost_basis
        total_assets = initial_cash + realized + unrealized
        cash_value = total_assets - market_value
        equity.append(round(total_assets, 4))
        cash_curve.append(round(cash_value, 4))
        if total_assets > peak:
            peak = total_assets
        dd = ((peak - total_assets) / peak * 100) if peak > 0 else 0.0
        drawdown_curve.append(round(dd, 4))

    return {
        "dates": ordered_dates,
        "equity_curve": equity,
        "cash_curve": cash_curve,
        "drawdown_curve": drawdown_curve,
    }


def _safe_float(val: str, default: float = 0.0) -> float:
    """Safely convert a string to a float.

    Args:
        val: The string value to convert.
        default: The default value to return if conversion fails.

    Returns:
        The converted float value, or the default if conversion fails
        or the value is NaN/Infinity.
    """
    try:
        v = float(val)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except (ValueError, TypeError):
        return default


def parse_value_log(log_dir: Path) -> dict[str, Any]:
    """Parse value.log and return equity curve data.

    Args:
        log_dir: The log directory path.

    Returns:
        A dictionary containing:
        - dates: List of date strings.
        - equity_curve: List of equity values.
        - cash_curve: List of cash values.
        - drawdown_curve: List of drawdown percentages.
    """
    rows = _parse_tsv(log_dir / "value.log")
    if not rows:
        rows = _parse_json_lines(log_dir / "value.log")
    if not rows:
        rows = _parse_pipe_key_value_lines(log_dir / "value.log")
    dates = []
    equity = []
    cash = []

    for row in rows:
        dt = _normalize_dt_text(
            row.get("dt") or row.get("datetime") or row.get("event_time") or row.get("log_time")
        )
        dt = _normalize_date_text(dt)
        dates.append(dt)
        equity.append(_safe_float(row.get("value", row.get("broker_value", "0"))))
        cash.append(_safe_float(row.get("cash", row.get("broker_cash", "0"))))

    # Calculate drawdown curve
    drawdown = []
    peak = 0.0
    for v in equity:
        if v > peak:
            peak = v
        dd = ((peak - v) / peak * 100) if peak > 0 else 0.0
        drawdown.append(round(dd, 4))

    return {
        "dates": dates,
        "equity_curve": equity,
        "cash_curve": cash,
        "drawdown_curve": drawdown,
    }


def _value_log_datetimes(log_dir: Path) -> list[str]:
    rows = _parse_json_lines(log_dir / "value.log")
    if not rows:
        rows = _parse_pipe_key_value_lines(log_dir / "value.log")
    result: list[str] = []
    for row in rows:
        dt = _normalize_dt_text(row.get("dt") or row.get("datetime") or row.get("event_time"))
        if dt:
            result.append(dt)
    return result


def parse_trade_log(log_dir: Path) -> list[dict[str, Any]]:
    """Parse trade.log and return a list of trade records.

    Only returns closed trades (isclosed=1).

    Args:
        log_dir: The log directory path.

    Returns:
        A list of trade record dictionaries.
    """
    rows = _parse_tsv(log_dir / "trade.log")
    if not rows:
        json_rows = _parse_json_lines(log_dir / "trade.log")
        pipe_rows = _parse_pipe_lines(log_dir / "trade.log") if not json_rows else []
        if not json_rows and not pipe_rows:
            return []

        grouped: dict[int, dict[str, Any]] = {}
        ungrouped_index = 1000000
        source_rows = json_rows or pipe_rows
        for row in source_rows:
            ref = int(_safe_float(row.get("ref", ungrouped_index), float(ungrouped_index)))
            if ref == ungrouped_index:
                ungrouped_index += 1
            item = grouped.setdefault(ref, {"ref": ref})
            dt_value = _normalize_dt_text(
                row.get("datetime") or row.get("event_time") or row.get("log_time")
            )
            event = str(row.get("event", "")).strip().upper()
            is_open = _is_truthy(row.get("isopen")) or event == "OPEN"
            is_closed = _is_truthy(row.get("isclosed")) or event == "CLOSED"
            data_name = row.get("data_name") or row.get("data") or item.get("data_name", "")
            if is_open:
                item["dtopen"] = dt_value
                item["open_size"] = _safe_float(row.get("size", 0.0))
                item["open_price"] = _safe_float(row.get("price", 0.0))
                item["open_value"] = _safe_float(row.get("value", 0.0))
                item["data_name"] = data_name
            if is_closed:
                item["dtclose"] = dt_value
                item["close_price"] = _safe_float(row.get("price", 0.0))
                item["pnl"] = _safe_float(row.get("pnl", 0.0))
                item["pnlcomm"] = _safe_float(row.get("pnlcomm", item.get("pnl", 0.0)))
                item["commission_close"] = _safe_float(row.get("commission", 0.0))
                if not item["commission_close"]:
                    item["commission_close"] = abs(
                        _safe_float(row.get("pnl", 0.0))
                        - _safe_float(row.get("pnlcomm", row.get("pnl", 0.0)))
                    )
                item["barlen"] = int(_safe_float(row.get("barlen", 0)))
                item["data_name"] = data_name
            item["commission_open"] = item.get("commission_open", 0.0) + (
                _safe_float(row.get("commission", 0.0)) if is_open else 0.0
            )
            size_for_direction = _safe_float(row.get("size", item.get("open_size", 0.0)), 0.0)
            if is_open or "direction" not in item:
                item["direction"] = "buy" if size_for_direction >= 0 else "sell"

        trades: list[dict[str, Any]] = []
        for item in sorted(grouped.values(), key=lambda payload: payload.get("dtclose") or payload.get("dtopen") or ""):
            if not item.get("dtclose"):
                continue
            open_size = abs(_safe_float(item.get("open_size", 0.0), 0.0))
            commission = _safe_float(item.get("commission_open", 0.0), 0.0) + _safe_float(
                item.get("commission_close", 0.0),
                0.0,
            )
            open_price = _safe_float(item.get("open_price", item.get("close_price", 0.0)), 0.0)
            open_value = _safe_float(item.get("open_value", 0.0), 0.0)
            if open_value <= 0 and open_size > 0 and open_price > 0:
                open_value = open_size * open_price
            trades.append(
                {
                    "ref": int(item.get("ref", 0)),
                    "datetime": _normalize_date_text(item.get("dtclose")),
                    "dtopen": _normalize_dt_text(item.get("dtopen")),
                    "dtclose": _normalize_dt_text(item.get("dtclose")),
                    "data_name": str(item.get("data_name", "")),
                    "direction": item.get("direction", "buy"),
                    "size": open_size,
                    "price": round(open_price, 4),
                    "value": round(abs(open_value), 2),
                    "commission": round(commission, 4),
                    "pnl": round(_safe_float(item.get("pnl", 0.0)), 2),
                    "pnlcomm": round(_safe_float(item.get("pnlcomm", item.get("pnl", 0.0))), 2),
                    "barlen": int(_safe_float(item.get("barlen", 0))),
                }
            )
        return trades

    trades = []

    for row in rows:
        if row.get("isclosed") != "1":
            continue

        trades.append(
            {
                "ref": int(_safe_float(row.get("ref", "0"))),
                "datetime": row.get("dtclose", "").split(" ")[0] if row.get("dtclose") else "",
                "dtopen": row.get("dtopen", "").split(" ")[0] if row.get("dtopen") else "",
                "dtclose": row.get("dtclose", "").split(" ")[0] if row.get("dtclose") else "",
                "data_name": row.get("data_name", ""),
                "direction": "buy" if row.get("long") == "1" else "sell",
                "size": abs(_safe_float(row.get("size", "0"))),
                "price": round(_safe_float(row.get("price", "0")), 4),
                "value": round(abs(_safe_float(row.get("value", "0"))), 2),
                "commission": round(_safe_float(row.get("commission", "0")), 4),
                "pnl": round(_safe_float(row.get("pnl", "0")), 2),
                "pnlcomm": round(_safe_float(row.get("pnlcomm", "0")), 2),
                "barlen": int(_safe_float(row.get("barlen", "0"))),
            }
        )

    return trades


def parse_order_log(log_dir: Path) -> list[dict[str, Any]]:
    """Parse order.log and return a list of completed orders.

    Args:
        log_dir: The log directory path.

    Returns:
        A list of completed order dictionaries.
    """
    rows = _parse_tsv(log_dir / "order.log")
    if not rows:
        json_rows = _parse_json_lines(log_dir / "order.log")
        if json_rows:
            return [
                {
                    "ref": int(_safe_float(row.get("ref", 0))),
                    "type": str(row.get("ordtype") or row.get("action") or row.get("type") or ""),
                    "size": _safe_float(row.get("size", 0.0)),
                    "price": round(
                        _safe_float(row.get("executed_price", row.get("price", 0.0))),
                        4,
                    ),
                    "commission": round(_safe_float(row.get("commission", 0.0)), 4),
                    "dt": _normalize_date_text(row.get("dt") or row.get("datetime")),
                    "data_name": str(row.get("data_name") or row.get("data") or ""),
                }
                for row in json_rows
                if str(row.get("status") or "").strip() == "Completed"
            ]

        pipe_rows = _parse_pipe_lines(log_dir / "order.log")
        return [
            {
                "ref": int(_safe_float(row.get("ref", 0))),
                "type": str(row.get("event") or row.get("action") or ""),
                "size": _safe_float(row.get("size", 0.0)),
                "price": round(_safe_float(row.get("price", row.get("executed_price", 0.0))), 4),
                "commission": round(_safe_float(row.get("commission", 0.0)), 4),
                "dt": _normalize_date_text(row.get("datetime")),
                "data_name": str(row.get("data_name") or row.get("data") or ""),
            }
            for row in pipe_rows
            if str(row.get("status") or "").strip() == "Completed"
        ]
    orders = []

    for row in rows:
        if row.get("status") != "Completed":
            continue

        orders.append(
            {
                "ref": int(_safe_float(row.get("ref", "0"))),
                "type": row.get("ordtype", ""),
                "size": _safe_float(row.get("size", "0")),
                "price": round(_safe_float(row.get("executed_price", "0")), 4),
                "commission": round(_safe_float(row.get("commission", "0")), 4),
                "dt": row.get("dt", "").split(" ")[0] if row.get("dt") else "",
                "data_name": row.get("data_name", ""),
            }
        )

    return orders


def parse_data_log(log_dir: Path) -> dict[str, Any]:
    """Parse data.log and return OHLCV + indicator data.

    Returns kline format data for frontend charts.

    Args:
        log_dir: The log directory path.

    Returns:
        A dictionary containing:
        - dates: List of date strings.
        - ohlc: List of [open, close, low, high] arrays.
        - volumes: List of volume values.
        - indicators: Dictionary of indicator values by column name.
    """
    rows = _parse_tsv(log_dir / "data.log")
    if not rows:
        bar_rows = _parse_json_lines(log_dir / "bar.log")
        if not bar_rows:
            bar_rows = _parse_pipe_key_value_lines(log_dir / "bar.log")
        if not bar_rows:
            return {"dates": [], "ohlc": [], "volumes": [], "indicators": {}}
        indicator_rows = _parse_json_lines(log_dir / "indicator.log")
        if not indicator_rows:
            indicator_rows = _parse_pipe_key_value_lines(log_dir / "indicator.log")
        fallback_dates = _value_log_datetimes(log_dir)
        if not fallback_dates:
            fallback_dates = parse_value_log(log_dir).get("dates", [])
        indicator_map: dict[str, dict[str, float]] = {}
        indicator_by_index: dict[int, dict[str, float]] = {}
        for index, row in enumerate(indicator_rows):
            dt = _normalize_dt_text(row.get("datetime") or row.get("dt"))
            if not dt and index < len(fallback_dates):
                dt = fallback_dates[index]
            values = _extract_indicator_values(row)
            if not values:
                continue
            if dt:
                indicator_map[dt] = values
            indicator_by_index[index] = values
        dates = []
        ohlc = []
        volumes = []
        indicators: dict[str, list[float]] = {}
        for index, row in enumerate(bar_rows):
            dt = _normalize_dt_text(row.get("datetime") or row.get("dt"))
            if not dt and index < len(fallback_dates):
                dt = fallback_dates[index]
            if not dt:
                continue
            dates.append(dt)
            open_price = _safe_float(row.get("open", row.get("o", row.get("O", 0.0))))
            high_price = _safe_float(row.get("high", row.get("h", row.get("H", 0.0))))
            low_price = _safe_float(row.get("low", row.get("l", row.get("L", 0.0))))
            close_price = _safe_float(row.get("close", row.get("c", row.get("C", 0.0))))
            ohlc.append([open_price, close_price, low_price, high_price])
            volumes.append(_safe_float(row.get("volume", row.get("vol", row.get("Volume", 0.0)))))
            row_indicators = indicator_map.get(dt) or indicator_by_index.get(index, {})
            for key, value in row_indicators.items():
                indicators.setdefault(key, [None] * (len(dates) - 1))
                indicators[key].append(value)
            for _key, values in indicators.items():
                if len(values) < len(dates):
                    values.append(None)
        return {
            "dates": dates,
            "ohlc": ohlc,
            "volumes": volumes,
            "indicators": indicators,
        }

    # Find indicator columns (non-standard columns)
    standard_cols = {
        "log_time",
        "dt",
        "data_name",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "openinterest",
    }
    all_cols = set(rows[0].keys()) if rows else set()
    indicator_cols = [c for c in all_cols - standard_cols if c]

    dates = []
    ohlc = []
    volumes = []
    indicators: dict[str, list[float]] = {col: [] for col in indicator_cols}

    for row in rows:
        dt = row.get("dt", "")
        if " " in dt:
            dt = dt.split(" ")[0]
        dates.append(dt)

        o = _safe_float(row.get("open", "0"))
        h = _safe_float(row.get("high", "0"))
        low = _safe_float(row.get("low", "0"))
        c = _safe_float(row.get("close", "0"))
        ohlc.append([o, c, low, h])
        volumes.append(_safe_float(row.get("volume", "0")))

        for col in indicator_cols:
            indicators[col].append(_safe_float(row.get(col, "0")))

    return {
        "dates": dates,
        "ohlc": ohlc,
        "volumes": volumes,
        "indicators": indicators,
    }


def parse_position_log(log_dir: Path) -> list[dict[str, Any]]:
    """Parse position.log and return a list of daily position snapshots.

    Each record contains: {dt, data_name, size, price}.

    Args:
        log_dir: The log directory path.

    Returns:
        A list of position snapshot dictionaries.
    """
    rows = _parse_tsv(log_dir / "position.log")
    if not rows:
        json_rows = _parse_json_lines(log_dir / "position.log")
        if json_rows:
            return [
                {
                    "dt": _normalize_date_text(row.get("datetime")),
                    "datetime": _normalize_dt_text(row.get("datetime")),
                    "data_name": row.get("data_name", ""),
                    "size": _safe_float(row.get("size", 0.0)),
                    "price": round(_safe_float(row.get("price", 0.0)), 4),
                    "market_value": round(_safe_float(row.get("value", 0.0)), 2),
                    "value": round(_safe_float(row.get("value", 0.0)), 2),
                }
                for row in json_rows
                if _normalize_dt_text(row.get("datetime"))
            ]
        pipe_rows = _parse_pipe_key_value_lines(log_dir / "position.log")
        if not pipe_rows:
            return []
        fallback_dates = _value_log_datetimes(log_dir)
        if not fallback_dates:
            fallback_dates = parse_value_log(log_dir).get("dates", [])
        positions = []
        for index, row in enumerate(pipe_rows):
            dt = _normalize_dt_text(row.get("datetime") or row.get("dt"))
            if not dt and index < len(fallback_dates):
                dt = fallback_dates[index]
            size = _safe_float(row.get("size", 0.0))
            price = _safe_float(row.get("price", 0.0))
            market_value = _safe_float(row.get("value", abs(size) * price))
            positions.append(
                {
                    "dt": _normalize_date_text(dt),
                    "datetime": dt,
                    "data_name": str(row.get("data_name") or row.get("event") or ""),
                    "size": size,
                    "price": round(price, 4),
                    "market_value": round(market_value, 2),
                    "value": round(market_value, 2),
                }
            )
        return positions
    positions = []
    for row in rows:
        size = _safe_float(row.get("size", "0"))
        price = _safe_float(row.get("price", "0"))
        dt = row.get("dt", "")
        if " " in dt:
            dt = dt.split(" ")[0]
        positions.append(
            {
                "dt": dt,
                "data_name": row.get("data_name", ""),
                "size": size,
                "price": round(price, 4),
                "market_value": round(abs(size) * price, 2),
                "value": round(abs(size) * price, 2),
            }
        )
    return positions


def parse_current_position(log_dir: Path) -> list[dict[str, Any]]:
    """Parse current_position.json and return the final position list.

    Args:
        log_dir: The log directory path.

    Returns:
        A list of final position dictionaries.
    """
    fp = log_dir / "current_position.json"
    if fp.is_file():
        try:
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
            result = []
            for item in data:
                size = _safe_float(str(item.get("size", 0)))
                price = _safe_float(str(item.get("price", 0)))
                market_value = item.get("value", item.get("market_value", size * price))
                result.append(
                    {
                        "data_name": item.get("data_name", ""),
                        "size": size,
                        "price": round(price, 4),
                        "market_value": round(_safe_float(market_value), 2),
                        "value": round(_safe_float(market_value), 2),
                    }
                )
            return result
        except (json.JSONDecodeError, OSError, KeyError, TypeError) as e:
            logger.warning("Failed to parse positions file %s: %s", fp, e)
            return []

    yaml_path = log_dir / "current_position.yaml"
    if not yaml_path.is_file():
        return []
    try:
        import yaml

        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        as_of = _normalize_dt_text(data.get("datetime"))
        positions = data.get("positions") or {}
        if not isinstance(positions, dict):
            return []
        result = []
        for data_name, item in positions.items():
            if not isinstance(item, dict):
                continue
            size = _safe_float(item.get("size", 0.0))
            price = _safe_float(item.get("price", 0.0))
            market_value = item.get("value")
            if market_value is None:
                market_value = size * _safe_float(item.get("current_price", price))
            result.append(
                {
                    "dt": _normalize_date_text(as_of),
                    "datetime": as_of,
                    "data_name": str(data_name),
                    "size": size,
                    "price": round(price, 4),
                    "market_value": round(_safe_float(market_value), 2),
                    "value": round(_safe_float(market_value), 2),
                }
            )
        return result
    except (OSError, TypeError, ValueError) as e:
        logger.warning("Failed to parse positions file %s: %s", yaml_path, e)
        return []


def parse_run_info(log_dir: Path) -> dict[str, Any]:
    """Parse run_info.json.

    Args:
        log_dir: The log directory path.

    Returns:
        The parsed run info dictionary, or an empty dict if parsing fails.
    """
    info_path = log_dir / "run_info.json"
    if not info_path.is_file():
        return {}
    try:
        with open(info_path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to parse run_info.json at %s: %s", info_path, e)
        return {}


def parse_log_dir(log_dir: Path, strategy_dir: Path | None = None) -> dict[str, Any] | None:
    strategy_root = strategy_dir
    if strategy_root is None:
        if log_dir.name == "logs":
            strategy_root = log_dir.parent
        elif log_dir.parent.name == "logs":
            strategy_root = log_dir.parent.parent
        else:
            strategy_root = log_dir.parent

    value_data = parse_value_log(log_dir)
    trades = parse_trade_log(log_dir)
    orders = parse_order_log(log_dir)
    kline_data = parse_data_log(log_dir)
    run_info = parse_run_info(log_dir)
    positions = parse_position_log(log_dir)
    if not positions:
        positions = parse_current_position(log_dir)
    if not value_data.get("equity_curve"):
        value_data = _synthesize_value_curve(strategy_root, kline_data, positions, trades, run_info)

    equity = value_data.get("equity_curve", [])
    initial_cash = equity[0] if equity else 100000.0
    final_value = equity[-1] if equity else initial_cash

    total_return = ((final_value - initial_cash) / initial_cash * 100) if initial_cash > 0 else 0.0

    n_days = len(equity)
    n_years = n_days / 252.0 if n_days > 0 else 1.0
    annual_return = (
        ((final_value / initial_cash) ** (1.0 / n_years) - 1) * 100
        if n_years > 0 and initial_cash > 0
        else 0.0
    )

    max_drawdown = (
        max(value_data.get("drawdown_curve", [0.0])) if value_data.get("drawdown_curve") else 0.0
    )

    if len(equity) > 1:
        returns = []
        for i in range(1, len(equity)):
            if equity[i - 1] > 0:
                returns.append((equity[i] - equity[i - 1]) / equity[i - 1])
        if returns:
            avg_ret = np.mean(returns)
            std_ret = np.std(returns)
            sharpe_ratio = (avg_ret / std_ret * (252**0.5)) if std_ret > 0 else 0.0
        else:
            sharpe_ratio = 0.0
    else:
        sharpe_ratio = 0.0

    total_trades = len(trades)
    profitable_trades = len([t for t in trades if t.get("pnlcomm", 0) > 0])
    losing_trades = len([t for t in trades if t.get("pnlcomm", 0) <= 0])
    win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0.0

    return {
        "run_info": run_info,
        "log_dir": str(log_dir),
        "total_return": round(total_return, 4),
        "annual_return": round(annual_return, 4),
        "sharpe_ratio": round(sharpe_ratio, 4),
        "max_drawdown": round(max_drawdown, 4),
        "win_rate": round(win_rate, 2),
        "total_trades": total_trades,
        "profitable_trades": profitable_trades,
        "losing_trades": losing_trades,
        "initial_cash": initial_cash,
        "final_value": round(final_value, 2),
        "equity_curve": equity,
        "equity_dates": value_data.get("dates", []),
        "cash_curve": value_data.get("cash_curve", []),
        "drawdown_curve": value_data.get("drawdown_curve", []),
        "trades": trades,
        "orders": orders,
        "kline": kline_data,
    }


def parse_all_logs(strategy_dir: Path) -> dict[str, Any] | None:
    """Parse the latest logs under the strategy directory and return complete backtest results.

    Args:
        strategy_dir: The strategy directory path.

    Returns:
        A complete backtest result dictionary containing equity curves,
        trade records, orders, K-line data, etc. Returns None if no
        log directory exists.
    """
    log_dir = find_latest_log_dir(strategy_dir)
    if not log_dir:
        return None
    return parse_log_dir(log_dir, strategy_dir=strategy_dir)
