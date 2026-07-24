"""
Portfolio management API routes.

Aggregates data across live trading strategy instances:
- Portfolio overview (total assets, PnL, strategy distribution)
- Aggregated positions (current positions per strategy)
- Aggregated trades (historical trades per strategy)
- Portfolio equity curve (stacked equity across strategies)
"""

import json
import logging
import math
import os
import sys
import typing
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.deps import get_current_user
from app.db.database import async_session_maker
from app.models.paper_runtime import PaperEquitySnapshot
from app.models.workspace import StrategyUnit, Workspace
from app.services import workspace_unit_runtime
from app.services.live_trading_manager import LiveTradingManager, get_live_trading_manager
from app.services.log_parser.normalize import normalize_dt_text
from app.services.log_parser_service import (
    find_latest_log_dir,
    parse_current_position,
    parse_position_log,
    parse_run_info,
    parse_trade_log,
    parse_value_log,
)
from app.services.position_valuation import EPSILON, contract_spec_for, value_position
from app.services.strategy_service import get_strategy_dir
from app.services.trading_asset_info_service import (
    gateway_position_symbol,
    load_runtime_config,
    normalize_gateway_position,
    query_local_asset_spec,
    signed_gateway_size,
    split_bidirectional_position_row,
    symbol_aliases,
)

logger = logging.getLogger(__name__)
router = APIRouter()
_ACTIVE_TRADING_STATUSES = {"queued", "running"}
_PORTFOLIO_TIMEZONE = ZoneInfo("Asia/Shanghai")
_COMMISSION_FIELD_KEYS = (
    "commission",
    "comm",
    "commissionAmount",
    "fee",
    "fees",
    "feeAmount",
    "execFee",
    "exec_fee",
    "execFeeV2",
    "exec_fee_v2",
    "execCommission",
    "exec_commission",
    "open_fee",
    "openFee",
    "open_commission",
    "openCommission",
    "positionCommission",
    "position_fee",
    "position_commission",
    "tradeFee",
    "trade_fee",
    "trade_commission",
    "broker_commission",
    "brokerCommission",
    "commission_amount",
    "Commission",
)
_GROSS_PNL_FIELD_KEYS = (
    "gross_pnl",
    "position_unrealized_pnl",
    "position_unrealised_pnl",
    "position_profit",
    "PositionProfit",
    "unrealized_profit",
    "unrealised_profit",
    "unrealizedProfit",
    "unrealisedProfit",
    "unRealizedProfit",
    "UnrealizedPnL",
    "unrealizedPnl",
    "unrealisedPnl",
    "unrealized_pnl",
    "unrealised_pnl",
    "unrealizedPNL",
    "unrealisedPNL",
    "unrealizedpnl",
    "unrealisedpnl",
    "floating_pnl",
    "position_pnl",
    "profit",
    "upl",
    "up",
)
_EXPLICIT_NET_PNL_FIELD_KEYS = (
    "pnlcomm",
    "net_pnl",
    "netPnl",
    "netPNL",
    "net_position_pnl",
    "netPositionPnl",
    "netPositionPNL",
    "net_unrealized_pnl",
    "netUnrealizedPnl",
    "netUnrealizedPNL",
    "unrealized_pnl_after_fee",
    "unrealizedPnlAfterFee",
    "position_pnl_after_fee",
    "positionPnlAfterFee",
)
_ASSET_SPEC_CONTRACT_KEYS = frozenset(
    {
        "multiplier",
        "mult",
        "contract_size",
        "trade_contract_size",
        "contract_multiplier",
        "ctVal",
        "VolumeMultiple",
        "CONTRACT_MULTIPLIER",
    }
)
_ASSET_SPEC_MARGIN_KEYS = frozenset(
    {
        "margin",
        "margin_rate",
        "margin_ratio",
        "leverage",
        "margin_amount",
        "initial_margin_per_lot",
        "margin_initial",
        "long_margin_rate",
        "short_margin_rate",
        "LongMarginRatio",
        "ShortMarginRatio",
        "LongMarginRatioByMoney",
        "ShortMarginRatioByMoney",
        "MARGIN_BUY",
        "MARGIN_SELL",
        "long_margin_amount",
        "short_margin_amount",
        "LongMarginRatioByVolume",
        "ShortMarginRatioByVolume",
        "MARGIN_PER_LOT",
        "LONG_MARGIN_AMOUNT",
        "SHORT_MARGIN_AMOUNT",
    }
)
_ASSET_SPEC_FEE_KEYS = frozenset(
    {
        "commission",
        "commission_rate",
        "open_commission_rate",
        "close_commission_rate",
        "close_today_commission_rate",
        "maker_commission_rate",
        "taker_commission_rate",
        "commission_amount",
        "open_commission_amount",
        "close_commission_amount",
        "close_today_commission_amount",
        "OpenRatioByMoney",
        "CloseRatioByMoney",
        "CloseTodayRatioByMoney",
        "OpenRatioByVolume",
        "CloseRatioByVolume",
        "CloseTodayRatioByVolume",
    }
)
_ASSET_SPEC_AUX_KEYS = frozenset(
    {
        "symbol",
        "data_name",
        "instrument",
        "InstrumentID",
        "exchange",
        "exchange_id",
        "asset_type",
        "instType",
        "contract_type",
        "ctType",
        "base_asset",
        "baseCcy",
        "quote_asset",
        "quoteCcy",
        "settle_currency",
        "settleCcy",
        "fee_currency",
        "feeCcy",
        "current_price",
        "latest_price",
        "last_price",
        "mark_price",
        "price_tick",
        "tick_size",
        "tickSz",
        "min_order_size",
        "min_qty",
        "minSz",
        "max_order_size",
        "max_qty",
        "maxLmtSz",
        "order_size_step",
        "lotSz",
    }
)


@dataclass
class _PortfolioSource:
    id: str
    strategy_id: str
    strategy_name: str
    status: str
    symbol: str = ""
    unit_id: str | None = None
    workspace_id: str | None = None
    trading_mode: str = "paper"
    log_dir: Path | None = None
    snapshot: dict[str, Any] | None = None
    live_positions: list[dict[str, Any]] | None = None
    live_account: dict[str, Any] | None = None
    resolved_asset_specs: dict[str, dict[str, Any]] = field(default_factory=dict)
    valuation_configs: tuple[dict[str, Any], ...] = ()
    position_source: str | None = None
    account_source: str | None = None
    asset_spec_source: str | None = None
    valuation_status: str = "empty"
    valuation_warnings: list[str] = field(default_factory=list)
    pid: int | None = None
    started_at: str | None = None
    updated_at: str | None = None


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


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _coerce_started_day(value: Any) -> str | None:
    text = normalize_dt_text(value).strip()
    if not text:
        return None
    return text[:10]


def _infer_started_day_from_pid(pid: int) -> str | None:
    if pid <= 0:
        return None
    if sys.platform == "win32":
        return None

    stat_path = Path(f"/proc/{pid}/stat")
    if not stat_path.is_file():
        return None

    try:
        stat_text = stat_path.read_text(encoding="utf-8")
        close_paren = stat_text.rfind(")")
        if close_paren < 0:
            return None
        parts = stat_text[close_paren + 2 :].split()
        if len(parts) < 20:
            return None
        start_ticks = int(parts[19])
    except (OSError, ValueError):
        return None

    try:
        with Path("/proc/stat").open(encoding="utf-8") as handle:
            boot_time: float | None = None
            for line in handle:
                if not line.startswith("btime"):
                    continue
                boot_time = float(line.split()[1])
                break
    except OSError:
        return None
    if boot_time is None:
        return None

    try:
        clock_ticks = os.sysconf("SC_CLK_TCK")
        epoch_seconds = boot_time + start_ticks / clock_ticks
        return datetime.fromtimestamp(epoch_seconds).strftime("%Y-%m-%d")
    except (AttributeError, OSError, ValueError):
        return None


