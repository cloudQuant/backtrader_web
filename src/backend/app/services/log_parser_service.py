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

Iteration 174 (C7) extracted the readers / normalisation / computation helpers
into the ``app.services.log_parser`` subpackage. This module now hosts only
the format-specific ``parse_*`` entry points and the ``parse_log_dir`` /
``parse_all_logs`` orchestration. The previously private ``_parse_*`` /
``_safe_float`` / ``_synthesize_value_curve`` names are re-exported (with
their leading underscore) so existing tests and downstream callers using
``from app.services.log_parser_service import _parse_tsv`` keep working.
"""

import json
import logging
import math
from pathlib import Path
from typing import Any

import numpy as np

from app.services.log_parser.computations import (
    synthesize_value_curve as _synthesize_value_curve,
)
from app.services.log_parser.normalize import (
    extract_indicator_values as _extract_indicator_values,
)
from app.services.log_parser.normalize import (
    is_truthy as _is_truthy,
)
from app.services.log_parser.normalize import (
    normalize_date_text as _normalize_date_text,
)
from app.services.log_parser.normalize import (
    normalize_dt_text as _normalize_dt_text,
)
from app.services.log_parser.normalize import (
    safe_float as _safe_float,
)
from app.services.log_parser.readers import (
    parse_json_lines as _parse_json_lines,
)
from app.services.log_parser.readers import (
    parse_pipe_key_value_lines as _parse_pipe_key_value_lines,
)
from app.services.log_parser.readers import (
    parse_pipe_lines as _parse_pipe_lines,
)
from app.services.log_parser.readers import (
    parse_tsv as _parse_tsv,
)
from app.services.strategy import runtime_support as strategy_runtime_support

logger = logging.getLogger(__name__)

MAX_ABS_EQUITY_VALUE = 1e15
MAX_EQUITY_CASH_RATIO = 1_000.0
MAX_EQUITY_STEP_RATIO = 1_000.0
MAX_SHARPE_RETURN_ABS = 10.0


def _market_value(value: Any) -> float:
    return round(_safe_float(value, 0.0), 8)


def _first_present(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _position_symbol(row: dict[str, Any], fallback: str = "") -> str:
    return str(
        _first_present(
            row,
            "data_name",
            "symbol",
            "instrument",
            "InstrumentID",
            "trade_symbol",
            "contract_symbol",
            "position_symbol_name",
            "symbol_name",
            "local_symbol",
            "localSymbol",
            "contractDesc",
            "contract_desc",
            "description",
            "ticker",
            "conid",
        )
        or fallback
        or ""
    ).strip()


def _position_size(row: dict[str, Any]) -> float:
    return _safe_float(
        _first_present(
            row,
            "size",
            "volume",
            "position",
            "qty",
            "quantity",
            "position_volume",
            "positionAmt",
            "pa",
            "Position",
            "Volume",
            "Qty",
            "Quantity",
            "trade_volume",
            "TradeVolume",
        ),
        0.0,
    )


def _position_entry_price(row: dict[str, Any]) -> float:
    return _safe_float(
        _first_present(
            row,
            "price",
            "avg_price",
            "average_price",
            "price_open",
            "avgCost",
            "avgPrice",
            "entryPrice",
            "ep",
            "averageCost",
            "Price",
            "AveragePrice",
        ),
        0.0,
    )


def _mark_estimated_market_value(
    payload: dict[str, Any], explicit_market_value: Any
) -> dict[str, Any]:
    if explicit_market_value in (None, ""):
        payload["market_value_estimated"] = True
    return payload


def _position_extra_fields(row: dict[str, Any]) -> dict[str, Any]:
    extras: dict[str, Any] = {}
    numeric_keys = (
        "current_price",
        "latest_price",
        "last_price",
        "LastPrice",
        "lastPrice",
        "mark_price",
        "markPrice",
        "market_price",
        "marketPrice",
        "SettlementPrice",
        "settlement_price",
        "PositionCost",
        "position_cost",
        "multiplier",
        "mult",
        "contract_multiplier",
        "contract_size",
        "trade_contract_size",
        "VolumeMultiple",
        "CONTRACT_MULTIPLIER",
        "price_tick",
        "tick_size",
        "PriceTick",
        "MIN_PRICE_CHANGE",
        "margin",
        "margin_rate",
        "margin_ratio",
        "long_margin_rate",
        "short_margin_rate",
        "LongMarginRatio",
        "ShortMarginRatio",
        "LongMarginRatioByMoney",
        "ShortMarginRatioByMoney",
        "MARGIN_RATIO",
        "MARGIN_BUY",
        "MARGIN_SELL",
        "leverage",
        "margin_value",
        "use_margin",
        "initial_margin",
        "maintain_margin",
        "UseMargin",
        "InitialMargin",
        "MaintainMargin",
        "margin_amount",
        "initial_margin_per_lot",
        "margin_initial",
        "initial_margin_amount",
        "long_margin_amount",
        "short_margin_amount",
        "LongMarginRatioByVolume",
        "ShortMarginRatioByVolume",
        "MARGIN_PER_LOT",
        "LONG_MARGIN_AMOUNT",
        "SHORT_MARGIN_AMOUNT",
        "commission",
        "comm",
        "fee",
        "fees",
        "open_commission",
        "position_fee",
        "position_commission",
        "trade_fee",
        "trade_commission",
        "commission_rate",
        "open_commission_rate",
        "close_commission_rate",
        "close_today_commission_rate",
        "OpenRatioByMoney",
        "CloseRatioByMoney",
        "CloseTodayRatioByMoney",
        "OPEN_FEE_RATE",
        "COMMISSION_OPEN_RATIO",
        "commission_amount",
        "OpenRatioByVolume",
        "CloseRatioByVolume",
        "CloseTodayRatioByVolume",
        "OPEN_FEE_AMOUNT",
        "OPEN_FEE_PER_LOT",
        "COMMISSION_OPEN_AMOUNT",
        "fillFee",
        "fill_fee",
        "fee_rate",
        "fee_amount",
        "pnl",
        "gross_pnl",
        "pnlcomm",
        "net_pnl",
        "position_pnl",
        "position_profit",
        "PositionProfit",
        "position_unrealized_pnl",
        "unrealized_profit",
        "unRealizedProfit",
        "UnrealizedPnL",
        "unrealizedPnl",
        "unrealized_pnl",
        "unrealizedPNL",
        "unrealizedpnl",
        "floating_pnl",
        "profit",
        "upl",
        "up",
    )
    for key in numeric_keys:
        if key in row and row.get(key) not in (None, ""):
            extras[key] = _safe_float(row.get(key), 0.0)
    text_keys = (
        "asset_type",
        "exchange",
        "exchange_id",
        "exchange_name",
        "direction",
        "side",
        "position_side",
        "positionSide",
        "PositionSide",
        "positionIdx",
        "position_idx",
        "trade_action",
        "position_type",
        "type",
        "PosiDirection",
        "posi_direction",
        "position_direction",
        "commission_method",
        "source",
        "position_source",
        "asset_spec_source",
        "broker",
        "gateway",
        "margin_type",
    )
    for key in text_keys:
        value = row.get(key)
        if value not in (None, ""):
            extras[key] = str(value)
    return extras


def _finite_metric(value: float, default: float = 0.0) -> float:
    return value if math.isfinite(value) else default


def _is_plausible_equity_value(
    value: float,
    *,
    cash: float,
    previous_equity: float | None,
) -> bool:
    if not math.isfinite(value) or abs(value) > MAX_ABS_EQUITY_VALUE:
        return False
    if math.isfinite(cash) and abs(cash) > 0:
        if abs(value) > abs(cash) * MAX_EQUITY_CASH_RATIO:
            return False
    if previous_equity is not None and math.isfinite(previous_equity) and abs(previous_equity) > 0:
        if abs(value / previous_equity) > MAX_EQUITY_STEP_RATIO:
            return False
    return True


def _equity_returns_for_metrics(equity: list[float]) -> list[float]:
    returns: list[float] = []
    for i in range(1, len(equity)):
        previous = equity[i - 1]
        current = equity[i]
        if previous <= 0 or not math.isfinite(previous) or not math.isfinite(current):
            continue
        ret = (current - previous) / previous
        if math.isfinite(ret) and abs(ret) <= MAX_SHARPE_RETURN_ABS:
            returns.append(ret)
    return returns


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
    datetimes = []
    equity = []
    cash = []
    previous_equity: float | None = None

    for row in rows:
        dt_full = _normalize_dt_text(
            row.get("dt") or row.get("datetime") or row.get("event_time") or row.get("log_time")
        )
        dt = _normalize_date_text(dt_full)
        equity_value = _safe_float(row.get("value", row.get("broker_value", "0")))
        cash_value = _safe_float(row.get("cash", row.get("broker_cash", "0")))
        if not _is_plausible_equity_value(
            equity_value,
            cash=cash_value,
            previous_equity=previous_equity,
        ):
            continue
        dates.append(dt)
        datetimes.append(dt_full or dt)
        equity.append(equity_value)
        cash.append(cash_value)
        previous_equity = equity_value

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
        "datetimes": datetimes,
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
        for item in sorted(
            grouped.values(),
            key=lambda payload: payload.get("dtclose") or payload.get("dtopen") or "",
        ):
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
                    "datetime": _normalize_dt_text(item.get("dtclose")),
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
                "datetime": _normalize_dt_text(row.get("dtclose")),
                "dtopen": _normalize_dt_text(row.get("dtopen")),
                "dtclose": _normalize_dt_text(row.get("dtclose")),
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
            positions = []
            for row in json_rows:
                if not _normalize_dt_text(row.get("datetime")):
                    continue
                explicit_market_value = _first_present(row, "value", "market_value")
                size = _position_size(row)
                price = _position_entry_price(row)
                market_value = (
                    explicit_market_value if explicit_market_value is not None else abs(size) * price
                )
                positions.append(
                    _mark_estimated_market_value(
                        {
                            "dt": _normalize_date_text(row.get("datetime")),
                            "datetime": _normalize_dt_text(row.get("datetime")),
                            "log_time": _normalize_dt_text(
                                row.get("log_time") or row.get("event_time")
                            ),
                            "data_name": _position_symbol(row),
                            "size": size,
                            "price": round(price, 4),
                            "market_value": _market_value(market_value),
                            "value": _market_value(market_value),
                            **_position_extra_fields(row),
                        },
                        explicit_market_value,
                    )
                )
            return positions
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
            size = _position_size(row)
            price = _position_entry_price(row)
            explicit_market_value = row.get("value")
            market_value = _safe_float(
                explicit_market_value if explicit_market_value not in (None, "") else abs(size) * price
            )
            positions.append(
                _mark_estimated_market_value(
                    {
                        "dt": _normalize_date_text(dt),
                        "datetime": dt,
                        "log_time": _normalize_dt_text(
                            row.get("log_time") or row.get("event_time")
                        ),
                        "data_name": _position_symbol(row, str(row.get("event") or "")),
                        "size": size,
                        "price": round(price, 4),
                        "market_value": _market_value(market_value),
                        "value": _market_value(market_value),
                        **_position_extra_fields(row),
                    },
                    explicit_market_value,
                )
            )
        return positions
    positions = []
    for row in rows:
        size = _position_size(row)
        price = _position_entry_price(row)
        datetime_text = _normalize_dt_text(row.get("datetime") or row.get("dt"))
        dt = _normalize_date_text(datetime_text)
        positions.append(
            _mark_estimated_market_value(
                {
                    "dt": dt,
                    "datetime": datetime_text,
                    "log_time": _normalize_dt_text(row.get("log_time") or row.get("event_time")),
                    "data_name": _position_symbol(row),
                    "size": size,
                    "price": round(price, 4),
                    "market_value": _market_value(abs(size) * price),
                    "value": _market_value(abs(size) * price),
                    **_position_extra_fields(row),
                },
                None,
            )
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
                if not isinstance(item, dict):
                    continue
                size = _position_size(item)
                price = _position_entry_price(item)
                explicit_market_value = _first_present(item, "value", "market_value")
                market_value = (
                    explicit_market_value if explicit_market_value is not None else size * price
                )
                result.append(
                    _mark_estimated_market_value(
                        {
                            "data_name": _position_symbol(item),
                            "size": size,
                            "price": round(price, 4),
                            "market_value": _market_value(market_value),
                            "value": _market_value(market_value),
                            **_position_extra_fields(item),
                        },
                        explicit_market_value,
                    )
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
            size = _position_size(item)
            price = _position_entry_price(item)
            explicit_market_value = _first_present(item, "value", "market_value")
            market_value = explicit_market_value
            if market_value is None:
                market_value = size * _safe_float(item.get("current_price", price))
            result.append(
                _mark_estimated_market_value(
                    {
                        "dt": _normalize_date_text(as_of),
                        "datetime": as_of,
                        "data_name": _position_symbol(item, str(data_name)),
                        "size": size,
                        "price": round(price, 4),
                        "market_value": _market_value(market_value),
                        "value": _market_value(market_value),
                        **_position_extra_fields(item),
                    },
                    explicit_market_value,
                )
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

    total_return = (
        ((final_value - initial_cash) / initial_cash * 100)
        if initial_cash > 0 and math.isfinite(initial_cash) and math.isfinite(final_value)
        else 0.0
    )
    total_return = _finite_metric(total_return)

    n_days = len(equity)
    n_years = n_days / 252.0 if n_days > 0 else 1.0
    annual_return = 0.0
    if (
        n_years > 0
        and initial_cash > 0
        and final_value > 0
        and math.isfinite(initial_cash)
        and math.isfinite(final_value)
    ):
        try:
            annual_return = ((final_value / initial_cash) ** (1.0 / n_years) - 1) * 100
        except OverflowError:
            annual_return = 0.0
    annual_return = _finite_metric(annual_return)

    max_drawdown = (
        max(value_data.get("drawdown_curve", [0.0])) if value_data.get("drawdown_curve") else 0.0
    )

    returns = _equity_returns_for_metrics(equity) if len(equity) > 1 else []
    if returns:
        avg_ret = float(np.mean(returns))
        std_ret = float(np.std(returns))
        sharpe_ratio = (avg_ret / std_ret * (252**0.5)) if std_ret > 0 else 0.0
        sharpe_ratio = _finite_metric(sharpe_ratio)
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
