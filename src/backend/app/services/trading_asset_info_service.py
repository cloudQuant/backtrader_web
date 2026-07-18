"""Resolve and persist trading asset specifications for live strategies."""

# This module remains a compatibility facade for the stage modules below.
# ruff: noqa: E402, F401, F821

from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

_CTP_EXCHANGES = frozenset({"SHFE", "DCE", "CZCE", "CFFEX", "INE", "GFEX"})
_COMMON_QUOTE_SUFFIXES = (
    "USDT",
    "USDC",
    "USD",
    "CNH",
    "CNY",
    "EUR",
    "JPY",
    "BTC",
    "ETH",
)
_FIAT_CURRENCIES = frozenset(
    {
        "AUD",
        "CAD",
        "CHF",
        "CNH",
        "CNY",
        "EUR",
        "GBP",
        "HKD",
        "JPY",
        "MXN",
        "NOK",
        "NZD",
        "SEK",
        "SGD",
        "TRY",
        "USD",
        "ZAR",
    }
)
_MT5_METAL_CONTRACT_SIZES = {
    "XAUUSD": 100.0,
    "XAGUSD": 5000.0,
    "XPTUSD": 100.0,
    "XPDUSD": 100.0,
}
_MT5_FOREX_CONTRACT_SIZE = 100000.0
COMMISSION_FIELD_KEYS = (
    "commission",
    "comm",
    "commissionAmount",
    "fee",
    "fees",
    "feeAmount",
    "execFee",
    "exec_fee",
    "execFeeV2",
    "exec_fee_v2",
    "execCommission",
    "exec_commission",
    "open_fee",
    "openFee",
    "open_commission",
    "openCommission",
    "positionCommission",
    "position_fee",
    "position_commission",
    "tradeFee",
    "trade_fee",
    "trade_commission",
    "broker_commission",
    "brokerCommission",
    "commission_amount",
    "Commission",
    "fillFee",
    "fill_fee",
)
CARRY_PNL_FIELD_KEYS = (
    "swap",
    "storage",
    "funding",
    "funding_fee",
    "fundingFee",
    "funding_fee_amount",
    "fundingFeeAmount",
    "interest",
    "borrow_interest",
    "borrowInterest",
    "financing_fee",
    "financingFee",
)
TODAY_POSITION_FIELD_KEYS = (
    "today_position",
    "td_position",
    "today_size",
    "today_volume",
    "td_volume",
    "TodayPosition",
    "TdPosition",
    "TodayVolume",
    "tdPos",
    "todayPos",
    "todayVol",
)
YESTERDAY_POSITION_FIELD_KEYS = (
    "yesterday_position",
    "yd_position",
    "yesterday_size",
    "yesterday_volume",
    "history_position",
    "history_size",
    "history_volume",
    "yd_volume",
    "YdPosition",
    "HistoryPosition",
    "YdVolume",
    "HistoryVolume",
    "ydPos",
    "yesterdayPos",
    "historyPos",
    "historyVol",
)
LONG_POSITION_FIELD_KEYS = (
    "long_position",
    "longPosition",
    "long_pos",
    "longPos",
    "long_size",
    "longSize",
    "long_qty",
    "longQty",
    "long_volume",
    "longVolume",
    "LongPosition",
    "LongVolume",
    "buy_position",
    "buyPosition",
)
SHORT_POSITION_FIELD_KEYS = (
    "short_position",
    "shortPosition",
    "short_pos",
    "shortPos",
    "short_size",
    "shortSize",
    "short_qty",
    "shortQty",
    "short_volume",
    "shortVolume",
    "ShortPosition",
    "ShortVolume",
    "sell_position",
    "sellPosition",
)
OKX_SIGNED_FEE_FIELD_KEYS = frozenset(
    {
        "fee",
        "position_fee",
        "position_commission",
        "trade_fee",
        "trade_commission",
        "fillFee",
        "fill_fee",
    }
)
EXPLICIT_NET_PNL_FIELD_KEYS = (
    "pnlcomm",
    "net_pnl",
    "netPnl",
    "netPNL",
    "net_position_pnl",
    "netPositionPnl",
    "netPositionPNL",
    "net_unrealized_pnl",
    "netUnrealizedPnl",
    "netUnrealizedPNL",
    "unrealized_pnl_after_fee",
    "unrealizedPnlAfterFee",
    "position_pnl_after_fee",
    "positionPnlAfterFee",
)
MARKABLE_NET_PNL_FIELD_KEYS = ("position_pnl", "pnl", "profit")
NET_PNL_FLAG_KEYS = (
    "position_pnl_is_net",
    "positionPnlIsNet",
    "pnl_is_net",
    "pnlIsNet",
    "profit_is_net",
    "profitIsNet",
    "position_pnl_includes_fee",
    "positionPnlIncludesFee",
    "pnl_includes_fee",
    "pnlIncludesFee",
    "profit_includes_fee",
    "profitIncludesFee",
    "position_pnl_includes_commission",
    "positionPnlIncludesCommission",
    "pnl_includes_commission",
    "pnlIncludesCommission",
    "profit_includes_commission",
    "profitIncludesCommission",
    "is_net_pnl",
    "isNetPnl",
)
INVERSE_CONTRACT_FLAG_KEYS = (
    "inverse",
    "is_inverse",
    "isInverse",
    "inverse_contract",
    "inverseContract",
)
RAW_ASSET_SPEC_FIELD_KEYS = (
    "multiplier",
    "mult",
    "inverse",
    "is_inverse",
    "isInverse",
    "inverse_contract",
    "inverseContract",
    "contract_notional_value",
    "okx_contract_value",
    "contract_multiplier",
    "contractMultiplier",
    "contract_size",
    "contractSize",
    "trade_contract_size",
    "tradeContractSize",
    "ctVal",
    "ctValCcy",
    "contract_value_currency",
    "contract_value_ccy",
    "ctMult",
    "volume_multiple",
    "asset_type",
    "instType",
    "contract_type",
    "ctType",
    "type",
    "contract",
    "linear",
    "base_asset",
    "baseCcy",
    "base",
    "quote_asset",
    "quoteCcy",
    "quote",
    "settle_currency",
    "settleCcy",
    "settle",
    "fee_currency",
    "feeCcy",
    "VolumeMultiple",
    "CONTRACT_MULTIPLIER",
    "price_tick",
    "tick_size",
    "price_unit",
    "tickSz",
    "PriceTick",
    "priceTick",
    "MIN_PRICE_CHANGE",
    "minPriceChange",
    "margin",
    "margin_rate",
    "marginRate",
    "margin_ratio",
    "marginRatio",
    "LongMarginRatio",
    "longMarginRatio",
    "ShortMarginRatio",
    "shortMarginRatio",
    "LongMarginRatioByMoney",
    "longMarginRatioByMoney",
    "ShortMarginRatioByMoney",
    "shortMarginRatioByMoney",
    "MARGIN_RATIO",
    "MARGIN_BUY",
    "MARGIN_SELL",
    "margin_amount",
    "marginAmount",
    "leverage",
    "lever",
    "max_leverage",
    "min_order_size",
    "min_qty",
    "minSz",
    "max_order_size",
    "max_qty",
    "maxLmtSz",
    "maxMktSz",
    "order_size_step",
    "qty_unit",
    "lotSz",
    "initial_margin_per_lot",
    "margin_initial",
    "marginInitial",
    "initial_margin_amount",
    "initialMargin",
    "initialMarginRatio",
    "LongMarginRatioByVolume",
    "longMarginRatioByVolume",
    "ShortMarginRatioByVolume",
    "shortMarginRatioByVolume",
    "MARGIN_PER_LOT",
    "LONG_MARGIN_AMOUNT",
    "SHORT_MARGIN_AMOUNT",
    "open_commission_rate",
    "openCommissionRate",
    "close_commission_rate",
    "closeCommissionRate",
    "close_today_commission_rate",
    "closeTodayCommissionRate",
    "close_yesterday_commission_rate",
    "closeYesterdayCommissionRate",
    "maker_commission_rate",
    "maker_fee_rate",
    "makerFeeRate",
    "taker_commission_rate",
    "taker_fee_rate",
    "takerFeeRate",
    "OpenRatioByMoney",
    "openRatioByMoney",
    "CloseRatioByMoney",
    "closeRatioByMoney",
    "CloseTodayRatioByMoney",
    "closeTodayRatioByMoney",
    "CloseYesterdayRatioByMoney",
    "closeYesterdayRatioByMoney",
    "OPEN_FEE_RATE",
    "openFeeRate",
    "CLOSE_FEE_RATE",
    "closeFeeRate",
    "CLOSE_TODAY_FEE_RATE",
    "closeTodayFeeRate",
    "CLOSE_YESTERDAY_FEE_RATE",
    "closeYesterdayFeeRate",
    "COMMISSION_OPEN_RATIO",
    "COMMISSION_CLOSE_RATIO",
    "COMMISSION_CLOSE_TODAY_RATIO",
    "COMMISSION_CLOSE_YESTERDAY_RATIO",
    "commission_amount",
    "commissionAmount",
    "open_fee_amount",
    "openFeeAmount",
    "open_commission_amount",
    "openCommissionAmount",
    "close_fee_amount",
    "closeFeeAmount",
    "close_commission_amount",
    "closeCommissionAmount",
    "close_today_fee_amount",
    "closeTodayFeeAmount",
    "close_today_commission_amount",
    "closeTodayCommissionAmount",
    "close_yesterday_fee_amount",
    "closeYesterdayFeeAmount",
    "close_yesterday_commission_amount",
    "closeYesterdayCommissionAmount",
    "OpenRatioByVolume",
    "openRatioByVolume",
    "CloseRatioByVolume",
    "closeRatioByVolume",
    "CloseTodayRatioByVolume",
    "closeTodayRatioByVolume",
    "CloseYesterdayRatioByVolume",
    "closeYesterdayRatioByVolume",
    "OPEN_FEE_AMOUNT",
    "OPEN_FEE_PER_LOT",
    "CLOSE_FEE_AMOUNT",
    "CLOSE_FEE_PER_LOT",
    "CLOSE_TODAY_FEE_AMOUNT",
    "CLOSE_TODAY_FEE_PER_LOT",
    "CLOSE_YESTERDAY_FEE_AMOUNT",
    "CLOSE_YESTERDAY_FEE_PER_LOT",
    "COMMISSION_OPEN_AMOUNT",
    "COMMISSION_CLOSE_AMOUNT",
    "COMMISSION_CLOSE_TODAY_AMOUNT",
    "COMMISSION_CLOSE_YESTERDAY_AMOUNT",
)
PRICE_PAYLOAD_FIELD_KEYS = (
    "mark_price",
    "markPrice",
    "markPx",
    "index_price",
    "indexPrice",
    "idxPx",
    "current_price",
    "latest_price",
    "last_price",
    "lastPrice",
    "LastPrice",
    "price",
    "market_price",
    "marketPrice",
    "mktPrice",
    "close",
    "last",
    "settlement_price",
    "SettlementPrice",
)
POSITION_SIZE_FIELD_KEYS = (
    "size",
    "volume",
    "position",
    "qty",
    "quantity",
    "trade_volume",
    "position_volume",
    "position_size",
    "positionSize",
    "position_qty",
    "positionQty",
    "position_quantity",
    "positionQuantity",
    "positionAmt",
    "pos",
    "pa",
    "contracts",
    "open_qty",
    "openQty",
    "open_volume",
    "openVolume",
    "net_qty",
    "netQty",
    "net_position",
    "netPosition",
    "net_position_size",
    "netPositionSize",
    "holding",
    "holdings",
    "Position",
    "Volume",
    "Qty",
    "Quantity",
    "TradeVolume",
)
BID_PRICE_FIELD_KEYS = (
    "bid_price",
    "bidPrice",
    "bidPx",
    "best_bid",
    "bestBid",
    "BidPrice1",
    "bid",
)
ASK_PRICE_FIELD_KEYS = (
    "ask_price",
    "askPrice",
    "askPx",
    "best_ask",
    "bestAsk",
    "AskPrice1",
    "ask",
)


