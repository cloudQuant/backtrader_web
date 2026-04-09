from __future__ import annotations

import importlib.util
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
    log_dir = BASE_DIR / 'logs'
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
