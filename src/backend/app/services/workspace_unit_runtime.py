from __future__ import annotations

import shutil
import textwrap
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from app.models.workspace import StrategyUnit
from app.services.strategy_service import get_strategy_dir

_WORKSPACE_UNITS_ROOT = Path(__file__).resolve().parents[4] / "workspace_units"
_ASSET_TYPE_ALIASES = {
    "外汇": "forex",
    "forex": "forex",
    "fx": "forex",
    "otc": "otc",
    "股票": "stock",
    "stock": "stock",
    "equity": "stock",
    "期货": "future",
    "future": "future",
    "futures": "future",
    "期权": "option",
    "option": "option",
    "options": "option",
}
_DEFAULT_UNIT_START_DATE = datetime(2020, 1, 1, tzinfo=timezone.utc)

_UNIT_RUN_PY = textwrap.dedent(
    """
    from __future__ import annotations

    import importlib.util
    import os
    import sys
    from pathlib import Path

    import backtrader as bt
    import pandas as pd
    import yaml
    from backtrader.comminfo import ComminfoFuturesPercent

    BASE_DIR = Path(__file__).resolve().parent


    class UnitPandasFeed(bt.feeds.PandasData):
        params = (
            ('datetime', None),
            ('open', -1),
            ('high', -1),
            ('low', -1),
            ('close', -1),
            ('volume', -1),
            ('openinterest', -1),
        )


    def load_config() -> dict:
        with (BASE_DIR / 'config.yaml').open('r', encoding='utf-8') as handle:
            return yaml.safe_load(handle) or {}


    def _safe_int(value, default=0):
        try:
            return int(value) if value is not None else default
        except (TypeError, ValueError):
            return default


    def _safe_float(value, default=0.0):
        try:
            return float(value) if value is not None else default
        except (TypeError, ValueError):
            return default


    def _timeframe_suffix(timeframe: str, timeframe_n: int) -> str:
        text = str(timeframe or '').strip().lower()
        if text in {'1d', 'd', 'd1', 'day', 'daily'}:
            return 'D1'
        if text in {'1h', 'h', 'h1', 'hour'}:
            return 'H1'
        if text in {'tick', 'ticks'}:
            return 'ticks'
        if text in {'1m', '1min', 'm1', 'minute'}:
            return '1min'
        if text in {'5m', '5min', 'm5'}:
            return '5min'
        multiplier = _safe_int(timeframe_n, 1)
        if multiplier > 1 and text in {'1m', '1min', 'm'}:
            return f'{multiplier}min'
        return text.upper() or 'D1'


    def _candidate_names(symbol: str, suffix: str) -> list[str]:
        raw = str(symbol or '').strip()
        if not raw:
            return []
        variants = [raw, raw.upper(), raw.lower()]
        names: list[str] = []
        for value in variants:
            if suffix:
                names.append(f'{value}_{suffix}.csv')
            names.append(f'{value}.csv')
        unique: list[str] = []
        seen: set[str] = set()
        for name in names:
            if name not in seen:
                unique.append(name)
                seen.add(name)
        return unique


    def resolve_data_file(config: dict) -> Path:
        data = config.get('data') or {}
        directory_path = Path(str(data.get('directory_path') or '')).expanduser()
        if not directory_path.is_dir():
            raise FileNotFoundError(f'Data directory not found: {directory_path}')
        symbol = str(data.get('symbol') or '').strip()
        if not symbol:
            raise ValueError('Config symbol is empty')
        suffix = _timeframe_suffix(data.get('timeframe', '1d'), _safe_int(data.get('timeframe_n'), 1))
        direct_dirs = [directory_path / suffix, directory_path]
        for root in direct_dirs:
            if not root.is_dir():
                continue
            for name in _candidate_names(symbol, suffix):
                candidate = root / name
                if candidate.is_file():
                    return candidate
        patterns = [f'{symbol}_*.csv', f'{symbol.upper()}_*.csv', f'{symbol.lower()}_*.csv']
        for pattern in patterns:
            matches = sorted(directory_path.rglob(pattern))
            if not matches:
                continue
            for match in matches:
                if suffix and (suffix.lower() in match.name.lower() or match.parent.name.lower() == suffix.lower()):
                    return match
            return matches[0]
        raise FileNotFoundError(f'No CSV file found for symbol={symbol} under {directory_path}')


    def load_dataframe(config: dict) -> tuple[pd.DataFrame, Path]:
        data = config.get('data') or {}
        csv_path = resolve_data_file(config)
        df = pd.read_csv(csv_path)
        rename_map = {}
        if 'time' in df.columns and 'datetime' not in df.columns:
            rename_map['time'] = 'datetime'
        if 'tick_volume' in df.columns and 'volume' not in df.columns:
            rename_map['tick_volume'] = 'volume'
        if 'open_interest' in df.columns and 'openinterest' not in df.columns:
            rename_map['open_interest'] = 'openinterest'
        if 'real_volume' in df.columns and 'openinterest' not in df.columns:
            rename_map['real_volume'] = 'openinterest'
        df = df.rename(columns=rename_map)
        if 'datetime' not in df.columns:
            raise ValueError(f'Missing datetime/time column in {csv_path}')
        for column in ('open', 'high', 'low', 'close'):
            if column not in df.columns:
                raise ValueError(f'Missing required column {column} in {csv_path}')
        if 'volume' not in df.columns:
            df['volume'] = 0.0
        if 'openinterest' not in df.columns:
            df['openinterest'] = 0.0
        df['datetime'] = pd.to_datetime(df['datetime'], errors='coerce', utc=True)
        df = df.dropna(subset=['datetime'])
        start_date = data.get('start_date')
        if start_date:
            start_ts = pd.to_datetime(start_date, errors='coerce', utc=True)
            if not pd.isna(start_ts):
                df = df[df['datetime'] >= start_ts]
        if data.get('use_end_date', True):
            end_date = data.get('end_date')
            if end_date:
                end_ts = pd.to_datetime(end_date, errors='coerce', utc=True)
                if not pd.isna(end_ts):
                    df = df[df['datetime'] <= end_ts]
        df = df.sort_values('datetime').drop_duplicates('datetime')
        df = df[['datetime', 'open', 'high', 'low', 'close', 'volume', 'openinterest']].copy()
        for column in ('open', 'high', 'low', 'close', 'volume', 'openinterest'):
            df[column] = pd.to_numeric(df[column], errors='coerce').fillna(0.0)
        df = df[(df['open'] > 0) & (df['close'] > 0)]
        sample_count = _safe_int(data.get('sample_count'), 0)
        bar_count = _safe_int(data.get('bar_count'), 0)
        limit = bar_count if bar_count > 0 else sample_count
        if limit > 0 and len(df) > limit:
            df = df.iloc[-limit:]
        if df.empty:
            raise ValueError(f'No data rows available after filtering for {csv_path}')
        df = df.set_index('datetime')
        return df, csv_path


    def _import_strategy_module(template_dir: Path, module_name: str | None) -> object:
        module_path = template_dir / module_name if module_name else None
        if module_path is None or not module_path.is_file():
            candidates = sorted(template_dir.glob('strategy_*.py'))
            if not candidates:
                raise FileNotFoundError(f'No strategy_*.py found under {template_dir}')
            module_path = candidates[0]
        spec = importlib.util.spec_from_file_location(module_path.stem, module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f'Cannot import strategy module: {module_path}')
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module


    def _pick_strategy_class(module: object):
        for value in vars(module).values():
            if isinstance(value, type) and issubclass(value, bt.Strategy) and value is not bt.Strategy:
                return value
        raise ValueError('No bt.Strategy subclass found in strategy module')


    def _pick_feed_class(module: object):
        for value in vars(module).values():
            if isinstance(value, type) and issubclass(value, bt.feeds.PandasData) and value is not bt.feeds.PandasData:
                return value
        return UnitPandasFeed


    def run():
        config = load_config()
        workspace_unit = config.get('workspace_unit') or {}
        template_dir = Path(str(workspace_unit.get('template_dir') or '')).expanduser()
        if not template_dir.is_dir():
            raise FileNotFoundError(f'Template dir not found: {template_dir}')
        module = _import_strategy_module(template_dir, workspace_unit.get('strategy_module'))
        strategy_class = _pick_strategy_class(module)
        feed_class = _pick_feed_class(module)
        df, csv_path = load_dataframe(config)
        data_cfg = config.get('data') or {}
        backtest_cfg = config.get('backtest') or {}
        params = config.get('params') or {}
        asset_type = str(data_cfg.get('asset_type') or workspace_unit.get('asset_type') or '').strip().lower()
        cerebro = bt.Cerebro(stdstats=True)
        name = str(data_cfg.get('symbol') or 'DATA')
        cerebro.adddata(feed_class(dataname=df), name=name)
        commission = _safe_float(backtest_cfg.get('commission'), 0.001)
        margin = backtest_cfg.get('margin')
        multiplier = backtest_cfg.get('multiplier', backtest_cfg.get('mult'))
        if asset_type in {'future', 'option'} and (margin is not None or multiplier is not None):
            cerebro.broker.addcommissioninfo(
                ComminfoFuturesPercent(
                    commission=commission,
                    margin=_safe_float(margin, 1.0),
                    mult=_safe_float(multiplier, 1.0),
                ),
                name=name,
            )
        else:
            cerebro.broker.setcommission(commission=commission)
        cerebro.broker.setcash(_safe_float(backtest_cfg.get('initial_cash'), 100000.0))
        cerebro.addstrategy(strategy_class, **params)
        forced_log_dir = os.environ.get('BACKTRADER_LOG_DIR', '').strip()
        log_dir = Path(forced_log_dir) if forced_log_dir else (BASE_DIR / 'logs')
        cerebro.addobserver(
            bt.observers.TradeLogger,
            log_orders=True,
            log_trades=True,
            log_positions=True,
            log_bars=True,
            log_indicators=True,
            log_dir=str(log_dir),
            log_format='text',
        )
        print(f'Loading data from {csv_path}')
        results = cerebro.run()
        final_value = cerebro.broker.getvalue()
        print(f'Final value: {final_value}')
        return results, final_value


    if __name__ == '__main__':
        run()
    """
).lstrip()


