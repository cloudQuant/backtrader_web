"""
Live trading instance management API routes.

This module provides endpoints for managing live trading strategy instances,
including starting, stopping, and monitoring live trading operations.
"""
from pathlib import Path
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.live_trading_instance import (
    LiveInstanceCreate,
    LiveInstanceInfo,
    LiveInstanceListResponse,
    LiveBatchResponse,
)
from app.schemas.analytics import (
    BacktestDetailResponse,
    KlineWithSignalsResponse,
    MonthlyReturnsResponse,
    PerformanceMetrics,
)
from app.services.live_trading_manager import get_live_trading_manager, LiveTradingManager
from app.services.log_parser_service import (
    find_latest_log_dir,
    parse_value_log,
    parse_trade_log,
    parse_data_log,
    parse_all_logs,
)
from app.services.analytics_service import AnalyticsService
from app.services.strategy_service import STRATEGIES_DIR
from app.api.deps import get_current_user

router = APIRouter()


def _get_manager() -> LiveTradingManager:
    """Get the live trading manager instance.

    Returns:
        The global LiveTradingManager instance.
    """
    return get_live_trading_manager()


@router.get("/", response_model=LiveInstanceListResponse, summary="List live trading instances")
async def list_instances(
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """List all live trading instances for the current user.

    Args:
        current_user: The authenticated user.
        mgr: The live trading manager instance.

    Returns:
        A list of live trading instances belonging to the user.
    """
    instances = mgr.list_instances(user_id=current_user.sub)
    return {"total": len(instances), "instances": instances}


@router.post("/", response_model=LiveInstanceInfo, summary="Add live trading instance")
async def add_instance(
    req: LiveInstanceCreate,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Add a new live trading instance.

    Args:
        req: The instance creation request.
        current_user: The authenticated user.
        mgr: The live trading manager instance.

    Returns:
        The created instance information.

    Raises:
        HTTPException: If the instance cannot be created.
    """
    try:
        return mgr.add_instance(req.strategy_id, req.params, user_id=current_user.sub)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{instance_id}", summary="Delete live trading instance")
async def remove_instance(
    instance_id: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Delete a live trading instance.

    Args:
        instance_id: The ID of the instance to delete.
        current_user: The authenticated user.
        mgr: The live trading manager instance.

    Returns:
        A success message.

    Raises:
        HTTPException: If the instance is not found.
    """
    if not mgr.remove_instance(instance_id, user_id=current_user.sub):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instance not found")
    return {"message": "Deleted successfully"}


@router.get("/{instance_id}", response_model=LiveInstanceInfo, summary="Get live trading instance details")
async def get_instance(
    instance_id: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Get details of a specific live trading instance.

    Args:
        instance_id: The ID of the instance.
        current_user: The authenticated user.
        mgr: The live trading manager instance.

    Returns:
        The instance information.

    Raises:
        HTTPException: If the instance is not found.
    """
    inst = mgr.get_instance(instance_id, user_id=current_user.sub)
    if not inst:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instance not found")
    return inst


@router.post("/{instance_id}/start", response_model=LiveInstanceInfo, summary="Start live trading instance")
async def start_instance(
    instance_id: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Start a live trading instance.

    Args:
        instance_id: The ID of the instance to start.
        current_user: The authenticated user.
        mgr: The live trading manager instance.

    Returns:
        The updated instance information.

    Raises:
        HTTPException: If the instance cannot be started.
    """
    try:
        return await mgr.start_instance(instance_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{instance_id}/stop", response_model=LiveInstanceInfo, summary="Stop live trading instance")
async def stop_instance(
    instance_id: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Stop a live trading instance.

    Args:
        instance_id: The ID of the instance to stop.
        current_user: The authenticated user.
        mgr: The live trading manager instance.

    Returns:
        The updated instance information.

    Raises:
        HTTPException: If the instance cannot be stopped.
    """
    try:
        return await mgr.stop_instance(instance_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/start-all", response_model=LiveBatchResponse, summary="Start all live trading instances")
async def start_all(
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Start all live trading instances.

    Args:
        current_user: The authenticated user.
        mgr: The live trading manager instance.

    Returns:
        A summary of the batch start operation.
    """
    return await mgr.start_all()


@router.post("/stop-all", response_model=LiveBatchResponse, summary="Stop all live trading instances")
async def stop_all(
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Stop all live trading instances.

    Args:
        current_user: The authenticated user.
        mgr: The live trading manager instance.

    Returns:
        A summary of the batch stop operation.
    """
    return await mgr.stop_all()


# ==================== Analytics Endpoints ====================

def _get_strategy_log_dir(mgr: LiveTradingManager, instance_id: str) -> Path:
    """Get the latest log directory for a strategy instance.

    Args:
        mgr: The live trading manager instance.
        instance_id: The ID of the live trading instance.

    Returns:
        The path to the log directory.

    Raises:
        HTTPException: If the instance or log directory is not found.
    """
    inst = mgr.get_instance(instance_id)
    if not inst:
        raise HTTPException(status_code=404, detail="Instance not found")
    strategy_dir = STRATEGIES_DIR / inst["strategy_id"]
    log_dir = find_latest_log_dir(strategy_dir)
    if not log_dir:
        raise HTTPException(status_code=404, detail="No log data available, please run the strategy first")
    return log_dir


@router.get("/{instance_id}/detail", response_model=BacktestDetailResponse, summary="Get live trading analysis details")
async def get_live_detail(
    instance_id: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Get detailed analysis for a live trading instance.

    Args:
        instance_id: The ID of the live trading instance.
        current_user: The authenticated user.
        mgr: The live trading manager instance.

    Returns:
        Detailed backtest analysis response including metrics, equity curve, and trades.

    Raises:
        HTTPException: If the instance or log data is not found.
    """
    inst = mgr.get_instance(instance_id)
    if not inst:
        raise HTTPException(status_code=404, detail="Instance not found")

    strategy_dir = STRATEGIES_DIR / inst["strategy_id"]
    log_result = parse_all_logs(strategy_dir)
    if not log_result:
        raise HTTPException(status_code=404, detail="No log data available")

    # Construct response in the same format as backtest analysis
    equity_dates = log_result.get("equity_dates", [])
    equity_values = log_result.get("equity_curve", [])
    cash_values = log_result.get("cash_curve", [])
    dd_values = log_result.get("drawdown_curve", [])
    trades_raw = log_result.get("trades", [])

    equity_curve = []
    drawdown_curve = []
    peak = 0.0
    for i, dt in enumerate(equity_dates):
        val = equity_values[i] if i < len(equity_values) else 0
        c = cash_values[i] if i < len(cash_values) else 0
        pv = val - c
        equity_curve.append({
            "date": dt, "total_assets": val, "cash": c,
            "position_value": round(pv, 2), "benchmark": None,
        })
        if val > peak:
            peak = val
        dd_pct = -((peak - val) / peak) if peak > 0 else 0
        drawdown_curve.append({
            "date": dt, "drawdown": round(dd_pct, 6),
            "peak": round(peak, 2), "trough": round(val, 2),
        })

    trades = []
    cum_pnl = 0.0
    for i, t in enumerate(trades_raw):
        pnl = t.get("pnlcomm", t.get("pnl", 0))
        cum_pnl += pnl
        trades.append({
            "id": i + 1,
            "datetime": t.get("datetime", t.get("dtclose", "")),
            "symbol": t.get("data_name", inst["strategy_id"]),
            "direction": t.get("direction", "long"),
            "price": t.get("price", 0),
            "size": t.get("size", 0),
            "value": t.get("value", 0),
            "commission": t.get("commission", 0),
            "pnl": round(pnl, 2),
            "return_pct": None,
            "holding_days": t.get("barlen", 0),
            "cumulative_pnl": round(cum_pnl, 2),
        })

    metrics = PerformanceMetrics(
        initial_capital=log_result.get("initial_cash", 100000),
        final_assets=log_result.get("final_value", 0),
        total_return=log_result.get("total_return", 0),
        annualized_return=log_result.get("annual_return", 0),
        max_drawdown=log_result.get("max_drawdown", 0),
        sharpe_ratio=log_result.get("sharpe_ratio", 0),
        win_rate=log_result.get("win_rate", 0),
        trade_count=log_result.get("total_trades", 0),
    )

    return BacktestDetailResponse(
        task_id=instance_id,
        strategy_name=inst.get("strategy_name", inst["strategy_id"]),
        symbol=inst["strategy_id"],
        start_date=equity_dates[0] if equity_dates else "",
        end_date=equity_dates[-1] if equity_dates else "",
        metrics=metrics,
        equity_curve=equity_curve,
        drawdown_curve=drawdown_curve,
        trades=trades,
        created_at=inst.get("created_at", ""),
    )


@router.get("/{instance_id}/kline", response_model=KlineWithSignalsResponse, summary="Get live trading K-line data")
async def get_live_kline(
    instance_id: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Get K-line data with trading signals for a live trading instance.

    Args:
        instance_id: The ID of the live trading instance.
        current_user: The authenticated user.
        mgr: The live trading manager instance.

    Returns:
        K-line data with buy/sell signals and indicators.

    Raises:
        HTTPException: If the instance or log directory is not found.
    """
    log_dir = _get_strategy_log_dir(mgr, instance_id)
    inst = mgr.get_instance(instance_id)

    kline_data = parse_data_log(log_dir)
    trades_raw = parse_trade_log(log_dir)

    kline_dates = kline_data.get("dates", [])
    ohlc_data = kline_data.get("ohlc", [])
    volumes = kline_data.get("volumes", [])
    log_indicators = kline_data.get("indicators", {})

    klines = []
    for j, dt in enumerate(kline_dates):
        if j >= len(ohlc_data):
            break
        row = ohlc_data[j]
        klines.append({
            "date": dt,
            "open": round(row[0], 4),
            "high": round(row[3], 4),
            "low": round(row[2], 4),
            "close": round(row[1], 4),
            "volume": volumes[j] if j < len(volumes) else 0,
        })

    # Build K-line close price mapping for signal price lookup
    kline_close_map = {}
    for k in klines:
        kline_close_map[k["date"]] = k["close"]

    # Trading signals (distinguish long/short direction, prefer K-line close price)
    signals = []
    for t in trades_raw:
        is_long = t.get("direction", "buy") == "buy" or t.get("long", True)
        if t.get("dtopen"):
            open_date = t["dtopen"][:10]
            signals.append({
                "date": open_date,
                "type": "buy" if is_long else "sell",
                "price": kline_close_map.get(open_date, t.get("price", 0)),
                "reason": "open",
            })
        if t.get("dtclose"):
            close_date = t["dtclose"][:10]
            signals.append({
                "date": close_date,
                "type": "sell" if is_long else "buy",
                "price": kline_close_map.get(close_date, t.get("price", 0)),
                "reason": "close",
            })

    indicators = log_indicators if log_indicators else {}

    return KlineWithSignalsResponse(
        symbol=inst["strategy_id"] if inst else "",
        klines=klines,
        signals=signals,
        indicators=indicators,
    )


@router.get("/{instance_id}/monthly-returns", response_model=MonthlyReturnsResponse, summary="Get live trading monthly returns")
async def get_live_monthly_returns(
    instance_id: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Get monthly returns for a live trading instance.

    Args:
        instance_id: The ID of the live trading instance.
        current_user: The authenticated user.
        mgr: The live trading manager instance.

    Returns:
        Monthly returns data with yearly summaries.

    Raises:
        HTTPException: If the instance or log directory is not found.
    """
    log_dir = _get_strategy_log_dir(mgr, instance_id)
    value_data = parse_value_log(log_dir)

    equity_dates = value_data.get("dates", [])
    equity_values = value_data.get("equity_curve", [])

    # Calculate monthly returns
    monthly_returns = {}
    current_month = None
    month_start_value = 0.0

    for i, dt in enumerate(equity_dates):
        value = equity_values[i] if i < len(equity_values) else 0
        try:
            month_key = dt[:7]  # "YYYY-MM"
            if month_key != current_month:
                if current_month and month_start_value > 0:
                    ret = (equity_values[i - 1] - month_start_value) / month_start_value
                    monthly_returns[current_month] = round(ret, 6)
                month_start_value = value
                current_month = month_key
        except Exception:
            pass

    if current_month and month_start_value > 0:
        ret = (equity_values[-1] - month_start_value) / month_start_value
        monthly_returns[current_month] = round(ret, 6)

    # Format returns
    returns = []
    years_set = set()
    for ym, ret in monthly_returns.items():
        parts = ym.split("-")
        y, m = int(parts[0]), int(parts[1])
        years_set.add(y)
        returns.append({"year": y, "month": m, "return_pct": ret})

    years = sorted(years_set)

    # Yearly summary
    summary = {}
    for y in years:
        year_rets = [r["return_pct"] for r in returns if r["year"] == y]
        total = 1.0
        for r in year_rets:
            total *= (1 + r)
        summary[str(y)] = round(total - 1, 6)

    return MonthlyReturnsResponse(
        returns=returns,
        years=years,
        summary=summary,
    )
