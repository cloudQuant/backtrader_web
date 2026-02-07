"""
实盘交易管理 API 路由
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
    return get_live_trading_manager()


@router.get("/", response_model=LiveInstanceListResponse, summary="获取实盘策略列表")
async def list_instances(
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    instances = mgr.list_instances()
    return {"total": len(instances), "instances": instances}


@router.post("/", response_model=LiveInstanceInfo, summary="添加实盘策略")
async def add_instance(
    req: LiveInstanceCreate,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    try:
        return mgr.add_instance(req.strategy_id, req.params)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{instance_id}", summary="删除实盘策略")
async def remove_instance(
    instance_id: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    if not mgr.remove_instance(instance_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="实例不存在")
    return {"message": "已删除"}


@router.get("/{instance_id}", response_model=LiveInstanceInfo, summary="获取实盘策略详情")
async def get_instance(
    instance_id: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    inst = mgr.get_instance(instance_id)
    if not inst:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="实例不存在")
    return inst


@router.post("/{instance_id}/start", response_model=LiveInstanceInfo, summary="启动实盘策略")
async def start_instance(
    instance_id: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    try:
        return await mgr.start_instance(instance_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{instance_id}/stop", response_model=LiveInstanceInfo, summary="停止实盘策略")
async def stop_instance(
    instance_id: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    try:
        return await mgr.stop_instance(instance_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/start-all", response_model=LiveBatchResponse, summary="一键启动所有策略")
async def start_all(
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    return await mgr.start_all()


@router.post("/stop-all", response_model=LiveBatchResponse, summary="一键停止所有策略")
async def stop_all(
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    return await mgr.stop_all()


# ==================== 分析接口 ====================

def _get_strategy_log_dir(mgr: LiveTradingManager, instance_id: str) -> Path:
    """获取实例对应的策略最新日志目录"""
    inst = mgr.get_instance(instance_id)
    if not inst:
        raise HTTPException(status_code=404, detail="实例不存在")
    strategy_dir = STRATEGIES_DIR / inst["strategy_id"]
    log_dir = find_latest_log_dir(strategy_dir)
    if not log_dir:
        raise HTTPException(status_code=404, detail="暂无日志数据，请先运行策略")
    return log_dir


@router.get("/{instance_id}/detail", response_model=BacktestDetailResponse, summary="获取实盘策略分析详情")
async def get_live_detail(
    instance_id: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    inst = mgr.get_instance(instance_id)
    if not inst:
        raise HTTPException(status_code=404, detail="实例不存在")

    strategy_dir = STRATEGIES_DIR / inst["strategy_id"]
    log_result = parse_all_logs(strategy_dir)
    if not log_result:
        raise HTTPException(status_code=404, detail="暂无日志数据")

    # 构造与回测分析相同格式的响应
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


@router.get("/{instance_id}/kline", response_model=KlineWithSignalsResponse, summary="获取实盘策略K线数据")
async def get_live_kline(
    instance_id: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
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

    # 交易信号
    signals = []
    for t in trades_raw:
        if t.get("dtopen"):
            signals.append({"date": t["dtopen"], "type": "buy", "price": t.get("price", 0), "reason": "开仓"})
        if t.get("dtclose"):
            signals.append({"date": t["dtclose"], "type": "sell", "price": t.get("price", 0), "reason": "平仓"})

    indicators = log_indicators if log_indicators else {}

    return KlineWithSignalsResponse(
        symbol=inst["strategy_id"] if inst else "",
        klines=klines,
        signals=signals,
        indicators=indicators,
    )


@router.get("/{instance_id}/monthly-returns", response_model=MonthlyReturnsResponse, summary="获取实盘策略月度收益")
async def get_live_monthly_returns(
    instance_id: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    log_dir = _get_strategy_log_dir(mgr, instance_id)
    value_data = parse_value_log(log_dir)

    equity_dates = value_data.get("dates", [])
    equity_values = value_data.get("equity_curve", [])

    # 计算月度收益
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

    # 格式化
    returns = []
    years_set = set()
    for ym, ret in monthly_returns.items():
        parts = ym.split("-")
        y, m = int(parts[0]), int(parts[1])
        years_set.add(y)
        returns.append({"year": y, "month": m, "return_pct": ret})

    years = sorted(years_set)

    # 年度汇总
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
