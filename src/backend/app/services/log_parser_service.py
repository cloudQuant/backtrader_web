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
"""

import json
import logging
import math
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_FLAT_LOG_FILENAMES = frozenset(
    {
        "value.log",
        "data.log",
        "trade.log",
        "bar.log",
        "indicator.log",
        "position.log",
        "order.log",
        "system.log",
        "tick.log",
    }
)


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
    logs_dir = strategy_dir / "logs"
    if not logs_dir.is_dir():
        return None

    subdirs = sorted(
        [d for d in logs_dir.iterdir() if d.is_dir()],
        key=lambda d: d.name,
        reverse=True,
    )
    if subdirs:
        return subdirs[0]
    # Fallback: logs written directly in logs/ (no subdirs), e.g. simulate strategies
    has_logs = any((logs_dir / f).is_file() for f in _FLAT_LOG_FILENAMES)
    return logs_dir if has_logs else None


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


def _normalize_dt_text(value: Any) -> str:
    text = str(value or "").strip()
    return text


def _normalize_date_text(value: Any) -> str:
    text = _normalize_dt_text(value)
    if " " in text:
        return text.split(" ")[0]
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
    values: dict[str, float] = {}
    for key, value in row.items():
        if key in ignored:
            continue
        if isinstance(value, (int, float)):
            values[key] = _safe_float(value)
    return values


def _load_strategy_config(strategy_dir: Path) -> dict[str, Any]:
    config_path = strategy_dir / "config.yaml"
    if not config_path.is_file():
        return {}
    try:
        import yaml

        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
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
    dates = []
    equity = []
    cash = []

    for row in rows:
        dt = row.get("dt", row.get("datetime", ""))
        if " " in dt:
            dt = dt.split(" ")[0]
        dates.append(dt)
        equity.append(_safe_float(row.get("value", "0")))
        cash.append(_safe_float(row.get("cash", "0")))

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
        if not json_rows:
            return []

        grouped: dict[int, dict[str, Any]] = {}
        ungrouped_index = 1000000
        for row in json_rows:
            ref = int(_safe_float(row.get("ref", ungrouped_index), float(ungrouped_index)))
            if ref == ungrouped_index:
                ungrouped_index += 1
            item = grouped.setdefault(ref, {"ref": ref})
            dt_value = _normalize_dt_text(row.get("datetime"))
            if _is_truthy(row.get("isopen")):
                item["dtopen"] = dt_value
                item["open_size"] = _safe_float(row.get("size", 0.0))
                item["open_price"] = _safe_float(row.get("price", 0.0))
                item["open_value"] = _safe_float(row.get("value", 0.0))
                item["data_name"] = row.get("data_name", item.get("data_name", ""))
            if _is_truthy(row.get("isclosed")):
                item["dtclose"] = dt_value
                item["close_price"] = _safe_float(row.get("price", 0.0))
                item["pnl"] = _safe_float(row.get("pnl", 0.0))
                item["pnlcomm"] = _safe_float(row.get("pnlcomm", item.get("pnl", 0.0)))
                item["commission_close"] = _safe_float(row.get("commission", 0.0))
                item["barlen"] = int(_safe_float(row.get("barlen", 0)))
                item["data_name"] = row.get("data_name", item.get("data_name", ""))
            item["commission_open"] = item.get("commission_open", 0.0) + (
                _safe_float(row.get("commission", 0.0)) if _is_truthy(row.get("isopen")) else 0.0
            )
            item["direction"] = (
                "buy"
                if _safe_float(row.get("size", item.get("open_size", 0.0)), 0.0) >= 0
                else "sell"
            )

        trades: list[dict[str, Any]] = []
        for item in sorted(grouped.values(), key=lambda payload: payload.get("dtclose") or payload.get("dtopen") or ""):
            if not item.get("dtclose"):
                continue
            open_size = abs(_safe_float(item.get("open_size", 0.0), 0.0))
            commission = _safe_float(item.get("commission_open", 0.0), 0.0) + _safe_float(
                item.get("commission_close", 0.0),
                0.0,
            )
            trades.append(
                {
                    "ref": int(item.get("ref", 0)),
                    "datetime": _normalize_date_text(item.get("dtclose")),
                    "dtopen": _normalize_dt_text(item.get("dtopen")),
                    "dtclose": _normalize_dt_text(item.get("dtclose")),
                    "data_name": str(item.get("data_name", "")),
                    "direction": item.get("direction", "buy"),
                    "size": open_size,
                    "price": round(_safe_float(item.get("open_price", item.get("close_price", 0.0))), 4),
                    "value": round(abs(_safe_float(item.get("open_value", 0.0))), 2),
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
            return {"dates": [], "ohlc": [], "volumes": [], "indicators": {}}
        indicator_rows = _parse_json_lines(log_dir / "indicator.log")
        indicator_map = {
            _normalize_dt_text(row.get("datetime")): _extract_indicator_values(row)
            for row in indicator_rows
            if _normalize_dt_text(row.get("datetime"))
        }
        dates = []
        ohlc = []
        volumes = []
        indicators: dict[str, list[float]] = {}
        for row in bar_rows:
            dt = _normalize_dt_text(row.get("datetime"))
            if not dt:
                continue
            dates.append(dt)
            open_price = _safe_float(row.get("open", 0.0))
            high_price = _safe_float(row.get("high", 0.0))
            low_price = _safe_float(row.get("low", 0.0))
            close_price = _safe_float(row.get("close", 0.0))
            ohlc.append([open_price, close_price, low_price, high_price])
            volumes.append(_safe_float(row.get("volume", 0.0)))
            for key, value in indicator_map.get(dt, {}).items():
                indicators.setdefault(key, [None] * (len(dates) - 1))
                indicators[key].append(value)
            for key, values in indicators.items():
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
        if not json_rows:
            return []
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
    if not fp.is_file():
        return []
    try:
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
        result = []
        for item in data:
            size = _safe_float(str(item.get("size", 0)))
            price = _safe_float(str(item.get("price", 0)))
            result.append(
                {
                    "data_name": item.get("data_name", ""),
                    "size": size,
                    "price": round(price, 4),
                    "market_value": round(abs(size) * price, 2),
                }
            )
        return result
    except Exception:
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
    except Exception:
        return {}


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

    # Parse various logs
    value_data = parse_value_log(log_dir)
    trades = parse_trade_log(log_dir)
    orders = parse_order_log(log_dir)
    kline_data = parse_data_log(log_dir)
    run_info = parse_run_info(log_dir)
    positions = parse_position_log(log_dir)
    if not value_data.get("equity_curve"):
        value_data = _synthesize_value_curve(strategy_dir, kline_data, positions, trades, run_info)

    # Calculate statistics
    equity = value_data.get("equity_curve", [])
    initial_cash = equity[0] if equity else 100000.0
    final_value = equity[-1] if equity else initial_cash

    total_return = ((final_value - initial_cash) / initial_cash * 100) if initial_cash > 0 else 0.0

    # Annualized return
    n_days = len(equity)
    n_years = n_days / 252.0 if n_days > 0 else 1.0
    annual_return = (
        ((final_value / initial_cash) ** (1.0 / n_years) - 1) * 100
        if n_years > 0 and initial_cash > 0
        else 0.0
    )

    # Maximum drawdown
    max_drawdown = (
        max(value_data.get("drawdown_curve", [0.0])) if value_data.get("drawdown_curve") else 0.0
    )

    # Sharpe ratio (simplified calculation)
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

    # Trade statistics
    total_trades = len(trades)
    profitable_trades = len([t for t in trades if t.get("pnlcomm", 0) > 0])
    losing_trades = len([t for t in trades if t.get("pnlcomm", 0) <= 0])
    win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0.0

    return {
        "run_info": run_info,
        "log_dir": str(log_dir),
        # Metrics
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
        # Curve data
        "equity_curve": equity,
        "equity_dates": value_data.get("dates", []),
        "cash_curve": value_data.get("cash_curve", []),
        "drawdown_curve": value_data.get("drawdown_curve", []),
        # Trades and orders
        "trades": trades,
        "orders": orders,
        # K-line data
        "kline": kline_data,
    }