def workspace_dir(workspace_id: str) -> Path:
    return _WORKSPACE_UNITS_ROOT / str(workspace_id or "")


def unit_dir(workspace_id: str, unit_id: str) -> Path:
    return workspace_dir(workspace_id) / str(unit_id or "")


def ensure_workspace_dir(workspace_id: str) -> Path:
    path = workspace_dir(workspace_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def remove_workspace_dir(workspace_id: str) -> None:
    shutil.rmtree(workspace_dir(workspace_id), ignore_errors=True)


def remove_unit_dir(workspace_id: str, unit_id: str) -> None:
    shutil.rmtree(unit_dir(workspace_id, unit_id), ignore_errors=True)


def _asset_type_for_unit(category: str) -> str:
    text = str(category or "").strip()
    lowered = text.lower()
    return _ASSET_TYPE_ALIASES.get(text, _ASSET_TYPE_ALIASES.get(lowered, lowered or "future"))


def _trading_data_type_for_asset(asset_type: str) -> str:
    mapping = {
        "future": "futures",
        "stock": "stock",
        "forex": "forex",
        "option": "options",
        "otc": "otc",
    }
    normalized = _asset_type_for_unit(asset_type)
    return mapping.get(normalized, normalized or "futures")


def _trading_exchange_for_unit(
    unit: StrategyUnit, asset_type: str, data_section: dict[str, Any]
) -> str:
    gateway_config = unit.gateway_config if isinstance(unit.gateway_config, dict) else {}
    params = dict(gateway_config.get("params") or {})
    gateway = dict(params.get("gateway") or {})
    exchange = (
        str(gateway.get("exchange_type") or data_section.get("exchange") or "").strip().upper()
    )
    if exchange:
        return exchange
    defaults = {
        "future": "CTP",
        "stock": "IB_WEB",
        "forex": "MT5",
        "otc": "MT5",
        "option": "CTP",
    }
    return defaults.get(_asset_type_for_unit(asset_type), "CTP")


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _strategy_module_name(template_dir: Path) -> str:
    candidates = sorted(template_dir.glob("strategy_*.py"))
    if not candidates:
        raise FileNotFoundError(f"No strategy_*.py found under {template_dir}")
    return candidates[0].name


def _default_unit_start_date_iso() -> str:
    return _DEFAULT_UNIT_START_DATE.isoformat()


def _default_unit_end_date_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_unit_data_config(data_config: dict[str, Any] | None) -> dict[str, Any]:
    normalized = dict(data_config or {})
    range_type = str(normalized.get("range_type") or "date").strip().lower()
    normalized["range_type"] = range_type if range_type in {"date", "sample"} else "date"
    if normalized["range_type"] == "date":
        if not str(normalized.get("start_date") or "").strip():
            normalized["start_date"] = _default_unit_start_date_iso()
        normalized["use_end_date"] = normalized.get("use_end_date") is not False
        if normalized["use_end_date"] and not str(normalized.get("end_date") or "").strip():
            normalized["end_date"] = _default_unit_end_date_iso()
        normalized.pop("sample_count", None)
        normalized.pop("bar_count", None)
    else:
        if normalized.get("sample_count") in (None, "", 0):
            normalized["sample_count"] = 1000
    return normalized


def _build_unit_config(unit: StrategyUnit, workspace_settings: dict[str, Any]) -> dict[str, Any]:
    strategy_id = str(unit.strategy_id or "").strip()
    if not strategy_id:
        raise ValueError("Strategy unit is missing strategy_id")
    template_dir = get_strategy_dir(strategy_id)
    template_config = deepcopy(_read_yaml(template_dir / "config.yaml"))
    strategy_section = dict(template_config.get("strategy") or {})
    if unit.strategy_name:
        strategy_section["name"] = unit.strategy_name
    template_config["strategy"] = strategy_section
    params_section = dict(template_config.get("params") or {})
    params_section.update(unit.params or {})
    template_config["params"] = params_section
    unit_settings = dict(unit.unit_settings or {})
    backtest_section = dict(template_config.get("backtest") or {})
    for key in ("initial_cash", "commission", "margin", "multiplier"):
        if unit_settings.get(key) is not None:
            backtest_section[key] = unit_settings[key]
    template_config["backtest"] = backtest_section
    category = unit.category or str((template_config.get("data") or {}).get("data_type") or "")
    asset_type = _asset_type_for_unit(category)
    data_source = dict(workspace_settings.get("data_source") or {})
    csv_section = dict(data_source.get("csv") or {})
    data_root = str(csv_section.get("directory_path") or "").strip()
    asset_root = str((Path(data_root) / asset_type).resolve()) if data_root else ""
    data_section = dict(template_config.get("data") or {})
    data_section.update(_normalize_unit_data_config(unit.data_config))
    data_section["symbol"] = unit.symbol or data_section.get("symbol", "")
    data_section["symbol_name"] = unit.symbol_name or data_section.get("symbol_name", "")
    data_section["asset_type"] = asset_type
    data_section["category"] = unit.category or data_section.get("category", "")
    data_section["timeframe"] = unit.timeframe or data_section.get("timeframe", "1d")
    data_section["timeframe_n"] = unit.timeframe_n or data_section.get("timeframe_n", 1)
    data_section["directory_path"] = asset_root
    template_config["data"] = data_section
    template_config["unit_settings"] = unit_settings
    template_config["optimization_config"] = dict(unit.optimization_config or {})
    template_config["workspace_unit"] = {
        "workspace_id": unit.workspace_id,
        "unit_id": unit.id,
        "group_name": unit.group_name or "",
        "strategy_id": strategy_id,
        "strategy_name": unit.strategy_name or "",
        "template_dir": str(template_dir),
        "strategy_module": _strategy_module_name(template_dir),
        "asset_type": asset_type,
        "data_source_type": str(data_source.get("type") or "csv"),
        "data_root": data_root,
    }
    return template_config


def sync_unit_runtime(unit: StrategyUnit, workspace_settings: dict[str, Any]) -> Path:
    target_dir = unit_dir(unit.workspace_id, unit.id)
    target_dir.mkdir(parents=True, exist_ok=True)
    config = _build_unit_config(unit, workspace_settings)
    with (target_dir / "config.yaml").open("w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, allow_unicode=True, sort_keys=False)
    (target_dir / "run.py").write_text(_UNIT_RUN_PY, encoding="utf-8")
    return target_dir


def _timeframe_to_bar_seconds(timeframe: str | None, timeframe_n: int | None = None) -> int | None:
    text = str(timeframe or "").strip().lower()
    multiplier = int(timeframe_n or 1)
    if text in {"1m", "m1", "1min", "minute", "minutes", "m"}:
        return 60 * max(multiplier, 1)
    if text in {"5m", "m5", "5min"}:
        return 300
    if text in {"15m", "m15", "15min"}:
        return 900
    if text in {"30m", "m30", "30min"}:
        return 1800
    if text in {"1h", "h1", "hour"}:
        return 3600 * max(multiplier, 1)
    if text in {"1d", "d1", "day", "daily"}:
        return 86400 * max(multiplier, 1)
    if text.endswith("s"):
        digits = "".join(ch for ch in text if ch.isdigit())
        if digits:
            return max(int(digits), 1)
    return None


def _merge_dict_section(
    target: dict[str, Any],
    key: str,
    incoming: dict[str, Any] | None,
) -> None:
    if not isinstance(incoming, dict) or not incoming:
        return
    merged = dict(target.get(key) or {})
    merged.update(incoming)
    target[key] = merged


def _apply_gateway_runtime_config(
    template_config: dict[str, Any],
    gateway_config: dict[str, Any] | None,
) -> None:
    params = (
        dict((gateway_config or {}).get("params") or {}) if isinstance(gateway_config, dict) else {}
    )
    if not params:
        return
    gateway = params.get("gateway")
    if isinstance(gateway, dict) and gateway:
        merged_gateway = dict(template_config.get("gateway") or {})
        merged_gateway.update(gateway)
        template_config["gateway"] = merged_gateway
    for key in ("ctp", "ib_web", "mt5", "binance", "okx"):
        value = params.get(key)
        if isinstance(value, dict) and value:
            _merge_dict_section(template_config, key, value)


def _build_trading_unit_config(
    unit: StrategyUnit, workspace_settings: dict[str, Any]
) -> dict[str, Any]:
    strategy_id = str(unit.strategy_id or "").strip()
    if not strategy_id:
        raise ValueError("Strategy unit is missing strategy_id")
    template_dir = get_strategy_dir(strategy_id)
    template_config = deepcopy(_read_yaml(template_dir / "config.yaml"))

    strategy_section = dict(template_config.get("strategy") or {})
    if unit.strategy_name:
        strategy_section["name"] = unit.strategy_name
    template_config["strategy"] = strategy_section

    params_section = dict(template_config.get("params") or {})
    params_section.update(unit.params or {})
    template_config["params"] = params_section

    symbol_section = dict(template_config.get("symbol") or {})
    if unit.symbol:
        symbol_section["code"] = unit.symbol
    if unit.symbol_name:
        symbol_section["name"] = unit.symbol_name
    if unit.category:
        symbol_section.setdefault("category", unit.category)
    if symbol_section:
        template_config["symbol"] = symbol_section

    data_section = dict(template_config.get("data") or {})
    data_section.update(_normalize_unit_data_config(unit.data_config))
    if unit.symbol:
        data_section["symbol"] = unit.symbol
    if unit.symbol_name:
        data_section["symbol_name"] = unit.symbol_name
    if unit.timeframe:
        data_section["timeframe"] = unit.timeframe
    if unit.timeframe_n:
        data_section["timeframe_n"] = unit.timeframe_n
    if unit.category:
        data_section["category"] = unit.category
    asset_type = _asset_type_for_unit(
        unit.category or str(data_section.get("data_type") or data_section.get("asset_type") or "")
    )
    exchange_type = _trading_exchange_for_unit(unit, asset_type, data_section)
    data_section["asset_type"] = asset_type
    data_section["data_type"] = _trading_data_type_for_asset(asset_type)
    data_section["exchange"] = exchange_type
    template_config["data"] = data_section

    simulate_section = dict(template_config.get("simulate") or {})
    unit_settings = dict(unit.unit_settings or {})
    for key in (
        "initial_cash",
        "commission",
        "slippage",
        "position_size",
        "duration_seconds",
        "session_timeout",
    ):
        if unit_settings.get(key) is not None:
            simulate_section[key] = unit_settings[key]
    if simulate_section:
        template_config["simulate"] = simulate_section

    live_section = dict(template_config.get("live") or {})
    if unit.symbol:
        live_section["symbol"] = unit.symbol
    bar_seconds = _timeframe_to_bar_seconds(unit.timeframe, unit.timeframe_n)
    if bar_seconds is not None:
        live_section["bar_seconds"] = bar_seconds
    for key in ("duration_seconds", "session_timeout"):
        if simulate_section.get(key) is not None and live_section.get(key) is None:
            live_section[key] = simulate_section[key]
    if live_section:
        template_config["live"] = live_section

    _apply_gateway_runtime_config(
        template_config,
        unit.gateway_config if isinstance(unit.gateway_config, dict) else {},
    )

    template_config["unit_settings"] = unit_settings
    template_config["optimization_config"] = dict(unit.optimization_config or {})
    template_config["workspace_unit"] = {
        "workspace_id": unit.workspace_id,
        "unit_id": unit.id,
        "group_name": unit.group_name or "",
        "strategy_id": strategy_id,
        "strategy_name": unit.strategy_name or "",
        "template_dir": str(template_dir),
        "strategy_module": _strategy_module_name(template_dir),
        "asset_type": asset_type,
        "runtime_mode": "trading",
        "workspace_settings": deepcopy(workspace_settings or {}),
    }
    return template_config


def _sync_trading_runtime_sources(template_dir: Path, target_dir: Path) -> None:
    for source in template_dir.iterdir():
        if not source.is_file():
            continue
        if source.suffix != ".py":
            continue
        shutil.copy2(source, target_dir / source.name)


def sync_trading_unit_runtime(unit: StrategyUnit, workspace_settings: dict[str, Any]) -> Path:
    target_dir = unit_dir(unit.workspace_id, unit.id)
    target_dir.mkdir(parents=True, exist_ok=True)
    template_dir = get_strategy_dir(str(unit.strategy_id or "").strip())
    _sync_trading_runtime_sources(template_dir, target_dir)
    config = _build_trading_unit_config(unit, workspace_settings)
    with (target_dir / "config.yaml").open("w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, allow_unicode=True, sort_keys=False)
    return target_dir


def sync_workspace_unit_runtime(
    unit: StrategyUnit,
    workspace_settings: dict[str, Any],
    workspace_type: str,
) -> Path:
    if str(workspace_type or "").strip().lower() == "trading":
        return sync_trading_unit_runtime(unit, workspace_settings)
    return sync_unit_runtime(unit, workspace_settings)
