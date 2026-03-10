"""
Backtest analytics API routes.
"""

import csv
import io
import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user
from app.db.sql_repository import SQLRepository
from app.models.backtest import BacktestTask
from app.schemas.analytics import (
    BacktestDetailResponse,
    KlineWithSignalsResponse,
    MonthlyReturnsResponse,
)
from app.services.analytics_service import AnalyticsService
from app.services.backtest_service import BacktestService
from app.services.log_parser_service import find_latest_log_dir, parse_data_log, parse_value_log
from app.services.strategy_service import STRATEGIES_DIR

router = APIRouter()


@lru_cache
def get_analytics_service():
    return AnalyticsService()


@lru_cache
def get_backtest_service():
    return BacktestService()


async def _resolve_log_dir(task_id: str, strategy_id: str) -> Path:
    """Resolve a task log directory (prefer DB log_dir, fallback to latest).

    Args:
        task_id: The unique identifier for the backtest task.
        strategy_id: The strategy identifier.

    Returns:
        Path to the log directory.
    """
    try:
        task_repo = SQLRepository(BacktestTask)
        task = await task_repo.get_by_id(task_id)
        if task and getattr(task, "log_dir", None):
            p = Path(task.log_dir)
            if p.is_dir():
                return p
    except Exception:
        pass
    # Fallback: compatible with old tasks
    strategy_dir = STRATEGIES_DIR / strategy_id
    return find_latest_log_dir(strategy_dir)


