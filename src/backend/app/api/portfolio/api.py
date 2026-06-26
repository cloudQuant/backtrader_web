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
from dataclasses import dataclass, field
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
from app.services.position_valuation import EPSILON, contract_spec_for, value_position
from app.services.strategy_service import get_strategy_dir
from app.services.trading_asset_info_service import (
    gateway_position_symbol,
    load_runtime_config,
    normalize_gateway_position,
    signed_gateway_size,
    symbol_aliases,
)

logger = logging.getLogger(__name__)
router = APIRouter()
_ACTIVE_TRADING_STATUSES = {"queued", "running"}
_COMMISSION_FIELD_KEYS = (
    "commission",
    "comm",
    "fee",
    "fees",
    "execFee",
    "exec_fee",
    "execFeeV2",
    "exec_fee_v2",
    "open_commission",
    "position_fee",
    "position_commission",
    "trade_fee",
    "trade_commission",
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
_EXPLICIT_NET_PNL_FIELD_KEYS = ("pnlcomm", "net_pnl", "netPnl", "netPNL")


@dataclass
class _PortfolioSource:
    id: str
    strategy_id: str
    strategy_name: str
    status: str
    symbol: str = ""
    workspace_id: str | None = None
    trading_mode: str = "paper"
    log_dir: Path | None = None
    snapshot: dict[str, Any] | None = None
    live_positions: list[dict[str, Any]] | None = None
    live_account: dict[str, Any] | None = None
    valuation_configs: tuple[dict[str, Any], ...] = ()
    position_source: str | None = None
    account_source: str | None = None
    asset_spec_source: str | None = None
    valuation_status: str = "empty"
    valuation_warnings: list[str] = field(default_factory=list)


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
    )


def _workspace_unit_log_dir(unit: StrategyUnit) -> Path | None:
    runtime_dir = workspace_unit_runtime.unit_dir(str(unit.workspace_id), str(unit.id))
    latest = find_latest_log_dir(runtime_dir)
    return Path(latest) if latest else None


def _workspace_unit_runtime_config(unit: StrategyUnit) -> dict[str, Any]:
    runtime_dir = workspace_unit_runtime.unit_dir(str(unit.workspace_id), str(unit.id))
    return load_runtime_config(runtime_dir)


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
        gateway_config = unit.gateway_config if isinstance(unit.gateway_config, dict) else {}
        runtime_config = _workspace_unit_runtime_config(unit)
        unit_name = str(unit.strategy_name or unit.strategy_id or unit.id)
        sources.append(
            _PortfolioSource(
                id=str(unit.trading_instance_id or unit.id),
                strategy_id=str(unit.strategy_id or unit.id),
                strategy_name=f"{workspace.name} / {unit_name}",
                status=str(unit.run_status or snapshot.get("instance_status") or "idle"),
                symbol=str(unit.symbol or ""),
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
            )
        )
    return sources


