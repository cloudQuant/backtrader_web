"""
Simulation analytics API routes.

Extracted from simulation.py to keep file sizes manageable.
Provides detail, kline, and monthly-returns endpoints for simulation instances.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.schemas.analytics import (
    BacktestDetailResponse,
    KlineWithSignalsResponse,
    MonthlyReturnsResponse,
    PerformanceMetrics,
)
from app.services.live_trading_manager import LiveTradingManager, get_live_trading_manager
from app.services.log_parser_service import (
    parse_all_logs,
    parse_data_log,
    parse_trade_log,
)
from app.services.strategy_service import get_strategy_dir

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_manager() -> LiveTradingManager:
    return get_live_trading_manager()


@router.get(
    "/{instance_id}/detail",
    response_model=BacktestDetailResponse,
    summary="Get simulation analysis details",
)
async def get_simulation_detail(
    instance_id: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Get detailed analysis for a simulation trading instance."""
    inst = mgr.get_instance(instance_id, user_id=current_user.sub)
    if not inst:
        raise HTTPException(status_code=404, detail="Instance not found")

    try:
        strategy_dir = get_strategy_dir(inst["strategy_id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    log_result = parse_all_logs(strategy_dir)
    if not log_result:
        raise HTTPException(status_code=404, detail="No log data available")

    equity_dates = log_result.get("equity_dates", [])
    equity_values = log_result.get("equity_curve", [])
    cash_values = log_result.get("cash_curve", [])
    trades_raw = log_result.get("trades", [])

    equity_curve = []
    drawdown_curve = []
    peak = 0.0
    for i, dt in enumerate(equity_dates):
        val = equity_values[i] if i < len(equity_values) else 0
        c = cash_values[i] if i < len(cash_values) else 0
        pv = val - c
        equity_curve.append(
            {
                "date": dt,
                "total_assets": val,
                "cash": c,
                "position_value": round(pv, 2),
                "benchmark": None,
            }
        )
        if val > peak:
            peak = val
        dd_pct = -((peak - val) / peak) if peak > 0 else 0
        drawdown_curve.append(
            {
                "date": dt,
                "drawdown": round(dd_pct, 6),
                "peak": round(peak, 2),
                "trough": round(val, 2),
            }
        )

    trades = []
    cum_pnl = 0.0
    for i, t in enumerate(trades_raw):
        pnl = t.get("pnlcomm", t.get("pnl", 0))
        cum_pnl += pnl
        trades.append(
            {
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
            }
        )

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


@router.get(
    "/{instance_id}/kline",
    response_model=KlineWithSignalsResponse,
    summary="Get simulation K-line data",
)
async def get_simulation_kline(
    instance_id: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Get K-line data with trading signals for a simulation instance."""
    from app.api.simulation import _get_strategy_log_dir

    inst = mgr.get_instance(instance_id, user_id=current_user.sub)
    if not inst:
        raise HTTPException(status_code=404, detail="Instance not found")
    log_dir = _get_strategy_log_dir(mgr, instance_id, current_user.sub)

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
        klines.append(
            {
                "date": dt,
                "open": round(row[0], 4),
                "high": round(row[3], 4),
                "low": round(row[2], 4),
                "close": round(row[1], 4),
                "volume": volumes[j] if j < len(volumes) else 0,
            }
        )

    kline_close_map = {k["date"]: k["close"] for k in klines}

    signals = []
    for t in trades_raw:
        is_long = t.get("direction", "buy") == "buy" or t.get("long", True)
        if t.get("dtopen"):
            open_date = t["dtopen"]
            if open_date not in kline_close_map:
                open_date = open_date[:10]
            signals.append(
                {
                    "date": open_date,
                    "type": "buy" if is_long else "sell",
                    "price": kline_close_map.get(open_date, t.get("price", 0)),
                    "reason": "open",
                }
            )
        if t.get("dtclose"):
            close_date = t["dtclose"]
            if close_date not in kline_close_map:
                close_date = close_date[:10]
            signals.append(
                {
                    "date": close_date,
                    "type": "sell" if is_long else "buy",
                    "price": kline_close_map.get(close_date, t.get("price", 0)),
                    "reason": "close",
                }
            )

    indicators = log_indicators if log_indicators else {}

    return KlineWithSignalsResponse(
        symbol=inst["strategy_id"] if inst else "",
        klines=klines,
        signals=signals,
        indicators=indicators,
    )


@router.get(
    "/{instance_id}/monthly-returns",
    response_model=MonthlyReturnsResponse,
    summary="Get simulation monthly returns",
)
async def get_simulation_monthly_returns(
    instance_id: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Get monthly returns for a simulation trading instance."""
    inst = mgr.get_instance(instance_id, user_id=current_user.sub)
    if not inst:
        raise HTTPException(status_code=404, detail="Instance not found")
    try:
        strategy_dir = get_strategy_dir(inst["strategy_id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    log_result = parse_all_logs(strategy_dir)
    if not log_result:
        raise HTTPException(status_code=404, detail="No log data available")

    value_data = {
        "dates": log_result.get("equity_dates", []),
        "equity_curve": log_result.get("equity_curve", []),
    }

    equity_dates = value_data.get("dates", [])
    equity_values = value_data.get("equity_curve", [])

    monthly_returns = {}
    current_month = None
    month_start_value = 0.0

    for i, dt in enumerate(equity_dates):
        value = equity_values[i] if i < len(equity_values) else 0
        try:
            month_key = dt[:7]
            if month_key != current_month:
                if current_month and month_start_value > 0:
                    ret = (equity_values[i - 1] - month_start_value) / month_start_value
                    monthly_returns[current_month] = round(ret, 6)
                month_start_value = value
                current_month = month_key
        except (IndexError, KeyError, TypeError, ValueError) as e:
            logger.debug("Skip invalid equity entry at index %s: %s", i, e)
            continue

    if current_month and month_start_value > 0 and equity_values:
        ret = (equity_values[-1] - month_start_value) / month_start_value
        monthly_returns[current_month] = round(ret, 6)

    returns = []
    years_set = set()
    for ym, ret in monthly_returns.items():
        parts = ym.split("-")
        y, m = int(parts[0]), int(parts[1])
        years_set.add(y)
        returns.append({"year": y, "month": m, "return_pct": ret})

    years = sorted(years_set)

    summary = {}
    for y in years:
        year_rets = [r["return_pct"] for r in returns if r["year"] == y]
        total = 1.0
        for r in year_rets:
            total *= 1 + r
        summary[str(y)] = round(total - 1, 6)

    return MonthlyReturnsResponse(
        returns=returns,
        years=years,
        summary=summary,
    )
