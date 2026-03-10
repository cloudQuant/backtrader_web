#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Batch fix simulate strategies to use .env for credentials (like a_td_sequential)."""
from __future__ import absolute_import, division, print_function, unicode_literals

import re
from pathlib import Path

STRATEGIES_DIR = Path(__file__).resolve().parents[1] / "strategies" / "simulate"

# (dir_name, strategy_module, strategy_class, display_name)
STRATEGIES = [
    ("al_turtle", "strategy_turtle", "TurtleStrategy", "Al Turtle"),
    ("au_boll_reverser", "strategy_boll_reverser", "BollReverserStrategy", "Au Boll Reverser"),
    ("c_chandelier_exit", "strategy_chandelier_exit", "ChandelierExitStrategy", "C Chandelier Exit"),
    ("CF_donchian_channel", "strategy_donchian_channel", "DonchianChannelStrategy", "CF Donchian Channel"),
    ("cs_hma_multitrend", "strategy_hma_multitrend", "HmaMultiTrendStrategy", "Cs Hma Multitrend"),
    ("cu_macd_atr", "strategy_macd_atr", "MACDATRStrategy", "Cu Macd Atr"),
    ("hc_supertrend", "strategy_supertrend", "SuperTrendStrategy", "Hc Supertrend"),
    ("i_r_breaker", "strategy_r_breaker", "RBreakerStrategy", "I R Breaker"),
    ("j_dual_thrust", "strategy_dual_thrust", "DualThrustStrategy", "J Dual Thrust"),
    ("jm_stochastic", "strategy_stochastic", "StochasticStrategy", "Jm Stochastic"),
    ("m_ichimoku_cloud", "strategy_ichimoku_cloud", "IchimokuCloudStrategy", "M Ichimoku Cloud"),
    ("MA_trix", "strategy_trix", "TrixStrategy", "MA Trix"),
    ("OI_rsi_dip_buy", "strategy_rsi_dip_buy", "RSIDipBuyStrategy", "OI RSI Dip Buy"),
    ("p_bb_rsi", "strategy_bb_rsi", "BbRsiStrategy", "P BB RSI"),
    ("rb_dual_ma", "strategy_dual_ma", "TwoMAStrategy", "Rb Dual Ma"),
    ("SR_keltner_channel", "strategy_keltner_channel", "KeltnerChannelStrategy", "SR Keltner Channel"),
    ("TA_cci", "strategy_cci", "CciStrategy", "TA CCI"),
    ("y_alligator", "strategy_alligator", "AlligatorStrategy", "Y Alligator"),
    ("zn_kelter", "strategy_kelter", "KeltnerStrategy", "Zn Kelter"),
]

RUN_TEMPLATE = '''#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""{display_name} strategy runner for simulated trading (CTP only).

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

from {strategy_module} import {strategy_class}

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
            f"config.yaml 不存在。请复制 config.example.yaml 为 config.yaml：\n"
            f"  cp config.example.yaml config.yaml"
        )
    with config_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {{}}


def build_ctp_store_config(config: dict) -> dict:
    """从 config 和 .env 合并 CTP 连接配置。凭证优先从环境变量读取。"""
    _load_dotenv()
    ctp = dict(config.get("ctp", {{}}) or {{}})
    live = dict(config.get("live", {{}}) or {{}})
    fronts = dict(ctp.get("fronts", {{}}) or {{}})
    network = live.get("network", "simnow")
    front = dict(
        fronts.get(network) or fronts.get("telecom") or fronts.get("simnow") or {{}}
    )
    inv = os.environ.get("CTP_INVESTOR_ID") or os.environ.get("CTP_USER_ID") or ctp.get("investor_id", "") or ctp.get("user_id", "")
    return {{
        "td_address": front.get("td_address", ""),
        "md_address": front.get("md_address", ""),
        "broker_id": os.environ.get("CTP_BROKER_ID") or ctp.get("broker_id", ""),
        "investor_id": inv,
        "user_id": inv,
        "password": os.environ.get("CTP_PASSWORD") or ctp.get("password", ""),
        "app_id": os.environ.get("CTP_APP_ID") or ctp.get("app_id", ""),
        "auth_code": os.environ.get("CTP_AUTH_CODE") or ctp.get("auth_code", ""),
    }}


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
    store = BtApiStore(provider="ctp", **store_cfg)
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
        cerebro.addstrategy({strategy_class}, **params)
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
    ctp_cfg = config.get("ctp", {{}}) or {{}}
    live_cfg = config.get("live", {{}}) or {{}}
    if not ctp_cfg or not live_cfg:
        raise SystemExit(
            "模拟交易必须配置 ctp 和 live,请填写 config.yaml 中的 ctp/live 节点。"
        )
    fronts = ctp_cfg.get("fronts", {{}}) or {{}}
    network = live_cfg.get("network", "simnow")
    front = dict(
        fronts.get(network) or fronts.get("telecom") or fronts.get("simnow") or {{}}
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
            + "\n".join("  - " + h for h in hints)
            + "\n可能原因: 非交易时段/网络不通/SimNow 维护/地址已变更"
        )

    print("  CTP 服务器可达,启动模拟交易...")
    return run_ctp_session(config)


if __name__ == "__main__":
    print("=" * 60)
    print("{display_name} Strategy")
    print("=" * 60)
    run()
'''