def _asset_spec_for_symbol(specs: dict[str, dict[str, Any]], symbol: str) -> dict[str, Any]:
    for key in symbol_aliases(symbol):
        item = specs.get(key)
        if isinstance(item, dict):
            return dict(item)
    return {}


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
        for container_key in ("contract_metadata", "contracts", "contract_specs", "instrument_specs"):
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
                recent_trades.extend(dict(item) for item in raw_trades if isinstance(item, dict))

    positions: list[dict[str, Any]] = []
    for item in matched_positions:
        symbol = gateway_position_symbol(item, source.symbol)
        positions.append(
            normalize_gateway_position(
                item,
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
                _append_unique(source.valuation_warnings, "检查策略网关绑定失败，账户权益将回落到日志")
            return None

    query_account = getattr(mgr, "query_instance_gateway_account", None)
    if not callable(query_account):
        if is_live:
            _append_unique(source.valuation_warnings, "当前管理器不支持实时网关账户查询，账户权益将回落到日志")
        return None
    try:
        account = query_account(source.id)
    except Exception:
        if is_live:
            _append_unique(source.valuation_warnings, "交易所网关账户查询失败，账户权益将回落到日志")
        return None
    if not isinstance(account, dict):
        if is_live:
            _append_unique(source.valuation_warnings, "交易所网关账户返回格式异常，账户权益将回落到日志")
        return None
    source.account_source = str(account.get("account_source") or "gateway").strip() or "gateway"
    return account


async def _portfolio_sources(
    current_user: Any,
    mgr: LiveTradingManager,
) -> list[_PortfolioSource]:
    workspace_sources = await _active_workspace_sources(current_user)
    sources = (
        workspace_sources
        if workspace_sources
        else [_source_from_instance(inst) for inst in _list_user_instances(mgr, current_user)]
    )
    for source in sources:
        live_positions = _live_positions_for_source(mgr, source)
        if live_positions is not None:
            source.live_positions = live_positions
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
        size = signed_gateway_size(row)
        if abs(size) <= EPSILON:
            continue
        price = _first_number(
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
        ) or 0.0
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
        source.position_source = str((source.snapshot or {}).get("position_source") or "snapshot")
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
    elif getattr(spec, "has_commission", False) and not has_real_commission and _has_any(
        row, *_GROSS_PNL_FIELD_KEYS
    ):
        warnings.append("持仓手续费未从交易所成交/持仓回报确认，当前按资产费率估算")
    return warnings


def _position_row_should_recalculate_local_pnl(
    row: dict[str, Any],
    spec: Any,
    *,
    position_source: str,
) -> bool:
    if str(position_source or "").strip().lower() == "gateway":
        return False
    if _has_any(row, *_EXPLICIT_NET_PNL_FIELD_KEYS):
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
        "avgCost",
        "avgPrice",
        "avgPx",
        "entryPrice",
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
    return _has_any(row, *_GROSS_PNL_FIELD_KEYS, "pnl")


def _position_row_for_valuation(
    row: dict[str, Any],
    spec: Any,
    *,
    position_source: str,
) -> dict[str, Any]:
    item = dict(row)
    if not _position_row_should_recalculate_local_pnl(
        item,
        spec,
        position_source=position_source,
    ):
        return item
    for key in (*_GROSS_PNL_FIELD_KEYS, "pnl"):
        item.pop(key, None)
    item["recalculated_position_pnl"] = True
    return item


def _valued_source_positions(source: _PortfolioSource) -> list[dict[str, Any]]:
    positions: list[dict[str, Any]] = []
    for row in _source_positions(source):
        symbol = str(row.get("data_name") or row.get("symbol") or "")
        spec = contract_spec_for(symbol, row, source.snapshot or {}, *source.valuation_configs)
        position_source = str(
            row.get("position_source")
            or row.get("source")
            or source.position_source
            or "local"
        ).strip()
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
            source.asset_spec_source = _unique_text([source.asset_spec_source, asset_spec_source])
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


def _source_trades(source: _PortfolioSource) -> list[dict[str, Any]]:
    if source.log_dir:
        return parse_trade_log(source.log_dir)
    return [
        dict(item) for item in (source.snapshot or {}).get("trades") or [] if isinstance(item, dict)
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
    counted_account_keys: set[str] = set()

    for source in sources:
        log_dir = source.log_dir
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

        value_data = parse_value_log(log_dir)
        equity = value_data.get("equity_curve", [])
        cash = value_data.get("cash_curve", [])
        trades = parse_trade_log(log_dir)

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
    counted_account_keys: set[str] = set()

    for source in sources:
        log_dir = source.log_dir
        value_data = parse_value_log(log_dir) if log_dir else {}
        dates = value_data.get("datetimes") or value_data.get("dates", [])
        equity = value_data.get("equity_curve", [])
        cash = value_data.get("cash_curve", [])

        if not dates:
            account_value = _source_account_value(source)
            if account_value is None:
                continue
            account_key = _source_account_key(source)
            if account_key in counted_account_keys:
                continue
            counted_account_keys.add(account_key)
            live_date = _source_account_time(source)
            dates = [live_date]
            equity = [account_value]
            cash = [_source_account_cash(source) or 0.0]
            value_source = source.account_source or "gateway"
        else:
            value_source = "log"

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
                "value_source": value_source,
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
                sc["_seen"] = True
            else:
                # Before a strategy's first point, it should contribute zero;
                # after that, carry its last known value forward.
                val = sc.get("_last", 0.0) if sc.get("_seen") else 0.0
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
                "value_source": sc.get("value_source"),
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
    counted_account_keys: set[str] = set()

    for source in sources:
        final = 0.0
        value_source = "log"
        account_value = _source_account_value(source)
        if account_value is not None:
            account_key = _source_account_key(source)
            if account_key in counted_account_keys:
                continue
            counted_account_keys.add(account_key)
            final = account_value
            value_source = source.account_source or "gateway"
        elif source.log_dir:
            value_data = parse_value_log(source.log_dir)
            equity = value_data.get("equity_curve", [])
            final = equity[-1] if equity else 0
        else:
            continue
        total += final
        items.append(
            {
                "strategy_id": source.strategy_id,
                "strategy_name": source.strategy_name,
                "instance_id": source.id,
                "value": _safe_round(final),
                "value_source": value_source,
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
