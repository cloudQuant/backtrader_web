#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Unified gateway-backed paper trading runner."""

from __future__ import absolute_import, division, print_function, unicode_literals

import importlib.util
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path


def _find_bt_web_root(path: Path) -> Path:
    for candidate in (path.parent, *path.parents):
        if (candidate / "src" / "backend").exists() and (candidate / "strategies").exists():
            return candidate
    return path.parents[3]


def _path_is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _prefer_local_backtrader(project_path: Path) -> None:
    module = sys.modules.get("backtrader")
    module_file = getattr(module, "__file__", None) if module is not None else None
    if module is None or (module_file and _path_is_relative_to(Path(module_file), project_path)):
        return
    for name in list(sys.modules):
        if name == "backtrader" or name.startswith("backtrader."):
            sys.modules.pop(name, None)


_BT_WEB = _find_bt_web_root(Path(__file__).resolve())
_BT_PROJECT = _BT_WEB.parent / "backtrader"
if _BT_PROJECT.exists() and str(_BT_PROJECT) not in sys.path:
    sys.path.insert(0, str(_BT_PROJECT))
if _BT_PROJECT.exists():
    _prefer_local_backtrader(_BT_PROJECT)
_BT_API_PY = _BT_WEB.parent / "bt_api_py"
if _BT_API_PY.exists() and str(_BT_API_PY) not in sys.path:
    sys.path.insert(0, str(_BT_API_PY))
_PYMT5 = _BT_WEB.parent / "pymt5"
if _PYMT5.exists() and str(_PYMT5) not in sys.path:
    sys.path.insert(0, str(_PYMT5))
_BACKEND_SRC = _BT_WEB / "src" / "backend"
if _BACKEND_SRC.exists() and str(_BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(_BACKEND_SRC))

import backtrader as bt  # noqa: E402
import yaml  # noqa: E402
from app.utils.backtrader_commission import (  # noqa: E402
    ComminfoFuturesFixed,
    ComminfoFuturesInverse,
    ComminfoFuturesMixed,
    ComminfoFuturesPercent,
)
try:
    from backtrader.feeds.btapifeed import BtApiFeed  # noqa: E402
    from backtrader.stores.btapistore import BtApiStore  # noqa: E402
except ImportError:  # Public Backtrader lacks the optional gateway adapter.
    BtApiFeed = None
    BtApiStore = None

BASE_DIR = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)
HEARTBEAT_FILE_NAME = "heartbeat.json"
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 30.0


def _safe_bool(value, default=False):
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off", ""}


def _load_dotenv() -> None:
    for candidate in (BASE_DIR / ".env", _BT_WEB / ".env", _BT_WEB.parent / ".env"):
        if not candidate.is_file():
            continue
        try:
            with candidate.open("r", encoding="utf-8") as handle:
                for line in handle:
                    text = line.strip()
                    if not text or text.startswith("#") or "=" not in text:
                        continue
                    key, _, value = text.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = value
        except OSError as exc:
            logger.warning("Could not read %s: %s", candidate, exc)


