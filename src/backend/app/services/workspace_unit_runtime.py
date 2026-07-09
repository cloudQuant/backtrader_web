from __future__ import annotations

import logging
import shutil
import textwrap
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from app.models.workspace import StrategyUnit
from app.services.strategy_service import get_strategy_dir

logger = logging.getLogger(__name__)

_WORKSPACE_UNITS_ROOT = Path(__file__).resolve().parents[4] / "workspace_units"
_DEFAULT_LIVE_QCHECK_SECONDS = 0.5
_SENSITIVE_CONFIG_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth_code",
    "authorization",
    "client_secret",
    "passphrase",
    "password",
    "refresh_token",
    "secret",
    "secret_key",
    "token",
}
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


def _positive_float(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def _bool_value(value: Any, default: bool) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off", ""}


def _exactbars_value(value: Any, default: bool | int = True) -> bool | int:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "yes", "on"}:
        return True
    if text in {"false", "no", "off"}:
        return False
    try:
        return int(value)
    except (TypeError, ValueError):
        return _bool_value(value, bool(default))

_UNIT_RUN_PY = textwrap.dedent(
    """
    from __future__ import annotations

    import importlib.util
    import logging
    import os
    import sys
    import time
    from pathlib import Path

    import backtrader as bt
    import pandas as pd
    import yaml
    from backtrader.comminfo import ComminfoFuturesFixed, ComminfoFuturesInverse, ComminfoFuturesMixed, ComminfoFuturesPercent

    BASE_DIR = Path(__file__).resolve().parent
    logger = logging.getLogger(__name__)
    _PANDAS_DATA_CLASS = getattr(bt.feeds, 'PandasData', None)
    if _PANDAS_DATA_CLASS is None:
        from backtrader.feeds.pandafeed import PandasData as _PANDAS_DATA_CLASS


    class UnitPandasFeed(_PANDAS_DATA_CLASS):
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


    def _safe_bool(value, default=False):
        if value in (None, ''):
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() not in {'0', 'false', 'no', 'off', ''}


    def _keepalive_seconds(config: dict) -> float:
        env_keepalive = os.environ.get('BACKTRADER_KEEPALIVE_AFTER_RUN')
        if _safe_bool(env_keepalive, False):
            return _safe_float(os.environ.get('BACKTRADER_KEEPALIVE_SECONDS'), 3600.0)
        for section_key in ('unit_settings', 'live', 'simulate'):
            section = config.get(section_key) or {}
            if not isinstance(section, dict):
                continue
            if _safe_bool(section.get('keepalive_after_run'), False):
                return _safe_float(section.get('keepalive_seconds'), 3600.0)
        return 0.0


    def _first_number(*values, default=None):
        for value in values:
            if value in (None, ''):
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return default


    def _normalise_rate(value, default=0.0):
        number = _first_number(value, default=default)
        if number is None:
            return default
        if number > 1.0:
            return number / 100.0
        return max(number, 0.0)


    def _normalise_signed_rate(value, default=None):
        number = _first_number(value, default=default)
        if number is None:
            return default
        if abs(number) > 1.0:
            return number / 100.0
        return number


    def _symbol_keys(symbol: str) -> list[str]:
        raw = str(symbol or '').strip()
        exchanges = {'SHFE', 'DCE', 'CZCE', 'CFFEX', 'INE', 'GFEX'}
        instrument = raw
        exchange = ''
        if '.' in raw:
            left, right = raw.split('.', 1)
            left = left.strip()
            right = right.strip()
            if left.upper() in exchanges:
                instrument, exchange = right, left.upper()
            elif right.upper() in exchanges:
                instrument, exchange = left, right.upper()
            else:
                instrument = left
        if '_' in raw:
            left, right = raw.split('_', 1)
            left = left.strip()
            right = right.strip()
            if left.upper() in exchanges:
                instrument, exchange = right, left.upper()
            elif right.upper() in exchanges:
                instrument, exchange = left, right.upper()
        keys = [raw, instrument, instrument.upper(), instrument.lower()]
        if exchange and instrument:
            keys.extend([
                f'{exchange}.{instrument}',
                f'{instrument}.{exchange}',
                f'{exchange}_{instrument}',
                f'{instrument}_{exchange}',
            ])
        result: list[str] = []
        seen: set[str] = set()
        for key in keys:
            if key and key not in seen:
                result.append(key)
                seen.add(key)
        return result


    def _as_dict(value):
        return dict(value) if isinstance(value, dict) else {}


    def _contract_metadata_for(config: dict, symbol: str) -> dict:
        for source in (
            config,
            _as_dict(config.get('params')),
            _as_dict(config.get('live')),
            _as_dict(config.get('simulate')),
            _as_dict(config.get('data')),
            _as_dict(config.get('backtest')),
        ):
            for container_key in ('contract_metadata', 'contracts', 'contract_specs', 'instrument_specs'):
                container = source.get(container_key)
                if not isinstance(container, dict):
                    continue
                for key in _symbol_keys(symbol):
                    item = container.get(key)
                    if isinstance(item, dict):
                        return dict(item)
        return {}


    def _explicit_commission_rate(meta: dict):
        method = str(meta.get('commission_method') or '').strip().lower()
        for key in (
            'commission',
            'commission_rate',
            'fee_rate',
            'open_fee_rate',
            'open_commission_rate',
            'OpenRatioByMoney',
            'COMMISSION_OPEN_RATIO',
        ):
            value = _first_number(meta.get(key))
            if value is None:
                continue
            if (
                method == 'percent_10k'
                or key == 'COMMISSION_OPEN_RATIO'
                or (key == 'OpenRatioByMoney' and value > 0.01)
            ):
                value = max(value, 0.0)
                return value / 10000.0 if value > 0.01 else value
            return _normalise_rate(value, 0.0)
        return None


    def _commission_rate(meta: dict, fallback):
        value = _explicit_commission_rate(meta)
        return fallback if value is None else value


    def _commission_amount(meta: dict):
        return _first_number(
            meta.get('commission_amount'),
            meta.get('fee_amount'),
            meta.get('commission_per_lot'),
            meta.get('open_fee_amount'),
            meta.get('open_commission_amount'),
            meta.get('OpenRatioByVolume'),
            meta.get('COMMISSION_OPEN_AMOUNT'),
        )


    def _commission_rate_from_keys(meta: dict, keys: tuple[str, ...]):
        method = str(meta.get('commission_method') or '').strip().lower()
        for key in keys:
            value = _first_number(meta.get(key))
            if value is None:
                continue
            if (
                method == 'percent_10k'
                or key.startswith('COMMISSION_')
                or key.endswith('RatioByMoney') and value > 0.01
            ):
                value = max(value, 0.0)
                return value / 10000.0 if value > 0.01 else value
            return _normalise_rate(value, 0.0)
        return None


    def _commission_amount_from_keys(meta: dict, keys: tuple[str, ...]):
        for key in keys:
            value = _first_number(meta.get(key))
            if value is not None:
                return max(value, 0.0)
        return None


    def _signed_commission_rate(meta: dict, *keys):
        for key in keys:
            value = _normalise_signed_rate(meta.get(key))
            if value is not None:
                return value
        return None


    def _text(value) -> str:
        return str(value or '').strip().lower().replace('-', '_')


    def _currency_code(value) -> str:
        return ''.join(ch for ch in str(value or '').strip().upper() if ch.isalnum())


    def _is_inverse_contract(meta: dict) -> bool:
        explicit = _text(
            meta.get('inverse')
            or meta.get('is_inverse')
            or meta.get('isInverse')
            or meta.get('inverse_contract')
            or meta.get('inverseContract')
        )
        if explicit in {'1', 'true', 'yes', 'y', 'inverse'}:
            return True
        if explicit in {'0', 'false', 'no', 'n', 'linear'}:
            return False

        contract_type = _text(
            meta.get('contract_type')
            or meta.get('contractType')
            or meta.get('ctType')
            or meta.get('type')
        )
        if 'inverse' in contract_type or 'coin_margined' in contract_type:
            return True
        if 'linear' in contract_type or 'usdt_margined' in contract_type or 'usdc_margined' in contract_type:
            return False

        contract_ccy = _currency_code(
            meta.get('contract_value_currency')
            or meta.get('contractValueCurrency')
            or meta.get('contract_value_ccy')
            or meta.get('ctValCcy')
        )
        base_ccy = _currency_code(
            meta.get('base_currency') or meta.get('baseCurrency') or meta.get('base_asset') or meta.get('baseCcy')
        )
        quote_ccy = _currency_code(
            meta.get('quote_currency') or meta.get('quoteCurrency') or meta.get('quote_asset') or meta.get('quoteCcy')
        )
        settle_ccy = _currency_code(
            meta.get('settle_currency')
            or meta.get('settleCurrency')
            or meta.get('settle_ccy')
            or meta.get('settleCcy')
            or meta.get('margin_currency')
            or meta.get('marginCcy')
        )
        fee_ccy = _currency_code(meta.get('fee_currency') or meta.get('feeCurrency') or meta.get('feeCcy'))
        if contract_ccy and quote_ccy and contract_ccy == quote_ccy and contract_ccy != base_ccy:
            return True
        if contract_ccy and base_ccy and contract_ccy == base_ccy:
            return False
        if base_ccy and quote_ccy and settle_ccy == base_ccy and settle_ccy != quote_ccy:
            return True
        return bool((contract_ccy or settle_ccy) and base_ccy and quote_ccy and fee_ccy == base_ccy and fee_ccy != quote_ccy)


    def _contract_multiplier(meta: dict, simulate_cfg: dict, backtest_cfg: dict, inverse_contract: bool):
        if inverse_contract:
            return _first_number(
                meta.get('contract_value'),
                meta.get('contractValue'),
                meta.get('contract_value_amount'),
                meta.get('contractValueAmount'),
                meta.get('contract_notional_value'),
                meta.get('okx_contract_value'),
                meta.get('ctVal'),
                meta.get('multiplier'),
                meta.get('mult'),
                meta.get('contract_multiplier'),
                meta.get('contract_size'),
                meta.get('trade_contract_size'),
                meta.get('ctMult'),
                meta.get('VolumeMultiple'),
                meta.get('CONTRACT_MULTIPLIER'),
                simulate_cfg.get('multiplier'),
                backtest_cfg.get('multiplier'),
                backtest_cfg.get('mult'),
                default=1.0,
            )
        return _first_number(
            meta.get('multiplier'),
            meta.get('mult'),
            meta.get('contract_multiplier'),
            meta.get('contract_size'),
            meta.get('trade_contract_size'),
            meta.get('contract_notional_value'),
            meta.get('okx_contract_value'),
            meta.get('ctVal'),
            meta.get('ctMult'),
            meta.get('VolumeMultiple'),
            meta.get('CONTRACT_MULTIPLIER'),
            simulate_cfg.get('multiplier'),
            backtest_cfg.get('multiplier'),
            backtest_cfg.get('mult'),
            default=1.0,
        )


    def _apply_commission_info(cerebro, config: dict, data_name: str) -> None:
        simulate_cfg = _as_dict(config.get('simulate'))
        backtest_cfg = _as_dict(config.get('backtest'))
        data_cfg = _as_dict(config.get('data'))
        asset_type = str(
            data_cfg.get('asset_type')
            or data_cfg.get('data_type')
            or _as_dict(config.get('workspace_unit')).get('asset_type')
            or ''
        ).strip().lower()
        meta = _contract_metadata_for(config, data_name)
        inverse_contract = _is_inverse_contract(meta)
        multiplier = _contract_multiplier(meta, simulate_cfg, backtest_cfg, inverse_contract)
        margin_value = _first_number(
            meta.get('margin'),
            meta.get('margin_rate'),
            meta.get('margin_ratio'),
            meta.get('long_margin_rate'),
            meta.get('LongMarginRatioByMoney'),
            meta.get('MARGIN_BUY'),
            backtest_cfg.get('margin'),
        )
        margin_amount = _first_number(
            meta.get('margin_amount'),
            meta.get('initial_margin_per_lot'),
            meta.get('margin_initial'),
            meta.get('initial_margin_amount'),
            meta.get('SYMBOL_MARGIN_INITIAL'),
        )
        leverage = _first_number(meta.get('leverage'), meta.get('lever'), meta.get('max_leverage'))
        margin_rate = 1.0 / leverage if leverage and leverage > 0 else _normalise_rate(margin_value, 1.0)
        margin_amount_param = max(margin_amount, 0.0) if margin_amount and margin_amount > 0 else None
        default_commission = _safe_float(backtest_cfg.get('commission'), 0.001)
        fixed_commission = _commission_amount(meta)
        derivative_like = bool(meta) or asset_type in {
            'future',
            'futures',
            'option',
            'options',
            'forex',
            'fx',
            'otc',
            'cfd',
            'swap',
            'swaps',
            'perpetual',
            'perp',
        }
        if derivative_like:
            explicit_rate = _explicit_commission_rate(meta)
            maker_rate = _signed_commission_rate(meta, 'maker_commission_rate', 'maker_fee_rate')
            taker_rate = _signed_commission_rate(meta, 'taker_commission_rate', 'taker_fee_rate')
            if explicit_rate is None:
                explicit_rate = taker_rate if taker_rate is not None else maker_rate
            close_rate = _commission_rate_from_keys(
                meta,
                (
                    'close_commission_rate',
                    'close_fee_rate',
                    'CloseRatioByMoney',
                    'CLOSE_FEE_RATE',
                    'COMMISSION_CLOSE_RATIO',
                ),
            )
            close_today_rate = _commission_rate_from_keys(
                meta,
                (
                    'close_today_commission_rate',
                    'close_today_fee_rate',
                    'CloseTodayRatioByMoney',
                    'CLOSETODAY_FEE_RATE',
                    'CLOSE_TODAY_FEE_RATE',
                    'COMMISSION_CLOSE_TODAY_RATIO',
                ),
            )
            close_yesterday_rate = _commission_rate_from_keys(
                meta,
                (
                    'close_yesterday_commission_rate',
                    'close_yesterday_fee_rate',
                    'CloseYesterdayRatioByMoney',
                    'CLOSEYESTERDAY_FEE_RATE',
                    'CLOSE_YESTERDAY_FEE_RATE',
                    'COMMISSION_CLOSE_YESTERDAY_RATIO',
                ),
            )
            close_amount = _commission_amount_from_keys(
                meta,
                (
                    'close_commission_amount',
                    'close_fee_amount',
                    'CloseRatioByVolume',
                    'CLOSE_FEE_AMOUNT',
                    'CLOSE_FEE_PER_LOT',
                    'COMMISSION_CLOSE_AMOUNT',
                ),
            )
            close_today_amount = _commission_amount_from_keys(
                meta,
                (
                    'close_today_commission_amount',
                    'close_today_fee_amount',
                    'CloseTodayRatioByVolume',
                    'CLOSETODAY_FEE_AMOUNT',
                    'CLOSE_TODAY_FEE_AMOUNT',
                    'CLOSE_TODAY_FEE_PER_LOT',
                    'COMMISSION_CLOSE_TODAY_AMOUNT',
                ),
            )
            close_yesterday_amount = _commission_amount_from_keys(
                meta,
                (
                    'close_yesterday_commission_amount',
                    'close_yesterday_fee_amount',
                    'CloseYesterdayRatioByVolume',
                    'CLOSEYESTERDAY_FEE_AMOUNT',
                    'CLOSE_YESTERDAY_FEE_AMOUNT',
                    'CLOSE_YESTERDAY_FEE_PER_LOT',
                    'COMMISSION_CLOSE_YESTERDAY_AMOUNT',
                ),
            )
            if inverse_contract:
                inverse_percent_rate = (
                    explicit_rate
                    if explicit_rate is not None
                    else (0.0 if fixed_commission is not None else default_commission)
                )
                comminfo = ComminfoFuturesInverse(
                    commission=inverse_percent_rate,
                    open_commission=explicit_rate,
                    close_commission=close_rate,
                    close_today_commission=close_today_rate,
                    close_yesterday_commission=close_yesterday_rate,
                    maker_commission=maker_rate,
                    taker_commission=taker_rate,
                    commission_amount=max(fixed_commission or 0.0, 0.0),
                    open_commission_amount=max(fixed_commission, 0.0) if fixed_commission is not None else None,
                    close_commission_amount=close_amount,
                    close_today_commission_amount=close_today_amount,
                    close_yesterday_commission_amount=close_yesterday_amount,
                    margin=max(margin_rate, 0.0),
                    margin_amount=margin_amount_param,
                    mult=max(multiplier or 1.0, 1e-12),
                )
                cerebro.broker.addcommissioninfo(comminfo, name=data_name)
                return
            if (
                fixed_commission is not None
                and explicit_rate is not None
                and str(meta.get('commission_method') or '').lower() != 'fixed_per_lot'
            ):
                comminfo = ComminfoFuturesMixed(
                    commission=max(explicit_rate, 0.0),
                    open_commission=max(explicit_rate, 0.0),
                    close_commission=close_rate,
                    close_today_commission=close_today_rate,
                    close_yesterday_commission=close_yesterday_rate,
                    maker_commission=maker_rate,
                    taker_commission=taker_rate,
                    commission_amount=max(fixed_commission, 0.0),
                    open_commission_amount=max(fixed_commission, 0.0),
                    close_commission_amount=close_amount,
                    close_today_commission_amount=close_today_amount,
                    close_yesterday_commission_amount=close_yesterday_amount,
                    margin=max(margin_rate, 0.0),
                    margin_amount=margin_amount_param,
                    mult=max(multiplier or 1.0, 1e-12),
                )
            elif fixed_commission is not None and (
                str(meta.get('commission_method') or '').lower() == 'fixed_per_lot'
                or explicit_rate is None
            ):
                comminfo = ComminfoFuturesFixed(
                    commission=max(fixed_commission, 0.0),
                    open_commission=max(fixed_commission, 0.0),
                    close_commission=close_amount,
                    close_today_commission=close_today_amount,
                    close_yesterday_commission=close_yesterday_amount,
                    margin=max(margin_rate, 0.0),
                    margin_amount=margin_amount_param,
                    mult=max(multiplier or 1.0, 1e-12),
                )
            else:
                comminfo = ComminfoFuturesPercent(
                    commission=explicit_rate if explicit_rate is not None else default_commission,
                    open_commission=explicit_rate if explicit_rate is not None else default_commission,
                    close_commission=close_rate,
                    close_today_commission=close_today_rate,
                    close_yesterday_commission=close_yesterday_rate,
                    maker_commission=maker_rate,
                    taker_commission=taker_rate,
                    margin=max(margin_rate, 0.0),
                    margin_amount=margin_amount_param,
                    mult=max(multiplier or 1.0, 1e-12),
                )
            cerebro.broker.addcommissioninfo(comminfo, name=data_name)
        else:
            cerebro.broker.setcommission(commission=default_commission)


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
        instrument = raw
        if '.' in instrument:
            left, right = instrument.split('.', 1)
            instrument = right if left.upper() in {'SHFE', 'DCE', 'CZCE', 'CFFEX', 'INE', 'GFEX'} else left
        if '_' in instrument:
            left, right = instrument.split('_', 1)
            instrument = right if left.upper() in {'SHFE', 'DCE', 'CZCE', 'CFFEX', 'INE', 'GFEX'} else left
        variants = [raw, instrument, raw.upper(), raw.lower(), instrument.upper(), instrument.lower()]
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


    def _symbol_product_prefix(symbol: str) -> str:
        raw = str(symbol or '').strip()
        if '.' in raw:
            left, right = raw.split('.', 1)
            raw = right if left.upper() in {'SHFE', 'DCE', 'CZCE', 'CFFEX', 'INE', 'GFEX'} else left
        if '_' in raw:
            left, right = raw.split('_', 1)
            raw = right if left.upper() in {'SHFE', 'DCE', 'CZCE', 'CFFEX', 'INE', 'GFEX'} else left
        letters = []
        for ch in raw:
            if ch.isalpha():
                letters.append(ch)
            elif letters:
                break
        return ''.join(letters).upper()


    def _candidate_patterns(symbol: str, suffix: str) -> list[str]:
        raw = str(symbol or '').strip()
        prefix = _symbol_product_prefix(raw)
        base_patterns = [f'{raw}_*.csv', f'{raw.upper()}_*.csv', f'{raw.lower()}_*.csv']
        if not prefix:
            return base_patterns
        prefix_patterns = []
        if suffix:
            prefix_patterns.extend([
                f'{prefix}[0-9]*_{suffix}.csv',
                f'{prefix.lower()}[0-9]*_{suffix}.csv',
                f'{prefix}*_{suffix}.csv',
                f'{prefix.lower()}*_{suffix}.csv',
            ])
        prefix_patterns.extend([
            f'{prefix}[0-9]*.csv',
            f'{prefix.lower()}[0-9]*.csv',
            f'{prefix}*.csv',
            f'{prefix.lower()}*.csv',
        ])
        patterns = prefix_patterns + base_patterns
        unique: list[str] = []
        seen: set[str] = set()
        for pattern in patterns:
            if pattern not in seen:
                unique.append(pattern)
                seen.add(pattern)
        return unique


    def _pick_matching_csv(matches: list[Path], suffix: str) -> Path | None:
        if not matches:
            return None
        ordered = sorted(matches)
        suffix_lower = str(suffix or '').lower()
        if suffix_lower:
            for match in ordered:
                if suffix_lower in match.name.lower() or match.parent.name.lower() == suffix_lower:
                    return match
        return ordered[0]


    def resolve_data_file(config: dict) -> Path:
        data = config.get('data') or {}
        raw_directory = str(data.get('directory_path') or '').strip()
        if not raw_directory:
            raw_directory = os.environ.get('BACKTRADER_DATA_DIR', '').strip()
        directory_path = Path(raw_directory or '.').expanduser()
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
            for pattern in _candidate_patterns(symbol, suffix):
                match = _pick_matching_csv(list(root.glob(pattern)), suffix)
                if match is not None:
                    return match
        for pattern in _candidate_patterns(symbol, suffix):
            match = _pick_matching_csv(list(directory_path.rglob(pattern)), suffix)
            if match is not None:
                return match
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
            if isinstance(value, type) and issubclass(value, _PANDAS_DATA_CLASS) and value is not _PANDAS_DATA_CLASS:
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
        params = config.get('params') or {}
        live_cfg = config.get('live') or {}
        simulate_cfg = config.get('simulate') or {}
        cerebro = bt.Cerebro(
            stdstats=_safe_bool(live_cfg.get('stdstats', simulate_cfg.get('stdstats')), False)
        )
        name = str(data_cfg.get('symbol') or 'DATA')
        cerebro.adddata(feed_class(dataname=df), name=name)
        _apply_commission_info(cerebro, config, name)
        backtest_cfg = config.get('backtest') or {}
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
        logger.info('Loading data from %s', csv_path)
        results = cerebro.run()
        final_value = cerebro.broker.getvalue()
        logger.info('Final value: %s', final_value)
        keepalive_seconds = _keepalive_seconds(config)
        if keepalive_seconds > 0:
            deadline = time.monotonic() + keepalive_seconds
            logger.info('Keeping local paper runtime alive for %.1fs', keepalive_seconds)
            while time.monotonic() < deadline:
                time.sleep(min(5.0, max(deadline - time.monotonic(), 0.1)))
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


def _asset_type_alias(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    lowered = text.lower()
    return _ASSET_TYPE_ALIASES.get(text) or _ASSET_TYPE_ALIASES.get(lowered)


def _asset_type_from_symbol(symbol: Any) -> str | None:
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return None
    if normalized.endswith((".SZ", ".SH", ".BJ", ".HK", ".US")):
        return "stock"
    futures_suffixes = (".CFE", ".CFFEX", ".SHFE", ".INE", ".DCE", ".CZCE", ".GFEX")
    futures_prefixes = (
        "IF",
        "IC",
        "IH",
        "IM",
        "TF",
        "TS",
        "AU",
        "AG",
        "CU",
        "AL",
        "ZN",
        "RB",
        "HC",
        "SC",
        "FU",
        "RU",
        "MA",
        "TA",
        "SA",
        "SR",
        "CF",
        "OI",
        "RM",
        "FG",
        "JM",
        "J",
        "I",
        "M",
        "Y",
        "P",
        "A",
        "B",
        "C",
        "CS",
        "L",
        "V",
        "PP",
        "EB",
        "EG",
        "PG",
        "AP",
    )
    if normalized.endswith(futures_suffixes):
        return "future"
    if any(
        normalized.startswith(prefix)
        and any(ch.isdigit() for ch in normalized[len(prefix) :])
        for prefix in futures_prefixes
    ):
        return "future"
    return None


def _asset_type_for_unit_config(
    *,
    category: Any,
    symbol: Any,
    data_config: dict[str, Any] | None,
    unit_settings: dict[str, Any] | None,
    template_data: dict[str, Any] | None = None,
) -> str:
    data_cfg = dict(data_config or {})
    settings = dict(unit_settings or {})
    template = dict(template_data or {})
    for value in (
        data_cfg.get("asset_type"),
        data_cfg.get("data_type"),
        settings.get("asset_type"),
        settings.get("data_type"),
        category,
        template.get("asset_type"),
        template.get("data_type"),
    ):
        alias = _asset_type_alias(value)
        if alias:
            return alias
    return _asset_type_from_symbol(symbol or data_cfg.get("symbol") or template.get("symbol")) or "future"


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
    if not template_dir.is_dir():
        # Template tree may be absent (see _sync_trading_runtime_sources).
        # Return empty so config generation degrades gracefully instead of
        # raising and 500-ing unit creation.
        return ""
    candidates = sorted(template_dir.glob("strategy_*.py"))
    if not candidates:
        return ""
    return candidates[0].name


def _default_unit_start_date_iso() -> str:
    return _DEFAULT_UNIT_START_DATE.isoformat()


def _default_unit_end_date_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _default_csv_directory_path() -> str:
    return str((Path(__file__).resolve().parents[4] / "data" / "datas").resolve())


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
    template_data = dict(template_config.get("data") or {})
    data_config = _normalize_unit_data_config(unit.data_config)
    category = unit.category or str(template_data.get("data_type") or "")
    asset_type = _asset_type_for_unit_config(
        category=category,
        symbol=unit.symbol,
        data_config=data_config,
        unit_settings=unit_settings,
        template_data=template_data,
    )
    data_source = dict(workspace_settings.get("data_source") or {})
    csv_section = dict(data_source.get("csv") or {})
    data_root = str(csv_section.get("directory_path") or "").strip()
    if not data_root:
        data_root = _default_csv_directory_path()
    asset_root = str((Path(data_root) / asset_type).resolve()) if data_root else ""
    data_section = template_data
    data_section.update(data_config)
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


def _is_sensitive_config_key(key: Any) -> bool:
    normalized = str(key or "").strip().lower().replace("-", "_")
    return normalized in _SENSITIVE_CONFIG_KEYS


def _strip_sensitive_config_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_sensitive_config_values(item)
            for key, item in value.items()
            if not _is_sensitive_config_key(key)
        }
    if isinstance(value, list):
        return [_strip_sensitive_config_values(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_strip_sensitive_config_values(item) for item in value)
    return deepcopy(value)


def _apply_gateway_runtime_config(
    template_config: dict[str, Any],
    gateway_config: dict[str, Any] | None,
) -> None:
    params = _strip_sensitive_config_values(
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
    data_config = _normalize_unit_data_config(unit.data_config)
    data_section.update(data_config)
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
    unit_settings = dict(unit.unit_settings or {})
    asset_type = _asset_type_for_unit_config(
        category=unit.category or str(data_section.get("data_type") or data_section.get("asset_type") or ""),
        symbol=unit.symbol or data_section.get("symbol"),
        data_config=data_config,
        unit_settings=unit_settings,
        template_data=data_section,
    )
    exchange_type = _trading_exchange_for_unit(unit, asset_type, data_section)
    data_section["asset_type"] = asset_type
    data_section["data_type"] = _trading_data_type_for_asset(asset_type)
    data_section["exchange"] = exchange_type
    data_source = dict((workspace_settings or {}).get("data_source") or {})
    csv_section = dict(data_source.get("csv") or {})
    data_root = str(csv_section.get("directory_path") or "").strip()
    if data_root and not str(data_section.get("directory_path") or "").strip():
        data_section["directory_path"] = str((Path(data_root) / asset_type).resolve())
    template_config["data"] = data_section

    simulate_section = dict(template_config.get("simulate") or {})
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
    live_qcheck = live_section.get("qcheck")
    for key in ("qcheck", "live_qcheck", "qcheck_seconds"):
        if unit_settings.get(key) is not None:
            live_qcheck = unit_settings[key]
            break
    live_section["qcheck"] = _positive_float(live_qcheck, _DEFAULT_LIVE_QCHECK_SECONDS)
    live_log_ticks = live_section.get("log_ticks")
    for key in ("log_ticks", "live_log_ticks"):
        if unit_settings.get(key) is not None:
            live_log_ticks = unit_settings[key]
            break
    live_section["log_ticks"] = _bool_value(live_log_ticks, False)
    live_log_positions = live_section.get("log_positions")
    for key in ("log_positions", "live_log_positions"):
        if unit_settings.get(key) is not None:
            live_log_positions = unit_settings[key]
            break
    live_section["log_positions"] = _bool_value(live_log_positions, True)
    live_log_indicators = live_section.get("log_indicators")
    for key in ("log_indicators", "live_log_indicators"):
        if unit_settings.get(key) is not None:
            live_log_indicators = unit_settings[key]
            break
    live_section["log_indicators"] = _bool_value(live_log_indicators, False)
    live_log_signals = live_section.get("log_signals")
    for key in ("log_signals", "live_log_signals"):
        if unit_settings.get(key) is not None:
            live_log_signals = unit_settings[key]
            break
    live_section["log_signals"] = _bool_value(live_log_signals, True)
    live_dispatch_ticks = live_section.get("dispatch_ticks")
    for key in ("dispatch_ticks", "notify_ticks", "live_dispatch_ticks", "live_notify_ticks"):
        if unit_settings.get(key) is not None:
            live_dispatch_ticks = unit_settings[key]
            break
    live_section["dispatch_ticks"] = _bool_value(live_dispatch_ticks, False)
    live_exactbars = live_section.get("exactbars")
    for key in ("exactbars", "live_exactbars"):
        if unit_settings.get(key) is not None:
            live_exactbars = unit_settings[key]
            break
    live_section["exactbars"] = _exactbars_value(live_exactbars, True)
    live_stdstats = live_section.get("stdstats")
    for key in ("stdstats", "live_stdstats"):
        if unit_settings.get(key) is not None:
            live_stdstats = unit_settings[key]
            break
    live_section["stdstats"] = _bool_value(live_stdstats, False)
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
    if not template_dir.is_dir():
        # The strategy template tree (src/strategies/) is developer-local and
        # not always present (e.g. fresh checkout, CI). Unit creation has
        # already persisted the unit; a missing template must not abort the
        # request with a 500. Skip copying and let the runtime fall back to
        # defaults — the unit can be re-synced once the template is available.
        logger.warning(
            "Strategy template dir not found, skipping runtime source sync: %s",
            template_dir,
        )
        return
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
    template_has_run_py = (template_dir / "run.py").is_file()
    _sync_trading_runtime_sources(template_dir, target_dir)
    if not template_has_run_py:
        (target_dir / "run.py").write_text(_UNIT_RUN_PY, encoding="utf-8")
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
