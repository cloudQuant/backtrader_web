#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Unified gateway-backed paper trading runner."""

from __future__ import absolute_import, division, print_function, unicode_literals

import importlib.util
import logging
import os
import sys
import threading
from pathlib import Path

_BT_WEB = Path(__file__).resolve().parents[3]
_BT_PROJECT = _BT_WEB.parent / "backtrader"
if _BT_PROJECT.exists() and str(_BT_PROJECT) not in sys.path:
    sys.path.insert(0, str(_BT_PROJECT))
_BT_API_PY = _BT_WEB.parent / "bt_api_py"
if _BT_API_PY.exists() and str(_BT_API_PY) not in sys.path:
    sys.path.insert(0, str(_BT_API_PY))
_PYMT5 = _BT_WEB.parent / "pymt5"
if _PYMT5.exists() and str(_PYMT5) not in sys.path:
    sys.path.insert(0, str(_PYMT5))

import backtrader as bt
import yaml
from backtrader.feeds.btapifeed import BtApiFeed
from backtrader.stores.btapistore import BtApiStore

BASE_DIR = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)


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


def _merge_gateway_env_config(config: dict, provider: str, exchange_type: str, asset_type: str) -> dict:
    gateway = dict(config.get("gateway") or {})
    account_id = str(
        os.environ.get("BT_GATEWAY_ACCOUNT_ID")
        or gateway.get("account_id")
        or ""
    ).strip()
    return {
        "provider": provider,
        "config": {
            "gateway_start_local_runtime": str(
                os.environ.get("BT_GATEWAY_START_LOCAL_RUNTIME", "0")
            ).strip().lower()
            not in {"0", "false", "no", "off", ""},
            "gateway_command_endpoint": str(os.environ.get("BT_GATEWAY_COMMAND_ENDPOINT") or "").strip(),
            "gateway_event_endpoint": str(os.environ.get("BT_GATEWAY_EVENT_ENDPOINT") or "").strip(),
            "gateway_market_endpoint": str(os.environ.get("BT_GATEWAY_MARKET_ENDPOINT") or "").strip(),
            "account_id": account_id,
            "exchange_type": exchange_type,
            "asset_type": asset_type,
        },
    }


def _build_ctp_store_config(config: dict, provider: str, asset_type: str) -> dict:
    ctp = dict(config.get("ctp") or {})
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
        },
    }


def _build_mt5_store_config(config: dict, provider: str, asset_type: str) -> dict:
    gateway = dict(config.get("gateway") or {})
    mt5 = dict(config.get("mt5") or {})
    account_id = str(
        gateway.get("account_id")
        or mt5.get("account_id")
        or os.environ.get("MT5_ACCOUNT_ID")
        or mt5.get("login")
        or os.environ.get("MT5_LOGIN")
        or ""
    ).strip()
    return {
        "provider": provider,
        "config": {
            "exchange_type": "MT5",
            "asset_type": asset_type or "OTC",
            "account_id": account_id,
            "login": str(gateway.get("login") or mt5.get("login") or os.environ.get("MT5_LOGIN") or "").strip(),
            "password": str(
                gateway.get("password")
                or mt5.get("password")
                or os.environ.get("MT5_PASSWORD")
                or ""
            ).strip(),
            "ws_uri": str(
                gateway.get("ws_uri")
                or mt5.get("ws_uri")
                or os.environ.get("MT5_WS_URI")
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

    print("=" * 60)
    print("Gateway Paper Trading Runner")
    print("=" * 60)
    print(f"  Provider: {provider}")
    print(f"  Exchange: {store_cfg.get('exchange_type')}")
    print(f"  Symbol: {symbol}")
    print(f"  Timeframe: {data_cfg.get('timeframe', '1m')}")

    store = BtApiStore(provider=provider, **store_cfg)
    store.start()
    try:
        bt_timeframe, compression = _resolve_timeframe(config)
        data = BtApiFeed(
            store=store,
            dataname=symbol,
            timeframe=bt_timeframe,
            compression=compression,
            backfill_start=True,
        )

        strategy_class = _import_strategy_class()
        log_dir = BASE_DIR / "logs"
        log_dir.mkdir(exist_ok=True)

        cerebro = bt.Cerebro(quicknotify=True)
        cerebro.broker.setcash(_safe_float(simulate_cfg.get("initial_cash"), 100000.0))
        cerebro.broker.setcommission(commission=_safe_float(simulate_cfg.get("commission"), 0.0005))
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
            log_positions=True,
            log_indicators=True,
            log_signals=True,
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
        if getattr(store, "is_connected", False):
            store.stop()

    print("Strategy finished.")
    return results


if __name__ == "__main__":
    run()