ENV_EXAMPLE = """# CTP 模拟交易凭证（从 config.yaml 移出，避免泄露）
# 复制为 .env 并填写实际值：cp .env.example .env
# .env 已加入 .gitignore，请勿提交

CTP_BROKER_ID=9999
CTP_INVESTOR_ID=your_simnow_id
CTP_USER_ID=your_simnow_id
CTP_PASSWORD=your_simnow_password
CTP_APP_ID=simnow_client_test
CTP_AUTH_CODE=0000000000000000

# 可选：开启 tick/bar 调试输出（生产环境请关闭）
# TD_DEBUG=1
"""


def fix_config_yaml(path: Path, live_symbol: str) -> None:
    """Remove credentials from config.yaml and ensure contract_metadata has live symbol."""
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    # Remove broker_id, investor_id, user_id, password from ctp section
    text = re.sub(r"^\s*broker_id:\s*[^\n]+\n", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*investor_id:\s*[^\n]+\n", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*user_id:\s*[^\n]+\n", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*password:\s*[^\n]+\n", "", text, flags=re.MULTILINE)
    # Add credential comment before ctp if not present
    if "# 凭证" not in text and "ctp:" in text:
        text = text.replace(
            "ctp:\n",
            "# 凭证(broker_id/investor_id/password)从 .env 读取，见 .env.example\nctp:\n",
            1,
        )
    # Ensure contract_metadata has live symbol
    if live_symbol and f"{live_symbol}:" not in text and "contract_metadata:" in text:
        # Add after contract_metadata section's first entry
        add_block = f"""
    {live_symbol}:
      min_price_tick: 1.0
      max_order_size: 1"""
        # Insert before the last contract or at end of contract_metadata
        match = re.search(r"(contract_metadata:\s*\n(?:\s+\w+:\s*\n(?:\s+\w+:[^\n]+\n)+)+)", text)
        if match:
            insert_pos = match.end()
            text = text[:insert_pos] + add_block + text[insert_pos:]
    path.write_text(text, encoding="utf-8")


def main():
    for dir_name, strategy_module, strategy_class, display_name in STRATEGIES:
        d = STRATEGIES_DIR / dir_name
        if not d.is_dir():
            print(f"Skip (not dir): {d}")
            continue

        run_py = d / "run.py"
        run_content = RUN_TEMPLATE.format(
            display_name=display_name,
            strategy_module=strategy_module,
            strategy_class=strategy_class,
        )
        run_py.write_text(run_content, encoding="utf-8")
        print(f"Updated run.py: {dir_name}")

        (d / ".env.example").write_text(ENV_EXAMPLE, encoding="utf-8")
        print(f"  .env.example")

        config_path = d / "config.yaml"
        live_symbol = None
        if config_path.exists():
            import yaml
            cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            live_symbol = (cfg.get("live") or {}).get("symbol")
        if not live_symbol:
            live_symbol = "rb2505"
        fix_config_yaml(config_path, live_symbol)
        print(f"  config.yaml (credentials removed)")

        example = d / "config.example.yaml"
        if config_path.exists() and not example.exists():
            example.write_text(config_path.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"  config.example.yaml created")
    print("Done.")


if __name__ == "__main__":
    main()
