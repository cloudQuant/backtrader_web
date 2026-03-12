#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Jm Stochastic strategy runner for simulated trading (CTP only).

模拟交易：必须连接 CTP 交易所，连接失败时报错退出。
凭证从 .env 读取，策略配置从 config.yaml 读取。
"""
from __future__ import absolute_import, division, print_function, unicode_literals

# 确保使用正确的 backtrader（支持 BtApiStore/BtApiFeed/Strategy 的 fork）
import logging
import os
import sys
from pathlib import Path as _Path

_bt_web = _Path(__file__).resolve().parents[3]
_bt_project = _bt_web.parent / "backtrader"
if _bt_project.exists() and str(_bt_project) not in sys.path:
    sys.path.insert(0, str(_bt_project))

import socket
import threading
from pathlib import Path
from urllib.parse import urlparse

import backtrader as bt
import yaml
from backtrader.brokers.btapibroker import BtApiBroker
from backtrader.feeds.btapifeed import BtApiFeed
from backtrader.stores.btapistore import BtApiStore

from strategy_stochastic import StochasticStrategy

BASE_DIR = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)


def _load_dotenv() -> None:
    """Load .env from strategy dir or project root into os.environ (only if not set)."""
    for candidate in (BASE_DIR / ".env", _bt_web / ".env"):
        if not candidate.is_file():
            continue
        try:
            with candidate.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        if key and key not in os.environ:
                            os.environ[key] = value
        except OSError as e:
            logger.warning("Could not read %s: %s", candidate, e)
        break


def load_config() -> dict:
    """Load strategy config from config.yaml."""
    config_path = BASE_DIR / "config.yaml"
    if not config_path.exists():
        raise SystemExit(
            "config.yaml 不存在。请复制 config.example.yaml 为 config.yaml：\n"
            "  cp config.example.yaml config.yaml"
        )
    with config_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def build_ctp_store_config(config: dict) -> dict:
    """从 config 和 .env 合并 CTP 连接配置。凭证优先从环境变量读取。"""
    _load_dotenv()
    ctp = dict(config.get("ctp", {}) or {})
    live = dict(config.get("live", {}) or {})
    fronts = dict(ctp.get("fronts", {}) or {})
    network = live.get("network", "simnow")
    front = dict(
        fronts.get(network) or fronts.get("telecom") or fronts.get("simnow") or {}
    )
    inv = os.environ.get("CTP_INVESTOR_ID") or os.environ.get("CTP_USER_ID") or ctp.get("investor_id", "") or ctp.get("user_id", "")
    store_config = {
        "td_address": front.get("td_address", ""),
        "md_address": front.get("md_address", ""),
        "broker_id": os.environ.get("CTP_BROKER_ID") or ctp.get("broker_id", ""),
        "investor_id": inv,
        "user_id": inv,
        "password": os.environ.get("CTP_PASSWORD") or ctp.get("password", ""),
        "app_id": os.environ.get("CTP_APP_ID") or ctp.get("app_id", ""),
        "auth_code": os.environ.get("CTP_AUTH_CODE") or ctp.get("auth_code", ""),
    }
    if get_store_provider(config) == "ctp_gateway":
        store_config.update(
            {
                "gateway_start_local_runtime": os.environ.get("BT_GATEWAY_START_LOCAL_RUNTIME", "0")
                not in {"0", "false", "False"},
                "gateway_command_endpoint": os.environ.get("BT_GATEWAY_COMMAND_ENDPOINT", ""),
                "gateway_event_endpoint": os.environ.get("BT_GATEWAY_EVENT_ENDPOINT", ""),
                "gateway_market_endpoint": os.environ.get("BT_GATEWAY_MARKET_ENDPOINT", ""),
                "account_id": os.environ.get("BT_GATEWAY_ACCOUNT_ID", inv),
                "exchange_type": os.environ.get("BT_GATEWAY_EXCHANGE_TYPE", "CTP"),
                "asset_type": os.environ.get("BT_GATEWAY_ASSET_TYPE", "FUTURE"),
            }
        )
    return store_config


def get_store_provider(config: dict) -> str:
    gateway = dict(config.get("gateway", {}) or {})
    provider = os.environ.get("BT_STORE_PROVIDER") or gateway.get("provider") or "ctp"
    return str(provider).strip().lower() or "ctp"


def check_tcp_connectivity(address: str, timeout: int = 5) -> bool:
    """检查 CTP 前置地址的 TCP 连通性。"""
    try:
        parsed = urlparse(address)
        host = parsed.hostname
        port = parsed.port
        if not host or not port:
            logger.debug("Invalid address format: %s", address)
            return False
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.close()
        return True
    except (socket.error, OSError, ValueError) as e:
        logger.debug("TCP connectivity check failed for %s: %s", address, e)
        return False


def run_ctp_session(config: dict):
    """使用 BtApiStore/BtApiFeed/BtApiBroker 连接 CTP,运行模拟盘."""
    live = dict(config.get("live", {}) or {})
    symbol = live.get("symbol", "rb2610")
    bar_seconds = int(live.get("bar_seconds", 60))
    run_seconds = int(live.get("duration_seconds", 3600))
    session_timeout = int(live.get("session_timeout", run_seconds + 100))
    contract_metadata = dict(live.get("contract_metadata", {}) or {})
    symbol_rules = dict(contract_metadata.get(symbol, {}) or {})
    symbol_rules.setdefault("min_price_tick", float(live.get("min_price_tick", 1.0)))
    symbol_rules.setdefault("max_order_size", int(live.get("max_order_size", 1)))
    contract_metadata[symbol] = symbol_rules

    store_cfg = build_ctp_store_config(config)
    store = BtApiStore(provider=get_store_provider(config), **store_cfg)
    store.start()
    try:
        broker = BtApiBroker(store=store, contract_metadata=contract_metadata)
        data = BtApiFeed(
            store=store,
            dataname=symbol,
            timeframe=bt.TimeFrame.Seconds,
            compression=bar_seconds,
            backfill_start=False,
        )
        log_dir = BASE_DIR / "logs"
        log_dir.mkdir(exist_ok=True)

        cerebro = bt.Cerebro(quicknotify=True)
        cerebro.setbroker(broker)
        cerebro.adddata(data)
        params = config.get("params", {}) or {}
        cerebro.addstrategy(StochasticStrategy, **params)
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
        stop_timer = threading.Timer(session_timeout, cerebro.runstop)
        stop_timer.daemon = True
        stop_timer.start()
        try:
            results = cerebro.run()
        finally:
            stop_timer.cancel()
    finally:
        if store.is_connected:
            store.stop()
    return results


def run():
    """主入口：仅支持 CTP 模拟盘,连接失败时报错退出."""
    _load_dotenv()
    config = load_config()
    ctp_cfg = config.get("ctp", {}) or {}
    live_cfg = config.get("live", {}) or {}
    if not ctp_cfg or not live_cfg:
        raise SystemExit(
            "模拟交易必须配置 ctp 和 live,请填写 config.yaml 中的 ctp/live 节点。"
        )
    fronts = ctp_cfg.get("fronts", {}) or {}
    network = live_cfg.get("network", "simnow")
    front = dict(
        fronts.get(network) or fronts.get("telecom") or fronts.get("simnow") or {}
    )
    broker_id = os.environ.get("CTP_BROKER_ID") or ctp_cfg.get("broker_id")
    password = os.environ.get("CTP_PASSWORD") or ctp_cfg.get("password")
    investor_id = os.environ.get("CTP_INVESTOR_ID") or os.environ.get("CTP_USER_ID") or ctp_cfg.get("investor_id") or ctp_cfg.get("user_id")
    has_creds = broker_id and password and investor_id
    has_addrs = front.get("td_address") and front.get("md_address")

    if not has_creds:
        raise SystemExit(
            "CTP 凭证不完整。请配置 .env 文件（复制 .env.example 为 .env 并填写）：\n"
            "  必需: CTP_BROKER_ID, CTP_INVESTOR_ID, CTP_USER_ID, CTP_PASSWORD\n"
            "  或保留 config.yaml 中的 ctp 凭证（不推荐，易泄露）。"
        )
    if not has_addrs:
        raise SystemExit(
            f"CTP fronts 中需配置 td_address 和 md_address（可用 network: telecom 或 simnow）。"
        )

    md_addr = front["md_address"]
    td_addr = front["td_address"]

    print("检查 CTP 服务器连通性...")
    print(f"  行情: {md_addr}")
    print(f"  交易: {td_addr}")

    md_ok = check_tcp_connectivity(md_addr, timeout=5)
    td_ok = check_tcp_connectivity(td_addr, timeout=5)

    if not md_ok or not td_ok:
        hints = []
        if not md_ok:
            hints.append(f"行情服务器不可达: {md_addr}")
        if not td_ok:
            hints.append(f"交易服务器不可达: {td_addr}")
        raise SystemExit(
            "CTP 服务器不可达,无法启动模拟交易。\n"
            + "\n".join("  - " + h for h in hints)
            + "\n可能原因: 非交易时段/网络不通/SimNow 维护/地址已变更"
        )

    print("  CTP 服务器可达,启动模拟交易...")
    return run_ctp_session(config)


if __name__ == "__main__":
    print("=" * 60)
    print("Jm Stochastic Strategy")
    print("=" * 60)
    run()
