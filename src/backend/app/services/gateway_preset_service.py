"""
Gateway preset definitions for live trading.

Extracted from LiveTradingManager (123-B) to isolate static preset
configuration data from runtime gateway lifecycle and instance management.
"""

import copy
from typing import Any

# ---------------------------------------------------------------------------
# Individual preset definitions
# ---------------------------------------------------------------------------

_CTP_FUTURES: dict[str, Any] = {
    "description": "Shared CTP gateway preset for domestic futures accounts.",
    "id": "ctp_futures_gateway",
    "name": "CTP Futures Gateway",
    "editable_fields": [
        {
            "key": "account_id",
            "label": "账户",
            "input_type": "string",
            "placeholder": "请输入期货账户",
        },
    ],
    "params": {
        "gateway": {
            "enabled": True,
            "provider": "ctp_gateway",
            "exchange_type": "CTP",
            "asset_type": "FUTURE",
            "account_id": "",
        }
    },
}

_IB_WEB_STOCK: dict[str, Any] = {
    "description": "IB Web preset for US stock trading via gateway mode.",
    "id": "ib_web_stock_gateway",
    "name": "IB Web Stock Gateway",
    "editable_fields": [
        {
            "key": "account_id",
            "label": "账户",
            "input_type": "string",
            "placeholder": "如 DU123456",
        },
        {
            "key": "base_url",
            "label": "Base URL",
            "input_type": "string",
            "placeholder": "如 https://localhost:5000",
        },
        {"key": "verify_ssl", "label": "SSL校验", "input_type": "boolean"},
    ],
    "params": {
        "gateway": {
            "enabled": True,
            "provider": "gateway",
            "exchange_type": "IB_WEB",
            "asset_type": "STK",
            "account_id": "DU123456",
            "base_url": "https://localhost:5000",
            "verify_ssl": False,
        }
    },
}

_IB_WEB_FUTURES: dict[str, Any] = {
    "description": "IB Web preset for futures trading via gateway mode.",
    "id": "ib_web_futures_gateway",
    "name": "IB Web Futures Gateway",
    "editable_fields": [
        {
            "key": "account_id",
            "label": "账户",
            "input_type": "string",
            "placeholder": "如 DU123456",
        },
        {
            "key": "base_url",
            "label": "Base URL",
            "input_type": "string",
            "placeholder": "如 https://localhost:5000",
        },
        {"key": "verify_ssl", "label": "SSL校验", "input_type": "boolean"},
    ],
    "params": {
        "gateway": {
            "enabled": True,
            "provider": "gateway",
            "exchange_type": "IB_WEB",
            "asset_type": "FUT",
            "account_id": "DU123456",
            "base_url": "https://localhost:5000",
            "verify_ssl": False,
        }
    },
}

_BINANCE_SWAP: dict[str, Any] = {
    "description": "Binance SWAP gateway preset for perpetual futures trading.",
    "id": "binance_swap_gateway",
    "name": "Binance SWAP Gateway",
    "editable_fields": [
        {
            "key": "account_id",
            "label": "账户标识",
            "input_type": "string",
            "placeholder": "自定义账户标识",
        },
        {
            "key": "api_key",
            "label": "API Key",
            "input_type": "string",
            "placeholder": "Binance API Key",
        },
        {
            "key": "secret_key",
            "label": "Secret Key",
            "input_type": "string",
            "placeholder": "Binance Secret Key",
        },
    ],
    "params": {
        "gateway": {
            "enabled": True,
            "provider": "gateway",
            "exchange_type": "BINANCE",
            "asset_type": "SWAP",
            "account_id": "",
            "api_key": "",
            "secret_key": "",
        }
    },
}

_OKX_SWAP: dict[str, Any] = {
    "description": "OKX SWAP gateway preset for perpetual futures trading.",
    "id": "okx_swap_gateway",
    "name": "OKX SWAP Gateway",
    "editable_fields": [
        {
            "key": "account_id",
            "label": "账户标识",
            "input_type": "string",
            "placeholder": "自定义账户标识",
        },
        {
            "key": "api_key",
            "label": "API Key",
            "input_type": "string",
            "placeholder": "OKX API Key",
        },
        {
            "key": "secret_key",
            "label": "Secret Key",
            "input_type": "string",
            "placeholder": "OKX Secret Key",
        },
        {
            "key": "passphrase",
            "label": "Passphrase",
            "input_type": "string",
            "placeholder": "OKX Passphrase",
        },
    ],
    "params": {
        "gateway": {
            "enabled": True,
            "provider": "gateway",
            "exchange_type": "OKX",
            "asset_type": "SWAP",
            "account_id": "",
            "api_key": "",
            "secret_key": "",
            "passphrase": "",
        }
    },
}

_MT5_FOREX: dict[str, Any] = {
    "description": "MT5 Forex gateway preset for MetaTrader 5 trading via pymt5 WebSocket.",
    "id": "mt5_forex_gateway",
    "name": "MT5 Forex Gateway",
    "editable_fields": [
        {
            "key": "account_id",
            "label": "账户标识",
            "input_type": "string",
            "placeholder": "自定义账户标识",
        },
        {
            "key": "login",
            "label": "MT5 账号",
            "input_type": "string",
            "placeholder": "MT5 登录账号（数字）",
        },
        {
            "key": "password",
            "label": "MT5 密码",
            "input_type": "string",
            "placeholder": "MT5 登录密码",
        },
        {
            "key": "ws_uri",
            "label": "WebSocket 地址",
            "input_type": "string",
            "placeholder": "默认 wss://web.metatrader.app/terminal",
        },
    ],
    "params": {
        "gateway": {
            "enabled": True,
            "provider": "mt5_gateway",
            "exchange_type": "MT5",
            "asset_type": "OTC",
            "account_id": "",
            "login": "",
            "password": "",
            "ws_uri": "",
            "symbol_suffix": "",
        }
    },
}

_ALL_PRESETS: list[dict[str, Any]] = [
    _CTP_FUTURES,
    _IB_WEB_STOCK,
    _IB_WEB_FUTURES,
    _BINANCE_SWAP,
    _OKX_SWAP,
    _MT5_FOREX,
]


def get_gateway_presets() -> list[dict[str, Any]]:
    """Return a deep copy of all available gateway presets.

    Each preset contains:
    - id: Unique preset identifier
    - name: Human-readable name
    - description: Preset description
    - editable_fields: List of user-configurable fields
    - params: Default parameter dictionary including gateway config

    Returns:
        A list of gateway preset dictionaries.
    """
    return copy.deepcopy(_ALL_PRESETS)