def load_config() -> dict:
    config_path = BASE_DIR / "config.yaml"
    if not config_path.exists():
        raise SystemExit("config.yaml 不存在。")
    with config_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _safe_int(value, default=0):
    try:
        return int(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _safe_float(value, default=0.0):
    try:
        return float(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _first_number(*values, default=None):
    for value in values:
        if value in (None, ""):
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


def _as_dict(value):
    return dict(value) if isinstance(value, dict) else {}


def _symbol_keys(symbol: str) -> list[str]:
    raw = str(symbol or "").strip()
    exchanges = {"SHFE", "DCE", "CZCE", "CFFEX", "INE", "GFEX"}
    instrument = raw
    exchange = ""
    if "." in raw:
        left, right = raw.split(".", 1)
        left = left.strip()
        right = right.strip()
        if left.upper() in exchanges:
            instrument, exchange = right, left.upper()
        elif right.upper() in exchanges:
            instrument, exchange = left, right.upper()
        else:
            instrument = left
    if "_" in raw:
        left, right = raw.split("_", 1)
        left = left.strip()
        right = right.strip()
        if left.upper() in exchanges:
            instrument, exchange = right, left.upper()
        elif right.upper() in exchanges:
            instrument, exchange = left, right.upper()
    keys = [raw, instrument, instrument.upper(), instrument.lower()]
    if exchange and instrument:
        keys.extend(
            [
                f"{exchange}.{instrument}",
                f"{instrument}.{exchange}",
                f"{exchange}_{instrument}",
                f"{instrument}_{exchange}",
            ]
        )
    result: list[str] = []
    seen: set[str] = set()
    for key in keys:
        if key and key not in seen:
            result.append(key)
            seen.add(key)
    return result


def _contract_metadata_for(config: dict, symbol: str) -> dict:
    for source in (
        config,
        _as_dict(config.get("params")),
        _as_dict(config.get("live")),
        _as_dict(config.get("simulate")),
        _as_dict(config.get("data")),
        _as_dict(config.get("backtest")),
    ):
        for container_key in ("contract_metadata", "contracts", "contract_specs", "instrument_specs"):
            container = source.get(container_key)
            if not isinstance(container, dict):
                continue
            for key in _symbol_keys(symbol):
                item = container.get(key)
                if isinstance(item, dict):
                    return dict(item)
    return {}


def _commission_rate_from_keys(meta: dict, *keys):
    method = str(meta.get("commission_method") or "").strip().lower()
    ratio_10k_keys = {
        "OpenRatioByMoney",
        "CloseRatioByMoney",
        "CloseTodayRatioByMoney",
        "CloseYesterdayRatioByMoney",
        "COMMISSION_OPEN_RATIO",
        "COMMISSION_CLOSE_RATIO",
        "COMMISSION_CLOSE_TODAY_RATIO",
        "COMMISSION_CLOSE_YESTERDAY_RATIO",
    }
    for key in keys:
        value = _first_number(meta.get(key))
        if value is None:
            continue
        if method == "percent_10k" or key in ratio_10k_keys or (
            key.endswith("RatioByMoney") and value > 0.01
        ):
            value = max(value, 0.0)
            return value / 10000.0 if value > 0.01 else value
        return _normalise_rate(value, 0.0)
    return None


def _explicit_commission_rate(meta: dict):
    return _commission_rate_from_keys(
        meta,
        "commission",
        "commission_rate",
        "fee_rate",
        "open_fee_rate",
        "open_commission_rate",
        "OpenRatioByMoney",
        "COMMISSION_OPEN_RATIO",
    )


def _signed_commission_rate(meta: dict, *keys):
    for key in keys:
        value = _normalise_signed_rate(meta.get(key))
        if value is not None:
            return value
    return None


def _commission_amount_from_keys(meta: dict, *keys):
    for key in keys:
        value = _first_number(meta.get(key))
        if value is not None:
            return value
    return None


def _commission_amount(meta: dict):
    return _commission_amount_from_keys(
        meta,
        "commission_amount",
        "fee_amount",
        "commission_per_lot",
        "open_fee_amount",
        "open_commission_amount",
        "OpenRatioByVolume",
        "COMMISSION_OPEN_AMOUNT",
    )


def _text(value) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _currency_code(value) -> str:
    return "".join(ch for ch in str(value or "").strip().upper() if ch.isalnum())


def _is_inverse_contract(meta: dict) -> bool:
    explicit = _text(
        meta.get("inverse")
        or meta.get("is_inverse")
        or meta.get("isInverse")
        or meta.get("inverse_contract")
        or meta.get("inverseContract")
    )
    if explicit in {"1", "true", "yes", "y", "inverse"}:
        return True
    if explicit in {"0", "false", "no", "n", "linear"}:
        return False

    contract_type = _text(
        meta.get("contract_type")
        or meta.get("contractType")
        or meta.get("ctType")
        or meta.get("type")
    )
    if "inverse" in contract_type or "coin_margined" in contract_type:
        return True
    if "linear" in contract_type or "usdt_margined" in contract_type or "usdc_margined" in contract_type:
        return False

    contract_ccy = _currency_code(
        meta.get("contract_value_currency")
        or meta.get("contractValueCurrency")
        or meta.get("contract_value_ccy")
        or meta.get("ctValCcy")
    )
    base_ccy = _currency_code(
        meta.get("base_currency") or meta.get("baseCurrency") or meta.get("base_asset") or meta.get("baseCcy")
    )
    quote_ccy = _currency_code(
        meta.get("quote_currency") or meta.get("quoteCurrency") or meta.get("quote_asset") or meta.get("quoteCcy")
    )
    settle_ccy = _currency_code(
        meta.get("settle_currency")
        or meta.get("settleCurrency")
        or meta.get("settle_ccy")
        or meta.get("settleCcy")
        or meta.get("margin_currency")
        or meta.get("marginCcy")
    )
    fee_ccy = _currency_code(meta.get("fee_currency") or meta.get("feeCurrency") or meta.get("feeCcy"))
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
            meta.get("contract_value"),
            meta.get("contractValue"),
            meta.get("contract_value_amount"),
            meta.get("contractValueAmount"),
            meta.get("contract_notional_value"),
            meta.get("okx_contract_value"),
            meta.get("ctVal"),
            meta.get("multiplier"),
            meta.get("mult"),
            meta.get("contract_multiplier"),
            meta.get("contract_size"),
            meta.get("trade_contract_size"),
            meta.get("ctMult"),
            meta.get("VolumeMultiple"),
            meta.get("CONTRACT_MULTIPLIER"),
            simulate_cfg.get("multiplier"),
            backtest_cfg.get("multiplier"),
            backtest_cfg.get("mult"),
            default=1.0,
        )
    return _first_number(
        meta.get("multiplier"),
        meta.get("mult"),
        meta.get("contract_multiplier"),
        meta.get("contract_size"),
        meta.get("trade_contract_size"),
        meta.get("contract_notional_value"),
        meta.get("okx_contract_value"),
        meta.get("ctVal"),
        meta.get("ctMult"),
        meta.get("VolumeMultiple"),
        meta.get("CONTRACT_MULTIPLIER"),
        simulate_cfg.get("multiplier"),
        backtest_cfg.get("multiplier"),
        backtest_cfg.get("mult"),
        default=1.0,
    )


def _apply_contract_commission(cerebro, config: dict, data_name: str) -> None:
    simulate_cfg = _as_dict(config.get("simulate"))
    backtest_cfg = _as_dict(config.get("backtest"))
    data_cfg = _as_dict(config.get("data"))
    asset_type = str(data_cfg.get("asset_type") or data_cfg.get("data_type") or "").strip().lower()
    meta = _contract_metadata_for(config, data_name)
    inverse_contract = _is_inverse_contract(meta)
    multiplier = _contract_multiplier(meta, simulate_cfg, backtest_cfg, inverse_contract)
    margin_value = _first_number(
        meta.get("margin"),
        meta.get("margin_rate"),
        meta.get("margin_ratio"),
        meta.get("long_margin_rate"),
        meta.get("LongMarginRatioByMoney"),
        meta.get("MARGIN_BUY"),
        simulate_cfg.get("margin"),
        backtest_cfg.get("margin"),
    )
    margin_amount = _first_number(
        meta.get("margin_amount"),
        meta.get("initial_margin_per_lot"),
        meta.get("margin_initial"),
        meta.get("initial_margin_amount"),
        meta.get("SYMBOL_MARGIN_INITIAL"),
    )
    leverage = _first_number(meta.get("leverage"))
    margin_rate = 1.0 / leverage if leverage and leverage > 0 else _normalise_rate(margin_value, 1.0)
    margin_amount_param = max(margin_amount, 0.0) if margin_amount and margin_amount > 0 else None
    default_commission = _safe_float(
        simulate_cfg.get("commission"),
        _safe_float(backtest_cfg.get("commission"), 0.0005),
    )
    commission_rate = _explicit_commission_rate(meta)
    close_commission_rate = _commission_rate_from_keys(
        meta,
        "close_fee_rate",
        "close_commission_rate",
        "CloseRatioByMoney",
        "COMMISSION_CLOSE_RATIO",
    )
    close_today_commission_rate = _commission_rate_from_keys(
        meta,
        "close_today_fee_rate",
        "close_today_commission_rate",
        "CloseTodayRatioByMoney",
        "COMMISSION_CLOSE_TODAY_RATIO",
    )
    close_yesterday_commission_rate = _commission_rate_from_keys(
        meta,
        "close_yesterday_fee_rate",
        "close_yesterday_commission_rate",
        "CloseYesterdayRatioByMoney",
        "COMMISSION_CLOSE_YESTERDAY_RATIO",
    )
    maker_commission_rate = _signed_commission_rate(
        meta,
        "maker_commission_rate",
        "maker_fee_rate",
    )
    taker_commission_rate = _signed_commission_rate(
        meta,
        "taker_commission_rate",
        "taker_fee_rate",
    )
    if commission_rate is None:
        commission_rate = (
            taker_commission_rate
            if taker_commission_rate is not None
            else maker_commission_rate
        )
    fixed_commission = _commission_amount(meta)
    close_fixed_commission = _commission_amount_from_keys(
        meta,
        "close_fee_amount",
        "close_commission_amount",
        "CloseRatioByVolume",
        "COMMISSION_CLOSE_AMOUNT",
    )
    close_today_fixed_commission = _commission_amount_from_keys(
        meta,
        "close_today_fee_amount",
        "close_today_commission_amount",
        "CloseTodayRatioByVolume",
        "COMMISSION_CLOSE_TODAY_AMOUNT",
    )
    close_yesterday_fixed_commission = _commission_amount_from_keys(
        meta,
        "close_yesterday_fee_amount",
        "close_yesterday_commission_amount",
        "CloseYesterdayRatioByVolume",
        "COMMISSION_CLOSE_YESTERDAY_AMOUNT",
    )
    percent_role_kwargs = {
        "open_commission": max(commission_rate, 0.0) if commission_rate is not None else None,
        "close_commission": close_commission_rate,
        "close_today_commission": close_today_commission_rate,
        "close_yesterday_commission": close_yesterday_commission_rate,
        "maker_commission": maker_commission_rate,
        "taker_commission": taker_commission_rate,
    }
    percent_role_kwargs = {
        key: value for key, value in percent_role_kwargs.items() if value is not None
    }
    fixed_role_kwargs = {
        "open_commission": max(fixed_commission, 0.0)
        if fixed_commission is not None
        else None,
        "close_commission": close_fixed_commission,
        "close_today_commission": close_today_fixed_commission,
        "close_yesterday_commission": close_yesterday_fixed_commission,
    }
    fixed_role_kwargs = {
        key: max(value, 0.0) for key, value in fixed_role_kwargs.items() if value is not None
    }
    mixed_amount_kwargs = {
        "open_commission_amount": max(fixed_commission, 0.0)
        if fixed_commission is not None
        else None,
        "close_commission_amount": close_fixed_commission,
        "close_today_commission_amount": close_today_fixed_commission,
        "close_yesterday_commission_amount": close_yesterday_fixed_commission,
    }
    mixed_amount_kwargs = {
        key: max(value, 0.0) for key, value in mixed_amount_kwargs.items() if value is not None
    }
    derivative_like = bool(meta) or asset_type in {
        "future",
        "futures",
        "option",
        "options",
        "forex",
        "fx",
        "otc",
        "cfd",
        "swap",
        "swaps",
        "perpetual",
        "perp",
    }
    if not derivative_like:
        cerebro.broker.setcommission(commission=default_commission)
        return

    if inverse_contract:
        inverse_percent_rate = (
            commission_rate
            if commission_rate is not None
            else (0.0 if fixed_commission is not None else default_commission)
        )
        comminfo = ComminfoFuturesInverse(
            commission=inverse_percent_rate,
            commission_amount=max(fixed_commission or 0.0, 0.0),
            margin=max(margin_rate, 0.0),
            margin_amount=margin_amount_param,
            mult=max(multiplier or 1.0, 1e-12),
            **percent_role_kwargs,
            **mixed_amount_kwargs,
        )
        cerebro.broker.addcommissioninfo(comminfo, name=data_name)
        return

    if (
        fixed_commission is not None
        and commission_rate is not None
        and str(meta.get("commission_method") or "").lower() != "fixed_per_lot"
    ):
        comminfo = ComminfoFuturesMixed(
            commission=max(commission_rate, 0.0),
            commission_amount=max(fixed_commission, 0.0),
            margin=max(margin_rate, 0.0),
            margin_amount=margin_amount_param,
            mult=max(multiplier or 1.0, 1e-12),
            **percent_role_kwargs,
            **mixed_amount_kwargs,
        )
    elif fixed_commission is not None and (
        str(meta.get("commission_method") or "").lower() == "fixed_per_lot"
        or commission_rate is None
    ):
        comminfo = ComminfoFuturesFixed(
            commission=max(fixed_commission, 0.0),
            margin=max(margin_rate, 0.0),
            margin_amount=margin_amount_param,
            mult=max(multiplier or 1.0, 1e-12),
            **fixed_role_kwargs,
        )
    else:
        comminfo = ComminfoFuturesPercent(
            commission=commission_rate if commission_rate is not None else default_commission,
            margin=max(margin_rate, 0.0),
            margin_amount=margin_amount_param,
            mult=max(multiplier or 1.0, 1e-12),
            **percent_role_kwargs,
        )
    cerebro.broker.addcommissioninfo(comminfo, name=data_name)


def _resolve_heartbeat_interval(config: dict) -> float:
    live = dict(config.get("live") or {})
    simulate = dict(config.get("simulate") or {})
    logging_cfg = dict(config.get("logging") or {})
    gateway = dict(config.get("gateway") or {})
    for section in (live, simulate, logging_cfg, gateway):
        for key in ("heartbeat_interval_seconds", "heartbeat_interval"):
            if key in section:
                return max(_safe_float(section.get(key), DEFAULT_HEARTBEAT_INTERVAL_SECONDS), 1.0)
    return DEFAULT_HEARTBEAT_INTERVAL_SECONDS


def _write_runner_heartbeat(log_dir: Path, started_at: float, status: str = "running") -> None:
    heartbeat_path = log_dir / HEARTBEAT_FILE_NAME
    tmp_path = log_dir / f".{HEARTBEAT_FILE_NAME}.{os.getpid()}.tmp"
    payload = {
        "pid": os.getpid(),
        "status": status,
        "timestamp": time.time(),
        "started_at": started_at,
    }
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=True, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_path, heartbeat_path)
    except OSError as exc:
        logger.debug("Could not write runner heartbeat: %s", exc)
        try:
            tmp_path.unlink()
        except OSError:
            pass


