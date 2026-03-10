#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""批量更新模拟策略配置，使用 SimNow 账号和随机 bar 周期."""

from __future__ import annotations

import os
import random
from pathlib import Path
from typing import Any

import yaml

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent.parent

SIMNOW_ENVIRONMENTS = {
    "new_7x24": {
        "name": "新7x24环境（看穿式前置）",
        "td_address": "tcp://182.254.243.31:40001",
        "md_address": "tcp://182.254.243.31:40011",
    },
    "7x24": {
        "name": "7x24环境",
        "td_address": "tcp://180.168.146.187:10133",
        "md_address": "tcp://180.168.146.187:10143",
    },
}

BAR_SECONDS_OPTIONS = [15, 30, 60]

STRATEGY_CONTRACTS = {
    "a_td_sequential": {"symbol": "a", "contract": "a2605", "min_tick": 1.0},
    "al_turtle": {"symbol": "al", "contract": "al2505", "min_tick": 5.0},
    "au_boll_reverser": {"symbol": "au", "contract": "au2506", "min_tick": 0.02},
    "c_chandelier_exit": {"symbol": "c", "contract": "c2505", "min_tick": 1.0},
    "CF_donchian_channel": {"symbol": "CF", "contract": "CF505", "min_tick": 5.0},
    "cs_hma_multitrend": {"symbol": "cs", "contract": "cs2505", "min_tick": 1.0},
    "cu_macd_atr": {"symbol": "cu", "contract": "cu2505", "min_tick": 10.0},
    "hc_supertrend": {"symbol": "hc", "contract": "hc2505", "min_tick": 1.0},
    "i_r_breaker": {"symbol": "i", "contract": "i2505", "min_tick": 0.5},
    "j_dual_thrust": {"symbol": "j", "contract": "j2505", "min_tick": 0.5},
    "jm_stochastic": {"symbol": "jm", "contract": "jm2505", "min_tick": 0.5},
    "m_ichimoku_cloud": {"symbol": "m", "contract": "m2505", "min_tick": 1.0},
    "MA_trix": {"symbol": "MA", "contract": "MA505", "min_tick": 1.0},
    "OI_rsi_dip_buy": {"symbol": "OI", "contract": "OI505", "min_tick": 1.0},
    "p_bb_rsi": {"symbol": "p", "contract": "p2505", "min_tick": 2.0},
    "rb_dual_ma": {"symbol": "rb", "contract": "rb2505", "min_tick": 1.0},
    "SR_keltner_channel": {"symbol": "SR", "contract": "SR505", "min_tick": 1.0},
    "TA_cci": {"symbol": "TA", "contract": "TA505", "min_tick": 2.0},
    "y_alligator": {"symbol": "y", "contract": "y2505", "min_tick": 1.0},
    "zn_kelter": {"symbol": "zn", "contract": "zn2505", "min_tick": 5.0},
}


def load_env() -> dict[str, str]:
    env_vars = {}
    for env_file in [PROJECT_ROOT / ".env", PROJECT_ROOT / "backtrader" / ".env"]:
        if env_file.exists():
            with env_file.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        env_vars[key.strip()] = value.strip()
    return env_vars


def create_example_config(config_path: Path) -> bool:
    example_path = config_path.parent / "config.example.yaml"
    if not example_path.exists():
        import shutil

        shutil.copy2(config_path, example_path)
        return True
    return False


def update_config(config_path: Path, env_vars: dict[str, str]) -> dict[str, Any]:
    with config_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    strategy_name = config_path.parent.name
    contract_info = STRATEGY_CONTRACTS.get(strategy_name, {})
    bar_seconds = random.choice(BAR_SECONDS_OPTIONS)

    simnow_env = SIMNOW_ENVIRONMENTS["new_7x24"]
    simnow_user = env_vars.get(
        "simnow_user_id", env_vars.get("SIMNOW_USER_ID", "your_simnow_user_id")
    )
    simnow_pass = env_vars.get(
        "simnow_password", env_vars.get("SIMNOW_PASSWORD", "your_simnow_password")
    )

    config["ctp"] = {
        "broker_id": "9999",
        "investor_id": simnow_user,
        "user_id": simnow_user,
        "password": simnow_pass,
        "app_id": "simnow_client_test",
        "auth_code": "0000000000000000",
        "user_product_info": "simnow_client",
        "interface_product_info": "simnow_client",
        "fronts": {
            "simnow": {
                "td_address": simnow_env["td_address"],
                "md_address": simnow_env["md_address"],
            }
        },
    }

    contract = contract_info.get("contract", "rb2505")
    min_tick = contract_info.get("min_tick", 1.0)

    config["live"] = {
        "symbol": contract,
        "network": "simnow",
        "bar_seconds": bar_seconds,
        "duration_seconds": 3600,
        "session_timeout": 3700,
        "min_price_tick": min_tick,
        "max_order_size": 1,
        "contract_metadata": {
            contract: {
                "min_price_tick": min_tick,
                "max_order_size": 1,
            }
        },
    }

    with config_path.open("w", encoding="utf-8") as f:
        yaml.dump(
            config, f, allow_unicode=True, default_flow_style=False, sort_keys=False
        )

    return {"strategy": strategy_name, "contract": contract, "bar_seconds": bar_seconds}


def update_gitignore():
    gitignore_path = PROJECT_ROOT / ".gitignore"
    patterns_to_add = [
        "backtrader_web/strategies/simulate/*/config.yaml",
    ]

    existing_lines = []
    if gitignore_path.exists():
        with gitignore_path.open("r", encoding="utf-8") as f:
            existing_lines = [line.strip() for line in f.readlines()]

    new_lines = []
    for pattern in patterns_to_add:
        if pattern not in existing_lines:
            new_lines.append(pattern)

    if new_lines:
        with gitignore_path.open("a", encoding="utf-8") as f:
            if existing_lines and not existing_lines[-1].endswith("\n"):
                f.write("\n")
            for line in new_lines:
                f.write(f"{line}\n")
        print(f"Added {len(new_lines)} patterns to .gitignore")


def main():
    env_vars = load_env()
    simnow_user = env_vars.get("simnow_user_id", "NOT_FOUND")
    print(f"Loaded simnow_user_id: {simnow_user}")
    update_gitignore()
    print()

    results = []
    example_created = 0
    for strategy_dir in sorted(BASE_DIR.iterdir()):
        if strategy_dir.is_dir() and not strategy_dir.name.startswith("_"):
            config_path = strategy_dir / "config.yaml"
            if config_path.exists():
                if create_example_config(config_path):
                    example_created += 1
                result = update_config(config_path, env_vars)
                results.append(result)
                print(
                    f"Updated: {result['strategy']:<25} | {result['contract']:<10} | bar={result['bar_seconds']}s"
                )

    print(
        f"\n总计更新 {len(results)} 个策略配置, 创建 {example_created} 个 config.example.yaml"
    )


if __name__ == "__main__":
    main()
