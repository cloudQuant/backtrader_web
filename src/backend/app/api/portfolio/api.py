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
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.deps import get_current_user
from app.db.database import async_session_maker
from app.models.workspace import StrategyUnit, Workspace
from app.services import workspace_unit_runtime
from app.services.live_trading_manager import LiveTradingManager, get_live_trading_manager
from app.services.log_parser_service import (
    find_latest_log_dir,
    parse_current_position,
    parse_position_log,
    parse_trade_log,
    parse_value_log,
)
from app.services.strategy_service import get_strategy_dir

logger = logging.getLogger(__name__)
router = APIRouter()
_ACTIVE_TRADING_STATUSES = {"queued", "running"}


@dataclass
class _PortfolioSource:
    id: str
    strategy_id: str
    strategy_name: str
    status: str
    workspace_id: str | None = None
    log_dir: Path | None = None
    snapshot: dict[str, Any] | None = None


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


def _current_user_id(current_user: Any) -> str | None:
    user_id = str(getattr(current_user, "sub", None) or getattr(current_user, "id", "") or "")
    return user_id.strip() or None


def _list_user_instances(
    mgr: LiveTradingManager,
    current_user: Any,
) -> list[dict[str, Any]]:
    user_id = _current_user_id(current_user)
    try:
        return mgr.list_instances(user_id=user_id) if user_id else mgr.list_instances()
    except TypeError:
        return mgr.list_instances()


def _as_path(value: Any) -> Path | None:
    text = str(value or "").strip()
    return Path(text).expanduser() if text else None


def _resolve_instance_log_dir(inst: dict[str, Any]) -> Path | None:
    explicit_log_dir = _as_path(inst.get("log_dir"))
    if explicit_log_dir is not None and explicit_log_dir.is_dir():
        return explicit_log_dir

    runtime_dir = _as_path(inst.get("runtime_dir"))
    if runtime_dir is not None:
        latest = find_latest_log_dir(runtime_dir)
        if latest:
            return Path(latest)

    try:
        strategy_dir = Path(get_strategy_dir(inst["strategy_id"]))
    except ValueError:
        return None
    latest = find_latest_log_dir(strategy_dir)
    return Path(latest) if latest else None


def _source_from_instance(inst: dict[str, Any]) -> _PortfolioSource:
    return _PortfolioSource(
        id=str(inst.get("id") or ""),
        strategy_id=str(inst.get("strategy_id") or ""),
        strategy_name=str(inst.get("strategy_name") or inst.get("strategy_id") or ""),
        status=str(inst.get("status") or "unknown"),
        workspace_id=str(inst.get("workspace_id") or "") or None,
        log_dir=_resolve_instance_log_dir(inst),
        snapshot={},
    )


def _workspace_unit_log_dir(unit: StrategyUnit) -> Path | None:
    runtime_dir = workspace_unit_runtime.unit_dir(str(unit.workspace_id), str(unit.id))
    latest = find_latest_log_dir(runtime_dir)
    return Path(latest) if latest else None


async def _active_workspace_sources(current_user: Any) -> list[_PortfolioSource]:
    """Load active trading workspace units from the database.

    The live-trading manager is process-local. Stress supervisors and the API
    server can run in separate Python processes, so portfolio pages must be able
    to aggregate from persisted workspace unit state and runtime logs.
    """
    user_id = _current_user_id(current_user)
    if not user_id:
        return []

    async with async_session_maker() as session:
        result = await session.execute(
            select(StrategyUnit, Workspace)
            .join(Workspace, StrategyUnit.workspace_id == Workspace.id)
            .where(Workspace.user_id == user_id)
            .where(Workspace.workspace_type == "trading")
            .where(StrategyUnit.run_status.in_(_ACTIVE_TRADING_STATUSES))
            .order_by(Workspace.name, StrategyUnit.sort_order, StrategyUnit.strategy_name)
        )
        rows = result.all()

    sources: list[_PortfolioSource] = []
    for unit, workspace in rows:
        snapshot = unit.trading_snapshot if isinstance(unit.trading_snapshot, dict) else {}
        unit_name = str(unit.strategy_name or unit.strategy_id or unit.id)
        sources.append(
            _PortfolioSource(
                id=str(unit.trading_instance_id or unit.id),
                strategy_id=str(unit.strategy_id or unit.id),
                strategy_name=f"{workspace.name} / {unit_name}",
                status=str(unit.run_status or snapshot.get("instance_status") or "idle"),
                workspace_id=str(workspace.id),
                log_dir=_workspace_unit_log_dir(unit),
                snapshot=dict(snapshot),
            )
        )
    return sources


async def _portfolio_sources(
    current_user: Any,
    mgr: LiveTradingManager,
) -> list[_PortfolioSource]:
    workspace_sources = await _active_workspace_sources(current_user)
    if workspace_sources:
        return workspace_sources
    return [_source_from_instance(inst) for inst in _list_user_instances(mgr, current_user)]