def _safe_float(value: Any, default: float | None = None) -> float | None:
    if value in (None, ""):
        return default
    if isinstance(value, dict):
        for key in ("cost", "amount", "value", "balance", "total", "commission", "fee"):
            item = value.get(key)
            if item not in (None, ""):
                return _safe_float(item, default)
        return default
    if isinstance(value, (list, tuple)):
        numbers = [_safe_float(item) for item in value]
        valid_numbers = [number for number in numbers if number is not None]
        return sum(valid_numbers) if valid_numbers else default
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
        if match:
            try:
                return float(match.group(0))
            except ValueError:
                return default
    return default


def _first_number(*values: Any, default: float | None = None) -> float | None:
    for value in values:
        number = _safe_float(value)
        if number is not None:
            return number
    return default


def _first_text(*values: Any, default: str = "") -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return default


def _explicit_inverse_flag(*configs: dict[str, Any] | None) -> bool | None:
    for config in configs:
        if not isinstance(config, dict):
            continue
        for key in INVERSE_CONTRACT_FLAG_KEYS:
            value = config.get(key)
            if value in (None, ""):
                continue
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return value != 0
            text = str(value).strip().lower()
            if text in {"1", "true", "yes", "y", "inverse", "coin_margined"}:
                return True
            if text in {"0", "false", "no", "n", "linear"}:
                return False
    return None


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _first_value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _first_value_with_key(row: dict[str, Any], *keys: str) -> tuple[str | None, Any]:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return key, value
    return None, None


def _sum_signed_amounts(row: dict[str, Any], keys: Iterable[str]) -> float:
    total = 0.0
    seen: set[str] = set()
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        value = row.get(key)
        if value in (None, ""):
            continue
        amount = _safe_float(value)
        if amount is not None:
            total += amount
    return total


def _uses_okx_fee_sign(row: dict[str, Any], asset_spec: dict[str, Any] | None = None) -> bool:
    spec = asset_spec or {}
    text = " ".join(
        str(value or "").strip().lower()
        for value in (
            row.get("source"),
            row.get("asset_spec_source"),
            row.get("exchange"),
            row.get("exchange_id"),
            row.get("exchange_name"),
            row.get("exchange_nae"),
            row.get("gateway"),
            row.get("broker"),
            spec.get("source"),
            spec.get("asset_spec_source"),
            spec.get("exchange"),
            spec.get("exchange_id"),
            spec.get("exchange_name"),
            spec.get("exchange_nae"),
        )
    )
    return "okx" in text


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "signed"}


