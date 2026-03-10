"""
Portfolio management API routes.

Aggregates data across live trading strategy instances:
- Portfolio overview (total assets, PnL, strategy distribution)
- Aggregated positions (current positions per strategy)
- Aggregated trades (historical trades per strategy)
- Portfolio equity curve (stacked equity across strategies)
"""

import logging
import math
from typing import Any, Dict, List

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.services.live_trading_manager import LiveTradingManager, get_live_trading_manager
from app.services.log_parser_service import (
    find_latest_log_dir,
    parse_current_position,
    parse_trade_log,
    parse_value_log,
)
from app.services.strategy_service import get_strategy_dir

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_manager() -> LiveTradingManager:
    """Get the live trading manager instance.

    Returns:
        LiveTradingManager: The live trading manager singleton instance.
    """
    return get_live_trading_manager()


def _safe_round(v: float, n: int = 2) -> float:
    """Safely round a float value, handling NaN and Infinity.

    Args:
        v: The value to round.
        n: Number of decimal places.

    Returns:
        The rounded value, or 0.0 if the value is NaN or Infinity.
    """
    if math.isnan(v) or math.isinf(v):
        return 0.0
    return round(v, n)


# ---------- Portfolio Overview ----------

# NOTE:
# The "simulation" variants below currently reuse the same aggregation logic as the
# live trading endpoints. If simulation instances are later stored separately from
# live instances, the underlying data source can be adjusted while keeping the
# API surface stable.


