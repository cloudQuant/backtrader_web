"""
Backtest analytics API routes.
"""

import csv
import io
import json
import logging
import typing
from datetime import datetime
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import get_current_user
from app.db.database import async_session_maker
from app.models.workspace import StrategyUnit, Workspace
from app.schemas.analytics import (
    BacktestDetailResponse,
    KlineWithSignalsResponse,
    MonthlyReturnsResponse,
)
from app.services.analytics_service import AnalyticsService
from app.services.backtest.logs import resolve_log_dir as _resolve_log_dir
from app.services.backtest_service import BacktestService
from app.services.log_parser_service import parse_data_log, parse_value_log

logger = logging.getLogger(__name__)

router = APIRouter()


@lru_cache
def get_analytics_service() -> typing.Any:
    return AnalyticsService()


@lru_cache
def get_backtest_service() -> typing.Any:
    return BacktestService()


def _normalize_chart_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if " " in text:
        return text.split(" ")[0]
    if "T" in text:
        return text.split("T")[0]
    return text


async def _resolve_strategy_display_name(
    task_id: str,
    fallback: str,
    user_id: str | None,
) -> str:
    """Resolve the user-facing strategy unit name for a backtest task."""
    try:
        async with async_session_maker() as session:
            stmt = (
                select(StrategyUnit.strategy_name, StrategyUnit.group_name)
                .join(Workspace, StrategyUnit.workspace_id == Workspace.id)
                .where(StrategyUnit.last_task_id == task_id)
                .limit(1)
            )
            if user_id:
                stmt = stmt.where(Workspace.user_id == user_id)
            row = (await session.execute(stmt)).first()
            if row:
                strategy_name = str(row[0] or "").strip()
                group_name = str(row[1] or "").strip()
                if strategy_name:
                    return strategy_name
                if group_name:
                    return group_name
    except Exception as exc:
        logger.debug("Failed to resolve strategy display name for %s: %s", task_id, exc)
    return fallback or "Unknown"