def _row_marks_pnl_as_net(row: dict[str, Any]) -> bool:
    return any(_truthy(row.get(key)) for key in NET_PNL_FLAG_KEYS)


def _internal_commission_from_exchange_fee(
    key: str | None,
    value: Any,
    *,
    row: dict[str, Any],
    asset_spec: dict[str, Any] | None = None,
) -> float:
    amount = _safe_float(value, 0.0) or 0.0
    if key in OKX_SIGNED_FEE_FIELD_KEYS and _uses_okx_fee_sign(row, asset_spec):
        return -amount
    return abs(amount)


def _normalize_decimal_rate(value: Any) -> float | None:
    number = _safe_float(value)
    if number is None:
        return None
    if number > 1:
        return number / 100.0
    return max(number, 0.0)


def _normalize_signed_decimal_rate(value: Any) -> float | None:
    number = _safe_float(value)
    if number is None:
        return None
    if abs(number) > 1:
        return number / 100.0
    return number


def _normalize_exchange_commission_rate(
    key: str | None,
    value: Any,
    *,
    source_text: str = "",
) -> float | None:
    number = _safe_float(value)
    if number is None:
        return None
    key_lower = str(key or "").strip().lower()
    if key_lower in {"makercommission", "takercommission"} and abs(number) > 1:
        return number / 10000.0
    if key_lower in {"makercommissionrate", "takercommissionrate"} and abs(number) > 1:
        return number / 10000.0
    rate = _normalize_signed_decimal_rate(number)
    if rate is None:
        return None
    if key_lower in {"makeru", "takeru"} or (
        key_lower in {"maker", "taker"} and "okx" in source_text
    ):
        return -rate
    return rate


_ASSET_SPEC_CONTAINER_KEYS = (
    "data",
    "result",
    "payload",
    "list",
    "rows",
    "items",
    "symbols",
    "instruments",
    "contracts",
    "markets",
)
_ASSET_SPEC_NESTED_DICT_KEYS = (
    "priceFilter",
    "price_filter",
    "lotSizeFilter",
    "lot_size_filter",
    "leverageFilter",
    "leverage_filter",
    "fee",
    "fees",
)


def _compact_symbol_text(value: Any) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", str(value or "")).upper()