async def get_backtest_data(
    task_id: str, backtest_service: BacktestService, user_id: Optional[str] = None
) -> Optional[dict]:
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

    # [B009] Use task-specific log directory to get real cash data
    real_cash_map: dict = {}
    task_log_dir = await _resolve_log_dir(task_id, result.strategy_id)
    try:
        if task_log_dir:
            value_data = parse_value_log(task_log_dir)
            for d, c in zip(value_data.get("dates", []), value_data.get("cash_curve", [])):
                real_cash_map[d] = c
    except Exception:
        pass

    peak = equity_values[0] if equity_values else 0

    for i, (date, value) in enumerate(zip(equity_dates, equity_values)):
        if value > peak:
            peak = value
        dd = (value - peak) / peak if peak > 0 else 0

        date_str = date if isinstance(date, str) else str(date)
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
        if task_log_dir:
            kline_data = parse_data_log(task_log_dir)
            kline_dates = kline_data.get("dates", [])
            kline_ohlc = kline_data.get("ohlc", [])
            kline_volumes = kline_data.get("volumes", [])
            log_indicators = kline_data.get("indicators", {})
            for j in range(len(kline_dates)):
                ohlc = kline_ohlc[j] if j < len(kline_ohlc) else [0, 0, 0, 0]
                klines.append(
                    {
                        "date": kline_dates[j],
                        "open": round(ohlc[0], 4),
                        "high": round(ohlc[3], 4),
                        "low": round(ohlc[2], 4),
                        "close": round(ohlc[1], 4),
                        "volume": kline_volumes[j] if j < len(kline_volumes) else 0,
                    }
                )
                kline_close_map[kline_dates[j]] = round(ohlc[1], 4)
    except Exception:
        pass

    # Convert trade records & generate signals
    # Prefer parsing from trade.log directly (always contains dtopen/dtclose),
    # fallback to DB stored trades
    trades = []
    signals = []

    log_trades = None
    if task_log_dir:
        try:
            from app.services.log_parser_service import parse_trade_log

            log_trades = parse_trade_log(task_log_dir)
        except Exception:
            log_trades = None

    # Use log_trades (complete fields) or result.trades (may lack dtopen/dtclose)
    source_trades = log_trades if log_trades else (result.trades or [])

    for i, t in enumerate(source_trades):
        td = t.model_dump() if hasattr(t, "model_dump") else (t if isinstance(t, dict) else {})
        trade = {
            "id": i + 1,
            "datetime": td.get("datetime", "") or td.get("dtclose", ""),
            "symbol": result.symbol,
            "direction": td.get("direction", "buy"),
            "price": td.get("price", 0),
            "size": td.get("size", 0),
            "value": td.get("value", 0),
            "commission": td.get("commission", 0),
            "pnl": td.get("pnl") or td.get("pnlcomm"),
            "barlen": td.get("barlen"),
        }
        trades.append(trade)

        # Generate open and close signals for each closed trade
        # Prefer K-line close price as signal price, fallback to trade avg price
        is_long = trade["direction"] == "buy"
        dtopen = td.get("dtopen", "") or ""
        dtclose = td.get("dtclose", "") or trade["datetime"] or ""
        if dtopen:
            open_date = dtopen[:10]
            signals.append(
                {
                    "date": open_date,
                    "type": "buy" if is_long else "sell",
                    "price": kline_close_map.get(open_date, trade["price"]),
                    "size": trade["size"],
                }
            )
        if dtclose:
            close_date = dtclose[:10]
            signals.append(
                {
                    "date": close_date,
                    "type": "sell" if is_long else "buy",
                    "price": kline_close_map.get(close_date, trade["price"]),
                    "size": trade["size"],
                }
            )

    # Fallback: use equity curve to derive if no log data
    if not klines:
        base_price = 10.0
        for i, date in enumerate(equity_dates):
            if i > 0 and equity_values[i - 1] > 0:
                change = (equity_values[i] - equity_values[i - 1]) / equity_values[i - 1]
                base_price = base_price * (1 + change * 0.5)
            klines.append(
                {
                    "date": date if isinstance(date, str) else str(date),
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

        for date, value in zip(equity_dates, equity_values):
            try:
                dt = datetime.strptime(date, "%Y-%m-%d") if isinstance(date, str) else date
                month_key = (dt.year, dt.month)

                if current_month != month_key:
                    if current_month and month_start_value > 0:
                        ret = (value - month_start_value) / month_start_value
                        monthly_returns[current_month] = round(ret, 6)
                    month_start_value = value
                    current_month = month_key
            except Exception:
                pass

        # Last month
        if current_month and month_start_value > 0:
            ret = (equity_values[-1] - month_start_value) / month_start_value
            monthly_returns[current_month] = round(ret, 6)

    return {
        "task_id": task_id,
        "strategy_name": result.strategy_id or "Unknown",
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
    current_user=Depends(get_current_user),
    service: AnalyticsService = Depends(get_analytics_service),
    backtest_service: BacktestService = Depends(get_backtest_service),
):
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
    result = await get_backtest_data(task_id, backtest_service, user_id=current_user.sub)

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
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user=Depends(get_current_user),
    service: AnalyticsService = Depends(get_analytics_service),
    backtest_service: BacktestService = Depends(get_backtest_service),
):
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
    result = await get_backtest_data(task_id, backtest_service, user_id=current_user.sub)

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
    current_user=Depends(get_current_user),
    service: AnalyticsService = Depends(get_analytics_service),
    backtest_service: BacktestService = Depends(get_backtest_service),
):
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
    result = await get_backtest_data(task_id, backtest_service, user_id=current_user.sub)

    if not result:
        raise HTTPException(status_code=404, detail="Backtest result not found")

    return service.process_monthly_returns(result["monthly_returns"])


@router.get("/{task_id}/optimization")
async def get_optimization_results(
    task_id: str,
    current_user=Depends(get_current_user),
):
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


@router.get("/{task_id}/export")
async def export_backtest_results(
    task_id: str,
    format: str = "csv",
    current_user=Depends(get_current_user),
    service: AnalyticsService = Depends(get_analytics_service),
    backtest_service: BacktestService = Depends(get_backtest_service),
):
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
    result = await get_backtest_data(task_id, backtest_service, user_id=current_user.sub)

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