def _start_runner_heartbeat(
    log_dir: Path,
    interval_seconds: float = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
) -> tuple[threading.Event, threading.Thread]:
    try:
        interval = float(interval_seconds)
    except (TypeError, ValueError):
        interval = DEFAULT_HEARTBEAT_INTERVAL_SECONDS
    interval = max(interval, 0.05)
    stop_event = threading.Event()
    started_at = time.time()

    def _loop() -> None:
        while not stop_event.is_set():
            _write_runner_heartbeat(log_dir, started_at, "running")
            stop_event.wait(interval)
        _write_runner_heartbeat(log_dir, started_at, "stopped")

    thread = threading.Thread(target=_loop, name="runner-heartbeat", daemon=True)
    thread.start()
    return stop_event, thread


def _stop_runner_heartbeat(heartbeat: tuple[threading.Event, threading.Thread]) -> None:
    stop_event, thread = heartbeat
    stop_event.set()
    thread.join(timeout=2.0)


def _gateway_timeout_defaults(exchange_type: str) -> tuple[float, float]:
    if exchange_type == "CTP":
        return 60.0, 20.0
    if exchange_type == "IB_WEB":
        return 30.0, 10.0
    return 60.0, 30.0


def _patch_gateway_client_compat() -> None:
    try:
        from bt_api_py.gateway.client import GatewayClient
    except ImportError:
        return

    if getattr(GatewayClient, "_ai_for_investor_compat_patched", False):
        return

    def _compat_command(self, command, payload=None):
        sender = getattr(self, "_send_command", None) or getattr(self, "_command", None)
        if sender is None:
            raise AttributeError("GatewayClient has no command sender")
        return sender(command, payload or {})

    def _compat_subscribe(self, symbols):
        values = [symbols] if isinstance(symbols, str) else list(symbols or [])
        result = _compat_command(self, "subscribe", {"symbols": values})
        subscribed: list[str] = []
        if isinstance(result, dict):
            candidate = (
                result.get("subscribed")
                or result.get("symbols")
                or result.get("accepted")
                or result.get("newly_subscribed")
                or []
            )
            subscribed = [str(symbol) for symbol in candidate if str(symbol)]
            normalized = dict(result)
            if subscribed and not normalized.get("subscribed"):
                normalized["subscribed"] = list(subscribed)
            if subscribed and not normalized.get("accepted"):
                normalized["accepted"] = list(subscribed)
            result = normalized
        elif isinstance(result, (list, tuple, set)):
            subscribed = [str(symbol) for symbol in result if str(symbol)]
            result = {
                "subscribed": list(subscribed),
                "accepted": list(subscribed),
                "skipped": [],
            }
        elif result is None:
            result = {"subscribed": [], "accepted": [], "skipped": []}
        if not hasattr(self, "subscribed"):
            self.subscribed = set()
        self.subscribed.update(subscribed)
        return result

    def _compat_wait_for_adapter_ready(self) -> None:
        base_timeout = _safe_float(getattr(self.config, "startup_timeout_sec", None), 30.0)
        exchange_type = str(getattr(self.config, "exchange_type", "") or "").strip().upper()
        timeout = base_timeout
        if exchange_type == "CTP":
            timeout = max(base_timeout * 3.0 + 4.0, base_timeout + 30.0)
        logger = logging.getLogger("bt_api_py.gateway.client")
        deadline = time.monotonic() + timeout
        interval = 0.5
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                result = _compat_command(self, "ping")
                if isinstance(result, dict) and result.get("ready"):
                    logger.info("Gateway adapter ready")
                    return
            except Exception as exc:
                last_error = exc
            time.sleep(interval)
        if last_error is None:
            logger.warning(
                "Gateway adapter not ready after %.1fs — commands may fail until connected",
                timeout,
            )
        else:
            logger.warning(
                "Gateway adapter not ready after %.1fs — last error: %s: %s",
                timeout,
                type(last_error).__name__,
                last_error,
            )

    GatewayClient.subscribe = _compat_subscribe
    GatewayClient._wait_for_adapter_ready = _compat_wait_for_adapter_ready
    GatewayClient._ai_for_investor_compat_patched = True


