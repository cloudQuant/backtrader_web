#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""批量更新所有策略的 run.py 文件，支持 CTP 模拟交易."""

from __future__ import annotations

import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

STRATEGY_INFO = {
    "CF_donchian_channel": {
        "class": "DonchianChannelStrategy",
        "module": "strategy_donchian_channel",
    },
    "MA_trix": {"class": "TrixStrategy", "module": "strategy_trix"},
    "OI_rsi_dip_buy": {"class": "RSIDipBuyStrategy", "module": "strategy_rsi_dip_buy"},
    "SR_keltner_channel": {
        "class": "KeltnerChannelStrategy",
        "module": "strategy_keltner_channel",
    },
    "TA_cci": {"class": "CciStrategy", "module": "strategy_cci"},
    "a_td_sequential": {
        "class": "TDSequentialStrategy",
        "module": "strategy_td_sequential",
    },
    "al_turtle": {"class": "TurtleStrategy", "module": "strategy_turtle"},
    "au_boll_reverser": {
        "class": "BollReverserStrategy",
        "module": "strategy_boll_reverser",
    },
    "c_chandelier_exit": {
        "class": "ChandelierExitStrategy",
        "module": "strategy_chandelier_exit",
    },
    "cs_hma_multitrend": {
        "class": "HmaMultiTrendStrategy",
        "module": "strategy_hma_multitrend",
    },
    "cu_macd_atr": {"class": "MACDATRStrategy", "module": "strategy_macd_atr"},
    "hc_supertrend": {"class": "SuperTrendStrategy", "module": "strategy_supertrend"},
    "i_r_breaker": {"class": "RBreakerStrategy", "module": "strategy_r_breaker"},
    "j_dual_thrust": {"class": "DualThrustStrategy", "module": "strategy_dual_thrust"},
    "jm_stochastic": {"class": "StochasticStrategy", "module": "strategy_stochastic"},
    "m_ichimoku_cloud": {
        "class": "IchimokuCloudStrategy",
        "module": "strategy_ichimoku_cloud",
    },
    "p_bb_rsi": {"class": "BbRsiStrategy", "module": "strategy_bb_rsi"},
    "rb_dual_ma": {"class": "TwoMAStrategy", "module": "strategy_dual_ma"},
    "y_alligator": {"class": "AlligatorStrategy", "module": "strategy_alligator"},
    "zn_kelter": {"class": "KeltnerStrategy", "module": "strategy_kelter"},
}