def _infer_started_day_from_log_dir(
    log_dir: Path,
    *,
    allow_mtime_fallback: bool = True,
) -> str | None:
    if not log_dir.is_dir():
        return None

    # Prefer an explicit run-level timestamp if strategy runtime persisted it.
    run_info = parse_run_info(log_dir)
    started_day = _coerce_started_day(
        run_info.get("started_at")
        or run_info.get("start_time")
        or run_info.get("startedAt")
        or run_info.get("startTime")
    )
    value_log = log_dir / "value.log"
    if not value_log.is_file():
        return None
    value_data = parse_value_log(log_dir, prefer_log_time=True)
    dates = list(value_data.get("dates", []))
    try:
        mtime_day = _coerce_started_day(
            datetime.fromtimestamp(value_log.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        )
        if not mtime_day:
            return None
    except OSError:
        return None
    if not dates:
        return None
    sorted_dates = sorted(dates)
    latest_date = sorted_dates[-1]
    if started_day and mtime_day <= started_day:
        return started_day
    if mtime_day <= latest_date:
        for dt in sorted_dates:
            if dt >= mtime_day:
                return dt
        return latest_date
    if mtime_day > latest_date:
        if allow_mtime_fallback:
            return mtime_day
        return latest_date
    return latest_date


def _trading_day(value: Any) -> str:
    """Return a timestamp's calendar day in the portfolio's local timezone."""
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text[:10]
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(_PORTFOLIO_TIMEZONE)
    return parsed.date().isoformat()


def _source_started_day(source: _PortfolioSource) -> str | None:
    """Return the source start day when available."""
    snapshot = _safe_dict(source.snapshot)
    explicit_started_day = (
        _coerce_started_day(source.started_at)
        or _coerce_started_day(snapshot.get("started_at"))
        or _coerce_started_day(snapshot.get("instance_started_at"))
        or _coerce_started_day(snapshot.get("start_time"))
        or _coerce_started_day(snapshot.get("startedAt"))
    )

    if str(source.status or "").strip().lower() not in _ACTIVE_TRADING_STATUSES:
        return explicit_started_day

    inferred_started_days: list[str] = []
    updated_started_day = _coerce_started_day(source.updated_at)
    if updated_started_day:
        inferred_started_days.append(updated_started_day)
    if source.pid:
        pid_started = _infer_started_day_from_pid(source.pid)
        if pid_started:
            inferred_started_days.append(pid_started)

    if source.log_dir:
        inferred_started = _infer_started_day_from_log_dir(
            source.log_dir,
            allow_mtime_fallback=source.pid is not None,
        )
        if inferred_started:
            inferred_started_days.append(inferred_started)

    if inferred_started_days:
        return max(inferred_started_days)
    return explicit_started_day


def _row_date(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = row.get(key)
        text = _trading_day(value)
        if text:
            return text
    return ""


def _filter_rows_after_source_start(
    rows: list[dict[str, Any]],
    source_started_day: str | None,
    keys: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Drop log rows that start before the active process start."""
    if not source_started_day:
        return rows

    started_day = _trading_day(source_started_day)
    if not started_day:
        return rows

    filtered: list[dict[str, Any]] = []
    for row in rows:
        dt = _row_date(row, keys)
        if not dt or dt >= started_day:
            filtered.append(row)
    return filtered


def _trim_curve_by_source_start(
    dates: list[str],
    equity: list[float],
    cash: list[float],
    source_started_day: str | None,
) -> tuple[list[str], list[float], list[float]]:
    if not source_started_day:
        return dates, equity, cash

    filtered_dates: list[str] = []
    filtered_equity: list[float] = []
    filtered_cash: list[float] = []
    for dt, value, cash_value in zip(dates, equity, cash, strict=False):
        if dt >= source_started_day:
            filtered_dates.append(dt)
            filtered_equity.append(value)
            filtered_cash.append(cash_value)
    return filtered_dates, filtered_equity, filtered_cash


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe_value(item) for item in value]
    return value


def _leverage_from_margin_rate(value: Any) -> float | None:
    margin_rate = _safe_float(value)
    if margin_rate <= EPSILON:
        return None
    return round(1.0 / margin_rate, 8)


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _unique_text(values: list[Any]) -> str | None:
    texts = [str(value or "").strip() for value in values]
    unique = sorted({text for text in texts if text})
    if not unique:
        return None
    if len(unique) == 1:
        return unique[0]
    return "mixed"


def _append_unique(target: list[str], *values: Any) -> None:
    seen = set(target)
    for value in values:
        if isinstance(value, (list, tuple, set)):
            _append_unique(target, *value)
            seen = set(target)
            continue
        text = str(value or "").strip()
        if text and text not in seen:
            target.append(text)
            seen.add(text)


def _has_any(row: dict[str, Any], *keys: str) -> bool:
    return any(row.get(key) not in (None, "") for key in keys)


def _first_number(row: dict[str, Any] | None, *keys: str) -> float | None:
    if not isinstance(row, dict):
        return None
    for key in keys:
        value = row.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, dict):
            nested_value = None
            for nested_key in ("amount", "value", "balance", "total"):
                candidate = value.get(nested_key)
                if candidate not in (None, ""):
                    nested_value = candidate
                    break
            if nested_value in (None, ""):
                continue
            value = nested_value
        if isinstance(value, str):
            value = value.strip().replace(",", "")
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _current_user_id(current_user: Any) -> str | None:
    user_id = str(getattr(current_user, "sub", None) or getattr(current_user, "id", "") or "")
    return user_id.strip() or None


def _list_user_instances(
    mgr: LiveTradingManager,
    current_user: Any,
    *,
    include_inactive: bool = False,
) -> list[dict[str, Any]]:
    user_id = _current_user_id(current_user)
    try:
        instances = mgr.list_instances(user_id=user_id) if user_id else mgr.list_instances()
    except TypeError:
        instances = mgr.list_instances()
    normalized: list[dict[str, Any]] = []
    for inst in instances:
        if not isinstance(inst, dict):
            continue
        status = str(inst.get("status") or "").strip().lower()
        instance_id = str(inst.get("id") or "").strip()
        if not instance_id or not status:
            if include_inactive:
                normalized.append(inst)
            continue
        effective = inst
        if status in _ACTIVE_TRADING_STATUSES and hasattr(mgr, "get_instance"):
            try:
                live_instance = mgr.get_instance(instance_id, user_id=user_id)
            except Exception:
                live_instance = None
            if isinstance(live_instance, dict):
                merged = dict(inst)
                merged_status = str(live_instance.get("status") or "").strip().lower()
                if merged_status:
                    status = merged_status
                    merged["status"] = merged_status
                merged_started = str(live_instance.get("started_at") or "").strip()
                if merged_started:
                    merged["started_at"] = merged_started
                merged_updated = str(live_instance.get("updated_at") or "").strip()
                if merged_updated:
                    merged["updated_at"] = merged_updated
                live_pid = _coerce_int(live_instance.get("pid"))
                if live_pid is not None:
                    merged["pid"] = live_pid
                effective = merged
                if include_inactive is False and merged_status not in _ACTIVE_TRADING_STATUSES:
                    continue
        elif not include_inactive and status not in _ACTIVE_TRADING_STATUSES:
            continue
        normalized.append(effective)
    if include_inactive:
        return normalized
    return [inst for inst in normalized if str(inst.get("status") or "").strip().lower() in _ACTIVE_TRADING_STATUSES]


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


def _runtime_config_for_instance(inst: dict[str, Any]) -> dict[str, Any]:
    runtime_dir = _as_path(inst.get("runtime_dir"))
    if runtime_dir is not None:
        config = load_runtime_config(runtime_dir)
        if config:
            return config
    try:
        strategy_dir = Path(get_strategy_dir(inst["strategy_id"]))
    except ValueError:
        return {}
    return load_runtime_config(strategy_dir)


def _source_from_instance(inst: dict[str, Any]) -> _PortfolioSource:
    params = inst.get("params") if isinstance(inst.get("params"), dict) else {}
    runtime_config = _runtime_config_for_instance(inst)
    return _PortfolioSource(
        id=str(inst.get("id") or ""),
        strategy_id=str(inst.get("strategy_id") or ""),
        strategy_name=str(inst.get("strategy_name") or inst.get("strategy_id") or ""),
        status=str(inst.get("status") or "unknown"),
        symbol=str(params.get("symbol") or ""),
        trading_mode=str(params.get("trading_mode") or "paper"),
        workspace_id=str(inst.get("workspace_id") or "") or None,
        log_dir=_resolve_instance_log_dir(inst),
        snapshot={},
        valuation_configs=(
            _safe_dict(runtime_config),
            _safe_dict(params),
            _safe_dict(params.get("unit_settings")),
            _safe_dict(params.get("data_config")),
            _safe_dict(params.get("gateway")),
            _safe_dict(params.get("simulate")),
            _safe_dict(params.get("backtest")),
            _safe_dict(params.get("live")),
        ),
        started_at=str(inst.get("started_at") or "").strip() or None,
        updated_at=_coerce_started_day(inst.get("updated_at")),
        pid=_coerce_int(inst.get("pid")),
    )


def _workspace_unit_log_dir(unit: StrategyUnit) -> Path | None:
    runtime_dir = workspace_unit_runtime.unit_dir(str(unit.workspace_id), str(unit.id))
    latest = find_latest_log_dir(runtime_dir)
    return Path(latest) if latest else None


def _workspace_unit_runtime_config(unit: StrategyUnit) -> dict[str, Any]:
    runtime_dir = workspace_unit_runtime.unit_dir(str(unit.workspace_id), str(unit.id))
    return load_runtime_config(runtime_dir)


def _manager_instances_by_id(
    mgr: LiveTradingManager,
    user_id: str | None,
    instance_ids: list[str],
) -> dict[str, dict[str, Any]] | None:
    """Load one process-validated instance snapshot for a portfolio refresh.

    ``LiveTradingManager.get_instance`` validates a process by scanning the OS
    process list. Calling it once per workspace unit turns a first-screen
    portfolio refresh into hundreds of identical process scans. Its selected
    instance API scans processes once without walking every persisted strategy
    directory, then returns only the workspace instances requested here.

    ``None`` intentionally preserves the per-instance compatibility path for
    lightweight manager fakes and unexpected manager failures.
    """
    get_active_instances = getattr(mgr, "get_active_instances", None)
    if callable(get_active_instances):
        try:
            instances = get_active_instances(instance_ids, user_id=user_id)
        except TypeError:
            try:
                instances = get_active_instances(instance_ids)
            except Exception:
                instances = None
        except Exception:
            instances = None
        if instances is not None:
            return {
                str(instance.get("id") or "").strip(): instance
                for instance in instances
                if isinstance(instance, dict) and str(instance.get("id") or "").strip()
            }

    list_instances = getattr(mgr, "list_instances", None)
    if not callable(list_instances):
        return None
    try:
        instances = list_instances(user_id=user_id) if user_id else list_instances()
    except TypeError:
        try:
            instances = list_instances()
        except Exception:
            return None
    except Exception:
        return None

    return {
        str(instance.get("id") or "").strip(): instance
        for instance in instances
        if isinstance(instance, dict) and str(instance.get("id") or "").strip()
    }


async def _active_workspace_sources(
    current_user: Any,
    mgr: LiveTradingManager,
    *,
    include_inactive: bool = False,
) -> list[_PortfolioSource]:
    """Load trading workspace units from the database.

    The live-trading manager is process-local. Stress supervisors and the API
    server can run in separate Python processes, so portfolio pages must be able
    to aggregate from persisted workspace unit state and runtime logs.
    """
    user_id = _current_user_id(current_user)
    if not user_id:
        return []

    async with async_session_maker() as session:
        query = (
            select(StrategyUnit, Workspace)
            .join(Workspace, StrategyUnit.workspace_id == Workspace.id)
            .where(Workspace.user_id == user_id)
            .where(Workspace.workspace_type == "trading")
            .order_by(Workspace.name, StrategyUnit.sort_order, StrategyUnit.strategy_name)
        )
        if not include_inactive:
            query = query.where(StrategyUnit.run_status.in_(_ACTIVE_TRADING_STATUSES))
        result = await session.execute(query)
        rows = result.all()

    instance_ids = [
        str(unit.trading_instance_id or "").strip()
        for unit, _workspace in rows
        if str(unit.trading_instance_id or "").strip()
    ]
    manager_instances = (
        _manager_instances_by_id(mgr, user_id, instance_ids)
        if not include_inactive and instance_ids
        else None
    )
    sources: list[_PortfolioSource] = []
    for unit, workspace in rows:
        snapshot = unit.trading_snapshot if isinstance(unit.trading_snapshot, dict) else {}
        gateway_config = unit.gateway_config if isinstance(unit.gateway_config, dict) else {}
        runtime_config = _workspace_unit_runtime_config(unit)
        unit_name = str(unit.strategy_name or unit.strategy_id or unit.id)
        db_status = str(unit.run_status or snapshot.get("instance_status") or "idle")
        status = db_status.strip().lower()
        instance_id = str(unit.trading_instance_id or "").strip()
        instance = None
        if (
            not include_inactive
            and status in _ACTIVE_TRADING_STATUSES
            and instance_id
            and hasattr(mgr, "get_instance")
        ):
            if manager_instances is not None:
                instance = manager_instances.get(instance_id)
            else:
                try:
                    instance = mgr.get_instance(instance_id, user_id=user_id)
                except Exception:
                    instance = None
            if isinstance(instance, dict):
                status = str(instance.get("status") or "idle").strip().lower()
            else:
                status = "idle"
            if status not in _ACTIVE_TRADING_STATUSES:
                continue
        elif not include_inactive and status in _ACTIVE_TRADING_STATUSES and not instance_id:
            # A workspace unit without a live instance handle should not be treated
            # as actively running, otherwise stale historical rows can leak old
            # equity curves into live portfolio views.
            continue
        started_at = str(
            instance.get("started_at") if isinstance(instance, dict) else ""
        ).strip() or None
        updated_at = str(
            instance.get("updated_at") if isinstance(instance, dict) else ""
        ).strip() or None
        if include_inactive and not started_at:
            started_at = (
                str(snapshot.get("started_at") or "")
                or str(snapshot.get("instance_started_at") or "")
                or str(snapshot.get("start_time") or "")
                or str(snapshot.get("startedAt") or "")
            ).strip() or None
        sources.append(
            _PortfolioSource(
                id=str(unit.trading_instance_id or unit.id),
                strategy_id=str(unit.strategy_id or unit.id),
                strategy_name=f"{workspace.name} / {unit_name}",
                status=status,
                symbol=str(unit.symbol or ""),
                unit_id=str(unit.id),
                trading_mode=str(unit.trading_mode or snapshot.get("mode") or "paper"),
                workspace_id=str(workspace.id),
                log_dir=_workspace_unit_log_dir(unit),
                snapshot=dict(snapshot),
                valuation_configs=(
                    _safe_dict(runtime_config),
                    _safe_dict(unit.unit_settings),
                    _safe_dict(unit.params),
                    _safe_dict(unit.data_config),
                    _safe_dict(gateway_config),
                    _safe_dict(gateway_config.get("params")),
                ),
                started_at=started_at,
                updated_at=updated_at,
                pid=_coerce_int(instance.get("pid") if isinstance(instance, dict) else None),
            )
        )
    return sources


async def _persisted_running_workspace_sources(current_user: Any) -> list[_PortfolioSource]:
    """Load first-screen sources from the workspace snapshots only.

    The workspace service persists these snapshots as it refreshes each unit.
    A portfolio landing page can therefore render from the durable state
    without constructing the live-trading manager, which may restore gateway
    sessions and enumerate every historical instance in the process.
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
            .where(StrategyUnit.run_status == "running")
            .order_by(Workspace.name, StrategyUnit.sort_order, StrategyUnit.strategy_name)
        )
        rows = result.all()

    sources: list[_PortfolioSource] = []
    for unit, workspace in rows:
        instance_id = str(unit.trading_instance_id or "").strip()
        if not instance_id:
            continue
        snapshot = unit.trading_snapshot if isinstance(unit.trading_snapshot, dict) else {}
        snapshot_status = str(snapshot.get("instance_status") or "running").strip().lower()
        if snapshot_status not in _ACTIVE_TRADING_STATUSES:
            continue
        unit_name = str(unit.strategy_name or unit.strategy_id or unit.id)
        started_at = str(
            snapshot.get("started_at")
            or snapshot.get("instance_started_at")
            or snapshot.get("start_time")
            or snapshot.get("startedAt")
            or ""
        ).strip() or None
        sources.append(
            _PortfolioSource(
                id=instance_id,
                strategy_id=str(unit.strategy_id or unit.id),
                strategy_name=f"{workspace.name} / {unit_name}",
                status="running",
                symbol=str(unit.symbol or ""),
                unit_id=str(unit.id),
                trading_mode=str(unit.trading_mode or snapshot.get("mode") or "paper"),
                workspace_id=str(workspace.id),
                log_dir=_workspace_unit_log_dir(unit),
                snapshot=dict(snapshot),
                started_at=started_at,
                updated_at=_coerce_started_day(unit.updated_at),
            )
        )
    return sources


def _asset_spec_for_symbol(specs: dict[str, dict[str, Any]], symbol: str) -> dict[str, Any]:
    for key in symbol_aliases(symbol):
        item = specs.get(key)
        if isinstance(item, dict):
            return dict(item)
    return {}


def _metadata_from_config(config: dict[str, Any], symbol: str) -> dict[str, Any]:
    for container_key in ("contract_metadata", "contracts", "contract_specs", "instrument_specs"):
        container = config.get(container_key)
        if not isinstance(container, dict):
            continue
        item = _asset_spec_for_symbol(
            {str(key): value for key, value in container.items() if isinstance(value, dict)},
            symbol,
        )
        if item:
            return item
    return {}


def _merge_source_contract_metadata(
    specs: dict[str, dict[str, Any]],
    source: _PortfolioSource,
    symbols: list[str],
) -> dict[str, dict[str, Any]]:
    completed = {str(key): dict(value) for key, value in specs.items() if isinstance(value, dict)}
    for symbol in symbols:
        for config in source.valuation_configs:
            metadata = _metadata_from_config(config, symbol)
            if metadata:
                _merge_asset_spec_aliases(completed, symbol, metadata)
    return completed


def _merge_asset_spec_aliases(
    specs: dict[str, dict[str, Any]],
    symbol: str,
    spec: dict[str, Any],
) -> None:
    if not spec:
        return
    spec = _json_safe_value(spec)
    existing = _asset_spec_for_symbol(specs, symbol)
    merged = dict(existing)
    core_contributed = False
    primary_source_contributed = False
    for key, value in spec.items():
        if _can_merge_asset_spec_value(existing, key, value):
            merged[key] = value
            if _is_asset_spec_core_key(key):
                core_contributed = True
            if _is_asset_spec_primary_source_key(existing, key):
                primary_source_contributed = True
    existing_source = str(existing.get("source") or existing.get("asset_spec_source") or "").strip()
    next_source = str(spec.get("source") or spec.get("asset_spec_source") or "").strip()
    if existing_source and next_source and existing_source != next_source and core_contributed:
        merged["source"] = _combined_asset_spec_source(existing_source, next_source)
        merged["asset_spec_source"] = merged["source"]
    elif next_source and not existing_source and primary_source_contributed:
        merged["source"] = next_source
        merged["asset_spec_source"] = next_source
    for key in symbol_aliases(symbol):
        specs[str(key)] = dict(merged)


def _combined_asset_spec_source(*sources: str) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for source in sources:
        for part in str(source or "").split("+"):
            text = part.strip()
            if text and text not in seen:
                parts.append(text)
                seen.add(text)
    return "+".join(parts)


def _can_merge_asset_spec_value(existing: dict[str, Any], key: str, value: Any) -> bool:
    if key in {"source", "asset_spec_source"} or value in (None, ""):
        return False
    if existing.get(key) not in (None, ""):
        return False
    if key in _ASSET_SPEC_CONTRACT_KEYS:
        return not _asset_spec_has_any(existing, _ASSET_SPEC_CONTRACT_KEYS)
    if key in _ASSET_SPEC_MARGIN_KEYS:
        return not _asset_spec_has_any(existing, _ASSET_SPEC_MARGIN_KEYS)
    if key in _ASSET_SPEC_FEE_KEYS:
        return not _asset_spec_has_any(existing, _ASSET_SPEC_FEE_KEYS)
    return key in _ASSET_SPEC_AUX_KEYS


def _is_asset_spec_core_key(key: str) -> bool:
    return (
        key in _ASSET_SPEC_CONTRACT_KEYS
        or key in _ASSET_SPEC_MARGIN_KEYS
        or key in _ASSET_SPEC_FEE_KEYS
    )


def _is_asset_spec_primary_source_key(existing: dict[str, Any], key: str) -> bool:
    if key in _ASSET_SPEC_CONTRACT_KEYS or key in _ASSET_SPEC_MARGIN_KEYS:
        return True
    if key in _ASSET_SPEC_FEE_KEYS:
        return not (
            _asset_spec_has_any(existing, _ASSET_SPEC_CONTRACT_KEYS)
            or _asset_spec_has_any(existing, _ASSET_SPEC_MARGIN_KEYS)
        )
    return key in _ASSET_SPEC_AUX_KEYS and not existing


def _asset_spec_has_any(spec: dict[str, Any], keys: frozenset[str]) -> bool:
    return any(spec.get(key) not in (None, "") for key in keys)


def _merge_asset_spec_update(
    existing: dict[str, Any],
    update: dict[str, Any],
) -> dict[str, Any]:
    update = _json_safe_value(update)
    merged = dict(existing)
    core_changed = False
    primary_source_changed = False
    for group in (_ASSET_SPEC_CONTRACT_KEYS, _ASSET_SPEC_MARGIN_KEYS, _ASSET_SPEC_FEE_KEYS):
        group_items = {key: update.get(key) for key in group if update.get(key) not in (None, "")}
        if not group_items:
            continue
        for key in group:
            if key in merged:
                merged.pop(key, None)
                core_changed = True
                if _is_asset_spec_primary_source_key(existing, key):
                    primary_source_changed = True
        for key, value in group_items.items():
            if merged.get(key) != value:
                merged[key] = value
                core_changed = True
                if _is_asset_spec_primary_source_key(existing, key):
                    primary_source_changed = True

    for key, value in update.items():
        if key in {"source", "asset_spec_source"} or value in (None, ""):
            continue
        if (
            key in _ASSET_SPEC_CONTRACT_KEYS
            or key in _ASSET_SPEC_MARGIN_KEYS
            or key in _ASSET_SPEC_FEE_KEYS
        ):
            continue
        if key in _ASSET_SPEC_AUX_KEYS and merged.get(key) != value:
            merged[key] = value

    existing_source = str(existing.get("source") or existing.get("asset_spec_source") or "").strip()
    next_source = str(update.get("source") or update.get("asset_spec_source") or "").strip()
    if existing_source and next_source and existing_source != next_source and core_changed:
        merged["source"] = _combined_asset_spec_source(existing_source, next_source)
        merged["asset_spec_source"] = merged["source"]
    elif next_source and not existing_source and primary_source_changed:
        merged["source"] = next_source
        merged["asset_spec_source"] = next_source
    return merged


def _position_spec_has_asset_metadata(spec: Any) -> bool:
    return bool(
        getattr(spec, "has_multiplier", False)
        or getattr(spec, "has_margin_rate", False)
        or getattr(spec, "has_margin_amount", False)
        or getattr(spec, "has_commission", False)
    )


def _row_can_use_local_asset_spec(row: dict[str, Any]) -> bool:
    if _has_any(row, *_EXPLICIT_NET_PNL_FIELD_KEYS, *_GROSS_PNL_FIELD_KEYS, "pnl"):
        return True
    return _has_any(
        row,
        "price",
        "avg_price",
        "average_price",
        "price_open",
        "entry_price",
        "avgCost",
        "avgPrice",
        "avgPx",
        "avg_entry_price",
        "avgEntryPrice",
        "entryPrice",
        "open_avg_price",
        "openAvgPrice",
        "Price",
        "AveragePrice",
    ) and _has_any(
        row,
        "current_price",
        "latest_price",
        "last_price",
        "mark_price",
        "markPrice",
        "markPx",
        "market_price",
        "lastPrice",
        "LastPrice",
        "price_current",
        "marketPrice",
        "mktPrice",
        "mp",
        "PriceCurrent",
        "CurrentPrice",
        "SettlementPrice",
        "settlement_price",
    )


def _contract_spec_for_position(
    symbol: str,
    row: dict[str, Any],
    source: _PortfolioSource,
) -> Any:
    spec = contract_spec_for(symbol, row, source.snapshot or {}, *source.valuation_configs)
    if _position_spec_has_asset_metadata(spec):
        return spec
    if not _row_can_use_local_asset_spec(row):
        return spec
    try:
        local_spec = query_local_asset_spec(symbol)
    except Exception:
        local_spec = {}
    if isinstance(local_spec, dict) and local_spec:
        return contract_spec_for(
            symbol,
            row,
            local_spec,
            source.snapshot or {},
            *source.valuation_configs,
        )
    return spec


def _complete_asset_specs_from_local(
    specs: dict[str, dict[str, Any]],
    symbols: list[str],
) -> dict[str, dict[str, Any]]:
    completed = {str(key): dict(value) for key, value in specs.items() if isinstance(value, dict)}
    for symbol in symbols:
        try:
            local_spec = query_local_asset_spec(symbol)
        except Exception:
            local_spec = {}
        if isinstance(local_spec, dict) and local_spec:
            _merge_asset_spec_aliases(completed, symbol, local_spec)
    return completed


def _append_symbol_candidate(target: list[str], value: Any) -> None:
    if isinstance(value, (list, tuple, set)):
        for item in value:
            _append_symbol_candidate(target, item)
        return
    text = str(value or "").strip()
    if text:
        target.append(text)


def _source_symbol_aliases(source: _PortfolioSource) -> set[str]:
    candidates: list[str] = []
    _append_symbol_candidate(candidates, source.symbol)
    for config in source.valuation_configs:
        if not isinstance(config, dict):
            continue
        for key in (
            "symbol",
            "data_name",
            "instrument",
            "InstrumentID",
            "trade_symbol",
            "contract_symbol",
            "localSymbol",
            "local_symbol",
            "contractDesc",
            "contract_desc",
            "description",
            "ticker",
            "symbols",
            "symbol_list",
        ):
            _append_symbol_candidate(candidates, config.get(key))
        data_config = config.get("data_config")
        if isinstance(data_config, dict):
            for key in ("symbol", "symbols", "symbol_list", "instrument", "InstrumentID"):
                _append_symbol_candidate(candidates, data_config.get(key))
        for container_key in (
            "contract_metadata",
            "contracts",
            "contract_specs",
            "instrument_specs",
        ):
            container = config.get(container_key)
            if not isinstance(container, dict):
                continue
            for item_key in container.keys():
                _append_symbol_candidate(candidates, item_key)
            for item in container.values():
                if not isinstance(item, dict):
                    continue
                for key in (
                    "symbol",
                    "data_name",
                    "instrument",
                    "InstrumentID",
                    "REFERENCE_CODE",
                    "localSymbol",
                    "local_symbol",
                    "contractDesc",
                    "contract_desc",
                    "description",
                ):
                    _append_symbol_candidate(candidates, item.get(key))

    aliases: set[str] = set()
    for candidate in candidates:
        for alias in symbol_aliases(candidate):
            aliases.add(alias)
            aliases.add(alias.upper())
    return aliases


def _position_symbol_matches(symbol: str, allowed_aliases: set[str]) -> bool:
    if not allowed_aliases:
        return True
    return any(
        alias in allowed_aliases or alias.upper() in allowed_aliases
        for alias in symbol_aliases(symbol)
    )


def _live_positions_for_source(
    mgr: LiveTradingManager,
    source: _PortfolioSource,
) -> list[dict[str, Any]] | None:
    if str(source.status or "").strip().lower() != "running" or not source.id:
        return None

    is_live = str(source.trading_mode or "").strip().lower() == "live"
    has_gateway = getattr(mgr, "has_instance_gateway", None)
    if callable(has_gateway):
        try:
            if not has_gateway(source.id):
                if is_live:
                    _append_unique(
                        source.valuation_warnings,
                        "运行中的策略未绑定可查询的交易所网关，持仓/盈亏将回落到本地日志或快照",
                    )
                return None
        except Exception:
            if is_live:
                _append_unique(
                    source.valuation_warnings,
                    "检查策略网关绑定失败，持仓/盈亏将回落到本地日志或快照",
                )
            return None

    query_positions = getattr(mgr, "query_instance_gateway_positions", None)
    if not callable(query_positions):
        if is_live:
            _append_unique(
                source.valuation_warnings,
                "当前管理器不支持实时网关持仓查询，持仓/盈亏将回落到本地日志或快照",
            )
        return None
    try:
        raw_positions = query_positions(source.id)
    except Exception:
        if is_live:
            _append_unique(
                source.valuation_warnings,
                "交易所网关持仓查询失败，持仓/盈亏将回落到本地日志或快照",
            )
        return None
    if not isinstance(raw_positions, list):
        _append_unique(source.valuation_warnings, "交易所网关持仓返回格式异常")
        return None

    allowed_aliases = _source_symbol_aliases(source)
    matched_positions: list[dict[str, Any]] = []
    symbols: list[str] = []
    seen: set[str] = set()
    for item in raw_positions:
        if not isinstance(item, dict):
            continue
        symbol = gateway_position_symbol(item, source.symbol)
        if allowed_aliases and not _position_symbol_matches(symbol, allowed_aliases):
            continue
        matched_positions.append(item)
        if symbol and symbol not in seen:
            symbols.append(symbol)
            seen.add(symbol)
    if source.symbol and source.symbol not in seen:
        symbols.append(source.symbol)

    asset_specs: dict[str, dict[str, Any]] = {}
    query_specs = getattr(mgr, "query_instance_asset_specs", None)
    if callable(query_specs) and symbols:
        try:
            raw_specs = query_specs(source.id, symbols)
        except Exception:
            _append_unique(
                source.valuation_warnings,
                "交易所资产规格查询失败，乘数/保证金/手续费可能使用本地配置或默认值",
            )
            raw_specs = {}
        if isinstance(raw_specs, dict):
            asset_specs = {
                str(key): dict(value) for key, value in raw_specs.items() if isinstance(value, dict)
            }
    asset_specs = _merge_source_contract_metadata(asset_specs, source, symbols)
    asset_specs = _complete_asset_specs_from_local(asset_specs, symbols)
    source.resolved_asset_specs = {
        str(key): dict(value) for key, value in asset_specs.items() if isinstance(value, dict)
    }

    recent_trades: list[dict[str, Any]] = []
    query_trades = getattr(mgr, "query_instance_gateway_trades", None)
    if callable(query_trades) and symbols:
        for symbol in symbols:
            try:
                raw_trades = query_trades(source.id, symbol=symbol, limit=500)
            except TypeError:
                raw_trades = query_trades(source.id)
            except Exception:
                raw_trades = []
            if isinstance(raw_trades, list):
                for item in raw_trades:
                    if not isinstance(item, dict):
                        continue
                    trade = dict(item)
                    trade.setdefault("__query_symbol", symbol)
                    recent_trades.append(trade)

    positions: list[dict[str, Any]] = []
    for item in matched_positions:
        for side_item in split_bidirectional_position_row(item):
            if abs(signed_gateway_size(side_item)) <= EPSILON:
                continue
            symbol = gateway_position_symbol(side_item, source.symbol)
            positions.append(
                normalize_gateway_position(
                    side_item,
                    fallback_symbol=source.symbol,
                    asset_spec=_asset_spec_for_symbol(asset_specs, symbol),
                    recent_trades=recent_trades,
                )
            )
    source.position_source = "gateway"
    return positions


def _live_account_for_source(
    mgr: LiveTradingManager,
    source: _PortfolioSource,
) -> dict[str, Any] | None:
    if str(source.status or "").strip().lower() != "running" or not source.id:
        return None

    is_live = str(source.trading_mode or "").strip().lower() == "live"
    has_gateway = getattr(mgr, "has_instance_gateway", None)
    if callable(has_gateway):
        try:
            if not has_gateway(source.id):
                return None
        except Exception:
            if is_live:
                _append_unique(
                    source.valuation_warnings, "检查策略网关绑定失败，账户权益将回落到日志"
                )
            return None

    query_account = getattr(mgr, "query_instance_gateway_account", None)
    if not callable(query_account):
        if is_live:
            _append_unique(
                source.valuation_warnings, "当前管理器不支持实时网关账户查询，账户权益将回落到日志"
            )
        return None
    try:
        account = query_account(source.id)
    except Exception:
        if is_live:
            _append_unique(
                source.valuation_warnings, "交易所网关账户查询失败，账户权益将回落到日志"
            )
        return None
    if not isinstance(account, dict):
        if is_live:
            _append_unique(
                source.valuation_warnings, "交易所网关账户返回格式异常，账户权益将回落到日志"
            )
        return None
    source.account_source = str(account.get("account_source") or "gateway").strip() or "gateway"
    return account


async def _persist_source_asset_specs(current_user: Any, source: _PortfolioSource) -> None:
    if not source.unit_id or not source.resolved_asset_specs:
        return
    user_id = _current_user_id(current_user)
    if not user_id:
        return

    async with async_session_maker() as session:
        result = await session.execute(
            select(StrategyUnit, Workspace)
            .join(Workspace, StrategyUnit.workspace_id == Workspace.id)
            .where(StrategyUnit.id == source.unit_id)
            .where(Workspace.user_id == user_id)
        )
        row = result.first()
        if row is None:
            return
        unit = row[0]
        params = _safe_dict(unit.params)
        metadata = (
            dict(params.get("contract_metadata"))
            if isinstance(params.get("contract_metadata"), dict)
            else {}
        )
        changed = False
        for key, value in source.resolved_asset_specs.items():
            if not isinstance(value, dict):
                continue
            existing_value = _asset_spec_for_symbol(metadata, str(key))
            merged_value = _merge_asset_spec_update(existing_value, value)
            if existing_value != merged_value:
                changed = True
            for alias in symbol_aliases(str(key)):
                alias_key = str(alias)
                if metadata.get(alias_key) != merged_value:
                    changed = True
                metadata[alias_key] = dict(merged_value)
        if not changed:
            return
        params["contract_metadata"] = metadata
        unit.params = params
        await session.commit()


async def _portfolio_sources(
    current_user: Any,
    mgr: LiveTradingManager,
    *,
    include_inactive: bool = False,
) -> list[_PortfolioSource]:
    workspace_sources = await _active_workspace_sources(
        current_user,
        mgr,
        include_inactive=include_inactive,
    )
    sources = (
        workspace_sources
        if workspace_sources
        else [_source_from_instance(inst) for inst in _list_user_instances(mgr, current_user, include_inactive=include_inactive)]
    )
    for source in sources:
        # A paper workspace is a collection of independent simulated portfolios.
        # Its gateway is only used to feed the running strategy, not to represent
        # the account/positions of every unit.  Querying that shared gateway here
        # once per unit both duplicates broker data and makes the risk page block
        # behind dozens of synchronous requests.  Use each unit's own logs and
        # persisted snapshot instead.  Keep the legacy instance fallback intact
        # for callers that do not originate from a workspace unit.
        if source.unit_id and str(source.trading_mode or "").strip().lower() == "paper":
            continue
        live_positions = _live_positions_for_source(mgr, source)
        if live_positions is not None:
            source.live_positions = live_positions
            await _persist_source_asset_specs(current_user, source)
        live_account = _live_account_for_source(mgr, source)
        if live_account is not None:
            source.live_account = live_account
    return sources


def _source_snapshot_positions(source: _PortfolioSource) -> list[dict[str, Any]]:
    return _snapshot_positions_for_portfolio(source.snapshot)


def _position_row_direction(row: dict[str, Any], size: float) -> str:
    for key in (
        "direction",
        "side",
        "position_side",
        "positionSide",
        "PositionSide",
        "positionIdx",
        "position_idx",
        "posSide",
        "trade_action",
        "position_type",
        "type",
        "PosiDirection",
        "posi_direction",
        "position_direction",
    ):
        value = row.get(key)
        if value in (None, ""):
            continue
        text = str(value).strip().lower()
        if text in {"long", "buy", "bought", "position_type_buy", "deal_type_buy"}:
            return "long"
        if text in {"short", "sell", "sold", "position_type_sell", "deal_type_sell"}:
            return "short"
        if text == "flat":
            return "flat"
        try:
            code = int(float(value))
        except (TypeError, ValueError):
            code = None
        key_text = key.lower()
        if key_text in {"trade_action", "position_type", "type"}:
            if code == 0:
                return "long"
            if code == 1:
                return "short"
        if key_text in {"posidirection", "posi_direction", "position_direction"}:
            if code == 2:
                return "long"
            if code == 3:
                return "short"
        if key_text in {"positionidx", "position_idx"}:
            if code == 1:
                return "long"
            if code == 2:
                return "short"
    if abs(size) <= EPSILON:
        return "flat"
    return "short" if size < 0 else "long"


def _latest_position_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest_by_key: dict[str, tuple[int, str, str, dict[str, Any]]] = {}
    latest_flat_by_key: dict[str, tuple[int, str, str, dict[str, Any]]] = {}
    latest_flat_by_symbol: dict[str, tuple[int, str, dict[str, Any]]] = {}
    for index, row in enumerate(rows):
        symbol = str(row.get("data_name") or row.get("symbol") or "").strip()
        if not symbol:
            continue
        size = _safe_float(row.get("size"), 0.0)
        direction = _position_row_direction(row, size)
        timestamp = str(row.get("datetime") or row.get("dt") or "")
        if abs(size) <= EPSILON:
            if direction in {"long", "short"}:
                key = f"{symbol}:{direction}"
                current_flat = latest_flat_by_key.get(key)
                if current_flat is None or (timestamp, index) >= (
                    current_flat[1],
                    current_flat[0],
                ):
                    latest_flat_by_key[key] = (index, timestamp, symbol, row)
                continue
            current_flat = latest_flat_by_symbol.get(symbol)
            if current_flat is None or (timestamp, index) >= (current_flat[1], current_flat[0]):
                latest_flat_by_symbol[symbol] = (index, timestamp, row)
            continue
        key = f"{symbol}:{direction}"
        current = latest_by_key.get(key)
        if current is None or (timestamp, index) >= (current[1], current[0]):
            latest_by_key[key] = (index, timestamp, symbol, row)

    latest_nonflat_by_symbol: dict[str, tuple[int, str]] = {}
    for index, timestamp, symbol, _row in latest_by_key.values():
        current = latest_nonflat_by_symbol.get(symbol)
        if current is None or (timestamp, index) >= (current[1], current[0]):
            latest_nonflat_by_symbol[symbol] = (index, timestamp)

    selected: list[tuple[int, dict[str, Any]]] = []
    for index, timestamp, symbol, row in latest_by_key.values():
        direction = _position_row_direction(row, _safe_float(row.get("size"), 0.0))
        key = f"{symbol}:{direction}"
        flat = latest_flat_by_symbol.get(symbol)
        if flat is not None and (flat[1], flat[0]) >= (timestamp, index):
            continue
        directional_flat = latest_flat_by_key.get(key)
        if directional_flat is not None and (directional_flat[1], directional_flat[0]) >= (
            timestamp,
            index,
        ):
            continue
        selected.append((index, row))
    for symbol, (index, timestamp, row) in latest_flat_by_symbol.items():
        latest_nonflat = latest_nonflat_by_symbol.get(symbol)
        if latest_nonflat is None or (timestamp, index) >= (latest_nonflat[1], latest_nonflat[0]):
            selected.append((index, row))
    for key, (index, timestamp, _symbol, row) in latest_flat_by_key.items():
        latest_nonflat = latest_by_key.get(key)
        if latest_nonflat is None or (timestamp, index) >= (
            latest_nonflat[1],
            latest_nonflat[0],
        ):
            selected.append((index, row))
    return [row for _index, row in sorted(selected, key=lambda item: item[0])]


def _parse_positions_for_portfolio(log_dir: Path) -> list[dict[str, Any]]:
    position_log_rows = parse_position_log(log_dir)
    if position_log_rows:
        return [
            row
            for row in _latest_position_rows(position_log_rows)
            if abs(_safe_float(row.get("size"), 0.0)) > EPSILON
        ]
    return [
        row
        for row in parse_current_position(log_dir)
        if abs(_safe_float(row.get("size"), 0.0)) > EPSILON
    ]


def _snapshot_positions_for_portfolio(snapshot: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = list((snapshot or {}).get("positions") or [])
    positions: list[dict[str, Any]] = []
    for raw_row in rows:
        if not isinstance(raw_row, dict):
            continue
        for row in split_bidirectional_position_row(raw_row):
            size = signed_gateway_size(row)
            if abs(size) <= EPSILON:
                continue
            price = (
                _first_number(
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
                )
                or 0.0
            )
            current_price = _first_number(
                row,
                "current_price",
                "latest_price",
                "last_price",
                "mark_price",
                "markPrice",
                "markPx",
                "market_price",
                "lastPrice",
                "LastPrice",
                "price_current",
                "marketPrice",
                "mktPrice",
                "mp",
                "PriceCurrent",
                "CurrentPrice",
                "SettlementPrice",
                "settlement_price",
            )
            explicit_market_value = _first_number(
                row,
                "market_value",
                "marketValue",
                "mktValue",
                "positionValue",
                "position_value",
                "value",
            )
            market_value = (
                explicit_market_value if explicit_market_value is not None else abs(size) * price
            )
            position = {
                **row,
                "data_name": gateway_position_symbol(row),
                "size": size,
                "price": price,
                "current_price": current_price,
                "market_value": market_value,
                "value": market_value,
                "position_pnl": row.get("position_pnl"),
                "pnl": row.get("pnl"),
                "pnlcomm": row.get("pnlcomm"),
                "gross_pnl": row.get("gross_pnl"),
                "commission": row.get("commission"),
                "commission_signed": row.get("commission_signed"),
                "multiplier": row.get("multiplier"),
                "margin_rate": row.get("margin_rate"),
                "margin": row.get("margin"),
                "margin_value": row.get("margin_value"),
                "use_margin": row.get("use_margin"),
                "initial_margin": row.get("initial_margin"),
                "maintain_margin": row.get("maintain_margin"),
                "updated_at": _position_updated_at(row),
                "data_time": _position_data_time(row),
                "source": row.get("source"),
                "position_source": row.get("position_source"),
                "asset_spec_source": row.get("asset_spec_source"),
                "valuation_status": row.get("valuation_status"),
                "valuation_warnings": list(row.get("valuation_warnings") or []),
            }
            if explicit_market_value is None:
                position["market_value_estimated"] = True
            positions.append(position)
    return positions


def _source_positions(source: _PortfolioSource) -> list[dict[str, Any]]:
    if source.live_positions is not None:
        source.position_source = "gateway"
        return source.live_positions
    snapshot_positions = _source_snapshot_positions(source)
    if snapshot_positions:
        source.position_source = "snapshot"
        return snapshot_positions
    if source.log_dir:
        source.position_source = "log"
        return _parse_positions_for_portfolio(source.log_dir)
    source.position_source = None
    return []


def _position_valuation_warnings(
    source: _PortfolioSource,
    row: dict[str, Any],
    spec: Any,
    *,
    position_source: str,
) -> list[str]:
    warnings: list[str] = []
    if (
        str(source.trading_mode or "").strip().lower() == "live"
        and str(source.status or "").strip().lower() == "running"
        and position_source != "gateway"
    ):
        warnings.append("未能从交易所网关确认当前持仓，当前数据来自本地日志/快照")
    if not getattr(spec, "has_multiplier", False) and not _has_any(
        row, "multiplier", "mult", "contract_multiplier", "contract_size"
    ):
        warnings.append("合约乘数未从交易所或本地资产信息确认，按 1 估算")
    if (
        not getattr(spec, "has_margin_rate", False)
        and not getattr(spec, "has_margin_amount", False)
        and not _has_any(
            row,
            "margin",
            "margin_rate",
            "margin_ratio",
            "leverage",
            "lever",
            "margin_value",
            "use_margin",
            "initial_margin",
            "imr",
            "margin_amount",
            "initial_margin_per_lot",
            "margin_initial",
            "maintain_margin",
            "mmr",
            "long_margin_amount",
            "short_margin_amount",
            "MARGIN_PER_LOT",
            "LONG_MARGIN_AMOUNT",
            "SHORT_MARGIN_AMOUNT",
        )
    ):
        warnings.append("保证金率未确认，按全额保证金估算")
    has_real_commission = _has_any(row, *_COMMISSION_FIELD_KEYS)
    if row.get("commission_currency_mismatch"):
        warnings.append("成交手续费币种与盈亏计价币种不一致，当前按资产费率估算手续费")
    if not getattr(spec, "has_commission", False) and not has_real_commission:
        warnings.append("手续费未确认，持仓盈亏未扣除真实手续费")
    elif (
        getattr(spec, "has_commission", False)
        and not has_real_commission
        and (row.get("generic_pnl_recalculated") or _has_any(row, *_GROSS_PNL_FIELD_KEYS))
    ):
        warnings.append("持仓手续费未从交易所成交/持仓回报确认，当前按资产费率估算")
    return warnings


def _position_row_should_recalculate_local_pnl(
    row: dict[str, Any],
    spec: Any,
    *,
    position_source: str,
    force: bool = False,
) -> bool:
    if not force and str(position_source or "").strip().lower() == "gateway":
        return False
    if not (
        getattr(spec, "has_multiplier", False)
        or getattr(spec, "has_commission", False)
        or getattr(spec, "has_margin_rate", False)
        or getattr(spec, "has_margin_amount", False)
    ):
        return False
    if not _has_any(
        row,
        "price",
        "avg_price",
        "average_price",
        "price_open",
        "entry_price",
        "avgCost",
        "avgPrice",
        "avgPx",
        "avg_entry_price",
        "avgEntryPrice",
        "entryPrice",
        "open_avg_price",
        "openAvgPrice",
        "Price",
        "AveragePrice",
    ):
        return False
    if not _has_any(
        row,
        "current_price",
        "latest_price",
        "last_price",
        "mark_price",
        "markPrice",
        "markPx",
        "market_price",
        "lastPrice",
        "LastPrice",
        "market_value",
        "marketValue",
        "positionValue",
        "position_value",
        "value",
    ):
        return False
    return _has_any(row, *_EXPLICIT_NET_PNL_FIELD_KEYS, *_GROSS_PNL_FIELD_KEYS, "pnl")


def _position_row_for_valuation(
    row: dict[str, Any],
    spec: Any,
    *,
    position_source: str,
) -> dict[str, Any]:
    item = dict(row)
    force_recalculate = bool(item.pop("force_recalculate_position_pnl", False))
    if not _position_row_should_recalculate_local_pnl(
        item,
        spec,
        position_source=position_source,
        force=force_recalculate,
    ):
        return item
    for key in (*_EXPLICIT_NET_PNL_FIELD_KEYS, *_GROSS_PNL_FIELD_KEYS, "pnl"):
        item.pop(key, None)
    if force_recalculate:
        item["market_value_estimated"] = True
    item["recalculated_position_pnl"] = True
    return item


def _valued_source_positions(source: _PortfolioSource) -> list[dict[str, Any]]:
    positions: list[dict[str, Any]] = []
    for raw_row in _source_positions(source):
        for row in split_bidirectional_position_row(raw_row):
            symbol = str(row.get("data_name") or row.get("symbol") or "")
            spec = _contract_spec_for_position(symbol, row, source)
            position_source = str(
                row.get("position_source") or row.get("source") or source.position_source or "local"
            ).strip()
            if (
                source.live_positions is None
                and str(source.position_source or "").strip().lower() in {"log", "snapshot"}
                and position_source.lower() == "gateway"
            ):
                position_source = str(source.position_source)
                row = dict(row)
                row["force_recalculate_position_pnl"] = True
            valuation_row = _position_row_for_valuation(
                row,
                spec,
                position_source=position_source,
            )
            valued = value_position(valuation_row, spec=spec)
            if valued is None:
                continue
            asset_spec_source = str(
                row.get("asset_spec_source") or getattr(spec, "source", "") or ""
            ).strip()
            row_warnings = _position_valuation_warnings(
                source,
                valuation_row,
                spec,
                position_source=position_source,
            )
            if valuation_row.get("recalculated_position_pnl"):
                row_warnings.append("本地/快照持仓盈亏已按最新资产乘数、保证金和手续费设置重新计算")
            _append_unique(source.valuation_warnings, row_warnings)
            if asset_spec_source:
                source.asset_spec_source = _unique_text(
                    [source.asset_spec_source, asset_spec_source]
                )
            source.valuation_status = "estimated" if source.valuation_warnings else "confirmed"
            positions.append(
                {
                    "data_name": valued.data_name or symbol,
                    "size": valued.size,
                    "price": valued.entry_price,
                    "latest_price": valued.current_price,
                    "market_value": valued.market_value,
                    "signed_market_value": _signed_market_value(valued.size, valued.market_value),
                    "position_pnl": valued.pnl,
                    "gross_pnl": valued.gross_pnl,
                    "commission": valued.commission,
                    "commission_source": valuation_row.get("commission_source")
                    or row.get("commission_source"),
                    "multiplier": valued.multiplier,
                    "margin_rate": valued.margin_rate,
                    "leverage": _leverage_from_margin_rate(valued.margin_rate),
                    "margin_value": valued.margin_value,
                    "updated_at": _position_updated_at(row),
                    "data_time": _position_data_time(row),
                    "direction": valued.direction,
                    "position_source": position_source,
                    "asset_spec_source": asset_spec_source or None,
                    "valuation_status": "estimated" if row_warnings else "confirmed",
                    "valuation_warnings": row_warnings,
                }
            )
    if not positions and source.position_source == "gateway":
        source.valuation_status = "confirmed"
    elif not positions and source.valuation_warnings:
        source.valuation_status = "stale_fallback"
    return positions


def _source_trades(
    source: _PortfolioSource,
    *,
    started_day: str | None = None,
) -> list[dict[str, Any]]:
    if source.log_dir:
        trades = parse_trade_log(source.log_dir)
    else:
        trades = [
            dict(item)
            for item in (source.snapshot or {}).get("trades") or []
            if isinstance(item, dict)
        ]
    return _filter_rows_after_source_start(
        trades,
        source_started_day=started_day,
        keys=("log_time", "event_time", "time", "dtclose", "datetime", "dtopen"),
    )


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
        if abs(size) <= EPSILON:
            continue
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


def _source_has_confirmed_flat_positions(source: _PortfolioSource) -> bool:
    if source.live_positions is not None:
        return True
    snapshot = source.snapshot if isinstance(source.snapshot, dict) else {}
    return isinstance(snapshot.get("positions"), list)


def _source_account_key(source: _PortfolioSource) -> str:
    account = source.live_account or {}
    for value in (
        account.get("gateway_key"),
        account.get("account_id"),
        account.get("account"),
        account.get("login"),
        source.id,
    ):
        text = str(value or "").strip()
        if text:
            return text
    return source.id


def _source_account_value(source: _PortfolioSource) -> float | None:
    return _first_number(
        source.live_account,
        "value",
        "equity",
        "Equity",
        "eq",
        "total_eq",
        "totalEq",
        "total_equity",
        "totalEquity",
        "account_value",
        "accountValue",
        "net_liquidation",
        "NetLiquidation",
        "netliquidation",
        "NetLiquidationValue",
        "total_margin",
        "totalMargin",
        "total_margin_balance",
        "totalMarginBalance",
        "margin_balance",
        "marginBalance",
        "total_wallet_balance",
        "totalWalletBalance",
        "wallet_balance",
        "walletBalance",
        "balance",
        "Balance",
    )


def _source_account_cash(source: _PortfolioSource) -> float | None:
    account = source.live_account
    cash = _first_number(
        account,
        "cash",
        "available_cash",
        "available",
        "Available",
        "available_funds",
        "AvailableFunds",
        "availablefunds",
        "available_balance",
        "availableBalance",
        "available_bal",
        "availableBal",
        "available_equity",
        "availableEquity",
        "avail_eq",
        "availEq",
        "avail_bal",
        "availBal",
        "total_available_balance",
        "totalAvailableBalance",
        "total_available_margin",
        "totalAvailableMargin",
        "free_collateral",
        "freeCollateral",
        "free_margin",
        "freeMargin",
        "marginFree",
        "margin_free",
        "withdraw_available",
        "withdrawAvailable",
        "available_to_withdraw",
        "availableToWithdraw",
    )
    if cash is not None:
        return cash

    margin = _first_number(
        account,
        "margin",
        "used_margin",
        "usedMargin",
        "margin_used",
        "marginUsed",
        "curr_margin",
        "CurrMargin",
        "initial_margin",
        "initialMargin",
        "initial_margin_requirement",
        "initialMarginRequirement",
        "total_initial_margin",
        "totalInitialMargin",
        "total_used_margin",
        "totalUsedMargin",
        "total_position_initial_margin",
        "totalPositionInitialMargin",
        "total_open_order_initial_margin",
        "totalOpenOrderInitialMargin",
        "imr",
        "maintain_margin",
        "maintenance_margin",
        "maintMargin",
    )
    value = _source_account_value(source)
    if value is not None and margin is not None:
        return value - margin

    return _first_number(
        source.live_account,
        "balance",
        "Balance",
    )


def _source_account_time(source: _PortfolioSource) -> str:
    account = source.live_account or {}
    for key in ("updated_at", "data_time", "datetime", "dt", "time", "timestamp"):
        value = account.get(key)
        text = str(value or "").strip()
        if text:
            return text
    return "live"


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


def _value_log_edge_rows(path: Path) -> tuple[list[str], list[str]]:
    """Read bounded head/tail samples from a value log without parsing its curve."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            head = [handle.readline().strip() for _ in range(32)]
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(size - 65536, 0))
            tail = handle.read().decode("utf-8", errors="ignore").splitlines()
    except OSError:
        return [], []
    return [line for line in head if line], [line.strip() for line in tail if line.strip()]


def _parse_value_log_edge_row(
    line: str,
    *,
    log_format: str,
    headers: list[str] | None = None,
) -> dict[str, Any]:
    """Parse one supported value-log row for the compact portfolio summary."""
    if log_format == "json":
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}
    if log_format == "tsv" and headers:
        values = line.split("\t")
        return {
            header: values[index] if index < len(values) else ""
            for index, header in enumerate(headers)
        }
    if log_format == "pipe":
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 2:
            return {}
        row: dict[str, Any] = {}
        for part in parts[1:]:
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            row[key.strip()] = value.strip()
        return row
    return {}


def _compact_value_log_summary(
    log_dir: Path | None,
    *,
    started_day: str | None = None,
) -> tuple[float, float, float] | None:
    """Return initial equity, latest equity and latest cash from a value log.

    Full portfolio analytics need every point in the curve. The first-screen
    cards only need its two endpoints, so scanning a bounded head/tail window
    avoids decoding thousands of JSON rows across a large workspace.
    """
    path = (log_dir / "value.log") if log_dir is not None else None
    if path is None or not path.is_file():
        return None
    if started_day:
        parsed = parse_value_log(path.parent, prefer_log_time=True)
        dates = list(parsed.get("dates") or [])
        equity = list(parsed.get("equity_curve") or [])
        cash = list(parsed.get("cash_curve") or [])
        if not dates or not equity:
            return None
        started = _trading_day(started_day)
        if started:
            dates, equity, cash = _trim_curve_by_source_start(dates, equity, cash, started)
        if not dates:
            return None
        if not cash:
            cash = [0.0 for _ in dates]
        return (equity[0], equity[-1], cash[-1])

    head, tail = _value_log_edge_rows(path)
    if not head:
        return None

    first = head[0]
    if first.startswith("{"):
        log_format, headers = "json", None
        head_rows = head
    elif "\t" in first:
        log_format, headers = "tsv", first.split("\t")
        head_rows = head[1:]
    elif "|" in first:
        log_format, headers = "pipe", None
        head_rows = head
    else:
        return None

    def extract(lines: list[str], *, reverse: bool = False) -> tuple[float, float] | None:
        candidates = reversed(lines) if reverse else lines
        for line in candidates:
            row = _parse_value_log_edge_row(line, log_format=log_format, headers=headers)
            value = _first_number(row, "value", "broker_value")
            if value is None or not math.isfinite(value) or abs(value) > 1e15:
                continue
            cash = _first_number(row, "cash", "broker_cash")
            if cash is None or not math.isfinite(cash) or abs(cash) > 1e15:
                cash = 0.0
            if cash and abs(value) > abs(cash) * 1000:
                continue
            return value, cash
        return None

    initial = extract(head_rows)
    latest = extract(tail, reverse=True)
    if initial is None or latest is None:
        return None
    return initial[0], latest[0], latest[1]


def _workspace_unit_value_log_summary(
    unit: StrategyUnit,
    *,
    started_day: str | None = None,
) -> tuple[float, float, float] | None:
    return _compact_value_log_summary(_workspace_unit_log_dir(unit), started_day=started_day)


def _is_running_portfolio_source(source: _PortfolioSource) -> bool:
    """Return whether a source belongs to a currently running workspace unit.

    ``_portfolio_sources`` obtains workspace instances through the live manager,
    which has already verified the process state before exposing ``running``.
    A PID is useful metadata, but not every compatible manager implementation
    exposes it; requiring it here silently removed valid portfolio sources.
    """
    return str(source.status or "").strip().lower() == "running"


def _compact_workspace_overview(rows: list[_PortfolioSource]) -> dict[str, Any]:
    """Build a first-screen portfolio summary from persisted workspace snapshots.

    The detailed portfolio view reads strategy logs and, for legacy instances,
    can query a gateway. That is appropriate for drill-down views but becomes
    prohibitively expensive when hundreds of paper units are running. The
    workspace snapshot is refreshed by the trading service, so it is the right
    source for the page's initial metric cards.
    """
    total_assets = 0.0
    total_cash = 0.0
    total_initial = 0.0
    total_position_gross = 0.0
    total_position_net = 0.0
    running_count = 0
    has_position_data = False

    # Sources from the live-manager path have already passed process validation,
    # while the fast landing-page path contains only persisted running units.
    # Requiring a process PID here would make the snapshot-only path discard all
    # valid first-screen data after an API-server restart.
    running_sources = [
        source
        for source in rows
        if str(source.status or "").strip().lower() == "running"
    ]

    for source in running_sources:
        snapshot = _safe_dict(source.snapshot)
        started_day = _source_started_day(source)
        long_value = max(
            _first_number(snapshot, "long_market_value", "long_value", "longMarketValue") or 0.0,
            0.0,
        )
        short_value = max(
            _first_number(snapshot, "short_market_value", "short_value", "shortMarketValue") or 0.0,
            0.0,
        )
        net_position_value = long_value - short_value
        value_summary = _compact_value_log_summary(source.log_dir, started_day=started_day)
        initial, assets, cash = value_summary if value_summary is not None else (0.0, 0.0, 0.0)

        total_initial += initial
        total_assets += assets
        total_cash += cash
        total_position_gross += long_value + short_value
        total_position_net += net_position_value
        if (
            isinstance(snapshot.get("positions"), list)
            or long_value > EPSILON
            or short_value > EPSILON
        ):
            has_position_data = True
        running_count += 1

    total_pnl = total_assets - total_initial
    total_pnl_pct = total_pnl / total_initial * 100 if total_initial > 0 else 0.0
    if not has_position_data:
        total_position_net = total_assets - total_cash
        total_position_gross = abs(total_position_net)
    return {
        "total_assets": _safe_round(total_assets),
        "total_cash": _safe_round(total_cash),
        "total_position_value": _safe_round(total_position_gross),
        "net_position_value": _safe_round(total_position_net),
        "total_initial_capital": _safe_round(total_initial),
        "total_pnl": _safe_round(total_pnl),
        "total_pnl_pct": _safe_round(total_pnl_pct, 2),
        "strategy_count": len(running_sources),
        "running_count": running_count,
        # Per-strategy metrics require scanning every value and trade log. They
        # are not rendered in the first screen and are intentionally omitted in
        # compact mode to keep the route DB-only.
        "strategies": [],
    }

async def _compact_portfolio_overview(
    current_user: Any,
    mgr: LiveTradingManager,
) -> dict[str, Any] | None:
    sources = await _active_workspace_sources(current_user, mgr, include_inactive=False)
    if any(
        str(source.trading_mode or "").strip().lower() == "live"
        for source in sources
    ):
        # Live workspaces may require a broker account query to remain accurate.
        # Retain the detailed path for that safety-sensitive case.
        return None
    return _compact_workspace_overview(sources)


async def _persisted_compact_portfolio_overview(current_user: Any) -> dict[str, Any]:
    """Build a first-screen overview without initializing the live manager."""
    return _compact_workspace_overview(await _persisted_running_workspace_sources(current_user))


@router.get(
    "/overview/summary",
    summary="Portfolio overview (persisted first-screen summary)",
    response_model=None,
)
async def get_portfolio_overview_summary(
    current_user: typing.Any = Depends(get_current_user),
) -> dict[str, Any]:
    """Return fast first-screen totals from persisted workspace snapshots.

    Detailed portfolio routes continue to validate live processes and gateways.
    This endpoint intentionally avoids that work so navigating to the portfolio
    page remains responsive when many historical instances exist.
    """
    return await _persisted_compact_portfolio_overview(current_user)


@router.get("/overview", summary="Portfolio overview (live trading)", response_model=None)
async def get_portfolio_overview(
    summary_only: bool = False,
    include_inactive: bool = False,
    current_user: typing.Any = Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
) -> typing.Any:
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
    if summary_only:
        compact_overview = await _compact_portfolio_overview(current_user, mgr)
        if compact_overview is not None:
            return compact_overview

    sources = await _portfolio_sources(current_user, mgr, include_inactive=include_inactive)
    if not include_inactive:
        sources = [source for source in sources if _is_running_portfolio_source(source)]

    total_assets = 0.0
    total_cash = 0.0
    total_initial = 0.0
    total_position_gross = 0.0
    total_position_net = 0.0
    has_position_data = False
    strategy_summaries = []
    counted_account_keys: set[str] = set()

    for source in sources:
        log_dir = source.log_dir
        started_day = _source_started_day(source) if not include_inactive else None
        valued_positions = _valued_source_positions(source)
        position_summary = _build_position_summary(valued_positions)
        has_source_positions = bool(
            position_summary["long_count"]
            or position_summary["short_count"]
            or position_summary["flat_count"]
        )
        has_source_position_data = has_source_positions or _source_has_confirmed_flat_positions(
            source
        )
        account_value = _source_account_value(source)
        account_cash = _source_account_cash(source)
        account_key = _source_account_key(source) if account_value is not None else ""
        account_counted = False
        if not log_dir:
            if account_value is not None and account_key not in counted_account_keys:
                total_assets += account_value
                total_cash += account_cash if account_cash is not None else 0.0
                total_initial += account_value
                counted_account_keys.add(account_key)
                account_counted = True
            if has_source_positions:
                has_position_data = True
                total_position_gross += float(position_summary["gross_market_value"])
                total_position_net += float(position_summary["net_market_value"])
            elif has_source_position_data:
                has_position_data = True
            strategy_summaries.append(
                {
                    "id": source.id,
                    "strategy_id": source.strategy_id,
                    "strategy_name": source.strategy_name,
                    "status": source.status,
                    "position_source": source.position_source,
                    "account_source": source.account_source,
                    "account_counted_in_totals": account_counted,
                    "asset_spec_source": source.asset_spec_source,
                    "valuation_status": source.valuation_status,
                    "valuation_warnings": list(source.valuation_warnings),
                    "total_assets": _safe_round(account_value or 0.0),
                    "initial_capital": _safe_round(account_value or 0.0),
                    "pnl": 0,
                    "pnl_pct": 0,
                    "total_trades": 0,
                    "win_rate": 0,
                }
            )
            continue

        value_data = parse_value_log(log_dir, prefer_log_time=True)
        equity = value_data.get("equity_curve", [])
        cash = value_data.get("cash_curve", [])
        if started_day:
            dates = value_data.get("dates", [])
            if dates and equity:
                dates, equity, cash = _trim_curve_by_source_start(
                    dates=dates,
                    equity=equity,
                    cash=cash,
                    source_started_day=started_day,
                )
            value_data["equity_curve"] = equity
            value_data["cash_curve"] = cash

        trades = _source_trades(source, started_day=started_day)

        initial = equity[0] if equity else 0
        final = equity[-1] if equity else 0
        final_cash = cash[-1] if cash else 0
        pnl = final - initial
        pnl_pct = (pnl / initial * 100) if initial > 0 else 0

        if account_value is not None:
            if account_key not in counted_account_keys:
                total_assets += account_value
                total_cash += account_cash if account_cash is not None else final_cash
                total_initial += initial if initial > 0 else account_value
                counted_account_keys.add(account_key)
                account_counted = True
        else:
            total_assets += final
            total_cash += final_cash
            total_initial += initial
        if has_source_positions:
            has_position_data = True
            total_position_gross += float(position_summary["gross_market_value"])
            total_position_net += float(position_summary["net_market_value"])
        elif has_source_position_data:
            has_position_data = True

        total_t = len(trades)
        win_t = len([t for t in trades if t.get("pnlcomm", 0) > 0])

        strategy_summaries.append(
            {
                "id": source.id,
                "strategy_id": source.strategy_id,
                "strategy_name": source.strategy_name,
                "status": source.status,
                "position_source": source.position_source,
                "account_source": source.account_source,
                "account_counted_in_totals": account_counted,
                "asset_spec_source": source.asset_spec_source,
                "valuation_status": source.valuation_status,
                "valuation_warnings": list(source.valuation_warnings),
                "total_assets": _safe_round(account_value if account_value is not None else final),
                "initial_capital": _safe_round(initial),
                "pnl": _safe_round(
                    (account_value - initial) if account_value is not None and initial > 0 else pnl
                ),
                "pnl_pct": _safe_round(
                    (
                        (account_value - initial) / initial * 100
                        if account_value is not None and initial > 0
                        else pnl_pct
                    ),
                    2,
                ),
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


@router.get("/positions", summary="Aggregated positions (live trading)", response_model=None)
async def get_portfolio_positions(
    include_inactive: bool = False,
    current_user: typing.Any = Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
) -> typing.Any:
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
    sources = await _portfolio_sources(current_user, mgr, include_inactive=include_inactive)
    positions = []

    for source in sources:
        cur_pos = _valued_source_positions(source)
        for p in cur_pos:
            size = float(p.get("size") or 0.0)
            if abs(size) <= EPSILON:
                continue
            price = float(p.get("price") or 0.0)
            market_value = float(p.get("market_value") or 0.0)
            latest_price = float(p.get("latest_price") or price)
            position_pnl = float(p.get("position_pnl") or 0.0)
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
                        float(p.get("signed_market_value") or 0.0), 6
                    ),
                    "position_pnl": _safe_round(position_pnl),
                    "gross_pnl": _safe_round(float(p.get("gross_pnl") or 0.0)),
                    "commission": _safe_round(float(p.get("commission") or 0.0), 4),
                    "commission_source": p.get("commission_source"),
                    "multiplier": _safe_round(float(p.get("multiplier") or 1.0), 8),
                    "margin_rate": _safe_round(float(p.get("margin_rate") or 0.0), 8),
                    "leverage": p.get("leverage"),
                    "margin_value": _safe_round(float(p.get("margin_value") or 0.0)),
                    "updated_at": _position_updated_at(p),
                    "data_time": _position_data_time(p),
                    "direction": "long" if size > 0 else ("short" if size < 0 else "flat"),
                    "position_source": p.get("position_source"),
                    "asset_spec_source": p.get("asset_spec_source"),
                    "valuation_status": p.get("valuation_status"),
                    "valuation_warnings": list(p.get("valuation_warnings") or []),
                }
            )

    response = {
        "total": len(positions),
        "positions": positions,
        "summary": _build_position_summary(positions),
    }
    warnings = [
        warning for source in sources for warning in list(source.valuation_warnings) if warning
    ]
    if warnings:
        response["warnings"] = warnings
    return response


# ---------- Aggregated Trades ----------


@router.get("/trades", summary="Aggregated trade records (live trading)", response_model=None)
async def get_portfolio_trades(
    limit: int = 200,
    workspace_ids: Annotated[list[str] | None, Query()] = None,
    include_inactive: bool = Query(default=False),
    current_user: typing.Any = Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
) -> typing.Any:
    """Return historical trades across strategies (from trade.log), sorted by close time.

    Args:
        limit: Maximum number of trades to return.
        current_user: The authenticated user.
        mgr: The live trading manager.

    Returns:
        A dictionary containing total count and list of trades, sorted by
        close date in descending order (most recent first).
    """
    workspace_id_set = _parse_query_ids(workspace_ids)
    include_inactive_sources = include_inactive
    sources = await _portfolio_sources(
        current_user,
        mgr,
        include_inactive=include_inactive_sources,
    )
    if workspace_id_set:
        sources = [source for source in sources if source.workspace_id in workspace_id_set]
    if not include_inactive:
        sources = [
            source for source in sources
            if str(source.status or "").strip().lower() in _ACTIVE_TRADING_STATUSES
        ]
    all_trades = []

    for source in sources:
        started_day = None if include_inactive else _source_started_day(source)
        trades = _source_trades(source, started_day=started_day)
        for t in trades:
            item = dict(t)
            item["strategy_id"] = source.strategy_id
            item["strategy_name"] = source.strategy_name
            item["instance_id"] = source.id
            item["workspace_id"] = source.workspace_id
            all_trades.append(item)

    # Sort by close date descending
    all_trades.sort(key=lambda x: x.get("dtclose", ""), reverse=True)

    return {"total": len(all_trades), "trades": all_trades[:limit]}


# ---------- Portfolio Equity Curve ----------


_PAPER_RUNTIME_MODES = frozenset({"paper", "simulation", "simulated"})
_MAX_PORTFOLIO_EQUITY_POINTS = 1_500


def _is_paper_runtime_source(source: _PortfolioSource) -> bool:
    """Return whether a source represents a simulated trading runtime."""
    return str(source.trading_mode or "paper").strip().lower() in _PAPER_RUNTIME_MODES


def _sample_indexes(length: int, max_points: int = _MAX_PORTFOLIO_EQUITY_POINTS) -> list[int]:
    """Return shared sample indexes so every portfolio series stays aligned."""
    if length <= max_points:
        return list(range(length))
    step = (length - 1) / (max_points - 1)
    return [round(index * step) for index in range(max_points)]


async def _paper_equity_points(
    current_user: typing.Any,
    sources: list[_PortfolioSource],
) -> dict[str, list[tuple[str, float, float, float]]]:
    """Load canonical equity snapshots for the current run of each paper instance."""
    instance_ids = sorted({source.id for source in sources if _is_paper_runtime_source(source)})
    user_id = _current_user_id(current_user)
    if not instance_ids or not user_id:
        return {}

    async with async_session_maker() as session:
        result = await session.execute(
            select(PaperEquitySnapshot)
            .where(
                PaperEquitySnapshot.user_id == user_id,
                PaperEquitySnapshot.instance_id.in_(instance_ids),
            )
            .order_by(
                PaperEquitySnapshot.instance_id,
                PaperEquitySnapshot.observed_at,
                PaperEquitySnapshot.id,
            )
        )
        snapshots = result.scalars().all()

    points_by_instance: dict[str, list[tuple[str, float, float, float]]] = {}
    for snapshot in snapshots:
        observed_at = snapshot.observed_at.replace(second=0, microsecond=0)
        point = (
            observed_at.isoformat(),
            float(snapshot.total_equity),
            float(snapshot.cash),
            float(snapshot.realized_pnl) + float(snapshot.unrealized_pnl),
        )
        # A paper instance id is deliberately reused when a workspace unit is
        # restarted. ``initial`` marks the beginning of the new runtime, so
        # prior snapshots must not be joined to its current equity curve.
        if str(snapshot.source or "").strip().lower() == "initial":
            points_by_instance[snapshot.instance_id] = []
        instance_points = points_by_instance.setdefault(snapshot.instance_id, [])
        if instance_points and instance_points[-1][0] == point[0]:
            instance_points[-1] = point
        else:
            instance_points.append(point)

    return points_by_instance


def _paper_runtime_value_data(
    source: _PortfolioSource,
    paper_points: list[tuple[str, float, float, float]],
) -> dict[str, list[Any]]:
    """Prepend current-runtime log history that predates paper snapshots."""
    snapshot_dates = [point[0] for point in paper_points]
    snapshot_equity = [point[1] for point in paper_points]
    snapshot_cash = [point[2] for point in paper_points]
    snapshot_pnl = [point[3] for point in paper_points]

    # ``parse_value_log`` already handles a missing or empty log directory.
    # Do not pre-filter with ``Path.is_dir``: compatibility adapters may hand
    # us a path-like runtime log location whose existence is resolved by the
    # parser itself, and an empty snapshot history must still fall back to it.
    log_data = parse_value_log(source.log_dir, prefer_log_time=False) if source.log_dir else {}
    log_dates = list(log_data.get("datetimes") or log_data.get("dates", []))
    log_equity = list(log_data.get("equity_curve", []))
    log_cash = list(log_data.get("cash_curve", []))
    first_snapshot_day = _trading_day(snapshot_dates[0]) if snapshot_dates else ""

    history_dates: list[str] = []
    history_equity: list[float] = []
    history_cash: list[float] = []
    history_pnl: list[float] = []
    initial_log_equity = _safe_float(log_equity[0]) if log_equity else 0.0
    initial_log_cash = _safe_float(log_cash[0]) if log_cash else initial_log_equity
    base_equity = snapshot_equity[0] if snapshot_equity else initial_log_equity
    base_cash = snapshot_cash[0] if snapshot_cash else initial_log_cash
    base_pnl = snapshot_pnl[0] if snapshot_pnl else 0.0
    for index, dt in enumerate(log_dates):
        if index >= len(log_equity):
            break
        if first_snapshot_day and _trading_day(dt) >= first_snapshot_day:
            continue
        equity_delta = _safe_float(log_equity[index]) - initial_log_equity
        cash_delta = (
            _safe_float(log_cash[index]) - initial_log_cash
            if index < len(log_cash)
            else equity_delta
        )
        history_dates.append(str(dt))
        history_equity.append(base_equity + equity_delta)
        history_cash.append(base_cash + cash_delta)
        history_pnl.append(base_pnl + equity_delta)

    return {
        "datetimes": [*history_dates, *snapshot_dates],
        "equity_curve": [*history_equity, *snapshot_equity],
        "cash_curve": [*history_cash, *snapshot_cash],
        "pnl_curve": [*history_pnl, *snapshot_pnl],
    }


@router.get("/equity", summary="Portfolio equity curve (live trading)", response_model=None)
async def get_portfolio_equity(
    workspace_ids: Annotated[list[str] | None, Query()] = None,
    include_inactive: bool = Query(default=False),
    current_user: typing.Any = Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
) -> typing.Any:
    """Return portfolio-level equity curve - aligning and stacking strategy equity by date.

    Also returns individual strategy equity curves so the client can switch
    between the whole portfolio and a strategy unit.

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
    workspace_id_set = _parse_query_ids(workspace_ids)
    include_inactive_sources = include_inactive
    sources = await _portfolio_sources(
        current_user,
        mgr,
        include_inactive=include_inactive_sources,
    )
    if workspace_id_set:
        sources = [source for source in sources if source.workspace_id in workspace_id_set]
    if not include_inactive:
        sources = [source for source in sources if _is_running_portfolio_source(source)]

    paper_points_by_source = await _paper_equity_points(current_user, sources)

    # Each strategy's date -> value mapping
    strategy_curves: list[dict[str, Any]] = []
    unavailable_strategies: list[dict[str, Any]] = []
    all_dates_set: set = set()
    counted_account_keys: set[str] = set()

    for source in sources:
        paper_runtime_source = _is_paper_runtime_source(source)
        if paper_runtime_source:
            paper_points = paper_points_by_source.get(source.id, [])
            value_data = _paper_runtime_value_data(source, paper_points)
        else:
            log_dir = source.log_dir
            value_data = parse_value_log(log_dir, prefer_log_time=True) if log_dir else {}
        dates = value_data.get("datetimes") or value_data.get("dates", [])
        equity = value_data.get("equity_curve", [])
        cash = value_data.get("cash_curve", [])
        pnl = value_data.get("pnl_curve", [])
        # A canonical paper snapshot is already scoped to the active runtime.
        # When it is not available we are reading a regular runtime log, so the
        # same start-time guard used by live strategies must apply.
        has_paper_snapshot = paper_runtime_source and bool(paper_points)
        if not include_inactive and not has_paper_snapshot:
            started_day = _source_started_day(source)
            if dates and equity:
                dates, equity, cash = _trim_curve_by_source_start(
                    dates=dates,
                    equity=equity,
                    cash=cash,
                    source_started_day=started_day,
                )

        if not pnl and equity:
            initial_equity = float(equity[0])
            pnl = [float(value) - initial_equity for value in equity]

        if not dates:
            # Paper snapshots belong to workspace units. Legacy manager
            # instances without a workspace must still be able to show their
            # gateway account when no local curve has been written yet.
            if paper_runtime_source and source.unit_id:
                unavailable_strategies.append(
                    {
                        "strategy_id": source.strategy_id,
                        "strategy_name": source.strategy_name,
                        "instance_id": source.id,
                        "values": [],
                        "value_source": "paper_snapshot_unavailable",
                    }
                )
                continue
            account_value = _source_account_value(source)
            if account_value is None:
                unavailable_strategies.append(
                    {
                        "strategy_id": source.strategy_id,
                        "strategy_name": source.strategy_name,
                        "instance_id": source.id,
                        "values": [],
                        "value_source": "unavailable",
                    }
                )
                continue
            account_key = _source_account_key(source)
            if account_key in counted_account_keys:
                unavailable_strategies.append(
                    {
                        "strategy_id": source.strategy_id,
                        "strategy_name": source.strategy_name,
                        "instance_id": source.id,
                        "values": [],
                        "value_source": "shared_account",
                    }
                )
                continue
            counted_account_keys.add(account_key)
            live_date = _source_account_time(source)
            dates = [live_date]
            equity = [account_value]
            cash = [_source_account_cash(source) or 0.0]
            pnl = [0.0]
            value_source = source.account_source or "gateway"
        else:
            value_source = "paper_snapshot_with_runtime_log" if has_paper_snapshot else "log"

        date_map = {}
        for i, dt in enumerate(dates):
            date_map[dt] = {
                "equity": equity[i] if i < len(equity) else 0,
                "cash": cash[i] if i < len(cash) else 0,
                "pnl": pnl[i] if i < len(pnl) else 0,
            }
        all_dates_set.update(dates)

        strategy_curves.append(
            {
                "strategy_id": source.strategy_id,
                "strategy_name": source.strategy_name,
                "instance_id": source.id,
                "date_map": date_map,
                "initial": equity[0] if equity else 0,
                "first_trading_day": _trading_day(dates[0]) if dates else "",
                "value_source": value_source,
            }
        )

    if not all_dates_set:
        return {
            "dates": [],
            "total_equity": [],
            "cumulative_pnl": [],
            "total_drawdown": [],
            "strategies": unavailable_strategies,
        }

    sorted_dates = sorted(all_dates_set)

    # Aggregate
    total_equity = []
    cumulative_pnl = []
    strategy_series = {sc["instance_id"]: [] for sc in strategy_curves}
    strategy_pnl_series = {sc["instance_id"]: [] for sc in strategy_curves}

    for dt in sorted_dates:
        day_total = 0.0
        day_pnl = 0.0
        for sc in strategy_curves:
            dm = sc["date_map"]
            if dt in dm:
                val = dm[dt]["equity"]
                sc["_seen"] = True
                series_val = val
                pnl_val = dm[dt]["pnl"]
                sc["_pnl_seen"] = True
            elif sc.get("_seen"):
                val = sc.get("_last", sc.get("initial", 0.0))
                series_val = val
                pnl_val = sc.get("_last_pnl", 0.0)
            else:
                # A process that first reports later in the *same* trading day
                # already had its initial capital at market open. Seed it only
                # within that day so an intraday startup does not create a
                # false portfolio jump. Earlier trading days must remain zero:
                # the runtime did not exist yet and should not rewrite history.
                starts_today = _trading_day(dt) == sc.get("first_trading_day")
                val = sc.get("initial", 0.0) if starts_today else 0.0
                series_val = val
                pnl_val = 0.0
            sc["_last"] = val
            sc["_last_pnl"] = pnl_val
            day_total += val
            day_pnl += pnl_val
            strategy_series[sc["instance_id"]].append(_safe_round(series_val))
            strategy_pnl_series[sc["instance_id"]].append(_safe_round(pnl_val))
        total_equity.append(_safe_round(day_total))
        cumulative_pnl.append(_safe_round(day_pnl))

    # Drawdown must use the same high-water mark as the total-equity curve
    # rendered by the client.  A cumulative-PnL peak with fixed initial capital
    # becomes inaccurate when the portfolio's capital or strategy mix changes.
    total_drawdown = []
    equity_peak = 0.0
    for equity_value in total_equity:
        equity_peak = max(equity_peak, equity_value)
        drawdown = (
            (equity_value - equity_peak) / equity_peak
            if equity_peak > EPSILON
            else 0.0
        )
        total_drawdown.append(_safe_round(drawdown, 6))

    # Sampling only after aggregation keeps every strategy on the same time
    # axis. Per-instance sampling creates staggered gaps and visible sawtooth
    # jumps when hundreds of runtimes are combined.
    sample_indexes = _sample_indexes(len(sorted_dates))
    sorted_dates = [sorted_dates[index] for index in sample_indexes]
    total_equity = [total_equity[index] for index in sample_indexes]
    cumulative_pnl = [cumulative_pnl[index] for index in sample_indexes]
    total_drawdown = [total_drawdown[index] for index in sample_indexes]
    strategy_series = {
        instance_id: [values[index] for index in sample_indexes]
        for instance_id, values in strategy_series.items()
    }
    strategy_pnl_series = {
        instance_id: [values[index] for index in sample_indexes]
        for instance_id, values in strategy_pnl_series.items()
    }

    strategies_out = []
    for sc in strategy_curves:
        strategies_out.append(
            {
                "strategy_id": sc["strategy_id"],
                "strategy_name": sc["strategy_name"],
                "instance_id": sc["instance_id"],
                "values": strategy_series[sc["instance_id"]],
                "pnl_values": strategy_pnl_series[sc["instance_id"]],
                "value_source": sc.get("value_source"),
            }
        )

    return {
        "dates": sorted_dates,
        "total_equity": total_equity,
        "cumulative_pnl": cumulative_pnl,
        "total_drawdown": total_drawdown,
        "strategies": [*strategies_out, *unavailable_strategies],
    }


# ---------- Asset Allocation ----------


def _allocation_asset_key(symbol: Any) -> str:
    """Return a stable display key that groups equivalent broker symbol aliases."""
    raw_symbol = str(symbol or "").strip()
    if not raw_symbol:
        return ""
    candidates = [
        "".join(character for character in str(alias).upper() if character.isalnum())
        for alias in symbol_aliases(raw_symbol)
    ]
    candidates = [candidate for candidate in candidates if candidate]
    return min(candidates, key=len) if candidates else raw_symbol.upper()


@router.get(
    "/allocation", summary="Asset allocation by open positions (live trading)", response_model=None
)
async def get_portfolio_allocation(
    workspace_ids: Annotated[list[str] | None, Query()] = None,
    include_inactive: bool = Query(default=False),
    current_user: typing.Any = Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
) -> typing.Any:
    """Return the open-position allocation of each traded asset in the portfolio.

    Positions from the same asset are merged across strategies and workspaces.
    Allocation weights use gross market exposure, so long and short legs both
    contribute to an asset's share of the portfolio.

    Args:
        workspace_ids: Optional trading workspace IDs to include.
        current_user: The authenticated user.
        mgr: The live trading manager.

    Returns:
        A dictionary containing:
            - total: Total gross market exposure of open positions
            - items: One merged allocation item per traded asset
    """
    workspace_id_set = _parse_query_ids(workspace_ids)
    include_inactive_sources = include_inactive
    sources = await _portfolio_sources(
        current_user,
        mgr,
        include_inactive=include_inactive_sources,
    )
    if workspace_id_set:
        sources = [source for source in sources if source.workspace_id in workspace_id_set]
        if not include_inactive:
            sources = [
                source for source in sources
                if str(source.status or "").strip().lower() in _ACTIVE_TRADING_STATUSES
            ]

    allocations: dict[str, dict[str, Any]] = {}
    total = 0.0

    for source in sources:
        for position in _valued_source_positions(source):
            size = _safe_float(position.get("size"), 0.0)
            market_value = abs(_safe_float(position.get("market_value"), 0.0))
            asset = _allocation_asset_key(position.get("data_name"))
            if not asset or abs(size) <= EPSILON or market_value <= EPSILON:
                continue
            item = allocations.setdefault(
                asset,
                {
                    "asset": asset,
                    "value": 0.0,
                    "long_value": 0.0,
                    "short_value": 0.0,
                    "net_value": 0.0,
                    "position_count": 0,
                },
            )
            item["value"] += market_value
            if size > 0:
                item["long_value"] += market_value
                item["net_value"] += market_value
            else:
                item["short_value"] += market_value
                item["net_value"] -= market_value
            item["position_count"] += 1
            total += market_value

    items = sorted(allocations.values(), key=lambda item: (-item["value"], item["asset"]))
    for item in items:
        item["value"] = _safe_round(item["value"])
        item["long_value"] = _safe_round(item["long_value"])
        item["short_value"] = _safe_round(item["short_value"])
        item["net_value"] = _safe_round(item["net_value"])
        item["weight"] = _safe_round(item["value"] / total * 100, 2) if total > 0 else 0

    return {"total": _safe_round(total), "items": items}


# =====================================================================
# Simulation trading variants
# =====================================================================


@router.get(
    "/simulation/overview", summary="Portfolio overview (simulation trading)", response_model=None
)
async def get_simulation_portfolio_overview(
    current_user: typing.Any = Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
) -> typing.Any:
    """Simulation portfolio overview.

    Currently reuses the same aggregation logic as live trading. This keeps the
    API stable for the frontend while allowing the underlying data source to be
    customized later if simulation instances are stored separately.
    """
    # Reuse the same logic as get_portfolio_overview for now
    return await get_portfolio_overview(current_user=current_user, mgr=mgr)


@router.get(
    "/simulation/positions",
    summary="Aggregated positions (simulation trading)",
    response_model=None,
)
async def get_simulation_portfolio_positions(
    current_user: typing.Any = Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
) -> typing.Any:
    """Simulation current positions across strategies.

    See `get_portfolio_positions` for field details.
    """
    return await get_portfolio_positions(current_user=current_user, mgr=mgr)


@router.get(
    "/simulation/trades",
    summary="Aggregated trade records (simulation trading)",
    response_model=None,
)
async def get_simulation_portfolio_trades(
    limit: int = 200,
    workspace_ids: Annotated[list[str] | None, Query()] = None,
    current_user: typing.Any = Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
) -> typing.Any:
    """Simulation historical trades across strategies.

    See `get_portfolio_trades` for field details.
    """
    return await get_portfolio_trades(
        limit=limit,
        workspace_ids=workspace_ids,
        current_user=current_user,
        mgr=mgr,
    )


@router.get(
    "/simulation/equity", summary="Portfolio equity curve (simulation trading)", response_model=None
)
async def get_simulation_portfolio_equity(
    current_user: typing.Any = Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
) -> typing.Any:
    """Simulation portfolio-level equity curve.

    See `get_portfolio_equity` for field details.
    """
    return await get_portfolio_equity(current_user=current_user, mgr=mgr)


@router.get(
    "/simulation/allocation",
    summary="Asset allocation by open positions (simulation trading)",
    response_model=None,
)
async def get_simulation_portfolio_allocation(
    workspace_ids: Annotated[list[str] | None, Query()] = None,
    current_user: typing.Any = Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
) -> typing.Any:
    """Simulation allocation across traded assets.

    See `get_portfolio_allocation` for field details.
    """
    return await get_portfolio_allocation(
        workspace_ids=workspace_ids,
        current_user=current_user,
        mgr=mgr,
    )