async def get_backtest_data(
    task_id: str,
    backtest_service: BacktestService,
    user_id: str | None = None,
    include_logs: bool = True,
    include_klines: bool = True,
) -> dict | None:
    """Load a backtest result with optional user_id authorization.

    Args:
        task_id: The unique identifier for the backtest task.
        backtest_service: BacktestService instance.
        user_id: Optional user ID for authorization.

    Returns:
        Dictionary containing backtest data including equity curve,
        trades, signals, klines, etc.
    """
    result = await backtest_service.get_result(task_id, user_id=user_id)

    if not result:
        return None

    # Convert equity curve format
    equity_curve = []
    drawdown_curve = []

    equity_values = result.equity_curve or []
    equity_dates = result.equity_dates or []
    _drawdown_values = result.drawdown_curve or []

    display_name = await _resolve_strategy_display_name(
        task_id,
        result.strategy_id or "Unknown",
        user_id,
    )

    # [B009] Use task-specific log directory to get real cash data when requested.
    real_cash_map: dict = {}
    task_log_dir = await _resolve_log_dir(task_id, result.strategy_id) if include_logs else None
    try:
        if task_log_dir:
            value_data = parse_value_log(task_log_dir)
            for d, c in zip(
                value_data.get("dates", []), value_data.get("cash_curve", []), strict=False
            ):
                normalized_date = _normalize_chart_date(d)
                if normalized_date:
                    real_cash_map[normalized_date] = c
    except Exception as e:
        # Value log parsing failed; use default cash calculation
        logger.debug("Failed to parse value log: %s", e)

    peak = equity_values[0] if equity_values else 0

    for _i, (date, value) in enumerate(zip(equity_dates, equity_values, strict=False)):
        if value > peak:
            peak = value
        dd = (value - peak) / peak if peak > 0 else 0

        date_str = _normalize_chart_date(date if isinstance(date, str) else str(date))
        cash = real_cash_map.get(date_str, value * 0.3)
        position = value - cash

        equity_curve.append(
            {
                "date": date_str,
                "total_assets": round(value, 2),
                "cash": round(cash, 2),
                "position_value": round(position, 2),
            }
        )

        drawdown_curve.append(
            {
                "date": date_str,
                "drawdown": round(dd, 6),
                "peak": round(peak, 2),
                "trough": round(value, 2),
            }
        )

    # [B009] Get real K-line data from task-specific log directory
    # (parse in advance for signal price lookup)
    klines = []
    log_indicators: dict = {}
    kline_close_map: dict = {}  # date -> close price
    try:
        if task_log_dir and include_klines:
            kline_data = parse_data_log(task_log_dir)
            kline_dates = kline_data.get("dates", [])
            kline_ohlc = kline_data.get("ohlc", [])
            kline_volumes = kline_data.get("volumes", [])
            log_indicators = kline_data.get("indicators", {})
            for j in range(len(kline_dates)):
                ohlc = kline_ohlc[j] if j < len(kline_ohlc) else [0, 0, 0, 0]
                kline_date = _normalize_chart_date(kline_dates[j])
                klines.append(
                    {
                        "date": kline_date,
                        "open": round(ohlc[0], 4),
                        "high": round(ohlc[3], 4),
                        "low": round(ohlc[2], 4),
                        "close": round(ohlc[1], 4),
                        "volume": kline_volumes[j] if j < len(kline_volumes) else 0,
                    }
                )
                if kline_date:
                    kline_close_map[kline_date] = round(ohlc[1], 4)
    except Exception as e:
        # K-line parsing failed; continue without klines
        logger.debug("K-line data parsing failed: %s", e)

    # Convert trade records & generate signals
    # Prefer parsing from trade.log directly (always contains dtopen/dtclose),
    # fallback to DB stored trades
    trades = []
    signals = []

    log_trades = None
    if task_log_dir and include_logs:
        try:
            from app.services.log_parser_service import parse_trade_log

            log_trades = parse_trade_log(task_log_dir)
        except (OSError, ValueError, KeyError) as e:
            logger.debug("Failed to parse trade log: %s", e)
            log_trades = None

    # Use log_trades (complete fields) or result.trades (may lack dtopen/dtclose)
    source_trades = log_trades if log_trades else (result.trades or [])

    for i, t in enumerate(source_trades):
        td = t.model_dump() if hasattr(t, "model_dump") else (t if isinstance(t, dict) else {})
        pnl = td.get("pnl") or td.get("pnlcomm")
        open_price = td.get("price", 0)
        size = td.get("size", 0)
        direction = td.get("direction", "buy")
        dtopen_raw = td.get("dtopen", "") or ""
        dtclose_raw = td.get("dtclose", "") or td.get("datetime", "") or ""

        # Derive close_price from pnl when possible
        close_price = None
        if pnl is not None and size and open_price:
            if direction == "buy":
                close_price = round(open_price + pnl / abs(size), 4)
            else:
                close_price = round(open_price - pnl / abs(size), 4)

        # Calculate holding days from dtopen/dtclose when barlen is missing or 0
        barlen = td.get("barlen") or 0
        if not barlen and dtopen_raw and dtclose_raw:
            try:
                d_open = datetime.strptime(_normalize_chart_date(dtopen_raw), "%Y-%m-%d")
                d_close = datetime.strptime(_normalize_chart_date(dtclose_raw), "%Y-%m-%d")
                barlen = max((d_close - d_open).days, 0)
            except (ValueError, TypeError):
                pass

        trade = {
            "id": i + 1,
            "datetime": td.get("datetime", "") or td.get("dtclose", ""),
            "dtopen": _normalize_chart_date(dtopen_raw),
            "dtclose": _normalize_chart_date(dtclose_raw),
            "symbol": result.symbol,
            "direction": direction,
            "price": open_price,
            "close_price": close_price,
            "size": size,
            "value": td.get("value", 0),
            "commission": td.get("commission", 0),
            "pnl": pnl,
            "barlen": barlen or None,
        }
        trades.append(trade)

        if include_klines:
            # Generate open and close signals for each closed trade.
            is_long = trade["direction"] == "buy"
            dtopen = td.get("dtopen", "") or ""
            dtclose = td.get("dtclose", "") or trade["datetime"] or ""
            if dtopen:
                open_date = _normalize_chart_date(dtopen)
                signals.append(
                    {
                        "date": open_date,
                        "type": "buy" if is_long else "sell",
                        "price": kline_close_map.get(open_date, trade["price"]),
                        "size": trade["size"],
                    }
                )
            if dtclose:
                close_date = _normalize_chart_date(dtclose)
                signals.append(
                    {
                        "date": close_date,
                        "type": "sell" if is_long else "buy",
                        "price": kline_close_map.get(close_date, trade["price"]),
                        "size": trade["size"],
                    }
                )

    # Fallback: use equity curve to derive if no log data
    if include_klines and not klines:
        base_price = 10.0
        for i, date in enumerate(equity_dates):
            if i > 0 and equity_values[i - 1] > 0:
                change = (equity_values[i] - equity_values[i - 1]) / equity_values[i - 1]
                base_price = base_price * (1 + change * 0.5)
            normalized_date = _normalize_chart_date(date if isinstance(date, str) else str(date))
            klines.append(
                {
                    "date": normalized_date,
                    "open": round(base_price * 0.998, 2),
                    "high": round(base_price * 1.01, 2),
                    "low": round(base_price * 0.99, 2),
                    "close": round(base_price, 2),
                    "volume": 500000,
                }
            )

    # Calculate monthly returns
    monthly_returns = {}
    if equity_dates and equity_values:
        month_start_value = equity_values[0]
        current_month = None

        for date, value in zip(equity_dates, equity_values, strict=False):
            try:
                normalized_date = _normalize_chart_date(
                    date if isinstance(date, str) else str(date)
                )
                dt = datetime.strptime(normalized_date, "%Y-%m-%d")
                month_key = (dt.year, dt.month)

                if current_month != month_key:
                    if current_month and month_start_value > 0:
                        ret = (value - month_start_value) / month_start_value
                        monthly_returns[current_month] = round(ret, 6)
                    month_start_value = value
                    current_month = month_key
            except Exception as e:
                # Date parsing failed; skip this entry
                logger.debug("Failed to parse date for monthly returns: %s", e)

        # Last month
        if current_month and month_start_value > 0:
            ret = (equity_values[-1] - month_start_value) / month_start_value
            monthly_returns[current_month] = round(ret, 6)

    return {
        "task_id": task_id,
        "strategy_name": display_name,
        "symbol": result.symbol or "Unknown",
        "start_date": str(result.start_date)[:10] if result.start_date else "",
        "end_date": str(result.end_date)[:10] if result.end_date else "",
        "equity_curve": equity_curve,
        "drawdown_curve": drawdown_curve,
        "trades": trades,
        "signals": signals,
        "klines": klines,
        "log_indicators": log_indicators,
        "monthly_returns": monthly_returns,
        "created_at": str(result.created_at) if result.created_at else "",
    }