def _resolve_provider(config: dict) -> str:
    provider = str(os.environ.get("BT_STORE_PROVIDER") or "").strip().lower()
    if provider:
        return provider
    gateway = dict(config.get("gateway") or {})
    provider = str(gateway.get("provider") or "").strip().lower()
    if provider:
        return provider
    exchange_type = str(gateway.get("exchange_type") or "").strip().upper()
    if exchange_type == "MT5":
        return "mt5_gateway"
    if exchange_type in {"IB", "IB_WEB"}:
        return "gateway"
    return "ctp_gateway"


def _resolve_exchange_type(config: dict) -> str:
    gateway = dict(config.get("gateway") or {})
    return str(
        os.environ.get("BT_GATEWAY_EXCHANGE_TYPE")
        or gateway.get("exchange_type")
        or config.get("exchange_type")
        or "CTP"
    ).strip().upper()


def _resolve_asset_type(config: dict, exchange_type: str) -> str:
    gateway = dict(config.get("gateway") or {})
    data = dict(config.get("data") or {})
    default_value = "OTC" if exchange_type == "MT5" else ("STK" if exchange_type == "IB_WEB" else "FUTURE")
    return str(
        os.environ.get("BT_GATEWAY_ASSET_TYPE")
        or gateway.get("asset_type")
        or data.get("asset_type")
        or default_value
    ).strip().upper()