@router.get("/overview", summary="Portfolio overview (live trading)")
async def get_portfolio_overview(
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Return portfolio-level aggregated metrics.

    Aggregates data across all live trading instances including total assets,
    cash, PnL, and per-strategy summaries.

    Args:
        current_user: The authenticated user.
        mgr: The live trading manager.

    Returns:
        A dictionary containing portfolio overview metrics including:
            - total_assets: Total portfolio value
            - total_cash: Total cash across all strategies
            - total_position_value: Total value of open positions
            - total_initial_capital: Total initial capital
            - total_pnl: Total profit/loss
            - total_pnl_pct: Total PnL percentage
            - strategy_count: Number of strategies
            - running_count: Number of running strategies
            - strategies: List of per-strategy summaries
    """
    instances = mgr.list_instances()

    total_assets = 0.0
    total_cash = 0.0
    total_initial = 0.0
    strategy_summaries = []

    for inst in instances:
        try:
            strategy_dir = get_strategy_dir(inst["strategy_id"])
        except ValueError:
            log_dir = None
        else:
            log_dir = find_latest_log_dir(strategy_dir)
        if not log_dir:
            strategy_summaries.append(
                {
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
                }
            )
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

        strategy_summaries.append(
            {
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
            }
        )

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


# ---------- Aggregated Positions ----------


@router.get("/positions", summary="Aggregated positions (live trading)")
async def get_portfolio_positions(
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Return current positions across strategies (from current_position.json).

    Args:
        current_user: The authenticated user.
        mgr: The live trading manager.

    Returns:
        A dictionary containing total count and list of positions with:
            - strategy_id: The strategy identifier
            - strategy_name: The strategy display name
            - instance_id: The instance identifier
            - data_name: The symbol/instrument name
            - size: Position size (positive for long, negative for short)
            - price: Average entry price
            - market_value: Current market value
            - direction: Position direction ("long", "short", or "flat")
    """
    instances = mgr.list_instances()
    positions = []

    for inst in instances:
        try:
            strategy_dir = get_strategy_dir(inst["strategy_id"])
        except ValueError:
            continue
        log_dir = find_latest_log_dir(strategy_dir)
        if not log_dir:
            continue

        cur_pos = parse_current_position(log_dir)
        for p in cur_pos:
            positions.append(
                {
                    "strategy_id": inst["strategy_id"],
                    "strategy_name": inst.get("strategy_name", inst["strategy_id"]),
                    "instance_id": inst["id"],
                    "data_name": p["data_name"],
                    "size": p["size"],
                    "price": p["price"],
                    "market_value": p["market_value"],
                    "direction": "long"
                    if p["size"] > 0
                    else ("short" if p["size"] < 0 else "flat"),
                }
            )

    return {"total": len(positions), "positions": positions}


# ---------- Aggregated Trades ----------


@router.get("/trades", summary="Aggregated trade records (live trading)")
async def get_portfolio_trades(
    limit: int = 200,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Return historical trades across strategies (from trade.log), sorted by close time.

    Args:
        limit: Maximum number of trades to return.
        current_user: The authenticated user.
        mgr: The live trading manager.

    Returns:
        A dictionary containing total count and list of trades, sorted by
        close date in descending order (most recent first).
    """
    instances = mgr.list_instances()
    all_trades = []

    for inst in instances:
        try:
            strategy_dir = get_strategy_dir(inst["strategy_id"])
        except ValueError:
            continue
        log_dir = find_latest_log_dir(strategy_dir)
        if not log_dir:
            continue

        trades = parse_trade_log(log_dir)
        for t in trades:
            t["strategy_id"] = inst["strategy_id"]
            t["strategy_name"] = inst.get("strategy_name", inst["strategy_id"])
            t["instance_id"] = inst["id"]
            all_trades.append(t)

    # Sort by close date descending
    all_trades.sort(key=lambda x: x.get("dtclose", ""), reverse=True)

    return {"total": len(all_trades), "trades": all_trades[:limit]}


# ---------- Portfolio Equity Curve ----------


@router.get("/equity", summary="Portfolio equity curve (live trading)")
async def get_portfolio_equity(
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Return portfolio-level equity curve - aligning and stacking strategy equity by date.

    Also returns individual strategy equity curves for stacked chart visualization.

    Args:
        current_user: The authenticated user.
        mgr: The live trading manager.

    Returns:
        A dictionary containing:
            - dates: List of all dates across strategies
            - total_equity: Portfolio total equity per date
            - total_drawdown: Portfolio drawdown per date
            - strategies: List of per-strategy equity curves
    """
    instances = mgr.list_instances()

    # Each strategy's date -> value mapping
    strategy_curves: List[Dict[str, Any]] = []
    all_dates_set: set = set()

    for inst in instances:
        try:
            strategy_dir = get_strategy_dir(inst["strategy_id"])
        except ValueError:
            continue
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

        strategy_curves.append(
            {
                "strategy_id": inst["strategy_id"],
                "strategy_name": inst.get("strategy_name", inst["strategy_id"]),
                "instance_id": inst["id"],
                "date_map": date_map,
                "initial": equity[0] if equity else 0,
            }
        )

    if not all_dates_set:
        return {"dates": [], "total_equity": [], "total_drawdown": [], "strategies": []}

    sorted_dates = sorted(all_dates_set)

    # Aggregate
    total_equity = []
    strategy_series = {sc["instance_id"]: [] for sc in strategy_curves}

    for dt in sorted_dates:
        day_total = 0.0
        for sc in strategy_curves:
            dm = sc["date_map"]
            if dt in dm:
                val = dm[dt]["equity"]
            else:
                # No data for this strategy on this date - use last known value
                val = sc.get("_last", sc["initial"])
            sc["_last"] = val
            day_total += val
            strategy_series[sc["instance_id"]].append(_safe_round(val))
        total_equity.append(_safe_round(day_total))

    # Portfolio drawdown
    total_drawdown = []
    peak = 0.0
    for v in total_equity:
        if v > peak:
            peak = v
        dd = -((peak - v) / peak) if peak > 0 else 0
        total_drawdown.append(_safe_round(dd, 6))

    strategies_out = []
    for sc in strategy_curves:
        strategies_out.append(
            {
                "strategy_id": sc["strategy_id"],
                "strategy_name": sc["strategy_name"],
                "instance_id": sc["instance_id"],
                "values": strategy_series[sc["instance_id"]],
            }
        )

    return {
        "dates": sorted_dates,
        "total_equity": total_equity,
        "total_drawdown": total_drawdown,
        "strategies": strategies_out,
    }


# ---------- Strategy Weights / Asset Allocation ----------


@router.get("/allocation", summary="Strategy asset allocation (live trading)")
async def get_portfolio_allocation(
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Return the asset allocation percentage of each strategy in the portfolio.

    Returns pie chart data showing the value distribution across strategies.

    Args:
        current_user: The authenticated user.
        mgr: The live trading manager.

    Returns:
        A dictionary containing:
            - total: Total portfolio value
            - items: List of allocation items with strategy_id, strategy_name,
                instance_id, value, and weight percentage
    """
    instances = mgr.list_instances()
    items = []
    total = 0.0

    for inst in instances:
        try:
            strategy_dir = get_strategy_dir(inst["strategy_id"])
        except ValueError:
            continue
        log_dir = find_latest_log_dir(strategy_dir)
        if not log_dir:
            continue

        value_data = parse_value_log(log_dir)
        equity = value_data.get("equity_curve", [])
        final = equity[-1] if equity else 0
        total += final
        items.append(
            {
                "strategy_id": inst["strategy_id"],
                "strategy_name": inst.get("strategy_name", inst["strategy_id"]),
                "instance_id": inst["id"],
                "value": _safe_round(final),
            }
        )

    for item in items:
        item["weight"] = _safe_round(item["value"] / total * 100, 2) if total > 0 else 0

    return {"total": _safe_round(total), "items": items}


# =====================================================================
# Simulation trading variants
# =====================================================================


@router.get("/simulation/overview", summary="Portfolio overview (simulation trading)")
async def get_simulation_portfolio_overview(
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Simulation portfolio overview.

    Currently reuses the same aggregation logic as live trading. This keeps the
    API stable for the frontend while allowing the underlying data source to be
    customized later if simulation instances are stored separately.
    """
    # Reuse the same logic as get_portfolio_overview for now
    return await get_portfolio_overview(current_user=current_user, mgr=mgr)


@router.get("/simulation/positions", summary="Aggregated positions (simulation trading)")
async def get_simulation_portfolio_positions(
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Simulation current positions across strategies.

    See `get_portfolio_positions` for field details.
    """
    return await get_portfolio_positions(current_user=current_user, mgr=mgr)


@router.get("/simulation/trades", summary="Aggregated trade records (simulation trading)")
async def get_simulation_portfolio_trades(
    limit: int = 200,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Simulation historical trades across strategies.

    See `get_portfolio_trades` for field details.
    """
    return await get_portfolio_trades(limit=limit, current_user=current_user, mgr=mgr)


@router.get("/simulation/equity", summary="Portfolio equity curve (simulation trading)")
async def get_simulation_portfolio_equity(
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Simulation portfolio-level equity curve.

    See `get_portfolio_equity` for field details.
    """
    return await get_portfolio_equity(current_user=current_user, mgr=mgr)


@router.get(
    "/simulation/allocation",
    summary="Strategy asset allocation (simulation trading)",
)
async def get_simulation_portfolio_allocation(
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Simulation asset allocation across strategies.

    See `get_portfolio_allocation` for field details.
    """
    return await get_portfolio_allocation(current_user=current_user, mgr=mgr)
