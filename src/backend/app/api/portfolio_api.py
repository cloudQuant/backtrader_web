"""
组合管理 API 路由

聚合所有实盘交易策略实例的数据：
- 组合概览（总资产、总盈亏、策略分布）
- 汇总持仓（各策略当前持仓）
- 汇总交易（各策略历史交易记录）
- 组合资金曲线（各策略资金曲线叠加）
"""
import math
import logging
from collections import defaultdict
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException

from app.services.live_trading_manager import get_live_trading_manager, LiveTradingManager
from app.services.log_parser_service import (
    find_latest_log_dir,
    parse_value_log,
    parse_trade_log,
    parse_current_position,
    parse_all_logs,
)
from app.services.strategy_service import STRATEGIES_DIR
from app.api.deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_manager() -> LiveTradingManager:
    return get_live_trading_manager()


def _safe_round(v: float, n: int = 2) -> float:
    if math.isnan(v) or math.isinf(v):
        return 0.0
    return round(v, n)


# ---------- 组合概览 ----------

@router.get("/overview", summary="组合概览")
async def get_portfolio_overview(
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """
    返回组合级别的汇总数据:
    - total_assets: 组合总资产
    - total_cash: 总可用现金
    - total_position_value: 总持仓市值
    - total_pnl: 组合总盈亏
    - total_pnl_pct: 组合总收益率
    - total_initial_capital: 组合总初始资金
    - strategy_count: 策略实例数
    - running_count: 运行中实例数
    - strategies: 各策略的概要信息
    """
    instances = mgr.list_instances()

    total_assets = 0.0
    total_cash = 0.0
    total_initial = 0.0
    strategy_summaries = []

    for inst in instances:
        strategy_dir = STRATEGIES_DIR / inst["strategy_id"]
        log_dir = find_latest_log_dir(strategy_dir)
        if not log_dir:
            strategy_summaries.append({
                "id": inst["id"],
                "strategy_id": inst["strategy_id"],
                "strategy_name": inst.get("strategy_name", inst["strategy_id"]),
                "status": inst["status"],
                "total_assets": 0,
                "initial_capital": 0,
                "pnl": 0,
                "pnl_pct": 0,
                "total_trades": 0,
                "win_rate": 0,
            })
            continue

        value_data = parse_value_log(log_dir)
        equity = value_data.get("equity_curve", [])
        cash = value_data.get("cash_curve", [])
        trades = parse_trade_log(log_dir)

        initial = equity[0] if equity else 0
        final = equity[-1] if equity else 0
        final_cash = cash[-1] if cash else 0
        pnl = final - initial
        pnl_pct = (pnl / initial * 100) if initial > 0 else 0

        total_assets += final
        total_cash += final_cash
        total_initial += initial

        total_t = len(trades)
        win_t = len([t for t in trades if t.get("pnlcomm", 0) > 0])

        strategy_summaries.append({
            "id": inst["id"],
            "strategy_id": inst["strategy_id"],
            "strategy_name": inst.get("strategy_name", inst["strategy_id"]),
            "status": inst["status"],
            "total_assets": _safe_round(final),
            "initial_capital": _safe_round(initial),
            "pnl": _safe_round(pnl),
            "pnl_pct": _safe_round(pnl_pct, 2),
            "total_trades": total_t,
            "win_rate": _safe_round(win_t / total_t * 100 if total_t > 0 else 0, 1),
        })

    total_pnl = total_assets - total_initial
    total_pnl_pct = (total_pnl / total_initial * 100) if total_initial > 0 else 0
    running_count = sum(1 for i in instances if i["status"] == "running")

    return {
        "total_assets": _safe_round(total_assets),
        "total_cash": _safe_round(total_cash),
        "total_position_value": _safe_round(total_assets - total_cash),
        "total_initial_capital": _safe_round(total_initial),
        "total_pnl": _safe_round(total_pnl),
        "total_pnl_pct": _safe_round(total_pnl_pct, 2),
        "strategy_count": len(instances),
        "running_count": running_count,
        "strategies": strategy_summaries,
    }


# ---------- 汇总持仓 ----------

@router.get("/positions", summary="汇总持仓")
async def get_portfolio_positions(
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """
    返回各策略的当前持仓（来自 current_position.json）。
    """
    instances = mgr.list_instances()
    positions = []

    for inst in instances:
        strategy_dir = STRATEGIES_DIR / inst["strategy_id"]
        log_dir = find_latest_log_dir(strategy_dir)
        if not log_dir:
            continue

        cur_pos = parse_current_position(log_dir)
        for p in cur_pos:
            positions.append({
                "strategy_id": inst["strategy_id"],
                "strategy_name": inst.get("strategy_name", inst["strategy_id"]),
                "instance_id": inst["id"],
                "data_name": p["data_name"],
                "size": p["size"],
                "price": p["price"],
                "market_value": p["market_value"],
                "direction": "多" if p["size"] > 0 else ("空" if p["size"] < 0 else "空仓"),
            })

    return {"total": len(positions), "positions": positions}


# ---------- 汇总交易 ----------

@router.get("/trades", summary="汇总交易记录")
async def get_portfolio_trades(
    limit: int = 200,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """
    返回各策略的历史交易记录（来自 trade.log，仅已关闭交易），
    按平仓时间降序排列。
    """
    instances = mgr.list_instances()
    all_trades = []

    for inst in instances:
        strategy_dir = STRATEGIES_DIR / inst["strategy_id"]
        log_dir = find_latest_log_dir(strategy_dir)
        if not log_dir:
            continue

        trades = parse_trade_log(log_dir)
        for t in trades:
            t["strategy_id"] = inst["strategy_id"]
            t["strategy_name"] = inst.get("strategy_name", inst["strategy_id"])
            t["instance_id"] = inst["id"]
            all_trades.append(t)

    # 按平仓日期降序
    all_trades.sort(key=lambda x: x.get("dtclose", ""), reverse=True)

    return {"total": len(all_trades), "trades": all_trades[:limit]}


# ---------- 组合资金曲线 ----------

@router.get("/equity", summary="组合资金曲线")
async def get_portfolio_equity(
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """
    返回组合级别的资金曲线 — 将各策略的资金按日期对齐并叠加。
    同时返回每个策略的独立资金曲线用于堆叠图。
    """
    instances = mgr.list_instances()

    # 每个策略的 date -> value 映射
    strategy_curves: List[Dict[str, Any]] = []
    all_dates_set: set = set()

    for inst in instances:
        strategy_dir = STRATEGIES_DIR / inst["strategy_id"]
        log_dir = find_latest_log_dir(strategy_dir)
        if not log_dir:
            continue

        value_data = parse_value_log(log_dir)
        dates = value_data.get("dates", [])
        equity = value_data.get("equity_curve", [])
        cash = value_data.get("cash_curve", [])

        if not dates:
            continue

        date_map = {}
        for i, dt in enumerate(dates):
            date_map[dt] = {
                "equity": equity[i] if i < len(equity) else 0,
                "cash": cash[i] if i < len(cash) else 0,
            }
        all_dates_set.update(dates)

        strategy_curves.append({
            "strategy_id": inst["strategy_id"],
            "strategy_name": inst.get("strategy_name", inst["strategy_id"]),
            "instance_id": inst["id"],
            "date_map": date_map,
            "initial": equity[0] if equity else 0,
        })

    if not all_dates_set:
        return {"dates": [], "total_equity": [], "total_drawdown": [], "strategies": []}

    sorted_dates = sorted(all_dates_set)

    # 聚合
    total_equity = []
    strategy_series = {sc["instance_id"]: [] for sc in strategy_curves}

    for dt in sorted_dates:
        day_total = 0.0
        for sc in strategy_curves:
            dm = sc["date_map"]
            if dt in dm:
                val = dm[dt]["equity"]
            else:
                # 该策略在该日期无数据 — 使用最近已知值
                val = sc.get("_last", sc["initial"])
            sc["_last"] = val
            day_total += val
            strategy_series[sc["instance_id"]].append(_safe_round(val))
        total_equity.append(_safe_round(day_total))

    # 组合回撤
    total_drawdown = []
    peak = 0.0
    for v in total_equity:
        if v > peak:
            peak = v
        dd = -((peak - v) / peak) if peak > 0 else 0
        total_drawdown.append(_safe_round(dd, 6))

    strategies_out = []
    for sc in strategy_curves:
        strategies_out.append({
            "strategy_id": sc["strategy_id"],
            "strategy_name": sc["strategy_name"],
            "instance_id": sc["instance_id"],
            "values": strategy_series[sc["instance_id"]],
        })

    return {
        "dates": sorted_dates,
        "total_equity": total_equity,
        "total_drawdown": total_drawdown,
        "strategies": strategies_out,
    }


# ---------- 策略权重 / 资产配置 ----------

@router.get("/allocation", summary="策略资产配置")
async def get_portfolio_allocation(
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """
    返回各策略在组合中的资产占比（饼图数据）。
    """
    instances = mgr.list_instances()
    items = []
    total = 0.0

    for inst in instances:
        strategy_dir = STRATEGIES_DIR / inst["strategy_id"]
        log_dir = find_latest_log_dir(strategy_dir)
        if not log_dir:
            continue

        value_data = parse_value_log(log_dir)
        equity = value_data.get("equity_curve", [])
        final = equity[-1] if equity else 0
        total += final
        items.append({
            "strategy_id": inst["strategy_id"],
            "strategy_name": inst.get("strategy_name", inst["strategy_id"]),
            "instance_id": inst["id"],
            "value": _safe_round(final),
        })

    for item in items:
        item["weight"] = _safe_round(item["value"] / total * 100, 2) if total > 0 else 0

    return {"total": _safe_round(total), "items": items}