def _resolve_strategy_identity(config: dict) -> str:
    workspace_unit = dict(config.get("workspace_unit") or {})
    gateway = dict(config.get("gateway") or {})
    value = (
        os.environ.get("BT_TRADING_INSTANCE_ID")
        or workspace_unit.get("unit_id")
        or gateway.get("strategy_id")
        or workspace_unit.get("strategy_id")
        or config.get("strategy_id")
        or "default"
    )
    return str(value or "default").strip() or "default"


def _merge_gateway_env_config(config: dict, provider: str, exchange_type: str, asset_type: str) -> dict:
    gateway = dict(config.get("gateway") or {})
    account_id = str(
        os.environ.get("BT_GATEWAY_ACCOUNT_ID")
        or gateway.get("account_id")
        or ""
    ).strip()
    default_startup_timeout, default_command_timeout = _gateway_timeout_defaults(exchange_type)
    return {
        "provider": provider,
        "config": {
            "gateway_start_local_runtime": _safe_bool(
                os.environ.get("BT_GATEWAY_START_LOCAL_RUNTIME", "0"),
                default=False,
            ),
            "gateway_command_endpoint": str(os.environ.get("BT_GATEWAY_COMMAND_ENDPOINT") or "").strip(),
            "gateway_event_endpoint": str(os.environ.get("BT_GATEWAY_EVENT_ENDPOINT") or "").strip(),
            "gateway_market_endpoint": str(os.environ.get("BT_GATEWAY_MARKET_ENDPOINT") or "").strip(),
            "account_id": account_id,
            "exchange_type": exchange_type,
            "asset_type": asset_type,
            "strategy_id": _resolve_strategy_identity(config),
            "gateway_startup_timeout_sec": _safe_float(
                os.environ.get("BT_GATEWAY_STARTUP_TIMEOUT_SEC"),
                default_startup_timeout,
            ),
            "gateway_command_timeout_sec": _safe_float(
                os.environ.get("BT_GATEWAY_COMMAND_TIMEOUT_SEC"),
                default_command_timeout,
            ),
        },
    }


