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


def _safe_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


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
                    "size": round(size, 4),
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

    @staticmethod
    def _position_updated_at(row: dict[str, Any]) -> str | None:
        return _safe_iso_text(
            row.get("updated_at")
            or row.get("log_time")
            or row.get("datetime")
            or row.get("dt")
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

        log_dir = _instance_log_dir(instance)
        if log_dir and log_dir.is_dir():
            log_result = parse_log_dir(log_dir) if full_log else None
            positions = cls._latest_position_rows(parse_position_log(log_dir))
            if not positions:
                positions = parse_current_position(log_dir)

            long_position = 0.0
            short_position = 0.0
            long_market_value = 0.0
            short_market_value = 0.0
            position_pnl = 0.0
            detail_positions: list[dict[str, Any]] = []
            latest_position_updated_at: str | None = None

            for item in positions:
                size = _safe_float(item.get("size"))
                entry_price = _safe_float(item.get("price"))
                market_value_raw = _safe_float(item.get("market_value", item.get("value")))
                current_price = (
                    abs(market_value_raw) / abs(size)
                    if abs(size) > 0 and abs(market_value_raw) > 0
                    else entry_price
                )
                pnl = (current_price - entry_price) * size
                direction = "long" if size >= 0 else "short"

                if size >= 0:
                    long_position += abs(size)
                    long_market_value += abs(size) * current_price
                else:
                    short_position += abs(size)
                    short_market_value += abs(size) * current_price

                position_pnl += pnl
                latest_price = current_price
                position_updated_at = cls._position_updated_at(item)
                position_data_time = cls._position_data_time(item)
                if position_updated_at and (
                    latest_position_updated_at is None
                    or position_updated_at > latest_position_updated_at
                ):
                    latest_position_updated_at = position_updated_at
                detail_positions.append(
                    {
                        "data_name": str(item.get("data_name") or ""),
                        "direction": direction,
                        "size": abs(size),
                        "price": round(entry_price, 4) if entry_price else None,
                        "current_price": round(current_price, 4) if current_price else None,
                        "market_value": round(abs(size) * current_price, 2),
                        "pnl": round(pnl, 2),
                        "updated_at": position_updated_at,
                        "data_time": position_data_time,
                    }
                )

            snapshot["positions"] = detail_positions
            if latest_position_updated_at:
                snapshot["updated_at"] = latest_position_updated_at
            snapshot["long_position"] = round(long_position, 4)
            snapshot["short_position"] = round(short_position, 4)
            snapshot["long_market_value"] = round(long_market_value, 2)
            snapshot["short_market_value"] = round(short_market_value, 2)
            snapshot["position_pnl"] = round(position_pnl, 2)

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
                snapshot["max_drawdown_rate"] = round(
                    _safe_float(log_result.get("max_drawdown")), 2
                )
                total_market_value = long_market_value + short_market_value
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
                        if (
                            not refreshed
                            or str(refreshed.get("status") or "").lower() != "running"
                        ):
                            raise
                        started = refreshed
                        already_running = True

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
            try:
                if unit.lock_running:
                    raise ValueError("该策略单元已锁定运行")
                if unit.lock_trading:
                    raise ValueError("该策略单元已锁定交易")
                if unit.trading_instance_id:
                    await manager.stop_instance(str(unit.trading_instance_id))
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
                unit.trading_snapshot = snapshot
            except Exception as exc:
                unit.run_status = "failed"
                unit.trading_snapshot = self.default_snapshot(
                    unit=unit,
                    instance_status="error",
                    error=str(exc),
                )
            results.append({"unit_id": unit.id, "cancelled": cancelled})

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
            long_market_value = _safe_float(snapshot.get("long_market_value"))
            short_market_value = _safe_float(snapshot.get("short_market_value"))
            position_pnl = _safe_float(snapshot.get("position_pnl"))
            market_value = round(long_market_value + short_market_value, 2)
            updated_at = self._latest_position_updated_at(position_rows) or _safe_iso_text(
                snapshot.get("updated_at")
            )
            data_time = self._latest_position_data_time(position_rows)
            total_long_value += long_market_value
            total_short_value += short_market_value
            total_pnl += position_pnl

            positions.append(
                {
                    "unit_id": str(unit.id),
                    "unit_name": str(unit.strategy_name or unit.strategy_id or unit.id),
                    "symbol": str(unit.symbol or ""),
                    "symbol_name": str(unit.symbol_name or "") or None,
                    "trading_mode": self.normalize_trading_mode(unit.trading_mode),
                    "long_position": round(_safe_float(snapshot.get("long_position")), 4),
                    "short_position": round(_safe_float(snapshot.get("short_position")), 4),
                    "avg_price": self._weighted_avg_price(position_rows),
                    "latest_price": (
                        round(_safe_float(snapshot.get("latest_price")), 4)
                        if snapshot.get("latest_price") is not None
                        else None
                    ),
                    "position_pnl": round(position_pnl, 2),
                    "market_value": market_value,
                    "updated_at": updated_at,
                    "data_time": data_time,
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