def _latest_position_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest_by_key: dict[str, tuple[int, str, dict[str, Any]]] = {}
    for index, row in enumerate(rows):
        key = str(row.get("data_name") or row.get("symbol") or "").strip()
        if not key:
            continue
        timestamp = str(row.get("datetime") or row.get("dt") or "")
        current = latest_by_key.get(key)
        if current is None or (timestamp, index) >= (current[1], current[0]):
            latest_by_key[key] = (index, timestamp, row)
    return [item[2] for item in latest_by_key.values()]


def _parse_positions_for_portfolio(log_dir: Path) -> list[dict[str, Any]]:
    positions = _latest_position_rows(parse_position_log(log_dir))
    if positions:
        return positions
    return parse_current_position(log_dir)


def _snapshot_positions_for_portfolio(snapshot: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = list((snapshot or {}).get("positions") or [])
    positions: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_size = float(row.get("size") or 0.0)
        direction = str(row.get("direction") or "").strip().lower()
        if direction == "short":
            size = -abs(raw_size)
        elif direction == "flat":
            size = 0.0
        else:
            size = abs(raw_size)
        price = float(row.get("price") or row.get("avg_price") or 0.0)
        market_value = float(row.get("market_value") or row.get("value") or abs(size) * price)
        positions.append(
            {
                "data_name": str(row.get("data_name") or row.get("symbol") or ""),
                "size": size,
                "price": price,
                "market_value": market_value,
                "position_pnl": float(row.get("position_pnl") or row.get("pnl") or 0.0),
                "updated_at": _position_updated_at(row),
                "data_time": _position_data_time(row),
            }
        )
    return positions


def _source_positions(source: _PortfolioSource) -> list[dict[str, Any]]:
    if source.log_dir:
        return _parse_positions_for_portfolio(source.log_dir)
    return _snapshot_positions_for_portfolio(source.snapshot)


def _source_trades(source: _PortfolioSource) -> list[dict[str, Any]]:
    if source.log_dir:
        return parse_trade_log(source.log_dir)
    return [
        dict(item)
        for item in (source.snapshot or {}).get("trades") or []
        if isinstance(item, dict)
    ]


def _parse_query_ids(values: list[str] | None) -> set[str]:
    ids: set[str] = set()
    for value in values or []:
        ids.update(part.strip() for part in value.split(",") if part.strip())
    return ids


def _position_updated_at(row: dict[str, Any]) -> Any:
    return row.get("updated_at") or row.get("log_time") or row.get("datetime") or row.get("dt")


def _position_data_time(row: dict[str, Any]) -> Any:
    return row.get("data_time") or row.get("datetime") or row.get("dt")


def _empty_position_summary() -> dict[str, float | int]:
    return {
        "total_long_value": 0.0,
        "total_short_value": 0.0,
        "gross_market_value": 0.0,
        "net_market_value": 0.0,
        "total_pnl": 0.0,
        "long_count": 0,
        "short_count": 0,
        "flat_count": 0,
    }


def _build_position_summary(positions: list[dict[str, Any]]) -> dict[str, float | int]:
    summary = _empty_position_summary()

    for item in positions:
        size = float(item.get("size") or 0.0)
        market_value = abs(float(item.get("market_value") or 0.0))
        pnl = float(item.get("position_pnl") or item.get("pnl") or 0.0)

        if size > 0:
            summary["total_long_value"] += market_value
            summary["long_count"] += 1
        elif size < 0:
            summary["total_short_value"] += market_value
            summary["short_count"] += 1
        else:
            summary["flat_count"] += 1

        summary["total_pnl"] += pnl

    total_long = float(summary["total_long_value"])
    total_short = float(summary["total_short_value"])
    summary["total_long_value"] = _safe_round(total_long)
    summary["total_short_value"] = _safe_round(total_short)
    summary["gross_market_value"] = _safe_round(total_long + total_short)
    summary["net_market_value"] = _safe_round(total_long - total_short)
    summary["total_pnl"] = _safe_round(float(summary["total_pnl"]))
    return summary


def _signed_market_value(size: float, market_value: float) -> float:
    gross_value = abs(market_value)
    if size > 0:
        return gross_value
    if size < 0:
        return -gross_value
    return 0.0


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
    sources = await _portfolio_sources(current_user, mgr)

    total_assets = 0.0
    total_cash = 0.0
    total_initial = 0.0
    total_position_gross = 0.0
    total_position_net = 0.0
    has_position_data = False
    strategy_summaries = []

    for source in sources:
        log_dir = source.log_dir
        if not log_dir:
            strategy_summaries.append(
                {
                    "id": source.id,
                    "strategy_id": source.strategy_id,
                    "strategy_name": source.strategy_name,
                    "status": source.status,
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
        position_summary = _build_position_summary(_source_positions(source))
        has_source_positions = bool(
            position_summary["long_count"]
            or position_summary["short_count"]
            or position_summary["flat_count"]
        )

        initial = equity[0] if equity else 0
        final = equity[-1] if equity else 0
        final_cash = cash[-1] if cash else 0
        pnl = final - initial
        pnl_pct = (pnl / initial * 100) if initial > 0 else 0

        total_assets += final
        total_cash += final_cash
        total_initial += initial
        if has_source_positions:
            has_position_data = True
            total_position_gross += float(position_summary["gross_market_value"])
            total_position_net += float(position_summary["net_market_value"])

        total_t = len(trades)
        win_t = len([t for t in trades if t.get("pnlcomm", 0) > 0])

        strategy_summaries.append(
            {
                "id": source.id,
                "strategy_id": source.strategy_id,
                "strategy_name": source.strategy_name,
                "status": source.status,
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
    running_count = sum(1 for source in sources if source.status == "running")
    fallback_net_position = total_assets - total_cash
    if not has_position_data:
        total_position_gross = abs(fallback_net_position)
        total_position_net = fallback_net_position

    return {
        "total_assets": _safe_round(total_assets),
        "total_cash": _safe_round(total_cash),
        "total_position_value": _safe_round(total_position_gross),
        "net_position_value": _safe_round(total_position_net),
        "total_initial_capital": _safe_round(total_initial),
        "total_pnl": _safe_round(total_pnl),
        "total_pnl_pct": _safe_round(total_pnl_pct, 2),
        "strategy_count": len(sources),
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
    sources = await _portfolio_sources(current_user, mgr)
    positions = []

    for source in sources:
        cur_pos = _source_positions(source)
        for p in cur_pos:
            size = float(p.get("size") or 0.0)
            price = float(p.get("price") or 0.0)
            market_value = float(p.get("market_value") or 0.0)
            latest_price = (
                abs(market_value) / abs(size) if abs(size) > 0 and market_value else price
            )
            position_pnl = float(
                p.get("position_pnl")
                if p.get("position_pnl") is not None
                else (
                    p.get("pnl")
                    if p.get("pnl") is not None
                    else (latest_price - price) * size
                )
            )
            positions.append(
                {
                    "strategy_id": source.strategy_id,
                    "strategy_name": source.strategy_name,
                    "instance_id": source.id,
                    "data_name": str(p.get("data_name") or ""),
                    "size": size,
                    "price": price,
                    "latest_price": _safe_round(latest_price, 4),
                    "market_value": _safe_round(abs(market_value), 6),
                    "signed_market_value": _safe_round(
                        _signed_market_value(size, market_value), 6
                    ),
                    "position_pnl": _safe_round(position_pnl),
                    "updated_at": _position_updated_at(p),
                    "data_time": _position_data_time(p),
                    "direction": "long"
                    if size > 0
                    else ("short" if size < 0 else "flat"),
                }
            )

    return {
        "total": len(positions),
        "positions": positions,
        "summary": _build_position_summary(positions),
    }


# ---------- Aggregated Trades ----------


@router.get("/trades", summary="Aggregated trade records (live trading)")
async def get_portfolio_trades(
    limit: int = 200,
    workspace_ids: Annotated[list[str] | None, Query()] = None,
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
    sources = await _portfolio_sources(current_user, mgr)
    workspace_id_set = _parse_query_ids(workspace_ids)
    if workspace_id_set:
        sources = [source for source in sources if source.workspace_id in workspace_id_set]
    all_trades = []

    for source in sources:
        trades = _source_trades(source)
        for t in trades:
            item = dict(t)
            item["strategy_id"] = source.strategy_id
            item["strategy_name"] = source.strategy_name
            item["instance_id"] = source.id
            all_trades.append(item)

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
    sources = await _portfolio_sources(current_user, mgr)

    # Each strategy's date -> value mapping
    strategy_curves: list[dict[str, Any]] = []
    all_dates_set: set = set()

    for source in sources:
        log_dir = source.log_dir
        if not log_dir:
            continue

        value_data = parse_value_log(log_dir)
        dates = value_data.get("datetimes") or value_data.get("dates", [])
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
                "strategy_id": source.strategy_id,
                "strategy_name": source.strategy_name,
                "instance_id": source.id,
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
    sources = await _portfolio_sources(current_user, mgr)
    items = []
    total = 0.0

    for source in sources:
        log_dir = source.log_dir
        if not log_dir:
            continue

        value_data = parse_value_log(log_dir)
        equity = value_data.get("equity_curve", [])
        final = equity[-1] if equity else 0
        total += final
        items.append(
            {
                "strategy_id": source.strategy_id,
                "strategy_name": source.strategy_name,
                "instance_id": source.id,
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
    workspace_ids: Annotated[list[str] | None, Query()] = None,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Simulation historical trades across strategies.

    See `get_portfolio_trades` for field details.
    """
    return await get_portfolio_trades(
        limit=limit,
        workspace_ids=workspace_ids,
        current_user=current_user,
        mgr=mgr,
    )


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