def _build_ctp_store_config(config: dict, provider: str, asset_type: str) -> dict:
    ctp = dict(config.get("ctp") or {})
    gateway = dict(config.get("gateway") or {})
    live = dict(config.get("live") or {})
    fronts = dict(ctp.get("fronts") or {})
    network = str(live.get("network") or "telecom")
    front = dict(fronts.get(network) or fronts.get("telecom") or fronts.get("simnow") or {})
    investor_id = str(
        os.environ.get("CTP_INVESTOR_ID")
        or os.environ.get("CTP_USER_ID")
        or os.environ.get("SIMNOW_USER_ID")
        or ctp.get("investor_id")
        or ctp.get("user_id")
        or ""
    ).strip()
    return {
        "provider": provider,
        "config": {
            "exchange_type": "CTP",
            "asset_type": asset_type or "FUTURE",
            "account_id": str(ctp.get("account_id") or investor_id).strip(),
            "strategy_id": _resolve_strategy_identity(config),
            "td_address": str(ctp.get("td_address") or front.get("td_address") or "").strip(),
            "md_address": str(ctp.get("md_address") or front.get("md_address") or "").strip(),
            "broker_id": str(ctp.get("broker_id") or os.environ.get("CTP_BROKER_ID") or "").strip(),
            "investor_id": investor_id,
            "user_id": investor_id,
            "password": str(
                os.environ.get("CTP_PASSWORD")
                or os.environ.get("SIMNOW_PASSWORD")
                or ctp.get("password")
                or ""
            ).strip(),
            "app_id": str(os.environ.get("CTP_APP_ID") or ctp.get("app_id") or "simnow_client_test").strip(),
            "auth_code": str(os.environ.get("CTP_AUTH_CODE") or ctp.get("auth_code") or "0000000000000000").strip(),
            "gateway_start_local_runtime": True,
            "gateway_startup_timeout_sec": _safe_float(
                gateway.get("startup_timeout_sec")
                or ctp.get("startup_timeout_sec")
                or os.environ.get("CTP_STARTUP_TIMEOUT_SEC"),
                60.0,
            ),
            "gateway_command_timeout_sec": _safe_float(
                gateway.get("command_timeout_sec")
                or ctp.get("command_timeout_sec")
                or os.environ.get("CTP_COMMAND_TIMEOUT_SEC"),
                20.0,
            ),
        },
    }


def _build_ib_store_config(config: dict, provider: str, asset_type: str) -> dict:
    gateway = dict(config.get("gateway") or {})
    ib_web = dict(config.get("ib_web") or {})
    return {
        "provider": provider,
        "config": {
            "exchange_type": "IB_WEB",
            "asset_type": asset_type or "STK",
            "strategy_id": _resolve_strategy_identity(config),
            "account_id": str(
                gateway.get("account_id")
                or ib_web.get("account_id")
                or os.environ.get("IB_WEB_ACCOUNT_ID")
                or ""
            ).strip(),
            "base_url": str(
                gateway.get("base_url")
                or ib_web.get("base_url")
                or os.environ.get("IB_WEB_BASE_URL")
                or "https://localhost:5000"
            ).strip(),
            "verify_ssl": bool(
                gateway.get("verify_ssl")
                if gateway.get("verify_ssl") is not None
                else ib_web.get("verify_ssl", False)
            ),
            "timeout": _safe_float(
                gateway.get("timeout")
                or ib_web.get("timeout")
                or os.environ.get("IB_WEB_TIMEOUT"),
                10.0,
            ),
            "access_token": str(
                gateway.get("access_token")
                or ib_web.get("access_token")
                or os.environ.get("IB_WEB_ACCESS_TOKEN")
                or ""
            ).strip(),
            "cookie_source": str(
                gateway.get("cookie_source")
                or ib_web.get("cookie_source")
                or os.environ.get("IB_WEB_COOKIE_SOURCE")
                or ""
            ).strip(),
            "cookie_browser": str(
                gateway.get("cookie_browser")
                or ib_web.get("cookie_browser")
                or os.environ.get("IB_WEB_COOKIE_BROWSER")
                or "chrome"
            ).strip(),
            "cookie_path": str(
                gateway.get("cookie_path")
                or ib_web.get("cookie_path")
                or os.environ.get("IB_WEB_COOKIE_PATH")
                or "/sso"
            ).strip(),
            "gateway_start_local_runtime": True,
            "gateway_startup_timeout_sec": _safe_float(
                gateway.get("startup_timeout_sec")
                or ib_web.get("startup_timeout_sec")
                or os.environ.get("IB_WEB_STARTUP_TIMEOUT_SEC"),
                30.0,
            ),
            "gateway_command_timeout_sec": _safe_float(
                gateway.get("command_timeout_sec")
                or ib_web.get("command_timeout_sec")
                or os.environ.get("IB_WEB_COMMAND_TIMEOUT_SEC"),
                10.0,
            ),
        },
    }


