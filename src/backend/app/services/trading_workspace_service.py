"""
Trading workspace service.

Provides strategy-unit level trading orchestration by reusing the existing
live trading manager/runtime while persisting state on workspace units.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from app.models.workspace import StrategyUnit
from app.schemas.trading import PositionManagerResponse, TradingDailySummaryResponse
from app.schemas.workspace import UnitStatusResponse
from app.services import workspace_unit_runtime
from app.services.auto_trading_scheduler import get_auto_trading_scheduler
from app.services.live_trading_manager import get_live_trading_manager
from app.services.log_parser_service import (
    parse_current_position,
    parse_log_dir,
    parse_position_log,
)
from app.services.position_valuation import EPSILON, contract_spec_for, value_position
from app.services.trading_asset_info_service import (
    LONG_POSITION_FIELD_KEYS,
    SHORT_POSITION_FIELD_KEYS,
    gateway_position_symbol,
    normalize_gateway_position,
    query_local_asset_spec,
    split_bidirectional_position_row,
    symbol_aliases,
)

_LIGHT_HYDRATE_PRESERVE_KEYS = (
    "today_pnl",
    "change_pct",
    "leverage",
    "cumulative_pnl",
    "max_drawdown_rate",
    "trading_day",
    "detail_route",
    "trades",
)
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
_PNL_FIELD_KEYS = (*_EXPLICIT_NET_PNL_FIELD_KEYS, "position_pnl", "pnl")
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
_POSITION_SIZE_ALIAS_KEYS = (
    "volume",
    "position",
    "qty",
    "quantity",
    "position_volume",
    "positionAmt",
    "pos",
    "pa",
    "Position",
    "Volume",
    "Qty",
    "Quantity",
    *LONG_POSITION_FIELD_KEYS,
    *SHORT_POSITION_FIELD_KEYS,
)
_POSITION_RESPONSE_REVALUE_KEYS = (
    "instrument",
    "InstrumentID",
    "instId",
    "contract",
    "side",
    "positionIdx",
    "pos",
    "posSide",
    "Position",
    "Volume",
    "Qty",
    "Quantity",
    "PosiDirection",
    "posi_direction",
    "position_direction",
    "price_open",
    "avgPx",
    "last_price",
    "lastPrice",
    "markPx",
    "markPrice",
    "LastPrice",
    "Price",
    "AveragePrice",
    "PositionCost",
    "position_cost",
    "positionValue",
    "VolumeMultiple",
    "CONTRACT_MULTIPLIER",
    "LongMarginRatioByMoney",
    "ShortMarginRatioByMoney",
    "LongMarginRatioByVolume",
    "ShortMarginRatioByVolume",
    "MARGIN_BUY",
    "MARGIN_SELL",
    "MARGIN_PER_LOT",
    "imr",
    "mmr",
    "positionIM",
    "positionIMByMp",
    "lever",
    "mgnMode",
    "OpenRatioByMoney",
    "OpenRatioByVolume",
    "OPEN_FEE_RATE",
    "OPEN_FEE_AMOUNT",
    "COMMISSION_OPEN_RATIO",
    "COMMISSION_OPEN_AMOUNT",
)
_CURRENT_PRICE_FIELD_KEYS = (
    "current_price",
    "latest_price",
    "last_price",
    "mark_price",
    "markPrice",
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


def _now_local_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_iso_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _round_quantity(value: Any) -> float:
    number = _safe_float(value, 0.0)
    rounded = round(number, 4)
    if abs(number) > EPSILON and abs(rounded) <= EPSILON:
        rounded = round(number, 8)
        if abs(rounded) <= EPSILON:
            return number
    return rounded


def _safe_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _unique_text(values: list[Any]) -> str | None:
    texts = [str(value or "").strip() for value in values]
    unique = sorted({text for text in texts if text})
    if not unique:
        return None
    if len(unique) == 1:
        return unique[0]
    return "mixed"


def _unique_number(values: list[Any]) -> float | None:
    numbers: list[float] = []
    for value in values:
        if value in (None, ""):
            continue
        number = _safe_float(value)
        numbers.append(number)
    if not numbers:
        return None
    first = numbers[0]
    if all(abs(item - first) <= EPSILON for item in numbers):
        return first
    return None


def _leverage_from_margin_rate(value: Any) -> float | None:
    margin_rate = _safe_float(value)
    if margin_rate <= EPSILON:
        return None
    return round(1.0 / margin_rate, 8)


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


def _merge_unit_contract_metadata(
    specs: dict[str, dict[str, Any]],
    unit: StrategyUnit,
    instance: dict[str, Any] | None,
    symbols: list[str],
) -> dict[str, dict[str, Any]]:
    completed = {str(key): dict(value) for key, value in specs.items() if isinstance(value, dict)}
    instance_params = _safe_dict((instance or {}).get("params"))
    configs = (
        _safe_dict(getattr(unit, "params", None)),
        _safe_dict(getattr(unit, "unit_settings", None)),
        _safe_dict(getattr(unit, "data_config", None)),
        _safe_dict(getattr(unit, "gateway_config", None)),
        instance_params,
        _safe_dict(instance_params.get("unit_settings")),
        _safe_dict(instance_params.get("data_config")),
        _safe_dict(instance_params.get("gateway")),
        _safe_dict(instance_params.get("simulate")),
        _safe_dict(instance_params.get("backtest")),
        _safe_dict(instance_params.get("live")),
    )
    for symbol in symbols:
        if _asset_spec_has_contract_metadata(_asset_spec_for_symbol(completed, symbol)):
            continue
        for config in configs:
            metadata = _metadata_from_config(config, symbol)
            if metadata:
                _merge_asset_spec_aliases(completed, symbol, metadata)
                break
    return completed


def _merge_asset_spec_aliases(
    specs: dict[str, dict[str, Any]],
    symbol: str,
    spec: dict[str, Any],
) -> None:
    if not spec:
        return
    existing = _asset_spec_for_symbol(specs, symbol)
    merged = dict(spec)
    merged.update(existing)
    existing_source = str(existing.get("source") or existing.get("asset_spec_source") or "").strip()
    next_source = str(spec.get("source") or spec.get("asset_spec_source") or "").strip()
    if existing_source and next_source and existing_source != next_source:
        merged["source"] = f"{existing_source}+{next_source}"
        merged["asset_spec_source"] = merged["source"]
    for key in symbol_aliases(symbol):
        specs[str(key)] = dict(merged)


def _asset_spec_has_contract_metadata(spec: dict[str, Any]) -> bool:
    return any(
        spec.get(key) not in (None, "")
        for key in (
            "multiplier",
            "mult",
            "contract_size",
            "trade_contract_size",
            "contract_multiplier",
            "ctVal",
            "VolumeMultiple",
            "CONTRACT_MULTIPLIER",
            "margin",
            "margin_rate",
            "margin_ratio",
            "leverage",
            "margin_amount",
            "initial_margin_per_lot",
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
        )
    )


def _complete_asset_specs_from_local(
    specs: dict[str, dict[str, Any]],
    symbols: list[str],
) -> dict[str, dict[str, Any]]:
    completed = {str(key): dict(value) for key, value in specs.items() if isinstance(value, dict)}
    for symbol in symbols:
        if _asset_spec_has_contract_metadata(_asset_spec_for_symbol(completed, symbol)):
            continue
        try:
            local_spec = query_local_asset_spec(symbol)
        except Exception:
            local_spec = {}
        if isinstance(local_spec, dict) and local_spec:
            _merge_asset_spec_aliases(completed, symbol, local_spec)
    return completed


def _append_symbol_candidate(target: list[str], value: Any) -> None:
    text = str(value or "").strip()
    if text and text not in target:
        target.append(text)


def _append_config_symbols(target: list[str], config: dict[str, Any]) -> None:
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
    ):
        _append_symbol_candidate(target, config.get(key))
    for key in ("symbols", "symbol_list", "instruments"):
        values = config.get(key)
        if isinstance(values, (list, tuple, set)):
            for value in values:
                _append_symbol_candidate(target, value)
    for section_key in ("data_config", "data", "live", "gateway", "params"):
        section = config.get(section_key)
        if isinstance(section, dict):
            _append_config_symbols(target, section)
    for container_key in ("contract_metadata", "contracts", "contract_specs", "instrument_specs"):
        container = config.get(container_key)
        if not isinstance(container, dict):
            continue
        for key, item in container.items():
            _append_symbol_candidate(target, key)
            if isinstance(item, dict):
                _append_config_symbols(target, item)


def _clear_runtime_logs_before_start(runtime_dir: Path) -> None:
    logs_dir = runtime_dir / "logs"
    if logs_dir.is_symlink() or logs_dir.is_file():
        logs_dir.unlink()
    elif logs_dir.is_dir():
        shutil.rmtree(logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)


def _instance_log_dir(instance: dict[str, Any] | None) -> Path | None:
    if not instance:
        return None

    log_dir_text = str(instance.get("log_dir") or "").strip()
    if log_dir_text:
        log_dir = Path(log_dir_text)
        if log_dir.is_dir():
            return log_dir

    runtime_dir_text = str(instance.get("runtime_dir") or "").strip()
    if runtime_dir_text:
        log_dir = Path(runtime_dir_text) / "logs"
        if log_dir.is_dir():
            return log_dir

    return None


class TradingWorkspaceService:
    """Trading orchestration for workspace strategy units."""

    @staticmethod
    def normalize_trading_mode(value: Any) -> str:
        text = str(value or "").strip().lower()
        return "live" if text == "live" else "paper"

    @staticmethod
    def normalize_gateway_config(config: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(config, dict):
            return {}
        params = config.get("params")
        normalized = {
            "preset_id": str(config.get("preset_id") or "").strip() or None,
            "name": str(config.get("name") or "").strip() or None,
            "params": params if isinstance(params, dict) else {},
        }
        return {key: value for key, value in normalized.items() if value not in (None, "", {})}

    @classmethod
    def default_snapshot(
        cls,
        *,
        unit: StrategyUnit,
        instance_status: str = "idle",
        error: str | None = None,
    ) -> dict[str, Any]:
        return {
            "instance_id": unit.trading_instance_id,
            "instance_status": instance_status,
            "mode": cls.normalize_trading_mode(unit.trading_mode),
            "error": error,
            "started_at": None,
            "stopped_at": None,
            "gateway_summary": cls.gateway_summary(
                unit.gateway_config if isinstance(unit.gateway_config, dict) else {}
            ),
            "long_position": 0.0,
            "short_position": 0.0,
            "today_pnl": None,
            "position_pnl": None,
            "latest_price": None,
            "change_pct": None,
            "long_market_value": 0.0,
            "short_market_value": 0.0,
            "leverage": None,
            "cumulative_pnl": None,
            "max_drawdown_rate": None,
            "trading_day": None,
            "updated_at": _now_local_text(),
            "detail_route": None,
            "position_source": None,
            "asset_spec_source": None,
            "valuation_status": "empty",
            "valuation_warnings": [],
            "positions": [],
            "trades": [],
        }

    @staticmethod
    def gateway_summary(gateway_config: dict[str, Any] | None) -> str | None:
        params = (gateway_config or {}).get("params")
        gateway = params.get("gateway") if isinstance(params, dict) else None
        if not isinstance(gateway, dict):
            return None
        parts = [
            str(gateway.get("exchange_type") or "").strip(),
            str(gateway.get("asset_type") or "").strip(),
            str(gateway.get("account_id") or "").strip(),
        ]
        summary = " / ".join(part for part in parts if part)
        return summary or None

    @staticmethod
    def _map_run_status(instance_status: str, error: str | None = None) -> str:
        text = str(instance_status or "").strip().lower()
        if text == "running":
            return "running"
        if text == "error" or error:
            return "failed"
        return "idle"

    @staticmethod
    def _normalize_trade_direction(value: Any, size: float) -> str:
        text = str(value or "").strip().lower()
        if text in {"buy", "long", "多", "多头"}:
            return "long"
        if text in {"sell", "short", "空", "空头"}:
            return "short"
        return "long" if size >= 0 else "short"

    @classmethod
    def _normalize_trade_rows(
        cls,
        raw_trades: list[Any],
        *,
        unit: StrategyUnit,
    ) -> list[dict[str, Any]]:
        symbol = str(unit.symbol or unit.symbol_name or unit.strategy_name or "")
        trades: list[dict[str, Any]] = []

        for index, payload in enumerate(raw_trades):
            if not isinstance(payload, dict):
                continue

            raw_size = _safe_float(payload.get("size"), 0.0)
            size = abs(raw_size)
            pnl = _safe_float(payload.get("pnl"), 0.0)
            pnlcomm = _safe_float(payload.get("pnlcomm"), pnl)
            price = _safe_float(payload.get("price"), 0.0)
            value = _safe_float(payload.get("value"), 0.0)
            commission = _safe_float(payload.get("commission"), 0.0)
            row_id = str(payload.get("id") or payload.get("ref") or index + 1)

            trades.append(
                {
                    "id": row_id,
                    "datetime": _safe_iso_text(payload.get("datetime")),
                    "dtopen": _safe_iso_text(payload.get("dtopen") or payload.get("open_time")),
                    "dtclose": _safe_iso_text(
                        payload.get("dtclose")
                        or payload.get("close_time")
                        or payload.get("datetime")
                    ),
                    "data_name": str(payload.get("data_name") or payload.get("symbol") or symbol),
                    "direction": cls._normalize_trade_direction(payload.get("direction"), raw_size),
                    "size": _round_quantity(size),
                    "price": round(price, 4) if price else None,
                    "value": round(value, 2) if value else None,
                    "commission": round(commission, 4),
                    "pnl": round(pnl, 2),
                    "pnlcomm": round(pnlcomm, 2),
                    "barlen": (
                        _safe_int(payload.get("barlen"))
                        if payload.get("barlen") is not None
                        else None
                    ),
                }
            )

        return trades[-200:]

    @staticmethod
    def _position_log_row_direction(row: dict[str, Any], size: float) -> str:
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

    @staticmethod
    def _latest_position_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        latest_by_key: dict[str, tuple[int, str, str, dict[str, Any]]] = {}
        latest_flat_by_key: dict[str, tuple[int, str, str, dict[str, Any]]] = {}
        latest_flat_by_symbol: dict[str, tuple[int, str, dict[str, Any]]] = {}
        for index, row in enumerate(rows):
            symbol = str(row.get("data_name") or row.get("symbol") or "").strip()
            if not symbol:
                continue
            size = _safe_float(row.get("size"), 0.0)
            direction = TradingWorkspaceService._position_log_row_direction(row, size)
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
                if current_flat is None or (timestamp, index) >= (
                    current_flat[1],
                    current_flat[0],
                ):
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
            direction = TradingWorkspaceService._position_log_row_direction(
                row, _safe_float(row.get("size"), 0.0)
            )
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
            if latest_nonflat is None or (timestamp, index) >= (
                latest_nonflat[1],
                latest_nonflat[0],
            ):
                selected.append((index, row))
        for key, (index, timestamp, _symbol, row) in latest_flat_by_key.items():
            latest_nonflat = latest_by_key.get(key)
            if latest_nonflat is None or (timestamp, index) >= (
                latest_nonflat[1],
                latest_nonflat[0],
            ):
                selected.append((index, row))
        return [row for _index, row in sorted(selected, key=lambda item: item[0])]

    @staticmethod
    def _position_updated_at(row: dict[str, Any]) -> str | None:
        return _safe_iso_text(
            row.get("updated_at") or row.get("log_time") or row.get("datetime") or row.get("dt")
        )

    @staticmethod
    def _position_data_time(row: dict[str, Any]) -> str | None:
        return _safe_iso_text(row.get("data_time") or row.get("datetime") or row.get("dt"))

    @classmethod
    def _latest_position_updated_at(cls, rows: list[dict[str, Any]]) -> str | None:
        latest: str | None = None
        for row in rows:
            timestamp = cls._position_updated_at(row)
            if timestamp and (latest is None or timestamp > latest):
                latest = timestamp
        return latest

    @classmethod
    def _latest_position_data_time(cls, rows: list[dict[str, Any]]) -> str | None:
        latest: str | None = None
        for row in rows:
            timestamp = cls._position_data_time(row)
            if timestamp and (latest is None or timestamp > latest):
                latest = timestamp
        return latest

    @classmethod
    def _contract_spec(
        cls,
        unit: StrategyUnit,
        symbol: str,
        instance: dict[str, Any] | None = None,
        *extra_configs: dict[str, Any],
    ):
        instance_params = _safe_dict((instance or {}).get("params"))
        return contract_spec_for(
            symbol,
            *extra_configs,
            _safe_dict(getattr(unit, "unit_settings", None)),
            _safe_dict(getattr(unit, "params", None)),
            _safe_dict(getattr(unit, "data_config", None)),
            _safe_dict(getattr(unit, "gateway_config", None)),
            instance_params,
            _safe_dict(instance_params.get("unit_settings")),
            _safe_dict(instance_params.get("data_config")),
            _safe_dict(instance_params.get("gateway")),
            _safe_dict(instance_params.get("simulate")),
            _safe_dict(instance_params.get("backtest")),
            _safe_dict(instance_params.get("live")),
        )

    @staticmethod
    def _position_source_for_row(row: dict[str, Any], fallback: str | None = None) -> str:
        return str(row.get("position_source") or row.get("source") or fallback or "local").strip()

    @staticmethod
    def _asset_spec_source_for_row(row: dict[str, Any], spec: Any) -> str | None:
        return (
            str(row.get("asset_spec_source") or getattr(spec, "source", "") or "").strip() or None
        )

    @staticmethod
    def _asset_spec_config_for_row(row: dict[str, Any]) -> dict[str, Any]:
        config = dict(row)
        config.pop("position_source", None)
        if config.get("asset_spec_source"):
            config["source"] = config.get("asset_spec_source")
        else:
            config.pop("source", None)
        return config

    @staticmethod
    def _has_any(row: dict[str, Any], *keys: str) -> bool:
        return any(row.get(key) not in (None, "") for key in keys)

    @staticmethod
    def _unit_contract_metadata(unit: StrategyUnit) -> dict[str, Any]:
        params = _safe_dict(getattr(unit, "params", None))
        metadata = params.get("contract_metadata")
        return dict(metadata) if isinstance(metadata, dict) else {}

    @classmethod
    def _unit_has_asset_valuation_config(cls, unit: StrategyUnit) -> bool:
        if cls._unit_contract_metadata(unit):
            return True
        for config in (
            _safe_dict(getattr(unit, "unit_settings", None)),
            _safe_dict(getattr(unit, "params", None)),
            _safe_dict(getattr(unit, "data_config", None)),
            _safe_dict(getattr(unit, "gateway_config", None)),
        ):
            if cls._has_any(
                config,
                "multiplier",
                "mult",
                "contract_multiplier",
                "contract_size",
                "trade_contract_size",
                "margin",
                "margin_rate",
                "margin_ratio",
                "leverage",
                "lever",
                "commission",
                "commission_rate",
                "open_commission_rate",
                "close_commission_rate",
                "taker_commission_rate",
                "maker_commission_rate",
                "commission_amount",
            ):
                return True
        return False

    @classmethod
    def _sync_unit_contract_metadata_from_instance(
        cls,
        unit: StrategyUnit,
        instance: dict[str, Any] | None,
    ) -> bool:
        instance_params = _safe_dict((instance or {}).get("params"))
        instance_metadata = instance_params.get("contract_metadata")
        if not isinstance(instance_metadata, dict) or not instance_metadata:
            return False

        params = _safe_dict(getattr(unit, "params", None))
        current_metadata = (
            dict(params.get("contract_metadata"))
            if isinstance(params.get("contract_metadata"), dict)
            else {}
        )
        changed = False
        for key, value in instance_metadata.items():
            if not isinstance(value, dict):
                continue
            normalized_key = str(key)
            normalized_value = dict(value)
            if current_metadata.get(normalized_key) != normalized_value:
                current_metadata[normalized_key] = normalized_value
                changed = True
        if not changed:
            return False
        params["contract_metadata"] = current_metadata
        unit.params = params
        return True

    @classmethod
    def _sync_unit_contract_metadata_from_specs(
        cls,
        unit: StrategyUnit,
        asset_specs: dict[str, dict[str, Any]],
    ) -> bool:
        if not asset_specs:
            return False

        params = _safe_dict(getattr(unit, "params", None))
        current_metadata = (
            dict(params.get("contract_metadata"))
            if isinstance(params.get("contract_metadata"), dict)
            else {}
        )
        changed = False
        for key, value in asset_specs.items():
            if not isinstance(value, dict):
                continue
            normalized_key = str(key)
            normalized_value = dict(value)
            if current_metadata.get(normalized_key) != normalized_value:
                current_metadata[normalized_key] = normalized_value
                changed = True
        if not changed:
            return False
        params["contract_metadata"] = current_metadata
        unit.params = params
        return True

    @classmethod
    def _unit_asset_spec_symbols(
        cls,
        unit: StrategyUnit,
        instance: dict[str, Any] | None,
    ) -> list[str]:
        candidates: list[str] = []
        _append_symbol_candidate(candidates, getattr(unit, "symbol", None))
        for config in (
            _safe_dict(getattr(unit, "params", None)),
            _safe_dict(getattr(unit, "data_config", None)),
            _safe_dict(getattr(unit, "unit_settings", None)),
            _safe_dict(getattr(unit, "gateway_config", None)),
            _safe_dict((instance or {}).get("params")),
        ):
            _append_config_symbols(candidates, config)

        symbols: list[str] = []
        seen: set[str] = set()
        for symbol in candidates:
            text = str(symbol or "").strip()
            key = text.upper()
            if not text or key in seen:
                continue
            symbols.append(text)
            seen.add(key)
        return symbols

    @classmethod
    def _refresh_unit_asset_specs_from_manager(
        cls,
        manager: Any,
        unit: StrategyUnit,
        instance: dict[str, Any] | None,
    ) -> bool:
        instance_id = str((instance or {}).get("id") or unit.trading_instance_id or "").strip()
        if not instance_id:
            return False
        query_specs = getattr(manager, "query_instance_asset_specs", None)
        if not callable(query_specs):
            return False
        symbols = cls._unit_asset_spec_symbols(unit, instance)
        if not symbols:
            return False
        try:
            raw_specs = query_specs(instance_id, symbols)
        except Exception:
            return False
        if not isinstance(raw_specs, dict):
            return False
        asset_specs = {
            str(key): dict(value)
            for key, value in raw_specs.items()
            if isinstance(value, dict) and value
        }
        if not asset_specs:
            return False
        return cls._sync_unit_contract_metadata_from_specs(unit, asset_specs)

    @classmethod
    def _position_row_should_recalculate_local_pnl(
        cls,
        row: dict[str, Any],
        spec: Any,
        *,
        position_source: str,
    ) -> bool:
        if str(position_source or "").strip().lower() == "gateway":
            return False
        if cls._has_any(row, *_EXPLICIT_NET_PNL_FIELD_KEYS):
            return False
        if not (
            getattr(spec, "has_multiplier", False)
            or getattr(spec, "has_commission", False)
            or getattr(spec, "has_margin_rate", False)
            or getattr(spec, "has_margin_amount", False)
        ):
            return False
        if not cls._has_any(
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
        if not cls._has_any(
            row,
            *_CURRENT_PRICE_FIELD_KEYS,
            "market_value",
            "marketValue",
            "positionValue",
            "position_value",
            "value",
        ):
            return False
        return cls._has_any(row, *_GROSS_PNL_FIELD_KEYS, "pnl")

    @classmethod
    def _position_row_for_valuation(
        cls,
        row: dict[str, Any],
        spec: Any,
        *,
        position_source: str,
    ) -> dict[str, Any]:
        item = dict(row)
        if not cls._position_row_should_recalculate_local_pnl(
            item,
            spec,
            position_source=position_source,
        ):
            return item
        for key in (*_GROSS_PNL_FIELD_KEYS, "pnl"):
            item.pop(key, None)
        item["recalculated_position_pnl"] = True
        return item

    @classmethod
    def _position_valuation_warnings(
        cls,
        unit: StrategyUnit,
        row: dict[str, Any],
        spec: Any,
        *,
        position_source: str,
    ) -> list[str]:
        warnings: list[str] = []
        trading_mode = cls.normalize_trading_mode(getattr(unit, "trading_mode", None))
        if trading_mode == "live" and position_source != "gateway":
            warnings.append("未能从交易所网关确认当前持仓，当前数据来自本地日志/快照")

        if not getattr(spec, "has_multiplier", False) and not cls._has_any(
            row, "multiplier", "mult", "contract_multiplier", "contract_size"
        ):
            warnings.append("合约乘数未从交易所或本地资产信息确认，按 1 估算")
        if (
            not getattr(spec, "has_margin_rate", False)
            and not getattr(spec, "has_margin_amount", False)
            and not cls._has_any(
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
        has_real_commission = cls._has_any(row, *_COMMISSION_FIELD_KEYS)
        if row.get("commission_currency_mismatch"):
            warnings.append("成交手续费币种与盈亏计价币种不一致，当前按资产费率估算手续费")
        if not getattr(spec, "has_commission", False) and not has_real_commission:
            warnings.append("手续费未确认，持仓盈亏未扣除真实手续费")
        elif (
            getattr(spec, "has_commission", False)
            and not has_real_commission
            and (row.get("generic_pnl_recalculated") or cls._has_any(row, *_GROSS_PNL_FIELD_KEYS))
        ):
            warnings.append("持仓手续费未从交易所成交/持仓回报确认，当前按资产费率估算")
        return warnings

    @classmethod
    def _unit_position_symbol_aliases(
        cls,
        unit: StrategyUnit,
        instance: dict[str, Any] | None,
    ) -> set[str]:
        candidates: list[str] = []
        _append_symbol_candidate(candidates, getattr(unit, "symbol", None))
        _append_config_symbols(candidates, _safe_dict(getattr(unit, "params", None)))
        _append_config_symbols(candidates, _safe_dict(getattr(unit, "data_config", None)))
        _append_config_symbols(candidates, _safe_dict(getattr(unit, "unit_settings", None)))
        _append_config_symbols(candidates, _safe_dict((instance or {}).get("params")))
        if not candidates:
            _append_symbol_candidate(candidates, getattr(unit, "symbol_name", None))

        aliases: set[str] = set()
        for symbol in candidates:
            aliases.update(symbol_aliases(symbol))
        return aliases

    @staticmethod
    def _position_symbol_matches(symbol: str, allowed_aliases: set[str]) -> bool:
        if not allowed_aliases:
            return True
        return any(alias in allowed_aliases for alias in symbol_aliases(symbol))

    @classmethod
    def _gateway_position_rows(
        cls,
        unit: StrategyUnit,
        instance: dict[str, Any] | None,
    ) -> list[dict[str, Any]] | None:
        instance_id = str((instance or {}).get("id") or unit.trading_instance_id or "").strip()
        if not instance_id:
            return None

        try:
            manager = get_live_trading_manager()
        except Exception:
            return None

        has_gateway = getattr(manager, "has_instance_gateway", None)
        if callable(has_gateway):
            try:
                if not has_gateway(instance_id):
                    return None
            except Exception:
                return None

        query_positions = getattr(manager, "query_instance_gateway_positions", None)
        if not callable(query_positions):
            return None
        try:
            raw_positions = query_positions(instance_id)
        except Exception:
            return None
        if not isinstance(raw_positions, list):
            return None

        fallback_symbol = str(unit.symbol or unit.symbol_name or unit.strategy_name or "")
        allowed_aliases = cls._unit_position_symbol_aliases(unit, instance)
        matched_positions: list[dict[str, Any]] = []
        symbols: list[str] = []
        seen: set[str] = set()
        for item in raw_positions:
            if not isinstance(item, dict):
                continue
            row_symbol = gateway_position_symbol(item)
            if allowed_aliases and not cls._position_symbol_matches(row_symbol, allowed_aliases):
                continue
            matched_positions.append(item)
            symbol = row_symbol or fallback_symbol
            if symbol and symbol not in seen:
                symbols.append(symbol)
                seen.add(symbol)
        if fallback_symbol and fallback_symbol not in seen:
            symbols.append(fallback_symbol)

        asset_specs: dict[str, dict[str, Any]] = {}
        query_specs = getattr(manager, "query_instance_asset_specs", None)
        if callable(query_specs) and symbols:
            try:
                raw_specs = query_specs(instance_id, symbols)
            except Exception:
                raw_specs = {}
            if isinstance(raw_specs, dict):
                asset_specs = {
                    str(key): dict(value)
                    for key, value in raw_specs.items()
                    if isinstance(value, dict)
                }
        asset_specs = _merge_unit_contract_metadata(asset_specs, unit, instance, symbols)
        asset_specs = _complete_asset_specs_from_local(asset_specs, symbols)
        if asset_specs:
            cls._sync_unit_contract_metadata_from_specs(unit, asset_specs)

        recent_trades: list[dict[str, Any]] = []
        query_trades = getattr(manager, "query_instance_gateway_trades", None)
        if callable(query_trades) and symbols:
            for symbol in symbols:
                try:
                    raw_trades = query_trades(instance_id, symbol=symbol, limit=500)
                except TypeError:
                    raw_trades = query_trades(instance_id)
                except Exception:
                    raw_trades = []
                if isinstance(raw_trades, list):
                    recent_trades.extend(
                        dict(item) for item in raw_trades if isinstance(item, dict)
                    )

        rows: list[dict[str, Any]] = []
        for item in matched_positions:
            for side_item in split_bidirectional_position_row(item):
                symbol = gateway_position_symbol(side_item, fallback_symbol)
                rows.append(
                    normalize_gateway_position(
                        side_item,
                        fallback_symbol=fallback_symbol,
                        asset_spec=_asset_spec_for_symbol(asset_specs, symbol),
                        recent_trades=recent_trades,
                    )
                )
        return rows

    @classmethod
    def _apply_position_rows_to_snapshot(
        cls,
        snapshot: dict[str, Any],
        unit: StrategyUnit,
        instance: dict[str, Any] | None,
        positions: list[dict[str, Any]],
    ) -> float | None:
        long_position = 0.0
        short_position = 0.0
        long_market_value = 0.0
        short_market_value = 0.0
        position_pnl = 0.0
        detail_positions: list[dict[str, Any]] = []
        latest_price: float | None = None
        latest_position_updated_at: str | None = None
        position_sources: list[str] = []
        asset_spec_sources: list[str] = []
        valuation_warnings = list(snapshot.get("valuation_warnings") or [])
        fallback_position_source = str(snapshot.get("position_source") or "").strip() or None

        fallback_symbol = str(unit.symbol or unit.symbol_name or unit.strategy_name or "")

        for raw_item in positions:
            for item in split_bidirectional_position_row(_safe_dict(raw_item)):
                data_name = gateway_position_symbol(item, fallback_symbol)
                spec = cls._contract_spec(
                    unit,
                    data_name,
                    instance,
                    cls._asset_spec_config_for_row(_safe_dict(item)),
                )
                position_source = cls._position_source_for_row(item, fallback_position_source)
                valuation_item = cls._position_row_for_valuation(
                    _safe_dict(item),
                    spec,
                    position_source=position_source,
                )
                valued = value_position(valuation_item, spec=spec)
                if valued is None:
                    continue
                asset_spec_source = cls._asset_spec_source_for_row(item, spec)
                row_warnings = cls._position_valuation_warnings(
                    unit,
                    valuation_item,
                    spec,
                    position_source=position_source,
                )
                if valuation_item.get("recalculated_position_pnl"):
                    row_warnings.append(
                        "本地/快照持仓盈亏已按最新资产乘数、保证金和手续费设置重新计算"
                    )
                _append_unique(valuation_warnings, row_warnings)
                position_sources.append(position_source)
                if asset_spec_source:
                    asset_spec_sources.append(asset_spec_source)

                if valued.size > 0:
                    long_position += abs(valued.size)
                    long_market_value += valued.market_value
                else:
                    short_position += abs(valued.size)
                    short_market_value += valued.market_value

                position_pnl += valued.pnl
                latest_price = valued.current_price
                position_updated_at = cls._position_updated_at(item)
                position_data_time = cls._position_data_time(item)
                if position_updated_at and (
                    latest_position_updated_at is None
                    or position_updated_at > latest_position_updated_at
                ):
                    latest_position_updated_at = position_updated_at
                detail_positions.append(
                    {
                        "data_name": valued.data_name or data_name,
                        "direction": valued.direction,
                        "size": _round_quantity(abs(valued.size)),
                        "price": round(valued.entry_price, 4) if valued.entry_price else None,
                        "current_price": round(valued.current_price, 4)
                        if valued.current_price
                        else None,
                        "market_value": round(valued.market_value, 2),
                        "margin_value": round(valued.margin_value, 2),
                        "multiplier": round(valued.multiplier, 8),
                        "margin_rate": round(valued.margin_rate, 8),
                        "leverage": _leverage_from_margin_rate(valued.margin_rate),
                        "commission": round(valued.commission, 4),
                        "commission_source": valuation_item.get("commission_source")
                        or item.get("commission_source"),
                        "commission_signed": True,
                        "gross_pnl": round(valued.gross_pnl, 2),
                        "pnl": round(valued.pnl, 2),
                        "pnlcomm": round(valued.pnl, 2),
                        "position_pnl": round(valued.pnl, 2),
                        "updated_at": position_updated_at,
                        "data_time": position_data_time,
                        "source": position_source,
                        "position_source": position_source,
                        "asset_spec_source": asset_spec_source,
                        "valuation_status": "estimated" if row_warnings else "confirmed",
                        "valuation_warnings": row_warnings,
                    }
                )
        snapshot["positions"] = detail_positions
        if not position_sources and fallback_position_source:
            position_sources.append(fallback_position_source)
        snapshot["position_source"] = _unique_text(position_sources)
        snapshot["asset_spec_source"] = _unique_text(asset_spec_sources)
        snapshot["valuation_warnings"] = valuation_warnings
        if valuation_warnings:
            snapshot["valuation_status"] = "estimated"
        elif snapshot.get("position_source") == "gateway":
            snapshot["valuation_status"] = "confirmed"
        else:
            snapshot["valuation_status"] = "empty" if not detail_positions else "estimated"
        if latest_position_updated_at:
            snapshot["updated_at"] = latest_position_updated_at
        snapshot["long_position"] = _round_quantity(long_position)
        snapshot["short_position"] = _round_quantity(short_position)
        snapshot["long_market_value"] = round(long_market_value, 2)
        snapshot["short_market_value"] = round(short_market_value, 2)
        snapshot["position_pnl"] = round(position_pnl, 2)
        return latest_price

    @classmethod
    def _build_instance_params(cls, unit: StrategyUnit) -> dict[str, Any]:
        params = dict(unit.params or {})
        params.setdefault("symbol", unit.symbol or "")
        params.setdefault("symbol_name", unit.symbol_name or "")
        params.setdefault("timeframe", unit.timeframe or "1d")
        params.setdefault("timeframe_n", unit.timeframe_n or 1)
        params.setdefault("category", unit.category or "")
        params.setdefault("data_config", dict(unit.data_config or {}))
        params.setdefault("unit_settings", dict(unit.unit_settings or {}))
        params["workspace_unit"] = {
            "workspace_id": unit.workspace_id,
            "unit_id": unit.id,
            "group_name": unit.group_name or "",
            "strategy_name": unit.strategy_name or "",
        }

        trading_mode = cls.normalize_trading_mode(unit.trading_mode)
        gateway_config = cls.normalize_gateway_config(
            unit.gateway_config if isinstance(unit.gateway_config, dict) else {}
        )

        if trading_mode == "live":
            gateway_params = gateway_config.get("params")
            if not isinstance(gateway_params, dict) or not isinstance(
                gateway_params.get("gateway"), dict
            ):
                raise ValueError("实盘单元缺少网关配置")
            params.update(gateway_params)
        else:
            gateway_params = gateway_config.get("params")
            if isinstance(gateway_params, dict) and isinstance(gateway_params.get("gateway"), dict):
                params.update(gateway_params)
            else:
                params["gateway"] = {"enabled": False}

        params["trading_mode"] = trading_mode
        return params

    @classmethod
    def _build_snapshot(
        cls,
        unit: StrategyUnit,
        instance: dict[str, Any] | None,
        *,
        full_log: bool = True,
    ) -> tuple[dict[str, Any], dict[str, Any], int | None, float | None]:
        instance_status = str((instance or {}).get("status") or "stopped").strip().lower()
        error = str((instance or {}).get("error") or "").strip() or None
        snapshot = cls.default_snapshot(
            unit=unit,
            instance_status="error" if error else (instance_status or "idle"),
            error=error,
        )
        if not full_log:
            current_snapshot = _safe_dict(getattr(unit, "trading_snapshot", None))
            for key in _LIGHT_HYDRATE_PRESERVE_KEYS:
                if key in current_snapshot:
                    snapshot[key] = current_snapshot[key]
        snapshot["instance_id"] = (instance or {}).get("id") or unit.trading_instance_id
        snapshot["started_at"] = _safe_iso_text((instance or {}).get("started_at"))
        snapshot["stopped_at"] = _safe_iso_text((instance or {}).get("stopped_at"))

        metrics_snapshot: dict[str, Any] = {}
        bar_count: int | None = None
        elapsed_seconds: float | None = None
        latest_price: float | None = None

        log_result: dict[str, Any] | None = None
        position_rows: list[dict[str, Any]] = []
        position_rows_source = "none"
        log_dir = _instance_log_dir(instance)
        if log_dir and log_dir.is_dir():
            log_result = parse_log_dir(log_dir) if full_log else None
            position_rows = cls._latest_position_rows(parse_position_log(log_dir))
            if position_rows:
                position_rows_source = "log"
            if not position_rows:
                position_rows = parse_current_position(log_dir)
                if position_rows:
                    position_rows_source = "snapshot"

        gateway_position_rows = cls._gateway_position_rows(unit, instance)
        if gateway_position_rows is not None:
            position_rows = gateway_position_rows
            position_rows_source = "gateway"
        elif (
            cls.normalize_trading_mode(getattr(unit, "trading_mode", None)) == "live"
            and instance_status == "running"
        ):
            snapshot["valuation_status"] = "stale_fallback"
            _append_unique(
                snapshot["valuation_warnings"],
                "运行中的实盘单元未能从交易所网关确认当前持仓，当前盈亏可能来自过期日志/快照",
            )

        if position_rows or gateway_position_rows is not None:
            snapshot["position_source"] = position_rows_source
            latest_price = cls._apply_position_rows_to_snapshot(
                snapshot,
                unit,
                instance,
                position_rows,
            )

        if log_result:
            snapshot["trades"] = cls._normalize_trade_rows(
                list(log_result.get("trades") or []),
                unit=unit,
            )

            kline = log_result.get("kline") or {}
            dates = list(kline.get("dates") or [])
            ohlc = list(kline.get("ohlc") or [])
            if dates:
                snapshot["trading_day"] = str(dates[-1])[:10]
                bar_count = len(dates)
            if len(ohlc) >= 1:
                last_close = _safe_float((ohlc[-1] or [None, None])[1], default=0.0)
                if last_close > 0:
                    snapshot["latest_price"] = round(last_close, 4)
                if len(ohlc) >= 2:
                    prev_close = _safe_float((ohlc[-2] or [None, None])[1], default=0.0)
                    if prev_close > 0 and last_close > 0:
                        snapshot["change_pct"] = round(
                            (last_close - prev_close) / prev_close * 100, 2
                        )

            equity_curve = list(log_result.get("equity_curve") or [])
            initial_cash = _safe_float(log_result.get("initial_cash"), 0.0)
            final_value = _safe_float(log_result.get("final_value"), 0.0)
            if len(equity_curve) >= 2:
                snapshot["today_pnl"] = round(equity_curve[-1] - equity_curve[-2], 2)
            snapshot["cumulative_pnl"] = round(final_value - initial_cash, 2)
            snapshot["max_drawdown_rate"] = round(_safe_float(log_result.get("max_drawdown")), 2)
            total_market_value = _safe_float(snapshot.get("long_market_value")) + _safe_float(
                snapshot.get("short_market_value")
            )
            if final_value > 0 and total_market_value > 0:
                snapshot["leverage"] = round(total_market_value / final_value, 4)
            if snapshot.get("latest_price") is None and latest_price is not None:
                snapshot["latest_price"] = round(latest_price, 4)

            metrics_snapshot = {
                "total_return": log_result.get("total_return"),
                "annual_return": log_result.get("annual_return"),
                "sharpe_ratio": log_result.get("sharpe_ratio"),
                "max_drawdown": log_result.get("max_drawdown"),
                "win_rate": log_result.get("win_rate"),
                "total_trades": log_result.get("total_trades"),
                "profitable_trades": log_result.get("profitable_trades"),
                "losing_trades": log_result.get("losing_trades"),
                "initial_cash": initial_cash,
                "final_value": final_value,
                "net_value": round(final_value / initial_cash, 6) if initial_cash > 0 else None,
                "net_profit": round(final_value - initial_cash, 2),
                "max_leverage": snapshot.get("leverage"),
                "trading_days": len(equity_curve),
            }

        if snapshot.get("latest_price") is None and latest_price is not None:
            snapshot["latest_price"] = round(latest_price, 4)

        started_at = snapshot.get("started_at")
        if started_at and snapshot.get("instance_status") == "running":
            try:
                started_dt = datetime.strptime(started_at, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                elapsed_seconds = None
            else:
                elapsed_seconds = round((datetime.now() - started_dt).total_seconds(), 2)

        return snapshot, metrics_snapshot, bar_count, elapsed_seconds

    async def hydrate_units(
        self,
        units: list[StrategyUnit],
        user_id: str,
        *,
        full_log: bool = True,
    ) -> bool:
        manager = get_live_trading_manager()
        changed = False

        for unit in units:
            instance = None
            if unit.trading_instance_id:
                instance = manager.get_instance(unit.trading_instance_id, user_id=user_id)

            params_before = _safe_dict(getattr(unit, "params", None))
            snapshot, metrics_snapshot, bar_count, elapsed_seconds = self._build_snapshot(
                unit,
                instance,
                full_log=full_log,
            )
            next_run_status = self._map_run_status(
                snapshot.get("instance_status", "idle"), snapshot.get("error")
            )

            if unit.run_status != next_run_status:
                unit.run_status = next_run_status
                changed = True
            if unit.trading_snapshot != snapshot:
                unit.trading_snapshot = snapshot
                changed = True
            if unit.metrics_snapshot != metrics_snapshot and metrics_snapshot:
                unit.metrics_snapshot = metrics_snapshot
                changed = True
            if bar_count is not None and unit.bar_count != bar_count:
                unit.bar_count = bar_count
                changed = True
            if elapsed_seconds is not None and unit.last_run_time != elapsed_seconds:
                unit.last_run_time = elapsed_seconds
                changed = True
            if _safe_dict(getattr(unit, "params", None)) != params_before:
                changed = True

        return changed

    async def start_units(
        self,
        units: list[StrategyUnit],
        user_id: str,
        workspace_settings: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        manager = get_live_trading_manager()
        results: list[dict[str, Any]] = []
        normalized_workspace_settings = dict(workspace_settings or {})

        for unit in units:
            try:
                if unit.lock_running:
                    raise ValueError("该策略单元已锁定运行")
                if unit.lock_trading:
                    raise ValueError("该策略单元已锁定交易")
                if not str(unit.strategy_id or "").strip():
                    raise ValueError("策略单元缺少策略模板")

                instance = None
                runtime_dir = workspace_unit_runtime.sync_trading_unit_runtime(
                    unit,
                    normalized_workspace_settings,
                )
                if unit.trading_instance_id:
                    instance = manager.get_instance(unit.trading_instance_id, user_id=user_id)
                    if instance is not None:
                        existing_runtime_dir = str(instance.get("runtime_dir") or "").strip()
                        if existing_runtime_dir != str(runtime_dir):
                            manager.remove_instance(unit.trading_instance_id, user_id=user_id)
                            unit.trading_instance_id = None
                            instance = None
                if instance is None:
                    created = manager.add_instance(
                        str(unit.strategy_id),
                        self._build_instance_params(unit),
                        user_id=user_id,
                        runtime_dir=str(runtime_dir),
                    )
                    unit.trading_instance_id = str(created.get("id") or "")
                    instance = manager.get_instance(unit.trading_instance_id, user_id=user_id)

                already_running = False
                if instance is not None and str(instance.get("status") or "").lower() == "running":
                    started = instance
                    already_running = True
                else:
                    _clear_runtime_logs_before_start(runtime_dir)
                    try:
                        started = await manager.start_instance(str(unit.trading_instance_id))
                    except ValueError as exc:
                        if str(exc) != "Strategy is already running":
                            raise
                        refreshed = manager.get_instance(
                            str(unit.trading_instance_id), user_id=user_id
                        )
                        if not refreshed or str(refreshed.get("status") or "").lower() != "running":
                            raise
                        started = refreshed
                        already_running = True

                self._sync_unit_contract_metadata_from_instance(unit, started)
                self._refresh_unit_asset_specs_from_manager(manager, unit, started)
                unit.run_status = "running"
                if not already_running:
                    unit.run_count = int(unit.run_count or 0) + 1
                snapshot, metrics_snapshot, bar_count, elapsed_seconds = self._build_snapshot(
                    unit, started
                )
                unit.trading_snapshot = snapshot
                if metrics_snapshot:
                    unit.metrics_snapshot = metrics_snapshot
                if bar_count is not None:
                    unit.bar_count = bar_count
                if elapsed_seconds is not None:
                    unit.last_run_time = elapsed_seconds
                results.append(
                    {
                        "unit_id": unit.id,
                        "task_id": unit.trading_instance_id,
                        "status": "running",
                        "already_running": already_running,
                    }
                )
            except Exception as exc:
                unit.run_status = "failed"
                unit.trading_snapshot = self.default_snapshot(
                    unit=unit,
                    instance_status="error",
                    error=str(exc),
                )
                results.append(
                    {
                        "unit_id": unit.id,
                        "task_id": None,
                        "status": "failed",
                        "error": str(exc),
                    }
                )

        return results

    async def stop_units(self, units: list[StrategyUnit], user_id: str) -> list[dict[str, Any]]:
        manager = get_live_trading_manager()
        results: list[dict[str, Any]] = []

        for unit in units:
            cancelled = False
            stopped_instance = None
            open_order_cancel: dict[str, Any] | None = None
            error_message: str | None = None
            try:
                if unit.lock_running:
                    raise ValueError("该策略单元已锁定运行")
                if unit.lock_trading:
                    raise ValueError("该策略单元已锁定交易")
                if unit.trading_instance_id:
                    stop_result = await manager.stop_instance(str(unit.trading_instance_id))
                    if isinstance(stop_result, dict):
                        value = stop_result.get("open_order_cancel")
                        open_order_cancel = value if isinstance(value, dict) else None
                    stopped_instance = manager.get_instance(
                        str(unit.trading_instance_id), user_id=user_id
                    )
                    cancelled = True
                unit.run_status = "idle"
                if stopped_instance:
                    snapshot, metrics_snapshot, bar_count, elapsed_seconds = self._build_snapshot(
                        unit, stopped_instance
                    )
                    if metrics_snapshot:
                        unit.metrics_snapshot = metrics_snapshot
                    if bar_count is not None:
                        unit.bar_count = bar_count
                    if elapsed_seconds is not None:
                        unit.last_run_time = elapsed_seconds
                else:
                    snapshot = self.default_snapshot(unit=unit, instance_status="stopped")
                    snapshot["stopped_at"] = _now_local_text()
                if open_order_cancel is not None:
                    snapshot["open_order_cancel"] = open_order_cancel
                unit.trading_snapshot = snapshot
            except Exception as exc:
                metadata = getattr(exc, "open_order_cancel", None)
                if isinstance(metadata, dict):
                    open_order_cancel = metadata
                error_message = str(exc)
                unit.run_status = "failed"
                snapshot = self.default_snapshot(
                    unit=unit,
                    instance_status="error",
                    error=str(exc),
                )
                if open_order_cancel is not None:
                    snapshot["open_order_cancel"] = open_order_cancel
                unit.trading_snapshot = snapshot
            result: dict[str, Any] = {"unit_id": unit.id, "cancelled": cancelled}
            if error_message:
                result["error"] = error_message
            if open_order_cancel is not None:
                result["open_order_cancel"] = open_order_cancel
            results.append(result)

        return results

    def get_auto_trading_config(self) -> dict[str, Any]:
        return dict(get_auto_trading_scheduler().get_config())

    def update_auto_trading_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        scheduler = get_auto_trading_scheduler()
        return dict(
            scheduler.update_config(
                enabled=payload.get("enabled"),
                buffer_minutes=payload.get("buffer_minutes"),
                sessions=payload.get("sessions"),
                scope=payload.get("scope"),
            )
        )

    def get_auto_trading_schedule(self) -> list[dict[str, Any]]:
        scheduler = get_auto_trading_scheduler()
        return [dict(item) for item in scheduler.get_schedule()]

    @staticmethod
    def _instance_log_result(
        unit: StrategyUnit,
        user_id: str,
    ) -> dict[str, Any] | None:
        if not unit.trading_instance_id:
            return None
        manager = get_live_trading_manager()
        instance = manager.get_instance(unit.trading_instance_id, user_id=user_id)
        if not instance:
            return None
        log_dir = _instance_log_dir(instance)
        if not log_dir:
            return None
        return parse_log_dir(log_dir)

    @staticmethod
    def _weighted_avg_price(positions: list[dict[str, Any]]) -> float | None:
        total_size = 0.0
        total_cost = 0.0
        for item in positions:
            size = abs(_safe_float(item.get("size")))
            price = _safe_float(item.get("price"))
            if size <= 0 or price <= 0:
                continue
            total_size += size
            total_cost += size * price
        if total_size <= 0:
            return None
        return round(total_cost / total_size, 4)

    @staticmethod
    def _position_row_direction(row: dict[str, Any]) -> str:
        direction = str(row.get("direction") or row.get("side") or "").strip().lower()
        if direction in {"short", "sell", "sold"}:
            return "short"
        raw_size = _safe_float(row.get("size"))
        return "short" if raw_size < 0 else "long"

    @staticmethod
    def _first_row_number(row: dict[str, Any], *keys: str) -> float | None:
        for key in keys:
            value = row.get(key)
            if value in (None, ""):
                continue
            return _safe_float(value)
        return None

    @classmethod
    def _position_row_open_size(cls, row: dict[str, Any]) -> float:
        size = abs(_safe_float(row.get("size")))
        if size > EPSILON:
            return size
        long_position = cls._first_row_number(row, *LONG_POSITION_FIELD_KEYS)
        short_position = cls._first_row_number(row, *SHORT_POSITION_FIELD_KEYS)
        return max(long_position or 0.0, 0.0) + max(short_position or 0.0, 0.0)

    @classmethod
    def _position_row_needs_response_valuation(cls, row: dict[str, Any]) -> bool:
        if abs(_safe_float(row.get("size"))) <= EPSILON and cls._has_any(
            row, *_POSITION_SIZE_ALIAS_KEYS
        ):
            return True
        if (
            abs(_safe_float(row.get("size"))) > EPSILON
            and not cls._has_any(row, *_EXPLICIT_NET_PNL_FIELD_KEYS)
            and cls._has_any(row, *_GROSS_PNL_FIELD_KEYS)
            and cls._has_any(row, *_COMMISSION_FIELD_KEYS)
        ):
            return True
        return cls._has_any(row, *_POSITION_RESPONSE_REVALUE_KEYS)

    @classmethod
    def _position_row_needs_asset_spec_revaluation(
        cls,
        unit: StrategyUnit,
        row: dict[str, Any],
    ) -> bool:
        if abs(_safe_float(row.get("size"))) <= EPSILON and not cls._has_any(
            row, *_POSITION_SIZE_ALIAS_KEYS
        ):
            return False
        if not cls._unit_has_asset_valuation_config(unit):
            return False
        if cls._has_any(row, *_EXPLICIT_NET_PNL_FIELD_KEYS):
            return False
        if cls._has_any(row, *_GROSS_PNL_FIELD_KEYS, "pnl") and cls._has_any(
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
            return True
        return not cls._has_any(row, "multiplier", "margin_rate", "margin_value")

    @classmethod
    def _position_rows_for_response_valuation(
        cls,
        rows: list[dict[str, Any]],
        snapshot: dict[str, Any],
    ) -> list[dict[str, Any]]:
        latest_price = snapshot.get("latest_price")
        updated_at = snapshot.get("updated_at")
        valued_rows: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            if (
                latest_price not in (None, "")
                and cls._first_row_number(item, *_CURRENT_PRICE_FIELD_KEYS) is None
            ):
                item["latest_price"] = latest_price
            if updated_at not in (None, "") and not cls._position_updated_at(item):
                item["updated_at"] = updated_at
            valued_rows.append(item)
        return valued_rows

    async def build_positions_response(
        self,
        units: list[StrategyUnit],
        user_id: str,
        *,
        hydrate: bool = True,
    ) -> PositionManagerResponse:
        if hydrate:
            await self.hydrate_units(units, user_id)

        positions: list[dict[str, Any]] = []
        total_long_value = 0.0
        total_short_value = 0.0
        total_pnl = 0.0

        for unit in units:
            snapshot = _safe_dict(unit.trading_snapshot)
            position_rows = list(snapshot.get("positions") or [])
            raw_position_rows = [row for row in position_rows if isinstance(row, dict)]
            if raw_position_rows and any(
                self._position_row_needs_response_valuation(row)
                or self._position_row_needs_asset_spec_revaluation(unit, row)
                for row in raw_position_rows
            ):
                latest_price = self._apply_position_rows_to_snapshot(
                    snapshot,
                    unit,
                    None,
                    self._position_rows_for_response_valuation(raw_position_rows, snapshot),
                )
                if latest_price is not None:
                    snapshot["latest_price"] = round(latest_price, 4)
                position_rows = list(snapshot.get("positions") or [])
            active_position_rows = [
                row
                for row in position_rows
                if isinstance(row, dict) and self._position_row_open_size(row) > EPSILON
            ]
            if position_rows and not active_position_rows:
                continue
            long_position = _safe_float(snapshot.get("long_position"))
            short_position = _safe_float(snapshot.get("short_position"))
            long_market_value = _safe_float(snapshot.get("long_market_value"))
            short_market_value = _safe_float(snapshot.get("short_market_value"))
            position_pnl = _safe_float(snapshot.get("position_pnl"))
            if active_position_rows:
                derived_long_position = 0.0
                derived_short_position = 0.0
                derived_long_market_value = 0.0
                derived_short_market_value = 0.0
                has_row_market_value = False
                row_pnl_values: list[float] = []
                for row in active_position_rows:
                    size = abs(_safe_float(row.get("size")))
                    long_size = self._first_row_number(row, *LONG_POSITION_FIELD_KEYS)
                    short_size = self._first_row_number(row, *SHORT_POSITION_FIELD_KEYS)
                    if size <= EPSILON and (
                        (long_size or 0.0) > EPSILON or (short_size or 0.0) > EPSILON
                    ):
                        row_long = max(long_size or 0.0, 0.0)
                        row_short = max(short_size or 0.0, 0.0)
                        derived_long_position += row_long
                        derived_short_position += row_short
                        row_market_value = self._first_row_number(row, "market_value")
                        if row_market_value is not None:
                            has_row_market_value = True
                            row_total = row_long + row_short
                            if row_total > EPSILON:
                                derived_long_market_value += abs(row_market_value) * (
                                    row_long / row_total
                                )
                                derived_short_market_value += abs(row_market_value) * (
                                    row_short / row_total
                                )
                        row_pnl = self._first_row_number(row, *_PNL_FIELD_KEYS)
                        if row_pnl is not None:
                            row_pnl_values.append(row_pnl)
                        continue
                    is_short = self._position_row_direction(row) == "short"
                    if is_short:
                        derived_short_position += size
                    else:
                        derived_long_position += size
                    row_market_value = self._first_row_number(row, "market_value")
                    if row_market_value is not None:
                        has_row_market_value = True
                        if is_short:
                            derived_short_market_value += abs(row_market_value)
                        else:
                            derived_long_market_value += abs(row_market_value)
                    row_pnl = self._first_row_number(row, *_PNL_FIELD_KEYS)
                    if row_pnl is not None:
                        row_pnl_values.append(row_pnl)
                if derived_long_position > EPSILON or derived_short_position > EPSILON:
                    long_position = derived_long_position
                    short_position = derived_short_position
                if has_row_market_value:
                    long_market_value = derived_long_market_value
                    short_market_value = derived_short_market_value
                if row_pnl_values:
                    position_pnl = sum(row_pnl_values)
            market_value = round(long_market_value + short_market_value, 2)
            if (
                abs(long_position) <= EPSILON
                and abs(short_position) <= EPSILON
                and abs(market_value) <= EPSILON
                and not active_position_rows
            ):
                continue
            updated_at = self._latest_position_updated_at(position_rows) or _safe_iso_text(
                snapshot.get("updated_at")
            )
            data_time = self._latest_position_data_time(active_position_rows)
            data_name = (
                str(
                    active_position_rows[0].get("data_name")
                    or active_position_rows[0].get("symbol")
                    or ""
                )
                if len(active_position_rows) == 1
                else ""
            )
            position_source = _unique_text(
                [
                    row.get("position_source") or row.get("source")
                    for row in active_position_rows
                    if isinstance(row, dict)
                ]
            ) or _safe_iso_text(snapshot.get("position_source"))
            asset_spec_source = _unique_text(
                [
                    row.get("asset_spec_source")
                    for row in active_position_rows
                    if isinstance(row, dict)
                ]
            ) or _safe_iso_text(snapshot.get("asset_spec_source"))
            valuation_warnings: list[str] = []
            _append_unique(valuation_warnings, snapshot.get("valuation_warnings") or [])
            for row in active_position_rows:
                if isinstance(row, dict):
                    _append_unique(valuation_warnings, row.get("valuation_warnings") or [])
            valuation_status = str(snapshot.get("valuation_status") or "").strip() or (
                "estimated" if valuation_warnings else "confirmed"
            )
            margin_value = sum(_safe_float(row.get("margin_value")) for row in active_position_rows)
            commission = sum(_safe_float(row.get("commission")) for row in active_position_rows)
            commission_source = _unique_text(
                [
                    row.get("commission_source")
                    for row in active_position_rows
                    if isinstance(row, dict)
                ]
            )
            gross_pnl_values = [
                row.get("gross_pnl")
                for row in active_position_rows
                if isinstance(row, dict) and row.get("gross_pnl") not in (None, "")
            ]
            gross_pnl = (
                sum(_safe_float(value) for value in gross_pnl_values) if gross_pnl_values else None
            )
            total_long_value += long_market_value
            total_short_value += short_market_value
            total_pnl += position_pnl

            positions.append(
                {
                    "unit_id": str(unit.id),
                    "unit_name": str(unit.strategy_name or unit.strategy_id or unit.id),
                    "symbol": data_name or str(unit.symbol or ""),
                    "data_name": data_name or None,
                    "symbol_name": str(unit.symbol_name or "") or None,
                    "trading_mode": self.normalize_trading_mode(unit.trading_mode),
                    "long_position": _round_quantity(long_position),
                    "short_position": _round_quantity(short_position),
                    "avg_price": self._weighted_avg_price(active_position_rows),
                    "latest_price": (
                        round(_safe_float(snapshot.get("latest_price")), 4)
                        if snapshot.get("latest_price") is not None
                        else None
                    ),
                    "position_pnl": round(position_pnl, 2),
                    "market_value": market_value,
                    "long_market_value": round(long_market_value, 2),
                    "short_market_value": round(short_market_value, 2),
                    "margin_value": round(margin_value, 2) if active_position_rows else None,
                    "multiplier": _unique_number(
                        [
                            row.get("multiplier")
                            for row in active_position_rows
                            if isinstance(row, dict)
                        ]
                    ),
                    "margin_rate": _unique_number(
                        [
                            row.get("margin_rate")
                            for row in active_position_rows
                            if isinstance(row, dict)
                        ]
                    ),
                    "leverage": _unique_number(
                        [
                            row.get("leverage")
                            or _leverage_from_margin_rate(row.get("margin_rate"))
                            for row in active_position_rows
                            if isinstance(row, dict)
                        ]
                    ),
                    "commission": round(commission, 4) if active_position_rows else None,
                    "commission_source": commission_source,
                    "gross_pnl": round(gross_pnl, 2) if gross_pnl is not None else None,
                    "updated_at": updated_at,
                    "data_time": data_time,
                    "position_source": position_source,
                    "asset_spec_source": asset_spec_source,
                    "valuation_status": valuation_status,
                    "valuation_warnings": valuation_warnings,
                }
            )

        positions.sort(key=lambda item: (item["symbol"], item["unit_name"]))
        return PositionManagerResponse(
            positions=positions,
            total_long_value=round(total_long_value, 2),
            total_short_value=round(total_short_value, 2),
            total_pnl=round(total_pnl, 2),
        )

    async def build_daily_summary_response(
        self,
        units: list[StrategyUnit],
        user_id: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> TradingDailySummaryResponse:
        summary_by_day: dict[str, dict[str, Any]] = {}

        for unit in units:
            log_result = self._instance_log_result(unit, user_id)
            if not log_result:
                continue

            dates = [str(value)[:10] for value in (log_result.get("equity_dates") or []) if value]
            equity_curve = list(log_result.get("equity_curve") or [])
            drawdown_curve = list(log_result.get("drawdown_curve") or [])
            trades = list(log_result.get("trades") or [])
            initial_cash = _safe_float(log_result.get("initial_cash"), 0.0)

            trade_count_by_day: dict[str, int] = {}
            for trade in trades:
                trade_day = str(
                    trade.get("dtclose") or trade.get("datetime") or trade.get("dtopen") or ""
                )[:10]
                if trade_day:
                    trade_count_by_day[trade_day] = trade_count_by_day.get(trade_day, 0) + 1

            equity_by_day: dict[str, float] = {}
            drawdown_by_day: dict[str, float] = {}
            for index, trading_date in enumerate(dates):
                previous = next(reversed(equity_by_day.values()), initial_cash)
                equity_value = _safe_float(
                    equity_curve[index] if index < len(equity_curve) else previous,
                    previous,
                )
                equity_by_day[trading_date] = equity_value
                drawdown_value = _safe_float(
                    drawdown_curve[index] if index < len(drawdown_curve) else 0.0,
                    0.0,
                )
                drawdown_by_day[trading_date] = max(
                    drawdown_by_day.get(trading_date, 0.0),
                    drawdown_value,
                )

            prev_equity = initial_cash
            for trading_date in sorted(equity_by_day):
                equity_value = equity_by_day[trading_date]
                if start_date and trading_date < start_date:
                    prev_equity = equity_value
                    continue
                if end_date and trading_date > end_date:
                    break

                daily_pnl = equity_value - prev_equity
                prev_equity = equity_value
                drawdown_value = drawdown_by_day.get(trading_date, 0.0)
                bucket = summary_by_day.setdefault(
                    trading_date,
                    {
                        "trading_date": trading_date,
                        "daily_pnl": 0.0,
                        "trade_count": 0,
                        "cumulative_pnl": 0.0,
                        "max_drawdown": 0.0,
                    },
                )
                bucket["daily_pnl"] += daily_pnl
                bucket["trade_count"] += trade_count_by_day.get(trading_date, 0)
                bucket["cumulative_pnl"] += equity_value - initial_cash
                bucket["max_drawdown"] = max(bucket["max_drawdown"], drawdown_value)

        summaries = [
            {
                "trading_date": trading_date,
                "daily_pnl": round(payload["daily_pnl"], 2),
                "trade_count": _safe_int(payload["trade_count"]),
                "cumulative_pnl": round(payload["cumulative_pnl"], 2),
                "max_drawdown": round(payload["max_drawdown"], 2),
            }
            for trading_date, payload in sorted(summary_by_day.items())
        ]
        return TradingDailySummaryResponse(summaries=summaries)

    def build_status_responses(self, units: list[StrategyUnit]) -> list[UnitStatusResponse]:
        responses: list[UnitStatusResponse] = []
        for unit in units:
            responses.append(
                UnitStatusResponse(
                    id=str(unit.id),
                    run_status=str(unit.run_status or "idle"),
                    last_task_id=str(unit.last_task_id) if unit.last_task_id else None,
                    metrics_snapshot=_safe_dict(unit.metrics_snapshot),
                    run_count=int(unit.run_count or 0),
                    last_run_time=float(unit.last_run_time)
                    if unit.last_run_time is not None
                    else None,
                    bar_count=int(unit.bar_count) if unit.bar_count is not None else None,
                    trading_instance_id=str(unit.trading_instance_id)
                    if unit.trading_instance_id
                    else None,
                    trading_snapshot=_safe_dict(unit.trading_snapshot),
                    trading_mode=self.normalize_trading_mode(unit.trading_mode),
                    lock_trading=bool(unit.lock_trading),
                    lock_running=bool(unit.lock_running),
                    opt_status=None,
                    opt_total=None,
                    opt_completed=None,
                    opt_progress=None,
                    opt_elapsed_time=None,
                    opt_remaining_time=None,
                )
            )
        return responses