@router.get("/{task_id}/detail", response_model=BacktestDetailResponse)
async def get_backtest_detail(
    task_id: str,
    current_user: typing.Any = Depends(get_current_user),
    service: AnalyticsService = Depends(get_analytics_service),
    backtest_service: BacktestService = Depends(get_backtest_service),
) -> typing.Any:
    """Get detailed backtest results including metrics and curves.

    Args:
        task_id: The unique identifier for the backtest task.
        current_user: Authenticated user.
        service: Analytics service dependency.
        backtest_service: Backtest service dependency.

    Returns:
        BacktestDetailResponse with performance metrics, equity curve,
        drawdown curve, and trades.

    Raises:
        HTTPException: If result not found (404).
    """
    # Get real backtest result from database
    result = await get_backtest_data(
        task_id,
        backtest_service,
        user_id=current_user.sub,
        include_logs=False,
        include_klines=False,
    )

    if not result:
        raise HTTPException(status_code=404, detail="Backtest result not found")

    # Calculate performance metrics
    metrics = service.calculate_metrics(result)

    # Process data
    equity_curve = service.process_equity_curve(result["equity_curve"])
    drawdown_curve = service.process_drawdown_curve(result["drawdown_curve"])
    trades = service.process_trades(result["trades"])

    return BacktestDetailResponse(
        task_id=task_id,
        strategy_name=result["strategy_name"],
        symbol=result["symbol"],
        start_date=result["start_date"],
        end_date=result["end_date"],
        metrics=metrics,
        equity_curve=equity_curve,
        drawdown_curve=drawdown_curve,
        trades=trades,
        created_at=result["created_at"],
    )


@router.get("/{task_id}/kline", response_model=KlineWithSignalsResponse)
async def get_kline_with_signals(
    task_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    current_user: typing.Any = Depends(get_current_user),
    service: AnalyticsService = Depends(get_analytics_service),
    backtest_service: BacktestService = Depends(get_backtest_service),
) -> typing.Any:
    """Get K-line data with trading signals for chart visualization.

    Args:
        task_id: The unique identifier for the backtest task.
        start_date: Optional start date filter (YYYY-MM-DD).
        end_date: Optional end date filter (YYYY-MM-DD).
        current_user: Authenticated user.
        service: Analytics service dependency.
        backtest_service: Backtest service dependency.

    Returns:
        KlineWithSignalsResponse with klines, signals, and indicators.

    Raises:
        HTTPException: If result not found (404).
    """
    result = await get_backtest_data(
        task_id,
        backtest_service,
        user_id=current_user.sub,
        include_logs=True,
        include_klines=True,
    )

    if not result:
        raise HTTPException(status_code=404, detail="Backtest result not found")

    klines = result["klines"]
    signals = result["signals"]

    # Date filtering
    if start_date:
        klines = [k for k in klines if k["date"] >= start_date]
        signals = [s for s in signals if s["date"] >= start_date]
    if end_date:
        klines = [k for k in klines if k["date"] <= end_date]
        signals = [s for s in signals if s["date"] <= end_date]

    # Prefer real indicators from logs, fallback to calculated MA
    log_indicators = result.get("log_indicators", {})
    if log_indicators:
        indicators = log_indicators
    else:
        indicators = service.calculate_indicators(klines)

    return KlineWithSignalsResponse(
        symbol=result["symbol"],
        klines=[
            {
                "date": k["date"],
                "open": k["open"],
                "high": k["high"],
                "low": k["low"],
                "close": k["close"],
                "volume": k["volume"],
            }
            for k in klines
        ],
        signals=service.process_signals(signals),
        indicators=indicators,
    )