def _build_mt5_store_config(config: dict, provider: str, asset_type: str) -> dict:
    gateway = dict(config.get("gateway") or {})
    mt5 = dict(config.get("mt5") or {})
    login = str(
        os.environ.get("MT5_LOGIN")
        or os.environ.get("MT5_ACCOUNT")
        or gateway.get("login")
        or mt5.get("login")
        or ""
    ).strip()
    account_id = str(
        os.environ.get("MT5_ACCOUNT_ID")
        or os.environ.get("MT5_ACCOUNT")
        or gateway.get("account_id")
        or mt5.get("account_id")
        or login
    ).strip()
    return {
        "provider": provider,
        "config": {
            "exchange_type": "MT5",
            "asset_type": asset_type or "OTC",
            "account_id": account_id,
            "strategy_id": _resolve_strategy_identity(config),
            "login": login,
            "password": str(
                os.environ.get("MT5_PASSWORD")
                or os.environ.get("MT5_PASS")
                or gateway.get("password")
                or mt5.get("password")
                or ""
            ).strip(),
            "ws_uri": str(
                os.environ.get("MT5_WS_URI")
                or gateway.get("ws_uri")
                or mt5.get("ws_uri")
                or "wss://web.metatrader.app/terminal"
            ).strip(),
            "symbol_suffix": str(
                gateway.get("symbol_suffix")
                or mt5.get("symbol_suffix")
                or os.environ.get("MT5_SYMBOL_SUFFIX")
                or ""
            ).strip(),
            "gateway_start_local_runtime": True,
            "gateway_startup_timeout_sec": _safe_int(gateway.get("startup_timeout_sec"), 120),
            "gateway_command_timeout_sec": _safe_int(gateway.get("command_timeout_sec"), 30),
        },
    }


def build_store_runtime(config: dict) -> dict:
    provider = _resolve_provider(config)
    exchange_type = _resolve_exchange_type(config)
    asset_type = _resolve_asset_type(config, exchange_type)
    if os.environ.get("BT_GATEWAY_COMMAND_ENDPOINT"):
        return _merge_gateway_env_config(config, provider, exchange_type, asset_type)
    if exchange_type == "MT5":
        return _build_mt5_store_config(config, provider, asset_type)
    if exchange_type == "IB_WEB":
        return _build_ib_store_config(config, provider, asset_type)
    return _build_ctp_store_config(config, provider, asset_type)


def _resolve_timeframe(config: dict):
    data_cfg = dict(config.get("data") or {})
    timeframe = str(data_cfg.get("timeframe") or "1m").strip().lower()
    timeframe_n = _safe_int(data_cfg.get("timeframe_n"), 1)
    minute_map = {
        "1m": 1,
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "1h": 60,
        "4h": 240,
        "1d": 1,
    }
    second_map = {"1s": 1, "5s": 5, "10s": 10, "15s": 15, "30s": 30}
    if timeframe in second_map:
        return bt.TimeFrame.Seconds, second_map[timeframe]
    if timeframe in {"1d", "d1", "day", "daily"}:
        return bt.TimeFrame.Days, max(timeframe_n, 1)
    if timeframe in minute_map:
        return bt.TimeFrame.Minutes, minute_map[timeframe]
    return bt.TimeFrame.Minutes, max(timeframe_n, 1)


def _resolve_feed_qcheck(config: dict) -> float:
    live = dict(config.get("live") or {})
    data = dict(config.get("data") or {})
    gateway = dict(config.get("gateway") or {})
    value = (
        live.get("qcheck")
        or live.get("qcheck_seconds")
        or data.get("qcheck")
        or gateway.get("qcheck")
    )
    qcheck = _safe_float(value, 0.5)
    return max(qcheck, 0.05)


def _resolve_log_ticks(config: dict) -> bool:
    live = dict(config.get("live") or {})
    simulate = dict(config.get("simulate") or {})
    logging_cfg = dict(config.get("logging") or {})
    value = (
        live.get("log_ticks")
        if live.get("log_ticks") is not None
        else (
            simulate.get("log_ticks")
            if simulate.get("log_ticks") is not None
            else logging_cfg.get("log_ticks")
        )
    )
    return _safe_bool(value, default=False)


def _resolve_trade_logger_option(config: dict, key: str, default: bool) -> bool:
    live = dict(config.get("live") or {})
    simulate = dict(config.get("simulate") or {})
    logging_cfg = dict(config.get("logging") or {})
    for section in (live, simulate, logging_cfg):
        if key in section:
            return _safe_bool(section.get(key), default=default)
    return default


def _resolve_dispatch_ticks(config: dict) -> bool:
    live = dict(config.get("live") or {})
    simulate = dict(config.get("simulate") or {})
    gateway = dict(config.get("gateway") or {})
    for section in (live, simulate, gateway):
        for key in ("dispatch_ticks", "notify_ticks"):
            if key in section:
                return _safe_bool(section.get(key), default=False)
    return False