def generate_run_py(strategy_name: str, class_name: str, module_name: str) -> str:
    display_name = strategy_name.replace("_", " ").title()
    return f'''#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""{display_name} strategy runner for simulated trading (CTP only).

模拟交易：必须连接 CTP 交易所，连接失败时报错退出。
Config 需包含完整 ctp + live 配置。
"""
from __future__ import absolute_import, division, print_function, unicode_literals

# 确保使用正确的 backtrader（支持 BtApiStore/BtApiFeed/Strategy 的 fork）
import sys
from pathlib import Path as _Path
_bt_web = _Path(__file__).resolve().parents[3]  # backtrader_web 根目录 (run.py 在 strategies/simulate/xxx/ 下)
_bt_project = _bt_web.parent / "backtrader"
if _bt_project.exists() and str(_bt_project) not in sys.path:
    sys.path.insert(0, str(_bt_project))

import socket
import threading
from pathlib import Path
from urllib.parse import urlparse

import backtrader as bt
import yaml
from backtrader.stores.btapistore import BtApiStore
from backtrader.feeds.btapifeed import BtApiFeed
from backtrader.brokers.btapibroker import BtApiBroker

from {module_name} import {class_name}

BASE_DIR = Path(__file__).resolve().parent


def load_config() -> dict:
    """Load configuration from config.yaml."""
    config_path = BASE_DIR / "config.yaml"
    with config_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {{}}


def build_ctp_store_config(config: dict) -> dict:
    """从策略 config.yaml 中提取 CTP 连接配置."""
    ctp = dict(config.get("ctp", {{}}) or {{}})
    live = dict(config.get("live", {{}}) or {{}})
    fronts = dict(ctp.get("fronts", {{}}) or {{}})
    network = live.get("network", "simnow")
    # simnow/telecom 互通：config 常用 telecom，默认 network 为 simnow
    front = dict(
        fronts.get(network) or fronts.get("telecom") or fronts.get("simnow") or {{}}
    )
    inv = ctp.get("investor_id", "") or ctp.get("user_id", "")
    store_config = {{
        "td_address": front.get("td_address", ""),
        "md_address": front.get("md_address", ""),
        "broker_id": ctp.get("broker_id", ""),
        "investor_id": inv,
        "user_id": inv,
        "password": ctp.get("password", ""),
        "app_id": ctp.get("app_id", ""),
        "auth_code": ctp.get("auth_code", ""),
    }}
    if get_store_provider(config) == "ctp_gateway":
        store_config.update(
            {{
                "gateway_start_local_runtime": os.environ.get("BT_GATEWAY_START_LOCAL_RUNTIME", "0")
                not in {{"0", "false", "False"}},
                "gateway_command_endpoint": os.environ.get("BT_GATEWAY_COMMAND_ENDPOINT", ""),
                "gateway_event_endpoint": os.environ.get("BT_GATEWAY_EVENT_ENDPOINT", ""),
                "gateway_market_endpoint": os.environ.get("BT_GATEWAY_MARKET_ENDPOINT", ""),
                "account_id": os.environ.get("BT_GATEWAY_ACCOUNT_ID", inv),
                "exchange_type": os.environ.get("BT_GATEWAY_EXCHANGE_TYPE", "CTP"),
                "asset_type": os.environ.get("BT_GATEWAY_ASSET_TYPE", "FUTURE"),
            }}
        )
    return store_config


def get_store_provider(config: dict) -> str:
    gateway = dict(config.get("gateway", {{}}) or {{}})
    provider = os.environ.get("BT_STORE_PROVIDER") or gateway.get("provider") or "ctp"
    return str(provider).strip().lower() or "ctp"


def check_tcp_connectivity(address: str, timeout: int = 5) -> bool:
    """检查 CTP 前置地址的 TCP 连通性."""
    try:
        parsed = urlparse(address)
        host = parsed.hostname
        port = parsed.port
        if not host or not port:
            return False
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


def run_ctp_session(config: dict):
    """使用 BtApiStore/BtApiFeed/BtApiBroker 连接 CTP,运行模拟盘."""
    live = dict(config.get("live", {{}}) or {{}})
    symbol = live.get("symbol", "rb2505")
    bar_seconds = int(live.get("bar_seconds", 60))
    run_seconds = int(live.get("duration_seconds", 3600))
    session_timeout = int(live.get("session_timeout", run_seconds + 100))
    contract_metadata = dict(live.get("contract_metadata", {{}}) or {{}})
    symbol_rules = dict(contract_metadata.get(symbol, {{}}) or {{}})
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
        params = config.get("params", {{}}) or {{}}
        cerebro.addstrategy({class_name}, **params)
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
    config = load_config()
    ctp_cfg = config.get("ctp", {{}}) or {{}}
    live_cfg = config.get("live", {{}}) or {{}}
    if not ctp_cfg or not live_cfg:
        raise SystemExit(
            "模拟交易必须配置 ctp 和 live,请填写 config.yaml 中的 ctp/live 节点。"
        )
    fronts = ctp_cfg.get("fronts", {{}}) or {{}}
    network = live_cfg.get("network", "simnow")
    # simnow/telecom 互通：优先 network，再回退 telecom/simnow
    front = dict(
        fronts.get(network) or fronts.get("telecom") or fronts.get("simnow") or {{}}
    )
    has_creds = all(
        ctp_cfg.get(k) for k in ("broker_id", "password")
    ) and (ctp_cfg.get("investor_id") or ctp_cfg.get("user_id"))
    has_addrs = front.get("td_address") and front.get("md_address")
    if not has_creds:
        raise SystemExit(
            "CTP 配置不完整,需填写 broker_id、investor_id、password。"
        )
    if not has_addrs:
        raise SystemExit(
            f"CTP fronts 中需配置 td_address 和 md_address（可用 network: telecom 或 simnow）。"
        )

    md_addr = front["md_address"]
    td_addr = front["td_address"]

    print(f"检查 CTP 服务器连通性...")
    print(f"  行情: {{md_addr}}")
    print(f"  交易: {{td_addr}}")

    md_ok = check_tcp_connectivity(md_addr, timeout=5)
    td_ok = check_tcp_connectivity(td_addr, timeout=5)

    if not md_ok or not td_ok:
        hints = []
        if not md_ok:
            hints.append(f"行情服务器不可达: {{md_addr}}")
        if not td_ok:
            hints.append(f"交易服务器不可达: {{td_addr}}")
        raise SystemExit(
            "CTP 服务器不可达,无法启动模拟交易。\\n"
            + "\\n".join(f"  - {{h}}" for h in hints)
            + "\\n可能原因: 非交易时段/网络不通/SimNow 维护/地址已变更"
        )

    print("  CTP 服务器可达,启动模拟交易...")
    return run_ctp_session(config)


if __name__ == "__main__":
    print("=" * 60)
    print("{display_name} Strategy")
    print("=" * 60)
    run()
'''


def update_all_run_py():
    """更新所有策略的 run.py 文件."""
    updated = 0
    skipped = 0

    for strategy_dir in sorted(BASE_DIR.iterdir()):
        if not strategy_dir.is_dir() or strategy_dir.name.startswith("_"):
            continue

        strategy_name = strategy_dir.name
        if strategy_name not in STRATEGY_INFO:
            print(f"[skip] {strategy_name}: 未找到策略信息")
            skipped += 1
            continue

        info = STRATEGY_INFO[strategy_name]
        run_py_path = strategy_dir / "run.py"

        content = generate_run_py(
            strategy_name=strategy_name,
            class_name=info["class"],
            module_name=info["module"],
        )

        with run_py_path.open("w", encoding="utf-8") as f:
            f.write(content)

        print(f"[ok] {strategy_name}")
        updated += 1

    print(f"\n总计更新 {updated} 个 run.py, 跳过 {skipped} 个")


if __name__ == "__main__":
    update_all_run_py()