@router.get("/{task_id}/monthly-returns", response_model=MonthlyReturnsResponse)
async def get_monthly_returns(
    task_id: str,
    current_user: typing.Any = Depends(get_current_user),
    service: AnalyticsService = Depends(get_analytics_service),
    backtest_service: BacktestService = Depends(get_backtest_service),
) -> typing.Any:
    """Get monthly returns data for heatmap visualization.

    Args:
        task_id: The unique identifier for the backtest task.
        current_user: Authenticated user.
        service: Analytics service dependency.
        backtest_service: Backtest service dependency.

    Returns:
        MonthlyReturnsResponse with monthly return data.

    Raises:
        HTTPException: If result not found (404).
    """
    result = await get_backtest_data(
        task_id,
        backtest_service,
        user_id=current_user.sub,
        include_logs=False,
        include_klines=False,
    )

    if not result:
        raise HTTPException(status_code=404, detail="Backtest result not found")

    return service.process_monthly_returns(result["monthly_returns"])


@router.get("/{task_id}/optimization", response_model=None)
async def get_optimization_results(
    task_id: str,
    current_user: typing.Any = Depends(get_current_user),
) -> typing.Any:
    """Get parameter optimization results for a backtest task.

    Note: This backtest task has no associated optimization results.
    Use the /api/v1/optimization/ module for parameter optimization.

    Args:
        task_id: The unique identifier for the backtest task.
        current_user: Authenticated user.

    Raises:
        HTTPException: Always (404) - optimization is a separate feature.
    """
    raise HTTPException(
        status_code=404,
        detail="This backtest task has no associated optimization results. "
        "Please use the 'Parameter Optimization' feature to run optimizations.",
    )


@router.get("/{task_id}/export", response_model=None)
async def export_backtest_results(
    task_id: str,
    format: str = "csv",
    current_user: typing.Any = Depends(get_current_user),
    service: AnalyticsService = Depends(get_analytics_service),
    backtest_service: BacktestService = Depends(get_backtest_service),
) -> typing.Any:
    """Export backtest results to CSV or JSON format.

    Args:
        task_id: The unique identifier for the backtest task.
        format: Export format - "csv" or "json". Defaults to "csv".
        current_user: Authenticated user.
        service: Analytics service dependency.
        backtest_service: Backtest service dependency.

    Returns:
        StreamingResponse with file attachment.

    Raises:
        HTTPException: If result not found (404) or format unsupported (400).
    """
    result = await get_backtest_data(
        task_id,
        backtest_service,
        user_id=current_user.sub,
        include_logs=True,
        include_klines=True,
    )

    if not result:
        raise HTTPException(status_code=404, detail="Backtest result not found")

    trades = result["trades"]

    if format == "csv":
        output = io.StringIO()
        # Handle empty trade records
        fieldnames = (
            trades[0].keys()
            if trades
            else [
                "id",
                "datetime",
                "symbol",
                "direction",
                "price",
                "size",
                "value",
                "commission",
                "pnl",
            ]
        )
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(trades)

        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=backtest_{task_id}.csv"},
        )

    elif format == "json":
        # Ensure the payload is JSON serializable
        # (e.g., tuple keys in monthly_returns).
        result_json = dict(result)
        monthly_returns = result_json.get("monthly_returns")
        if isinstance(monthly_returns, dict):
            safe_monthly_returns = {}
            for k, v in monthly_returns.items():
                if isinstance(k, tuple) and len(k) == 2:
                    y, m = k
                    safe_monthly_returns[f"{int(y):04d}-{int(m):02d}"] = v
                else:
                    safe_monthly_returns[str(k)] = v
            result_json["monthly_returns"] = safe_monthly_returns

        return StreamingResponse(
            iter([json.dumps(result_json, ensure_ascii=False, indent=2)]),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=backtest_{task_id}.json"},
        )

    raise HTTPException(status_code=400, detail="Unsupported export format")