def _payload_symbol_values(row: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in (
        "symbol",
        "data_name",
        "symbol_name",
        "instId",
        "instrument",
        "instrument_id",
        "InstrumentID",
        "REFERENCE_CODE",
        "localSymbol",
        "local_symbol",
        "pair",
        "id",
        "name",
        "contract",
        "contract_code",
        "contractCode",
    ):
        value = row.get(key)
        if value not in (None, ""):
            values.append(str(value).strip())
    return values


def _payload_matches_symbol(row: dict[str, Any], symbol: str) -> bool:
    if not symbol:
        return True
    aliases = _symbol_keys(symbol)
    candidates = {str(item or "").strip().upper() for item in aliases if str(item or "").strip()}
    candidates.update(_compact_symbol_text(item) for item in aliases if str(item or "").strip())
    for value in _payload_symbol_values(row):
        text = str(value or "").strip()
        if not text:
            continue
        if text.upper() in candidates or _compact_symbol_text(text) in candidates:
            return True
    return False


def _select_payload_row(payload: Any, symbol: str) -> dict[str, Any] | None:
    if not isinstance(payload, (list, tuple, set)):
        return None
    rows = [item for item in payload if isinstance(item, dict)]
    if not rows:
        return None
    if symbol:
        for row in rows:
            if _payload_matches_symbol(row, symbol):
                return row
        if len(rows) > 1:
            return None
    return rows[0]


def _select_symbol_keyed_payload(payload: Any, symbol: str) -> dict[str, Any] | None:
    if not isinstance(payload, dict) or not symbol:
        return None
    aliases = _symbol_keys(symbol)
    compact_aliases = {_compact_symbol_text(alias) for alias in aliases}
    for alias in aliases:
        item = payload.get(alias)
        if isinstance(item, dict):
            return dict(item)
    for key, item in payload.items():
        if not isinstance(item, dict):
            continue
        key_text = str(key or "").strip()
        if key_text in aliases or _compact_symbol_text(key_text) in compact_aliases:
            selected = dict(item)
            selected.setdefault("symbol", key_text)
            return selected
    return None


def _looks_like_symbol_keyed_payload(payload: dict[str, Any]) -> bool:
    dict_values = [value for value in payload.values() if isinstance(value, dict)]
    return len(dict_values) > 1 and len(dict_values) == len(payload)


def _flatten_asset_spec_payload(data: dict[str, Any]) -> dict[str, Any]:
    flattened = dict(data)
    for key in _ASSET_SPEC_NESTED_DICT_KEYS:
        nested = flattened.get(key)
        if isinstance(nested, dict):
            for nested_key, nested_value in nested.items():
                flattened.setdefault(str(nested_key), nested_value)

    filters = flattened.get("filters")
    if isinstance(filters, (list, tuple, set)):
        for item in filters:
            if not isinstance(item, dict):
                continue
            filter_type = str(item.get("filterType") or item.get("filter_type") or "").strip()
            for nested_key, nested_value in item.items():
                if nested_key in {"filterType", "filter_type"}:
                    continue
                flattened.setdefault(str(nested_key), nested_value)
                if filter_type:
                    flattened.setdefault(f"{filter_type}_{nested_key}", nested_value)
    return flattened


def _unwrap_payload_dict(raw: dict[str, Any], *, symbol: str = "") -> dict[str, Any]:
    data = dict(raw)
    for _ in range(10):
        for key in _ASSET_SPEC_CONTAINER_KEYS:
            payload = data.get(key)
            row: dict[str, Any] | None = None
            if isinstance(payload, dict):
                row = _select_symbol_keyed_payload(payload, symbol)
                if row is None:
                    if symbol and _looks_like_symbol_keyed_payload(payload):
                        continue
                    row = payload
            else:
                row = _select_payload_row(payload, symbol)
            if row is None:
                continue
            base = {
                item_key: item_value for item_key, item_value in data.items() if item_key != key
            }
            base.update(row)
            if base == data:
                return _flatten_asset_spec_payload(data)
            data = base
            break
        else:
            break
    return _flatten_asset_spec_payload(data)


def _normalize_ctp_commission_rate(value: Any) -> float | None:
    number = _safe_float(value)
    if number is None:
        return None
    if number > 0.01:
        return number / 10000.0
    return max(number, 0.0)


def _normalize_symbol(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "." in text:
        left, right = text.split(".", 1)
        left_text = left.strip()
        right_text = right.strip()
        left_exchange = left_text.upper()
        right_exchange = right_text.upper()
        if left_exchange in _CTP_EXCHANGES:
            return right_text
        if right_exchange in _CTP_EXCHANGES:
            return left_text
        return left_text
    if "_" in text:
        left, right = text.split("_", 1)
        left_text = left.strip()
        right_text = right.strip()
        left_exchange = left_text.upper()
        right_exchange = right_text.upper()
        if left_exchange in _CTP_EXCHANGES:
            return right_text
        if right_exchange in _CTP_EXCHANGES:
            return left_text
    return text


def _split_symbol_exchange(value: Any) -> tuple[str, str]:
    text = str(value or "").strip()
    if not text:
        return "", ""
    if "." in text:
        left, right = text.split(".", 1)
        left_text = left.strip()
        right_text = right.strip()
        left_exchange = left_text.upper()
        right_exchange = right_text.upper()
        if left_exchange in _CTP_EXCHANGES:
            return right_text, left_exchange
        if right_exchange in _CTP_EXCHANGES:
            return left_text, right_exchange
        return left_text, ""
    if "_" in text:
        left, right = text.split("_", 1)
        left_text = left.strip()
        right_text = right.strip()
        left_exchange = left_text.upper()
        right_exchange = right_text.upper()
        if left_exchange in _CTP_EXCHANGES:
            return right_text, left_exchange
        if right_exchange in _CTP_EXCHANGES:
            return left_text, right_exchange
    return text, ""


def symbol_aliases(symbol: Any) -> list[str]:
    """Return lookup aliases for exchange-prefixed and instrument-prefixed symbols."""
    raw = str(symbol or "").strip()
    instrument, exchange = _split_symbol_exchange(raw)
    keys = [raw, instrument, instrument.upper(), instrument.lower()]
    compact = re.sub(r"[^0-9A-Za-z]", "", instrument or raw)
    if compact:
        keys.extend([compact, compact.upper(), compact.lower()])
        compact_upper = compact.upper()
        for quote in _COMMON_QUOTE_SUFFIXES:
            if not compact_upper.endswith(quote) or len(compact_upper) <= len(quote):
                continue
            base = compact_upper[: -len(quote)]
            for separator in ("/", "-", "_"):
                keys.extend(
                    [
                        f"{base}{separator}{quote}",
                        f"{base.lower()}{separator}{quote.lower()}",
                    ]
                )
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


def _symbol_keys(symbol: Any) -> list[str]:
    return symbol_aliases(symbol)


def _query_symbol_keys(symbol: Any) -> list[str]:
    keys = list(_symbol_keys(symbol))
    normalized = _normalize_symbol(symbol)
    if normalized:
        keys.append(normalized)
    result: list[str] = []
    seen: set[str] = set()
    for key in keys:
        text = str(key or "").strip()
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


def _product_code(symbol: Any) -> str:
    match = re.match(r"([A-Za-z]+)", _normalize_symbol(symbol))
    return match.group(1).upper() if match else ""


def _compact_underlying_symbol(symbol: Any) -> str:
    compact = _compact_symbol_text(_normalize_symbol(symbol))
    if len(compact) >= 6:
        head = compact[:6]
        if head in _MT5_METAL_CONTRACT_SIZES:
            return head
        if head[:3] in _FIAT_CURRENCIES and head[3:6] in _FIAT_CURRENCIES:
            return head
    return compact


def _query_local_otc_spec(symbol: str) -> dict[str, Any]:
    # Import lazily so the compatibility facade finishes initialising before the
    # decomposed normalizer imports its shared helpers from this module.
    from app.services.asset_info.normalization import normalize_asset_spec

    compact = _compact_underlying_symbol(symbol)
    if compact in _MT5_METAL_CONTRACT_SIZES:
        return normalize_asset_spec(
            {
                "symbol": symbol,
                "asset_type": "commodity",
                "exchange": "MT5",
                "contract_size": _MT5_METAL_CONTRACT_SIZES[compact],
            },
            symbol=symbol,
            source="local_mt5_defaults",
        )
    if len(compact) == 6 and compact[:3] in _FIAT_CURRENCIES and compact[3:] in _FIAT_CURRENCIES:
        return normalize_asset_spec(
            {
                "symbol": symbol,
                "asset_type": "forex",
                "exchange": "MT5",
                "contract_size": _MT5_FOREX_CONTRACT_SIZE,
            },
            symbol=symbol,
            source="local_mt5_defaults",
        )
    return {}


def _object_get(obj: Any, *names: str) -> Any:
    for name in names:
        if isinstance(obj, dict) and name in obj:
            return obj.get(name)
        if hasattr(obj, name):
            return getattr(obj, name)
    return None


def _call_or_value(value: Any) -> Any:
    if callable(value):
        try:
            return value()
        except TypeError:
            return None
    return value


def _lookup_payload_value(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload.get(key)
    lower_map = {str(key).lower(): value for key, value in payload.items()}
    for key in keys:
        value = lower_map.get(key.lower())
        if value not in (None, ""):
            return value
    return None


def _positive_price(value: Any) -> float | None:
    number = _safe_float(value)
    if number is not None and number > 0:
        return number
    return None


def _price_from_payload(payload: Any) -> float | None:
    if isinstance(payload, dict):
        price = _positive_price(_lookup_payload_value(payload, *PRICE_PAYLOAD_FIELD_KEYS))
        if price is not None:
            return price
        bid = _positive_price(_lookup_payload_value(payload, *BID_PRICE_FIELD_KEYS))
        ask = _positive_price(_lookup_payload_value(payload, *ASK_PRICE_FIELD_KEYS))
        if bid is not None and ask is not None:
            return (bid + ask) / 2.0
        for key in ("data", "result", "ticker", "tick", "payload", "rows", "items", "list"):
            nested = payload.get(key)
            if nested is payload:
                continue
            price = _price_from_payload(nested)
            if price is not None:
                return price
        return None

    if isinstance(payload, (list, tuple, set)):
        for item in payload:
            price = _price_from_payload(item)
            if price is not None:
                return price
        return None

    price = _positive_price(payload)
    if price is not None:
        return price

    for name in (
        *PRICE_PAYLOAD_FIELD_KEYS,
        "get_mark_price",
        "get_last_price",
        "get_price",
    ):
        price = _positive_price(_call_or_value(getattr(payload, name, None)))
        if price is not None:
            return price
    bid = _positive_price(
        _call_or_value(_object_get(payload, *BID_PRICE_FIELD_KEYS, "get_bid_price"))
    )
    ask = _positive_price(
        _call_or_value(_object_get(payload, *ASK_PRICE_FIELD_KEYS, "get_ask_price"))
    )
    if bid is not None and ask is not None:
        return (bid + ask) / 2.0
    return None


def _extract_existing_metadata(config: dict[str, Any], symbol: str) -> dict[str, Any]:
    for container_key in ("contract_metadata", "contracts", "contract_specs", "instrument_specs"):
        container = config.get(container_key)
        if not isinstance(container, dict):
            continue
        for key in _symbol_keys(symbol):
            item = container.get(key)
            if isinstance(item, dict):
                return dict(item)
    return {}


def gateway_position_symbol(row: dict[str, Any], fallback: str = "") -> str:
    return str(
        _first_value(
            row,
            "data_name",
            "symbol",
            "instrument",
            "InstrumentID",
            "instId",
            "trade_symbol",
            "contract_symbol",
            "position_symbol_name",
            "symbol_name",
            "local_symbol",
            "localSymbol",
            "contractDesc",
            "contract_desc",
            "description",
            "ticker",
            "conid",
        )
        or fallback
        or ""
    ).strip()


def _side_from_position_value(key: str, value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if text in {"long", "buy", "bought", "position_type_buy", "deal_type_buy"}:
        return "long"
    if text in {"short", "sell", "sold", "position_type_sell", "deal_type_sell"}:
        return "short"

    try:
        code = int(float(value))
    except (TypeError, ValueError):
        code = None
    key_text = str(key or "").strip().lower()
    if key_text in {"trade_action", "position_type", "type"}:
        if code == 0:
            return "long"
        if code == 1:
            return "short"
    if key_text in {"posidirection", "posi_direction", "position_direction"}:
        if code == 2:
            return "long"
        if code == 3:
            return "short"
    if key_text in {"positionidx", "position_idx"}:
        if code == 1:
            return "long"
        if code == 2:
            return "short"
    return None


def _position_side(row: dict[str, Any], signed_size: float | None = None) -> str | None:
    for key in (
        "side",
        "posSide",
        "positionSide",
        "position_side",
        "PositionSide",
        "holdSide",
        "positionIdx",
        "position_idx",
        "trade_action",
        "position_type",
        "type",
        "PosiDirection",
        "posi_direction",
        "position_direction",
        "direction",
    ):
        side = _side_from_position_value(key, row.get(key))
        if side:
            return side
    if signed_size is not None:
        if signed_size > 0:
            return "long"
        if signed_size < 0:
            return "short"
    return None


def signed_gateway_size(row: dict[str, Any]) -> float:
    long_position = _first_number(*(row.get(key) for key in LONG_POSITION_FIELD_KEYS))
    short_position = _first_number(*(row.get(key) for key in SHORT_POSITION_FIELD_KEYS))
    raw_size_value = _first_value(row, *POSITION_SIZE_FIELD_KEYS)
    raw_size_number = _first_number(raw_size_value)
    has_explicit_size = raw_size_value not in (None, "") and raw_size_number is not None
    raw_size = raw_size_number or 0.0
    if (
        not has_explicit_size
        and abs(raw_size) <= 1e-12
        and (long_position is not None or short_position is not None)
    ):
        long_size = max(long_position or 0.0, 0.0)
        short_size = max(short_position or 0.0, 0.0)
        if long_size > 1e-12 or short_size > 1e-12:
            return long_size - short_size
    direction = _position_side(row)
    if direction == "short":
        return -abs(raw_size)
    return raw_size


_LONG_MARKET_VALUE_FIELD_KEYS = (
    "long_market_value",
    "longMarketValue",
    "long_position_value",
    "longPositionValue",
    "long_notional",
    "longNotional",
)
_SHORT_MARKET_VALUE_FIELD_KEYS = (
    "short_market_value",
    "shortMarketValue",
    "short_position_value",
    "shortPositionValue",
    "short_notional",
    "shortNotional",
)
_MARKET_VALUE_FIELD_KEYS = (
    "market_value",
    "marketValue",
    "MarketValue",
    "mktValue",
    "positionValue",
    "position_value",
    "notionalUsd",
    "notional_usd",
    "notional",
    "notionalValue",
    "notional_value",
    "position_notional_usd",
    "position_notional",
    "positionNotional",
    "value",
)
_LONG_PRICE_FIELD_KEYS = (
    "long_price",
    "longPrice",
    "long_avg_price",
    "longAvgPrice",
    "long_avgPx",
    "longAvgPx",
    "long_entry_price",
    "longEntryPrice",
    "long_open_price",
    "longOpenPrice",
    "long_average_price",
    "longAveragePrice",
    "long_avg_cost",
    "longAvgCost",
)
_SHORT_PRICE_FIELD_KEYS = (
    "short_price",
    "shortPrice",
    "short_avg_price",
    "shortAvgPrice",
    "short_avgPx",
    "shortAvgPx",
    "short_entry_price",
    "shortEntryPrice",
    "short_open_price",
    "shortOpenPrice",
    "short_average_price",
    "shortAveragePrice",
    "short_avg_cost",
    "shortAvgCost",
)
_PRICE_FIELD_KEYS = (
    "price",
    "avg_price",
    "average_price",
    "price_open",
    "entry_price",
    "avgCost",
    "avgPrice",
    "avgPx",
    "avg_entry_price",
    "avgEntryPrice",
    "entryPrice",
    "open_avg_price",
    "openAvgPrice",
    "ep",
    "Price",
    "AveragePrice",
)
_LONG_PNL_FIELD_KEYS = (
    "long_pnl",
    "longPnl",
    "longPNL",
    "long_position_pnl",
    "longPositionPnl",
    "longPositionPNL",
    "long_unrealized_pnl",
    "longUnrealizedPnl",
    "longUnrealizedPNL",
    "long_unrealized_profit",
    "longUnrealizedProfit",
    "long_profit",
    "longProfit",
)
_SHORT_PNL_FIELD_KEYS = (
    "short_pnl",
    "shortPnl",
    "shortPNL",
    "short_position_pnl",
    "shortPositionPnl",
    "shortPositionPNL",
    "short_unrealized_pnl",
    "shortUnrealizedPnl",
    "shortUnrealizedPNL",
    "short_unrealized_profit",
    "shortUnrealizedProfit",
    "short_profit",
    "shortProfit",
)
_POSITION_SPLIT_DROP_KEYS = (
    *_MARKET_VALUE_FIELD_KEYS,
    *_LONG_MARKET_VALUE_FIELD_KEYS,
    *_SHORT_MARKET_VALUE_FIELD_KEYS,
    *_LONG_PRICE_FIELD_KEYS,
    *_SHORT_PRICE_FIELD_KEYS,
    *_LONG_PNL_FIELD_KEYS,
    *_SHORT_PNL_FIELD_KEYS,
    "gross_pnl",
    "position_unrealized_pnl",
    "position_unrealised_pnl",
    "position_profit",
    "PositionProfit",
    "unrealized_profit",
    "unrealised_profit",
    "unRealizedProfit",
    "UnrealizedPnL",
    "unrealizedPnl",
    "unrealisedPnl",
    "unrealized_pnl",
    "unrealised_pnl",
    "unrealizedPNL",
    "unrealisedPNL",
    "unrealizedpnl",
    "unrealisedpnl",
    "floating_pnl",
    "profit",
    "upl",
    "up",
    "position_pnl",
    "pnl",
    "pnlcomm",
    "net_pnl",
    "netPnl",
    "netPNL",
    "net_position_pnl",
    "netPositionPnl",
    "netPositionPNL",
    "net_unrealized_pnl",
    "netUnrealizedPnl",
    "netUnrealizedPNL",
    "unrealized_pnl_after_fee",
    "unrealizedPnlAfterFee",
    "position_pnl_after_fee",
    "positionPnlAfterFee",
    "commission",
    "comm",
    "fee",
    "fees",
    "execFee",
    "exec_fee",
    "execFeeV2",
    "exec_fee_v2",
    "open_commission",
    "position_fee",
    "position_commission",
    "trade_fee",
    "trade_commission",
    "commission_amount",
    "Commission",
    "commission_source",
    "commission_signed",
    *CARRY_PNL_FIELD_KEYS,
)


def _set_position_side_fields(
    item: dict[str, Any],
    *,
    side: str,
    signed_size: float,
) -> None:
    item["size"] = signed_size
    item["direction"] = side
    item["side"] = side
    item["posSide"] = side
    item["positionSide"] = side
    item["position_side"] = side
    item["PositionSide"] = side
    item["holdSide"] = side


def _set_side_position_sizes(
    item: dict[str, Any],
    *,
    side: str,
    size: float,
) -> None:
    own_keys = LONG_POSITION_FIELD_KEYS if side == "long" else SHORT_POSITION_FIELD_KEYS
    other_keys = SHORT_POSITION_FIELD_KEYS if side == "long" else LONG_POSITION_FIELD_KEYS
    for key in own_keys:
        item[key] = size
    for key in other_keys:
        item[key] = 0.0


def _copy_first_number(
    item: dict[str, Any],
    row: dict[str, Any],
    keys: tuple[str, ...],
    targets: tuple[str, ...],
    *,
    absolute: bool = False,
) -> None:
    value = _first_number(*(row.get(key) for key in keys))
    if value is None:
        return
    value = abs(value) if absolute else value
    for target in targets:
        item[target] = value


def _copy_allocated_signed_amount(
    item: dict[str, Any],
    row: dict[str, Any],
    keys: tuple[str, ...],
    target: str,
    ratio: float,
) -> None:
    if not any(key in row and row.get(key) not in (None, "") for key in keys):
        return
    item[target] = _sum_signed_amounts(row, keys) * ratio


def _clear_split_aggregate_fields(item: dict[str, Any]) -> None:
    for key in _POSITION_SPLIT_DROP_KEYS:
        item.pop(key, None)


def split_bidirectional_position_row(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Split a single exchange hedge-mode row into side-specific rows.

    Some gateways expose one row containing both long and short quantities for
    the same instrument. Valuation must run per side; netting that row to zero
    hides the position and loses the side-specific commission and PnL.
    """
    if not isinstance(row, dict):
        return []

    item = dict(row)
    long_position = _first_number(*(item.get(key) for key in LONG_POSITION_FIELD_KEYS))
    short_position = _first_number(*(item.get(key) for key in SHORT_POSITION_FIELD_KEYS))
    long_size = max(long_position or 0.0, 0.0)
    short_size = max(short_position or 0.0, 0.0)
    if long_size <= 1e-12 or short_size <= 1e-12:
        return [item]

    split_rows: list[dict[str, Any]] = []
    for side, side_size, market_keys, price_keys, pnl_keys in (
        (
            "long",
            long_size,
            _LONG_MARKET_VALUE_FIELD_KEYS,
            _LONG_PRICE_FIELD_KEYS,
            _LONG_PNL_FIELD_KEYS,
        ),
        (
            "short",
            short_size,
            _SHORT_MARKET_VALUE_FIELD_KEYS,
            _SHORT_PRICE_FIELD_KEYS,
            _SHORT_PNL_FIELD_KEYS,
        ),
    ):
        side_row = dict(item)
        _clear_split_aggregate_fields(side_row)
        total_side_size = max(long_size + short_size, 1e-12)
        side_ratio = side_size / total_side_size
        _set_position_side_fields(
            side_row,
            side=side,
            signed_size=side_size if side == "long" else -side_size,
        )
        _set_side_position_sizes(side_row, side=side, size=side_size)
        _copy_first_number(
            side_row,
            item,
            market_keys,
            ("market_value", "position_value", "value"),
            absolute=True,
        )
        _copy_first_number(side_row, item, price_keys, _PRICE_FIELD_KEYS)
        _copy_first_number(side_row, item, pnl_keys, ("gross_pnl",))
        _copy_allocated_signed_amount(
            side_row,
            item,
            CARRY_PNL_FIELD_KEYS,
            "swap",
            side_ratio,
        )
        split_rows.append(side_row)

    return split_rows


def _compact_symbol(value: Any) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", str(value or "")).upper()


def _trade_symbol(row: dict[str, Any], fallback: str = "") -> str:
    return str(
        _first_value(
            row,
            "__query_symbol",
            "query_symbol",
            "data_name",
            "symbol",
            "instrument",
            "InstrumentID",
            "instId",
            "trade_symbol",
            "position_symbol_name",
            "symbol_name",
        )
        or fallback
        or ""
    ).strip()


def _trade_matches_symbol(row: dict[str, Any], symbol: str) -> bool:
    expected = {_compact_symbol(item) for item in symbol_aliases(symbol)}
    expected = {item for item in expected if item}
    if not expected:
        return True
    trade_symbol = _compact_symbol(_trade_symbol(row))
    return not trade_symbol or trade_symbol in expected


def _trade_position_side(row: dict[str, Any]) -> str | None:
    for key in (
        "posSide",
        "positionSide",
        "position_side",
        "PositionSide",
        "holdSide",
        "positionIdx",
        "position_idx",
        "ps",
    ):
        side = _side_from_position_value(key, row.get(key))
        if side:
            return side
    return None


def _trade_matches_position_side(row: dict[str, Any], position_side: str | None) -> bool:
    if position_side not in {"long", "short"}:
        return True
    trade_side = _trade_position_side(row)
    return trade_side is None or trade_side == position_side


def _trade_signed_size(row: dict[str, Any]) -> float:
    raw_size = (
        _first_number(
            _first_value(
                row,
                "size",
                "volume",
                "qty",
                "quantity",
                "fillSz",
                "fill_size",
                "execQty",
                "exec_qty",
                "trade_volume",
                "TradeVolume",
            ),
            default=0.0,
        )
        or 0.0
    )
    if raw_size < 0:
        return raw_size
    side = (
        str(
            _first_value(
                row,
                "side",
                "trade_side",
                "direction",
                "action",
                "S",
            )
            or ""
        )
        .strip()
        .lower()
    )
    if side in {"sell", "short", "s"}:
        return -abs(raw_size)
    if side in {"buy", "long", "b"}:
        return abs(raw_size)
    return raw_size


def _trade_commission(
    row: dict[str, Any], asset_spec: dict[str, Any] | None = None
) -> float | None:
    key, value = _first_value_with_key(
        row,
        "trade_commission",
        "tradeCommission",
        "tradeFee",
        "trade_fee",
        "broker_commission",
        "brokerCommission",
        "fillFee",
        "fill_fee",
        "execFee",
        "exec_fee",
        "execFeeV2",
        "exec_fee_v2",
        "execCommission",
        "exec_commission",
        "fee",
        "feeAmount",
        "commission",
        "comm",
        "commissionAmount",
        "Commission",
    )
    if value in (None, ""):
        return None
    commission = _internal_commission_from_exchange_fee(key, value, row=row, asset_spec=asset_spec)
    conversion_rate = _fee_valuation_conversion_rate(
        row,
        _trade_symbol(row),
        asset_spec,
    )
    if conversion_rate is None:
        return None
    return commission * conversion_rate


def _asset_spec_has_nonzero_fee(asset_spec: dict[str, Any] | None) -> bool:
    if not isinstance(asset_spec, dict):
        return False
    for key in (
        "commission_rate",
        "open_commission_rate",
        "close_commission_rate",
        "close_today_commission_rate",
        "close_yesterday_commission_rate",
        "maker_commission_rate",
        "maker_fee_rate",
        "taker_commission_rate",
        "taker_fee_rate",
        "commission_amount",
        "open_commission_amount",
        "close_commission_amount",
        "close_today_commission_amount",
        "close_yesterday_commission_amount",
    ):
        number = _safe_float(asset_spec.get(key))
        if number is not None and abs(number) > 1e-12:
            return True
    return False


def _currency_code(value: Any) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", str(value or "")).upper()


def _is_inverse_contract_spec(
    row: dict[str, Any],
    asset_spec: dict[str, Any] | None = None,
) -> bool:
    spec = asset_spec or {}
    explicit_flag = _explicit_inverse_flag(row, spec)
    if explicit_flag is not None:
        return explicit_flag

    contract_type = _first_text(
        row.get("contract_type"),
        row.get("ctType"),
        row.get("contractType"),
        row.get("category"),
        spec.get("contract_type"),
        spec.get("ctType"),
        spec.get("contractType"),
        spec.get("category"),
    ).lower()
    if "inverse" in contract_type:
        return True
    if "linear" in contract_type:
        return False

    contract_ccy = _currency_code(
        _first_text(
            row.get("contract_value_currency"),
            row.get("contract_value_ccy"),
            row.get("ctValCcy"),
            spec.get("contract_value_currency"),
            spec.get("contract_value_ccy"),
            spec.get("ctValCcy"),
        )
    )
    if not contract_ccy:
        return False
    base_ccy = _currency_code(
        _first_text(
            row.get("base_asset"), row.get("baseCcy"), spec.get("base_asset"), spec.get("baseCcy")
        )
    )
    quote_ccy = _currency_code(
        _first_text(
            row.get("quote_asset"),
            row.get("quoteCcy"),
            spec.get("quote_asset"),
            spec.get("quoteCcy"),
        )
    )
    settle_ccy = _currency_code(
        _first_text(
            row.get("settle_currency"),
            row.get("settleCcy"),
            row.get("fee_currency"),
            row.get("feeCcy"),
            spec.get("settle_currency"),
            spec.get("settleCcy"),
            spec.get("fee_currency"),
            spec.get("feeCcy"),
        )
    )
    if quote_ccy and contract_ccy == quote_ccy and contract_ccy != base_ccy:
        return True
    return bool(base_ccy and settle_ccy == base_ccy and contract_ccy != base_ccy)


def _trade_fee_currency(row: dict[str, Any]) -> str:
    fee_currency = _nested_fee_currency(
        row.get("fee"),
        row.get("fees"),
        row.get("commission"),
        row.get("comm"),
        row.get("Commission"),
        row.get("commissionAmount"),
        row.get("trade_fee"),
        row.get("tradeFee"),
        row.get("fillFee"),
        row.get("execFee"),
        row.get("execCommission"),
    )
    return _currency_code(
        _first_value(
            row,
            "fee_currency",
            "trade_fee_currency",
            "commissionAsset",
            "commission_asset",
            "feeCurrency",
            "fillFeeCcy",
            "fill_fee_currency",
            "feeCcy",
            "fee_ccy",
        )
        or fee_currency
    )


def _nested_fee_currency(*values: Any) -> str:
    currencies: list[str] = []
    seen: set[str] = set()

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            currency = _first_text(
                value.get("currency"),
                value.get("ccy"),
                value.get("asset"),
                value.get("coin"),
                value.get("fee_currency"),
                value.get("feeCurrency"),
                value.get("feeCcy"),
                value.get("commissionAsset"),
                value.get("commission_asset"),
            )
            code = _currency_code(currency)
            if code and code not in seen:
                seen.add(code)
                currencies.append(code)
            for nested_key in ("fee", "fees", "commission", "comm"):
                nested = value.get(nested_key)
                if nested is not value:
                    collect(nested)
        elif isinstance(value, (list, tuple, set)):
            for item in value:
                collect(item)

    for value in values:
        collect(value)
    if not currencies:
        return ""
    return currencies[0] if len(currencies) == 1 else "mixed"


def _trade_price(row: dict[str, Any]) -> float | None:
    return _positive_price(
        _first_value(
            row,
            "price",
            "fillPx",
            "fill_px",
            "execPrice",
            "exec_price",
            "avgPx",
            "avg_price",
            "avgPrice",
            "lastPrice",
            "last_price",
            "markPx",
            "mark_price",
            "L",
            "p",
        )
    )


_RAW_EXCHANGE_GROSS_PNL_KEYS = frozenset(
    {
        "position_unrealized_pnl",
        "position_unrealised_pnl",
        "unrealized_profit",
        "unrealised_profit",
        "unrealizedProfit",
        "unrealisedProfit",
        "unRealizedProfit",
        "UnrealizedPnL",
        "unrealizedPnl",
        "unrealisedPnl",
        "unrealized_pnl",
        "unrealised_pnl",
        "unrealizedPNL",
        "unrealisedPNL",
        "unrealizedpnl",
        "unrealisedpnl",
        "floating_pnl",
        "upl",
        "up",
        "position_profit",
        "PositionProfit",
    }
)
_RECALCULABLE_POSITION_PNL_KEYS = frozenset(
    (*MARKABLE_NET_PNL_FIELD_KEYS, "gross_pnl", "position_profit", "PositionProfit")
)


def _pnl_currency(row: dict[str, Any]) -> str:
    return _currency_code(
        _first_value(
            row,
            "pnl_currency",
            "pnlCurrency",
            "pnlCcy",
            "uplCcy",
            "unrealizedPnlCurrency",
            "unrealisedPnlCurrency",
            "profit_currency",
            "profitCurrency",
            "currency",
            "ccy",
        )
    )


def _quote_currency_candidates(symbol: str, asset_spec: dict[str, Any] | None = None) -> set[str]:
    spec = asset_spec or {}
    candidates = {
        _currency_code(
            _first_value(spec, "valuation_currency", "quote_asset", "quote_currency", "quoteCcy")
        )
    }
    if _is_inverse_contract_spec({}, spec):
        candidates.add(
            _currency_code(
                _first_value(
                    spec,
                    "contract_value_currency",
                    "contract_value_ccy",
                    "ctValCcy",
                )
            )
        )
    compact = _compact_symbol(symbol)
    for quote in _COMMON_QUOTE_SUFFIXES:
        if compact.endswith(quote) and len(compact) > len(quote):
            candidates.add(quote)
    return {item for item in candidates if item}


def _base_currency_candidates(symbol: str, asset_spec: dict[str, Any] | None = None) -> set[str]:
    spec = asset_spec or {}
    candidates = {
        _currency_code(
            _first_value(
                spec,
                "base_asset",
                "base_currency",
                "baseCcy",
                "settle_currency",
                "settleCcy",
                "margin_asset",
                "marginAsset",
                "margin_coin",
                "marginCoin",
            )
        )
    }
    compact = _compact_symbol(symbol)
    for quote in _COMMON_QUOTE_SUFFIXES:
        if compact.endswith(quote) and len(compact) > len(quote):
            candidates.add(compact[: -len(quote)])
    return {item for item in candidates if item}


def _fee_valuation_conversion_rate(
    row: dict[str, Any],
    symbol: str,
    asset_spec: dict[str, Any] | None = None,
) -> float | None:
    fee_currency = _trade_fee_currency(row)
    if not fee_currency:
        return 1.0
    if fee_currency in _quote_currency_candidates(symbol, asset_spec):
        return 1.0
    if fee_currency in _base_currency_candidates(symbol, asset_spec):
        price = (
            _trade_price(row) or _price_from_payload(row) or _price_from_payload(asset_spec or {})
        )
        if price and price > 0:
            return price
    return None


def _pnl_valuation_conversion_rate(
    row: dict[str, Any],
    symbol: str,
    asset_spec: dict[str, Any] | None = None,
    *,
    current_price: float | None = None,
    inverse_contract: bool = False,
    field_key: str | None = None,
) -> float | None:
    currency = _pnl_currency(row)
    if currency:
        if currency in _quote_currency_candidates(symbol, asset_spec):
            return 1.0
        if currency in _base_currency_candidates(symbol, asset_spec):
            price = current_price or _trade_price(row) or _price_from_payload(row)
            if price and price > 0:
                return price
            return None
        return 1.0

    if inverse_contract and str(field_key or "") in _RAW_EXCHANGE_GROSS_PNL_KEYS:
        settlement_currency = _currency_code(
            _first_value(
                row,
                "settle_currency",
                "settleCcy",
                "settleCoin",
            )
        )
        if not settlement_currency and isinstance(asset_spec, dict):
            settlement_currency = _currency_code(
                _first_value(asset_spec, "settle_currency", "settleCcy", "settleCoin")
            )
        if settlement_currency and settlement_currency in _quote_currency_candidates(
            symbol,
            asset_spec,
        ):
            return 1.0
        price = current_price or _trade_price(row) or _price_from_payload(row)
        if price and price > 0:
            return price
        return None
    return 1.0


def _normalized_pnl_amount(
    row: dict[str, Any],
    symbol: str,
    asset_spec: dict[str, Any] | None = None,
    *,
    field_key: str | None = None,
    value: Any = None,
    current_price: float | None = None,
    inverse_contract: bool = False,
) -> float | None:
    amount = _safe_float(value)
    if amount is None:
        return None
    conversion_rate = _pnl_valuation_conversion_rate(
        row,
        symbol,
        asset_spec,
        current_price=current_price,
        inverse_contract=inverse_contract,
        field_key=field_key,
    )
    if conversion_rate is None:
        return None
    return amount * conversion_rate


def _should_recalculate_generic_pnl(
    *,
    field_key: str | None,
    explicit_net_pnl_value: Any,
    size: float,
    entry_price: float,
    current_price: Any,
    multiplier: float,
    has_multiplier: bool,
) -> bool:
    if explicit_net_pnl_value not in (None, ""):
        return False
    if field_key not in _RECALCULABLE_POSITION_PNL_KEYS:
        return False
    if not has_multiplier:
        return False
    current_price_number = _safe_float(current_price)
    return (
        abs(size) > 1e-12
        and entry_price > 0
        and current_price_number is not None
        and current_price_number > 0
        and multiplier > 0
    )


def _numbers_close(left: float, right: float) -> bool:
    return abs(left - right) <= max(abs(left), abs(right), 1.0) * 1e-6


def _should_recalculate_unscaled_exchange_pnl(
    *,
    field_key: str | None,
    explicit_net_pnl_value: Any,
    explicit_gross_pnl_value: Any,
    size: float,
    entry_price: float,
    current_price: Any,
    multiplier: float,
    has_multiplier: bool,
    inverse_contract: bool,
) -> bool:
    if explicit_net_pnl_value not in (None, ""):
        return False
    if field_key not in _RAW_EXCHANGE_GROSS_PNL_KEYS:
        return False
    if inverse_contract or not has_multiplier or multiplier <= 1.0 + 1e-12:
        return False
    current_price_number = _safe_float(current_price)
    explicit = _safe_float(explicit_gross_pnl_value)
    if (
        abs(size) <= 1e-12
        or entry_price <= 0
        or current_price_number is None
        or current_price_number <= 0
        or explicit is None
    ):
        return False
    scaled = (current_price_number - entry_price) * size * multiplier
    unscaled = (current_price_number - entry_price) * size
    if _numbers_close(explicit, scaled):
        return False
    return _numbers_close(explicit, unscaled)


def _valuation_currency_candidates(
    symbol: str,
    asset_spec: dict[str, Any] | None = None,
) -> set[str]:
    spec = asset_spec or {}
    candidates = _quote_currency_candidates(symbol, spec)
    if _is_inverse_contract_spec({}, spec):
        candidates.update(_base_currency_candidates(symbol, spec))
    return candidates


def _trade_fee_currency_is_compatible(
    row: dict[str, Any],
    symbol: str,
    asset_spec: dict[str, Any] | None = None,
) -> bool:
    return _fee_valuation_conversion_rate(row, symbol, asset_spec) is not None


def _trade_time_key(row: dict[str, Any], index: int) -> tuple[float, int]:
    value = _first_value(
        row,
        "trade_time",
        "time",
        "timestamp",
        "ts",
        "execTime",
        "exec_time",
        "fillTime",
        "uTime",
        "cTime",
        "transactTime",
    )
    number = _safe_float(value)
    return (number if number is not None else float(index), index)


def _open_trade_commission_for_position(
    *,
    symbol: str,
    size: float,
    trades: Iterable[dict[str, Any]] | None,
    asset_spec: dict[str, Any] | None = None,
    position_side: str | None = None,
) -> tuple[float | None, str | None]:
    if not trades or abs(size) <= 1e-12:
        return None, None
    matched = [
        dict(row)
        for row in trades
        if isinstance(row, dict)
        and _trade_matches_symbol(row, symbol)
        and _trade_matches_position_side(row, position_side)
    ]
    if not matched:
        return None, None
    ordered = sorted(enumerate(matched), key=lambda item: _trade_time_key(item[1], item[0]))

    lots: list[dict[str, Any]] = []
    blocked_reason: str | None = None
    for _index, row in ordered:
        signed_size = _trade_signed_size(row)
        if abs(signed_size) <= 1e-12:
            continue
        has_fee_field = any(
            _first_value(row, key) not in (None, "")
            for key in (
                "trade_commission",
                "tradeCommission",
                "tradeFee",
                "trade_fee",
                "broker_commission",
                "brokerCommission",
                "fillFee",
                "fill_fee",
                "execFee",
                "exec_fee",
                "execFeeV2",
                "exec_fee_v2",
                "execCommission",
                "exec_commission",
                "fee",
                "feeAmount",
                "commission",
                "comm",
                "commissionAmount",
                "Commission",
            )
        )
        fee_compatible = _trade_fee_currency_is_compatible(row, symbol, asset_spec)
        fee = _trade_commission(row, asset_spec) if has_fee_field and fee_compatible else None
        if has_fee_field and not fee_compatible:
            blocked_reason = "commission_currency_mismatch"

        sign = 1.0 if signed_size > 0 else -1.0
        remaining = abs(signed_size)
        original = remaining

        while lots and remaining > 1e-12 and lots[0]["qty"] * sign < 0:
            lot = lots[0]
            lot_abs = abs(lot["qty"])
            closed = min(lot_abs, remaining)
            if lot_abs > 1e-12:
                lot["fee"] *= max((lot_abs - closed) / lot_abs, 0.0)
            lot["qty"] += sign * closed
            remaining -= closed
            if abs(lot["qty"]) <= 1e-12:
                lots.pop(0)

        if remaining > 1e-12:
            lots.append(
                {
                    "qty": sign * remaining,
                    "fee": (fee or 0.0) * (remaining / original if original > 1e-12 else 0.0),
                    "fee_valid": fee is not None,
                }
            )

    open_size = sum(lot["qty"] for lot in lots)
    tolerance = max(abs(size) * 1e-8, 1e-10)
    if abs(open_size - size) > tolerance:
        return None, None
    if not lots or any(not lot.get("fee_valid") for lot in lots):
        return None, blocked_reason
    return sum(lot["fee"] for lot in lots), None


def __getattr__(name: str) -> Any:
    """Lazily expose moved compatibility helpers without an import cycle."""
    from app.services import asset_info
    try:
        value = getattr(asset_info, name)
    except AttributeError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    globals()[name] = value
    return value