def _resolve_exactbars(config: dict):
    live = dict(config.get("live") or {})
    simulate = dict(config.get("simulate") or {})
    cerebro_cfg = dict(config.get("cerebro") or {})
    for section in (live, simulate, cerebro_cfg):
        if "exactbars" not in section:
            continue
        value = section.get("exactbars")
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
            return _safe_bool(value, default=True)
    return True


def _resolve_stdstats(config: dict) -> bool:
    live = dict(config.get("live") or {})
    simulate = dict(config.get("simulate") or {})
    cerebro_cfg = dict(config.get("cerebro") or {})
    for section in (live, simulate, cerebro_cfg):
        if "stdstats" in section:
            return _safe_bool(section.get("stdstats"), default=False)
    return False


def _import_strategy_class():
    candidates = sorted(BASE_DIR.glob("strategy_*.py"))
    if not candidates:
        raise RuntimeError("未找到 strategy_*.py")
    module_path = candidates[0]
    spec = importlib.util.spec_from_file_location(module_path.stem, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法导入策略模块: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_path.stem] = module
    spec.loader.exec_module(module)
    for value in vars(module).values():
        if isinstance(value, type) and issubclass(value, bt.Strategy) and value is not bt.Strategy:
            return value
    raise RuntimeError("未找到 bt.Strategy 子类")


def run():
    _load_dotenv()
    _patch_gateway_client_compat()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = load_config()
    params = dict(config.get("params") or {})
    data_cfg = dict(config.get("data") or {})
    simulate_cfg = dict(config.get("simulate") or {})
    live_cfg = dict(config.get("live") or {})
    symbol = str(data_cfg.get("symbol") or live_cfg.get("symbol") or "").strip()
    if not symbol:
        raise SystemExit("缺少 data.symbol/live.symbol 配置")

    runtime = build_store_runtime(config)
    provider = runtime["provider"]
    store_cfg = dict(runtime["config"])
    if BtApiFeed is None or BtApiStore is None:
        raise SystemExit("Gateway runner requires the bt_api_py Backtrader feed and store adapters")

    print("=" * 60)
    print("Gateway Paper Trading Runner")
    print("=" * 60)
    print(f"  Provider: {provider}")
    print(f"  Exchange: {store_cfg.get('exchange_type')}")
    print(f"  Symbol: {symbol}")
    print(f"  Timeframe: {data_cfg.get('timeframe', '1m')}")

    log_dir = BASE_DIR / "logs"
    heartbeat = _start_runner_heartbeat(log_dir, _resolve_heartbeat_interval(config))
    store = None
    try:
        store = BtApiStore(provider=provider, **store_cfg)
        store.start()
        bt_timeframe, compression = _resolve_timeframe(config)
        data = BtApiFeed(
            store=store,
            dataname=symbol,
            timeframe=bt_timeframe,
            compression=compression,
            backfill_start=True,
            qcheck=_resolve_feed_qcheck(config),
            dispatch_ticks=_resolve_dispatch_ticks(config),
        )

        strategy_class = _import_strategy_class()
        log_dir.mkdir(exist_ok=True)

        cerebro = bt.Cerebro(
            quicknotify=True,
            exactbars=_resolve_exactbars(config),
            stdstats=_resolve_stdstats(config),
        )
        cerebro.broker.setcash(_safe_float(simulate_cfg.get("initial_cash"), 100000.0))
        _apply_contract_commission(cerebro, config, symbol)
        slippage = _safe_float(simulate_cfg.get("slippage"), 0.0)
        if slippage > 0:
            try:
                cerebro.broker.set_slippage_perc(perc=slippage)
            except AttributeError:
                logger.debug("Broker does not support set_slippage_perc", exc_info=True)
        cerebro.adddata(data, name=symbol)
        cerebro.addstrategy(strategy_class, **params)
        cerebro.addobserver(
            bt.observers.TradeLogger,
            log_dir=str(log_dir),
            log_format="json",
            log_orders=True,
            log_trades=True,
            log_positions=_resolve_trade_logger_option(config, "log_positions", True),
            log_indicators=_resolve_trade_logger_option(config, "log_indicators", False),
            log_signals=_resolve_trade_logger_option(config, "log_signals", True),
            log_ticks=_resolve_log_ticks(config),
        )

        duration_seconds = _safe_int(
            simulate_cfg.get("duration_seconds", live_cfg.get("duration_seconds")),
            7200,
        )
        session_timeout = _safe_int(
            simulate_cfg.get("session_timeout", live_cfg.get("session_timeout")),
            duration_seconds + 60,
        )

        print(f"  启动模拟交易 (timeout={session_timeout}s)...")
        stop_timer = threading.Timer(session_timeout, cerebro.runstop)
        stop_timer.daemon = True
        stop_timer.start()
        try:
            results = cerebro.run()
        finally:
            stop_timer.cancel()
    finally:
        try:
            if store is not None and getattr(store, "is_connected", False):
                store.stop()
        finally:
            _stop_runner_heartbeat(heartbeat)

    print("Strategy finished.")
    return results


if __name__ == "__main__":
    run()
