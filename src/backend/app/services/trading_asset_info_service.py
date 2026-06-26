"""Resolve and persist trading asset specifications for live strategies."""

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
COMMISSION_FIELD_KEYS = (
    "commission",
    "comm",
    "fee",
    "fees",
    "execFee",
    "exec_fee",
    "open_commission",
    "position_fee",
    "position_commission",
    "trade_fee",
    "trade_commission",
    "commission_amount",
    "Commission",
    "fillFee",
    "fill_fee",
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
    "contract_size",
    "trade_contract_size",
    "ctVal",
    "ctValCcy",
    "contract_value_currency",
    "contract_value_ccy",
    "ctMult",
    "asset_type",
    "instType",
    "contract_type",
    "ctType",
    "base_asset",
    "baseCcy",
    "quote_asset",
    "quoteCcy",
    "settle_currency",
    "settleCcy",
    "fee_currency",
    "feeCcy",
    "VolumeMultiple",
    "CONTRACT_MULTIPLIER",
    "price_tick",
    "tick_size",
    "price_unit",
    "tickSz",
    "PriceTick",
    "MIN_PRICE_CHANGE",
    "margin",
    "margin_rate",
    "margin_ratio",
    "LongMarginRatio",
    "ShortMarginRatio",
    "LongMarginRatioByMoney",
    "ShortMarginRatioByMoney",
    "MARGIN_RATIO",
    "MARGIN_BUY",
    "MARGIN_SELL",
    "margin_amount",
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
    "initial_margin_amount",
    "LongMarginRatioByVolume",
    "ShortMarginRatioByVolume",
    "MARGIN_PER_LOT",
    "LONG_MARGIN_AMOUNT",
    "SHORT_MARGIN_AMOUNT",
    "open_commission_rate",
    "close_commission_rate",
    "close_today_commission_rate",
    "close_yesterday_commission_rate",
    "maker_commission_rate",
    "maker_fee_rate",
    "taker_commission_rate",
    "taker_fee_rate",
    "OpenRatioByMoney",
    "CloseRatioByMoney",
    "CloseTodayRatioByMoney",
    "CloseYesterdayRatioByMoney",
    "OPEN_FEE_RATE",
    "CLOSE_FEE_RATE",
    "CLOSE_TODAY_FEE_RATE",
    "CLOSE_YESTERDAY_FEE_RATE",
    "COMMISSION_OPEN_RATIO",
    "COMMISSION_CLOSE_RATIO",
    "COMMISSION_CLOSE_TODAY_RATIO",
    "COMMISSION_CLOSE_YESTERDAY_RATIO",
    "commission_amount",
    "open_fee_amount",
    "open_commission_amount",
    "close_fee_amount",
    "close_commission_amount",
    "close_today_fee_amount",
    "close_today_commission_amount",
    "close_yesterday_fee_amount",
    "close_yesterday_commission_amount",
    "OpenRatioByVolume",
    "CloseRatioByVolume",
    "CloseTodayRatioByVolume",
    "CloseYesterdayRatioByVolume",
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
                row = payload
            else:
                row = _select_payload_row(payload, symbol)
            if row is None:
                continue
            base = {item_key: item_value for item_key, item_value in data.items() if item_key != key}
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
    bid = _positive_price(_call_or_value(_object_get(payload, *BID_PRICE_FIELD_KEYS, "get_bid_price")))
    ask = _positive_price(_call_or_value(_object_get(payload, *ASK_PRICE_FIELD_KEYS, "get_ask_price")))
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
    raw_size = (
        _first_number(
            _first_value(row, "size", "volume", "position", "qty", "quantity", "trade_volume"),
            _first_value(
                row,
                "position_volume",
                "positionAmt",
                "pos",
                "pa",
                "Position",
                "Volume",
                "Qty",
                "Quantity",
                "TradeVolume",
            ),
            default=0.0,
        )
        or 0.0
    )
    direction = _position_side(row)
    if direction == "short":
        return -abs(raw_size)
    return raw_size


def _compact_symbol(value: Any) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", str(value or "")).upper()


def _trade_symbol(row: dict[str, Any], fallback: str = "") -> str:
    return str(
        _first_value(
            row,
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
    return _compact_symbol(_trade_symbol(row)) in expected


def _trade_position_side(row: dict[str, Any]) -> str | None:
    for key in (
        "posSide",
        "positionSide",
        "position_side",
        "PositionSide",
        "holdSide",
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
    raw_size = _first_number(
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
    ) or 0.0
    if raw_size < 0:
        return raw_size
    side = str(
        _first_value(
            row,
            "side",
            "trade_side",
            "direction",
            "action",
            "S",
        )
        or ""
    ).strip().lower()
    if side in {"sell", "short", "s"}:
        return -abs(raw_size)
    if side in {"buy", "long", "b"}:
        return abs(raw_size)
    return raw_size


def _trade_commission(row: dict[str, Any], asset_spec: dict[str, Any] | None = None) -> float | None:
    key, value = _first_value_with_key(
        row,
        "trade_commission",
        "trade_fee",
        "fillFee",
        "fill_fee",
        "execFee",
        "exec_fee",
        "fee",
        "commission",
        "comm",
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
        _first_text(row.get("base_asset"), row.get("baseCcy"), spec.get("base_asset"), spec.get("baseCcy"))
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
    )


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
        price = _trade_price(row) or _price_from_payload(row) or _price_from_payload(asset_spec or {})
        if price and price > 0:
            return price
    return None


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
                "trade_fee",
                "fillFee",
                "fill_fee",
                "execFee",
                "exec_fee",
                "fee",
                "commission",
                "comm",
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


def normalize_gateway_position(
    row: dict[str, Any],
    *,
    fallback_symbol: str = "",
    asset_spec: dict[str, Any] | None = None,
    recent_trades: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Normalize exchange position rows to the valuation input shape."""
    symbol = gateway_position_symbol(row, fallback_symbol)
    size = signed_gateway_size(row)
    position_side = _position_side(row, size)
    inverse_contract = _is_inverse_contract_spec(row, asset_spec)
    multiplier_keys = (
        (
            "contract_value",
            "contractValue",
            "contract_value_amount",
            "contractValueAmount",
            "contract_notional_value",
            "okx_contract_value",
            "ctVal",
            "multiplier",
            "mult",
            "contract_size",
            "trade_contract_size",
            "contract_multiplier",
            "ctMult",
            "VolumeMultiple",
            "CONTRACT_MULTIPLIER",
        )
        if inverse_contract
        else (
            "multiplier",
            "mult",
            "contract_size",
            "trade_contract_size",
            "contract_notional_value",
            "okx_contract_value",
            "contract_multiplier",
            "ctVal",
            "ctMult",
            "VolumeMultiple",
            "CONTRACT_MULTIPLIER",
        )
    )
    multiplier = (
        _first_number(
            _first_value(asset_spec or {}, *multiplier_keys),
            _first_value(row, *multiplier_keys),
            default=1.0,
        )
        or 1.0
    )
    price = (
        _safe_float(
            _first_value(
                row,
                "price",
                "avg_price",
                "average_price",
                "price_open",
                "avgCost",
                "avgPrice",
                "avgPx",
                "entryPrice",
                "ep",
                "Price",
                "AveragePrice",
            ),
            0.0,
        )
        or 0.0
    )
    if (
        price <= 0
        and abs(size) > 0
        and multiplier > 0
        and not inverse_contract
    ):
        position_cost = _safe_float(
            _first_value(
                row,
                "PositionCost",
                "position_cost",
                "positionCost",
                "OpenCost",
                "open_cost",
                "openCost",
            )
        )
        if position_cost and position_cost > 0:
            price = position_cost / (abs(size) * multiplier)
    current_price = _first_value(
        row,
        "current_price",
        "latest_price",
        "last_price",
        "last",
        "mark_price",
        "markPrice",
        "markPx",
        "index_price",
        "indexPrice",
        "idxPx",
        "market_price",
        "price_current",
        "marketPrice",
        "mktPrice",
        "mp",
        "PriceCurrent",
        "CurrentPrice",
        "LastPrice",
    )
    if current_price in (None, "") and isinstance(asset_spec, dict):
        current_price = _first_value(
            asset_spec,
            "current_price",
            "latest_price",
            "last_price",
            "mark_price",
            "market_price",
        )
    if current_price in (None, ""):
        current_price = _first_value(row, "SettlementPrice", "settlement_price")
    current_price_number = _safe_float(current_price)
    if current_price_number is not None:
        current_price = current_price_number

    commission_key, commission_value = _first_value_with_key(row, *COMMISSION_FIELD_KEYS)
    has_commission = commission_value not in (None, "")
    has_swap = any(key in row and row.get(key) not in (None, "") for key in ("swap", "storage"))
    commission_source = None
    commission_unconfirmed_reason = None
    commission = 0.0
    if has_commission:
        raw_commission = _internal_commission_from_exchange_fee(
            commission_key,
            commission_value,
            row=row,
            asset_spec=asset_spec,
        )
        conversion_rate = _fee_valuation_conversion_rate(row, symbol, asset_spec)
        if conversion_rate is None:
            has_commission = False
            commission_unconfirmed_reason = "commission_currency_mismatch"
        else:
            commission = raw_commission * conversion_rate
    if not has_commission:
        actual_commission, trade_unconfirmed_reason = _open_trade_commission_for_position(
            symbol=symbol,
            size=size,
            trades=recent_trades,
            asset_spec=asset_spec,
            position_side=position_side,
        )
        if actual_commission is not None:
            commission = actual_commission
            has_commission = True
            commission_source = "gateway.trades"
            commission_unconfirmed_reason = None
        elif trade_unconfirmed_reason:
            commission_unconfirmed_reason = trade_unconfirmed_reason
    swap = _safe_float(_first_value(row, "swap", "storage"), 0.0) or 0.0
    explicit_net_pnl_value = _first_value(
        row,
        "pnlcomm",
        "net_pnl",
        "netPnl",
        "netPNL",
    )
    gross_pnl_value = _first_value(
        row,
        "gross_pnl",
        "position_unrealized_pnl",
        "position_unrealised_pnl",
        "unrealized_profit",
        "unrealised_profit",
        "unRealizedProfit",
        "UnrealizedPnL",
        "unrealizedPnl",
        "unrealisedPnl",
        "unrealizedpnl",
        "unrealisedpnl",
        "unrealized_pnl",
        "unrealised_pnl",
        "unrealizedPNL",
        "unrealisedPNL",
        "floating_pnl",
        "upl",
        "up",
        "position_profit",
        "PositionProfit",
        "position_pnl",
        "profit",
        "pnl",
    )
    explicit_net_pnl = (
        _safe_float(explicit_net_pnl_value) if explicit_net_pnl_value is not None else None
    )
    gross_pnl = _safe_float(gross_pnl_value) if gross_pnl_value is not None else None
    net_pnl = None
    if explicit_net_pnl is not None:
        net_pnl = explicit_net_pnl
    elif gross_pnl is not None and has_commission:
        net_pnl = gross_pnl + swap - commission
    explicit_margin = _safe_float(
        _first_value(
            row,
            "margin_value",
            "use_margin",
            "initial_margin",
            "maintain_margin",
            "UseMargin",
            "InitialMargin",
            "MaintainMargin",
            "positionIM",
            "positionIMByMp",
            "positionMM",
            "positionMMByMp",
            "isolatedMargin",
            "isolated_margin",
            "imr",
            "mmr",
        )
    )

    normalized: dict[str, Any] = {}
    if isinstance(asset_spec, dict):
        normalized.update(asset_spec)
        asset_spec_source = str(asset_spec.get("source") or "").strip()
        if asset_spec_source:
            normalized["asset_spec_source"] = asset_spec_source
    normalized.update(
        {
            "data_name": symbol,
            "symbol": symbol,
            "size": size,
            "price": price,
            "current_price": current_price,
            "source": "gateway",
            "position_source": "gateway",
        }
    )
    for key in RAW_ASSET_SPEC_FIELD_KEYS:
        value = row.get(key)
        if value in (None, "") or normalized.get(key) not in (None, ""):
            continue
        number = _safe_float(value)
        normalized[key] = number if number is not None else value
    today_position = _first_number(*(row.get(key) for key in TODAY_POSITION_FIELD_KEYS))
    if today_position is not None:
        normalized["today_position"] = today_position
    yesterday_position = _first_number(*(row.get(key) for key in YESTERDAY_POSITION_FIELD_KEYS))
    if yesterday_position is not None:
        normalized["yesterday_position"] = yesterday_position
    if has_commission:
        normalized["commission"] = commission
        normalized["commission_signed"] = True
        if commission_source:
            normalized["commission_source"] = commission_source
    if commission_unconfirmed_reason == "commission_currency_mismatch":
        normalized["commission_currency_mismatch"] = True
    if has_swap:
        normalized["swap"] = swap
    realized_pnl = _first_value(row, "realized_pnl", "position_realized_pnl", "realizedPnl", "realised_pnl")
    if realized_pnl not in (None, ""):
        normalized["realized_pnl"] = realized_pnl
    leverage = _first_value(row, "leverage", "lever", "max_leverage")
    if leverage not in (None, ""):
        normalized["leverage"] = leverage
    margin_type = _first_value(row, "margin_type", "mgnMode")
    if margin_type not in (None, ""):
        normalized["margin_type"] = margin_type
    if net_pnl is not None:
        normalized["pnlcomm"] = net_pnl
        normalized["position_pnl"] = net_pnl
    if gross_pnl is not None:
        normalized["gross_pnl"] = gross_pnl
    market_value = _first_value(
        row,
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
    if market_value not in (None, ""):
        market_value_number = _safe_float(market_value)
        normalized["market_value"] = market_value_number if market_value_number is not None else market_value
    if explicit_margin is not None:
        normalized["margin_value"] = abs(explicit_margin)
        normalized["use_margin"] = abs(explicit_margin)
    return {key: value for key, value in normalized.items() if value not in (None, "")}


def normalize_asset_spec(
    raw: Any,
    *,
    symbol: str = "",
    source: str = "",
) -> dict[str, Any]:
    """Normalize exchange/local contract metadata to portfolio valuation fields."""
    if raw is None:
        return {}
    if isinstance(raw, (list, tuple, set)):
        selected = _select_payload_row(raw, symbol)
        if selected is None:
            return {}
        raw = selected
    if not isinstance(raw, dict):
        for method_name in ("get_data", "to_dict", "as_dict", "dict", "model_dump"):
            payload = _call_or_value(getattr(raw, method_name, None))
            if payload not in (None, "") and payload is not raw:
                raw = payload
                break
    if isinstance(raw, (list, tuple, set)):
        selected = _select_payload_row(raw, symbol)
        if selected is None:
            return {}
        raw = selected
    if not isinstance(raw, dict):
        raw = {
            name: _call_or_value(getattr(raw, name))
            for name in dir(raw)
            if not name.startswith("_")
        }

    data = _unwrap_payload_dict(dict(raw), symbol=symbol)
    normalized_symbol = _first_text(
        symbol,
        data.get("symbol"),
        data.get("data_name"),
        data.get("instrument"),
        data.get("InstrumentID"),
        data.get("REFERENCE_CODE"),
        data.get("localSymbol"),
        data.get("local_symbol"),
        data.get("contractDesc"),
        data.get("contract_desc"),
        data.get("description"),
    )

    asset_type_text = _first_text(data.get("asset_type"), data.get("instType"), data.get("category"))
    contract_type_text = _first_text(
        data.get("contract_type"),
        data.get("ctType"),
        data.get("contractType"),
    )
    contract_value_currency = _first_text(
        data.get("contract_value_currency"),
        data.get("contract_value_ccy"),
        data.get("ctValCcy"),
        data.get("contractValueCurrency"),
    )
    base_asset = _first_text(data.get("base_asset"), data.get("baseCcy"), data.get("baseCoin"))
    quote_asset = _first_text(data.get("quote_asset"), data.get("quoteCcy"), data.get("quoteCoin"))
    settle_currency = _first_text(
        data.get("settle_currency"),
        data.get("settleCcy"),
        data.get("settleCoin"),
    )
    fee_currency = _first_text(data.get("fee_currency"), data.get("feeCcy"), data.get("feeCoin"))
    okx_contract_value = _first_number(
        data.get("contract_value"),
        data.get("contractValue"),
        data.get("contract_value_amount"),
        data.get("contractValueAmount"),
        data.get("contract_notional_value"),
        data.get("okx_contract_value"),
        data.get("ctVal"),
    )
    contract_multiplier = _first_number(
        data.get("contract_multiplier"),
        data.get("ctMult"),
    )
    is_derivative = asset_type_text.upper() in {
        "SWAP",
        "FUTURES",
        "FUTURE",
        "OPTION",
        "LINEAR",
        "INVERSE",
    } or any(
        token in contract_type_text.upper()
        for token in ("PERP", "PERPETUAL", "FUTURE", "FUTURES", "SWAP", "OPTION")
    )
    is_inverse = _is_inverse_contract_spec(data, data)
    if is_inverse:
        multiplier = _first_number(
            okx_contract_value,
            data.get("multiplier"),
            data.get("mult"),
            data.get("contract_size"),
            data.get("trade_contract_size"),
            contract_multiplier,
            data.get("VolumeMultiple"),
            data.get("CONTRACT_MULTIPLIER"),
        )
    else:
        multiplier = _first_number(
            data.get("multiplier"),
            data.get("mult"),
        )
        if multiplier is None:
            multiplier = (
                okx_contract_value
                if is_derivative and okx_contract_value is not None
                else _first_number(
                    data.get("contract_size"),
                    data.get("trade_contract_size"),
                    contract_multiplier,
                    data.get("VolumeMultiple"),
                    data.get("CONTRACT_MULTIPLIER"),
                    okx_contract_value,
                )
            )
        if multiplier is None and is_derivative and "linear" in (
            f"{asset_type_text} {contract_type_text}".lower()
        ):
            multiplier = 1.0
    price_tick = _first_number(
        data.get("price_tick"),
        data.get("tick_size"),
        data.get("min_price_change"),
        data.get("price_unit"),
        data.get("tickSize"),
        data.get("tickSz"),
        data.get("PriceTick"),
        data.get("MIN_PRICE_CHANGE"),
    )
    min_order_size = _first_number(
        data.get("min_order_size"),
        data.get("min_order_qty"),
        data.get("minOrderQty"),
        data.get("min_size"),
        data.get("min_qty"),
        data.get("minQty"),
        data.get("minSz"),
        data.get("min_volume"),
        data.get("volume_min"),
        data.get("min_lot"),
        data.get("lot_min"),
        data.get("SYMBOL_VOLUME_MIN"),
    )
    max_order_size = _first_number(
        data.get("max_order_size"),
        data.get("max_order_qty"),
        data.get("maxOrderQty"),
        data.get("max_size"),
        data.get("max_qty"),
        data.get("maxQty"),
        data.get("maxLmtSz"),
        data.get("max_volume"),
        data.get("volume_max"),
        data.get("max_lot"),
        data.get("lot_max"),
        data.get("SYMBOL_VOLUME_MAX"),
    )
    market_max_order_size = _first_number(
        data.get("market_max_order_size"),
        data.get("max_market_order_size"),
        data.get("max_mkt_order_size"),
        data.get("maxMktSz"),
        data.get("maxMktOrderQty"),
        data.get("maxMarketOrderQty"),
    )
    order_size_step = _first_number(
        data.get("order_size_step"),
        data.get("size_step"),
        data.get("qty_step"),
        data.get("qtyStep"),
        data.get("qty_unit"),
        data.get("quantity_step"),
        data.get("volume_step"),
        data.get("lot_step"),
        data.get("step_size"),
        data.get("stepSize"),
        data.get("lotSz"),
        data.get("SYMBOL_VOLUME_STEP"),
    )
    long_margin_rate = _normalize_decimal_rate(
        _first_number(
            data.get("long_margin_rate"),
            data.get("LongMarginRatio"),
            data.get("LongMarginRatioByMoney"),
            data.get("LONG_MARGIN_RATE"),
            data.get("MARGIN_BUY"),
        )
    )
    short_margin_rate = _normalize_decimal_rate(
        _first_number(
            data.get("short_margin_rate"),
            data.get("ShortMarginRatio"),
            data.get("ShortMarginRatioByMoney"),
            data.get("SHORT_MARGIN_RATE"),
            data.get("MARGIN_SELL"),
        )
    )
    margin_rate = _normalize_decimal_rate(
        _first_number(
            data.get("margin"),
            data.get("margin_rate"),
            data.get("margin_ratio"),
            data.get("required_margin_percent"),
            data.get("require_margin_percent"),
            data.get("maintain_margin_percent"),
            data.get("MARGIN_RATIO"),
        )
    )
    leverage = _first_number(
        data.get("leverage"),
        data.get("lever"),
        data.get("max_leverage"),
        data.get("maxLeverage"),
    )
    if margin_rate is None:
        margin_rate = (
            (1.0 / leverage)
            if leverage and leverage > 0
            else long_margin_rate or short_margin_rate
        )
    margin_amount = _first_number(
        data.get("margin_amount"),
        data.get("initial_margin_per_lot"),
        data.get("margin_initial"),
        data.get("initial_margin_amount"),
        data.get("SYMBOL_MARGIN_INITIAL"),
        data.get("MARGIN_PER_LOT"),
        data.get("LONG_MARGIN_AMOUNT"),
        data.get("LONG_MARGIN_PER_LOT"),
    )
    long_margin_amount = _first_number(
        data.get("long_margin_amount"),
        data.get("LongMarginRatioByVolume"),
        data.get("LONG_MARGIN_AMOUNT"),
        data.get("LONG_MARGIN_PER_LOT"),
    )
    short_margin_amount = _first_number(
        data.get("short_margin_amount"),
        data.get("ShortMarginRatioByVolume"),
        data.get("SHORT_MARGIN_AMOUNT"),
        data.get("SHORT_MARGIN_PER_LOT"),
    )

    source_text = f"{source or ''} {data.get('source') or ''}".lower()
    commission_rate_key, commission_rate_raw = _first_value_with_key(
        data,
        "commission",
        "commission_rate",
        "fee_rate",
        "open_fee_rate",
        "open_commission_rate",
        "OpenRatioByMoney",
        "OPEN_FEE_RATE",
        "COMMISSION_OPEN_RATIO",
    )
    commission_rate = _safe_float(commission_rate_raw)
    close_rate_key, close_rate_raw = _first_value_with_key(
        data,
        "close_commission_rate",
        "close_fee_rate",
        "CloseRatioByMoney",
        "CLOSE_FEE_RATE",
        "COMMISSION_CLOSE_RATIO",
    )
    close_commission_rate = _safe_float(close_rate_raw)
    close_today_rate_key, close_today_rate_raw = _first_value_with_key(
        data,
        "close_today_commission_rate",
        "close_today_fee_rate",
        "CloseTodayRatioByMoney",
        "CLOSE_TODAY_FEE_RATE",
        "CLOSETODAY_FEE_RATE",
        "COMMISSION_CLOSE_TODAY_RATIO",
    )
    close_today_commission_rate = _safe_float(close_today_rate_raw)
    close_yesterday_rate_key, close_yesterday_rate_raw = _first_value_with_key(
        data,
        "close_yesterday_commission_rate",
        "close_yesterday_fee_rate",
        "CloseYesterdayRatioByMoney",
        "CLOSE_YESTERDAY_FEE_RATE",
        "CLOSEYESTERDAY_FEE_RATE",
        "COMMISSION_CLOSE_YESTERDAY_RATIO",
    )
    close_yesterday_commission_rate = _safe_float(close_yesterday_rate_raw)

    def _normalize_role_commission_rate(key: str | None, value: float | None) -> float | None:
        if value is None:
            return None
        key_text = str(key or "")
        if (
            key_text.startswith("COMMISSION_")
            or key_text.endswith("RatioByMoney")
            and value > 0.01
            or "ctp" in source_text
            and value > 0.01
        ):
            return _normalize_ctp_commission_rate(value)
        return _normalize_decimal_rate(value)

    maker_rate_key, maker_rate_raw = _first_value_with_key(
        data,
        "maker_commission_rate",
        "maker_fee_rate",
        "makerCommissionRate",
        "makerCommission",
        "makerU",
        "maker",
    )
    taker_rate_key, taker_rate_raw = _first_value_with_key(
        data,
        "taker_commission_rate",
        "taker_fee_rate",
        "takerCommissionRate",
        "takerCommission",
        "takerU",
        "taker",
    )
    maker_commission_rate = _normalize_exchange_commission_rate(
        maker_rate_key,
        maker_rate_raw,
        source_text=source_text,
    )
    taker_commission_rate = _normalize_exchange_commission_rate(
        taker_rate_key,
        taker_rate_raw,
        source_text=source_text,
    )
    if commission_rate is None:
        commission_rate = (
            taker_commission_rate
            if taker_commission_rate is not None
            else maker_commission_rate
        )
    commission_amount_key, commission_amount_raw = _first_value_with_key(
        data,
        "commission_amount",
        "fee_amount",
        "commission_per_lot",
        "open_fee_amount",
        "open_commission_amount",
        "OpenRatioByVolume",
        "OPEN_FEE_AMOUNT",
        "OPEN_FEE_PER_LOT",
        "COMMISSION_OPEN_AMOUNT",
    )
    commission_amount = _safe_float(commission_amount_raw)
    _close_amount_key, close_amount_raw = _first_value_with_key(
        data,
        "close_commission_amount",
        "close_fee_amount",
        "CloseRatioByVolume",
        "CLOSE_FEE_AMOUNT",
        "CLOSE_FEE_PER_LOT",
        "COMMISSION_CLOSE_AMOUNT",
    )
    close_commission_amount = _safe_float(close_amount_raw)
    _close_today_amount_key, close_today_amount_raw = _first_value_with_key(
        data,
        "close_today_commission_amount",
        "close_today_fee_amount",
        "CloseTodayRatioByVolume",
        "CLOSE_TODAY_FEE_AMOUNT",
        "CLOSETODAY_FEE_AMOUNT",
        "CLOSE_TODAY_FEE_PER_LOT",
        "COMMISSION_CLOSE_TODAY_AMOUNT",
    )
    close_today_commission_amount = _safe_float(close_today_amount_raw)
    _close_yesterday_amount_key, close_yesterday_amount_raw = _first_value_with_key(
        data,
        "close_yesterday_commission_amount",
        "close_yesterday_fee_amount",
        "CloseYesterdayRatioByVolume",
        "CLOSE_YESTERDAY_FEE_AMOUNT",
        "CLOSEYESTERDAY_FEE_AMOUNT",
        "CLOSE_YESTERDAY_FEE_PER_LOT",
        "COMMISSION_CLOSE_YESTERDAY_AMOUNT",
    )
    close_yesterday_commission_amount = _safe_float(close_yesterday_amount_raw)

    spec: dict[str, Any] = dict(data)
    explicit_inverse = _explicit_inverse_flag(data)
    if is_inverse:
        spec["inverse"] = True
        spec["is_inverse"] = True
    elif explicit_inverse is False:
        spec["inverse"] = False
        spec["is_inverse"] = False
    if normalized_symbol:
        spec["symbol"] = normalized_symbol
    if source:
        spec["source"] = source
    if asset_type_text:
        spec["asset_type"] = asset_type_text
        spec.setdefault("instType", asset_type_text)
    if contract_type_text:
        spec["contract_type"] = contract_type_text
        spec.setdefault("ctType", contract_type_text)
    if contract_value_currency:
        spec["contract_value_currency"] = contract_value_currency
        spec["contract_value_ccy"] = contract_value_currency
        spec["ctValCcy"] = contract_value_currency
    if base_asset:
        spec["base_asset"] = base_asset
        spec.setdefault("baseCcy", base_asset)
    if quote_asset:
        spec["quote_asset"] = quote_asset
        spec.setdefault("quoteCcy", quote_asset)
    if settle_currency:
        spec["settle_currency"] = settle_currency
        spec.setdefault("settleCcy", settle_currency)
    if fee_currency:
        spec["fee_currency"] = fee_currency
        spec.setdefault("feeCcy", fee_currency)
    exchange = _first_text(
        data.get("exchange"), data.get("exchange_id"), data.get("ExchangeID"), data.get("EXCHANGE")
    )
    if exchange:
        spec["exchange"] = exchange
        spec["exchange_id"] = exchange
    if multiplier and multiplier > 0:
        spec["multiplier"] = multiplier
        spec["contract_multiplier"] = multiplier
        spec["contract_size"] = multiplier
        if okx_contract_value is not None and okx_contract_value > 0:
            spec["contract_notional_value"] = okx_contract_value
            spec["okx_contract_value"] = okx_contract_value
        if contract_multiplier is not None and contract_multiplier > 0:
            spec["contract_multiplier_raw"] = contract_multiplier
    if price_tick and price_tick > 0:
        spec["price_tick"] = price_tick
        spec["tick_size"] = price_tick
    if min_order_size is not None and min_order_size > 0:
        spec["min_order_size"] = min_order_size
        spec["min_qty"] = min_order_size
        spec["volume_min"] = min_order_size
    if max_order_size is not None and max_order_size > 0:
        spec["max_order_size"] = max_order_size
        spec["max_qty"] = max_order_size
        spec["volume_max"] = max_order_size
    if market_max_order_size is not None and market_max_order_size > 0:
        spec["market_max_order_size"] = market_max_order_size
        spec["max_market_order_size"] = market_max_order_size
    if order_size_step is not None and order_size_step > 0:
        spec["order_size_step"] = order_size_step
        spec["qty_step"] = order_size_step
        spec["volume_step"] = order_size_step
    if margin_rate is not None:
        spec["margin"] = margin_rate
        spec["margin_rate"] = margin_rate
    if leverage is not None and leverage > 0:
        spec["leverage"] = leverage
        spec["lever"] = leverage
        spec.setdefault("max_leverage", leverage)
    if margin_amount is not None and margin_amount > 0:
        spec["margin_amount"] = margin_amount
        spec["initial_margin_per_lot"] = margin_amount
        spec["margin_initial"] = margin_amount
    if long_margin_amount is not None and long_margin_amount > 0:
        spec["long_margin_amount"] = long_margin_amount
    if short_margin_amount is not None and short_margin_amount > 0:
        spec["short_margin_amount"] = short_margin_amount
    if long_margin_rate is not None:
        spec["long_margin_rate"] = long_margin_rate
    if short_margin_rate is not None:
        spec["short_margin_rate"] = short_margin_rate
    if commission_rate is not None:
        normalized_commission_rate = _normalize_role_commission_rate(
            commission_rate_key,
            commission_rate,
        ) or 0.0
        if commission_rate_key == "COMMISSION_OPEN_RATIO" and data.get("commission_method") is None:
            spec["commission_method"] = "percent_10k"
        spec["commission_rate"] = normalized_commission_rate
        spec["open_commission_rate"] = normalized_commission_rate
    close_commission_rate = _normalize_role_commission_rate(
        close_rate_key,
        close_commission_rate,
    )
    if close_commission_rate is not None:
        spec["close_commission_rate"] = close_commission_rate
    close_today_commission_rate = _normalize_role_commission_rate(
        close_today_rate_key,
        close_today_commission_rate,
    )
    if close_today_commission_rate is not None:
        spec["close_today_commission_rate"] = close_today_commission_rate
    close_yesterday_commission_rate = _normalize_role_commission_rate(
        close_yesterday_rate_key,
        close_yesterday_commission_rate,
    )
    if close_yesterday_commission_rate is not None:
        spec["close_yesterday_commission_rate"] = close_yesterday_commission_rate
    if maker_commission_rate is not None:
        spec["maker_commission_rate"] = maker_commission_rate
    if taker_commission_rate is not None:
        spec["taker_commission_rate"] = taker_commission_rate
        taker_rate = _normalize_decimal_rate(taker_commission_rate) or 0.0
        spec.setdefault("commission_rate", taker_rate)
        spec.setdefault(
            "open_commission_rate",
            taker_rate,
        )
        spec.setdefault("close_commission_rate", taker_rate)
    if commission_amount is not None:
        spec["commission_amount"] = max(commission_amount, 0.0)
        spec.setdefault("open_commission_amount", max(commission_amount, 0.0))
    if close_commission_amount is not None:
        spec["close_commission_amount"] = max(close_commission_amount, 0.0)
    if close_today_commission_amount is not None:
        spec["close_today_commission_amount"] = max(close_today_commission_amount, 0.0)
    if close_yesterday_commission_amount is not None:
        spec["close_yesterday_commission_amount"] = max(close_yesterday_commission_amount, 0.0)
    return {key: value for key, value in spec.items() if value not in (None, "")}


def _query_local_futures_spec(symbol: str) -> dict[str, Any]:
    product = _product_code(symbol)
    if not product:
        return {}
    try:
        import pymysql

        from app.data_fetch.configs.db_config import DB_CONFIG
    except Exception:
        return {}

    connection = None
    try:
        connection = pymysql.connect(
            host=DB_CONFIG.get("host"),
            user=DB_CONFIG.get("user"),
            password=DB_CONFIG.get("password"),
            database=DB_CONFIG.get("database"),
            port=int(DB_CONFIG.get("port") or 3306),
            connect_timeout=1,
            read_timeout=1,
            cursorclass=pymysql.cursors.DictCursor,
        )
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM FUTURES_TRADING_FEES
                WHERE UPPER(PRODUCT_CODE) = %s OR UPPER(REFERENCE_CODE) = %s
                ORDER BY BASEDATE DESC
                LIMIT 1
                """,
                (product, _normalize_symbol(symbol).upper()),
            )
            row = cursor.fetchone()
            if row:
                return normalize_asset_spec(row, symbol=symbol, source="local_futures_fees")
            cursor.execute(
                """
                SELECT *
                FROM FUTURES_COMMISSION_INFO
                WHERE UPPER(REFERENCE_CODE) = %s OR UPPER(REFERENCE_CODE) LIKE %s
                ORDER BY BASEDATE DESC
                LIMIT 1
                """,
                (_normalize_symbol(symbol).upper(), f"{product}%"),
            )
            row = cursor.fetchone()
            if row:
                return normalize_asset_spec(row, symbol=symbol, source="local_futures_commission")
    except Exception:
        return {}
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
    return {}


def query_local_asset_spec(symbol: str) -> dict[str, Any]:
    """Return locally stored asset metadata for a symbol when available."""
    return _query_local_futures_spec(symbol)


def _runtime_adapter(gateway: dict[str, Any] | None) -> Any:
    runtime = (gateway or {}).get("runtime") if isinstance(gateway, dict) else None
    return getattr(runtime, "adapter", None) if runtime is not None else None


def _safe_getattr(obj: Any, name: str) -> Any:
    try:
        return getattr(obj, name, None)
    except Exception:
        return None


def _gateway_asset_query_targets(adapter: Any) -> list[tuple[str, Any]]:
    candidates: list[tuple[str, Any]] = [("gateway", adapter)]
    client = _safe_getattr(adapter, "client")
    if client is not None:
        candidates.append(("gateway.client", client))
    feed = _safe_getattr(adapter, "feed")
    if feed is not None:
        candidates.append(("gateway.feed", feed))
    client_feed = _safe_getattr(client, "feed") if client is not None else None
    if client_feed is not None:
        candidates.append(("gateway.client.feed", client_feed))

    result: list[tuple[str, Any]] = []
    seen: set[int] = set()
    for label, target in candidates:
        if target is None:
            continue
        marker = id(target)
        if marker in seen:
            continue
        seen.add(marker)
        result.append((label, target))
    return result


_FEE_SPEC_KEYS = (
    "commission_rate",
    "open_commission_rate",
    "close_commission_rate",
    "close_today_commission_rate",
    "close_yesterday_commission_rate",
    "maker_commission_rate",
    "taker_commission_rate",
    "commission_amount",
    "open_commission_amount",
    "close_commission_amount",
    "close_today_commission_amount",
    "close_yesterday_commission_amount",
)


def _has_fee_spec(spec: dict[str, Any]) -> bool:
    return any(spec.get(key) not in (None, "") for key in _FEE_SPEC_KEYS)


_ASSET_SPEC_METADATA_KEYS = tuple(
    dict.fromkeys(
        (
            *RAW_ASSET_SPEC_FIELD_KEYS,
            *_FEE_SPEC_KEYS,
            "price_tick",
            "tick_size",
            "min_order_size",
            "max_order_size",
            "market_max_order_size",
            "order_size_step",
            "baseCoin",
            "quoteCoin",
            "settleCoin",
            "contractType",
            "category",
            "maxLeverage",
        )
    )
)


def _has_asset_metadata(spec: dict[str, Any]) -> bool:
    return any(spec.get(key) not in (None, "") for key in _ASSET_SPEC_METADATA_KEYS)


def _query_gateway_fee_spec(adapter: Any, symbol: str) -> dict[str, Any]:
    for target_label, target in _gateway_asset_query_targets(adapter):
        for method_name in (
            "get_fee",
            "fetch_fee",
            "get_fee_rate",
            "fetch_fee_rate",
            "get_commission_rate",
            "fetch_commission_rate",
        ):
            method = _safe_getattr(target, method_name)
            if not callable(method):
                continue
            for query_symbol in _query_symbol_keys(symbol):
                try:
                    payload = method(query_symbol)
                except Exception:
                    continue
                spec = normalize_asset_spec(
                    payload,
                    symbol=symbol,
                    source=f"{target_label}.{method_name}",
                )
                if _has_fee_spec(spec):
                    return spec
    return {}


def _merge_fee_spec(spec: dict[str, Any], fee_spec: dict[str, Any]) -> dict[str, Any]:
    if not fee_spec:
        return spec
    merged = dict(spec)
    source = str(merged.get("source") or "").strip()
    fee_source = str(fee_spec.get("source") or "").strip()
    for key, value in fee_spec.items():
        if key == "source":
            continue
        merged[key] = value
    if fee_source:
        merged["fee_source"] = fee_source
    if source:
        merged["source"] = source
    return merged


def _gateway_asset_method_attempts(
    method_name: str,
    query_symbol: str,
    target: Any,
    adapter: Any,
    *,
    include_empty_call: bool = False,
) -> list[tuple[tuple[Any, ...], dict[str, Any]]]:
    asset_type = _first_text(
        _safe_getattr(target, "asset_type"),
        _safe_getattr(adapter, "asset_type"),
    )
    attempts: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    instrument_method = method_name in {
        "get_instruments",
        "fetch_instruments",
        "get_public_instruments",
        "fetch_public_instruments",
    }
    if query_symbol:
        if instrument_method and asset_type:
            attempts.append(((), {"asset_type": asset_type, "inst_id": query_symbol}))
        if instrument_method:
            attempts.extend(
                (
                    ((), {"inst_id": query_symbol}),
                    ((), {"instId": query_symbol}),
                    ((), {"instrument": query_symbol}),
                )
            )
        attempts.extend(
            (
                ((query_symbol,), {}),
                ((), {"symbol": query_symbol}),
                ((), {"inst_id": query_symbol}),
                ((), {"instId": query_symbol}),
                ((), {"instrument": query_symbol}),
            )
        )
    if include_empty_call:
        if instrument_method and asset_type:
            attempts.append(((), {"asset_type": asset_type}))
        attempts.append(((), {}))

    result: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    seen: set[str] = set()
    for args, kwargs in attempts:
        marker = repr((args, sorted(kwargs.items())))
        if marker in seen:
            continue
        seen.add(marker)
        result.append((args, kwargs))
    return result


def _query_gateway_common_asset_spec(
    adapter: Any,
    symbol: str,
    fee_spec: dict[str, Any],
) -> dict[str, Any]:
    method_names = (
        "get_exchange_info",
        "fetch_exchange_info",
        "get_instruments",
        "fetch_instruments",
        "get_public_instruments",
        "fetch_public_instruments",
        "get_contract",
        "fetch_contract",
        "query_symbol",
        "get_market",
        "fetch_market",
    )
    for target_label, target in _gateway_asset_query_targets(adapter):
        for method_name in method_names:
            method = _safe_getattr(target, method_name)
            if not callable(method):
                continue
            attempts: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
            for query_symbol in _query_symbol_keys(symbol):
                attempts.extend(
                    _gateway_asset_method_attempts(
                        method_name,
                        query_symbol,
                        target,
                        adapter,
                    )
                )
            attempts.extend(
                _gateway_asset_method_attempts(
                    method_name,
                    "",
                    target,
                    adapter,
                    include_empty_call=True,
                )
            )
            for args, kwargs in attempts:
                try:
                    payload = method(*args, **kwargs)
                except Exception:
                    continue
                spec = normalize_asset_spec(
                    payload,
                    symbol=symbol,
                    source=f"{target_label}.{method_name}",
                )
                if _has_asset_metadata(spec):
                    return _merge_fee_spec(spec, fee_spec)
    return {}


def query_gateway_asset_spec(gateway: dict[str, Any] | None, symbol: str) -> dict[str, Any]:
    adapter = _runtime_adapter(gateway)
    if adapter is None:
        return {}

    fee_spec = _query_gateway_fee_spec(adapter, symbol)
    for target_label, target in _gateway_asset_query_targets(adapter):
        for method_name in ("get_symbol_info", "fetch_symbol_info"):
            method = _safe_getattr(target, method_name)
            if callable(method):
                for query_symbol in _query_symbol_keys(symbol):
                    try:
                        info = method(query_symbol)
                    except Exception:
                        info = None
                    if info:
                        spec = normalize_asset_spec(
                            info,
                            symbol=symbol,
                            source=f"{target_label}.{method_name}",
                        )
                        if _has_asset_metadata(spec):
                            return _merge_fee_spec(spec, fee_spec)

    specs = getattr(adapter, "_symbol_specs", None)
    if isinstance(specs, dict):
        for key in _symbol_keys(symbol):
            item = specs.get(key)
            if isinstance(item, dict) and item:
                spec = normalize_asset_spec(item, symbol=symbol, source="gateway.symbol_cache")
                return _merge_fee_spec(spec, fee_spec)

    spec = _query_gateway_common_asset_spec(adapter, symbol, fee_spec)
    if spec:
        return spec

    trader = getattr(getattr(adapter, "feed", None), "trader_client", None)
    query_instrument = getattr(trader, "query_instrument", None)
    if callable(query_instrument):
        try:
            info = query_instrument(_normalize_symbol(symbol), timeout=2)
        except Exception:
            info = None
        spec = normalize_asset_spec(info, symbol=symbol, source="gateway.query_instrument")
        if spec:
            return _merge_fee_spec(spec, fee_spec)

    price_ticks = getattr(adapter, "_price_ticks", None)
    if isinstance(price_ticks, dict):
        for key in _symbol_keys(symbol):
            tick = _safe_float(price_ticks.get(key))
            if tick and tick > 0:
                spec = {
                    "symbol": symbol,
                    "price_tick": tick,
                    "tick_size": tick,
                    "source": "gateway.price_tick_cache",
                }
                return _merge_fee_spec(spec, fee_spec)

    return fee_spec


def query_gateway_last_price(gateway: dict[str, Any] | None, symbol: str) -> float | None:
    adapter = _runtime_adapter(gateway)
    if adapter is None:
        return None
    for attr_name in (
        "last_price",
        "last_prices",
        "_last_price",
        "_last_prices",
        "latest_price",
        "latest_prices",
        "mark_price",
        "mark_prices",
        "market_price",
        "market_prices",
        "_latest_ticks",
        "latest_ticks",
        "tickers",
        "ticker",
        "ticks",
        "last_tick",
        "last_ticks",
    ):
        payload = getattr(adapter, attr_name, None)
        if isinstance(payload, dict):
            for key in _symbol_keys(symbol):
                if key not in payload:
                    continue
                price = _price_from_payload(payload.get(key))
                if price is not None:
                    return price
            price = _price_from_payload(payload)
            if price is not None:
                return price
        else:
            price = _price_from_payload(payload)
            if price is not None:
                return price
    for method_name in (
        "get_last_price",
        "fetch_last_price",
        "get_latest_price",
        "fetch_latest_price",
        "get_mark_price",
        "fetch_mark_price",
        "get_ticker",
        "fetch_ticker",
        "get_tick",
        "fetch_tick",
    ):
        method = getattr(adapter, method_name, None)
        if not callable(method):
            continue
        for query_symbol in _query_symbol_keys(symbol):
            try:
                payload = method(query_symbol)
            except Exception:
                continue
            price = _price_from_payload(payload)
            if price is not None:
                return price
    return None


def load_runtime_config(strategy_dir: Path) -> dict[str, Any]:
    try:
        config_path = strategy_dir / "config.yaml"
        if not config_path.is_file():
            return {}
        raw_config = config_path.read_text(encoding="utf-8")
    except Exception:
        return {}
    if not isinstance(raw_config, str):
        return {}
    try:
        data = yaml.safe_load(raw_config) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def symbols_for_instance(instance: dict[str, Any], strategy_dir: Path) -> list[str]:
    config = load_runtime_config(strategy_dir)
    params = _as_dict(instance.get("params"))
    candidates: list[Any] = [
        params.get("symbol"),
        _as_dict(params.get("data_config")).get("symbol"),
        _as_dict(config.get("data")).get("symbol"),
        _as_dict(config.get("live")).get("symbol"),
        _as_dict(config.get("symbol")).get("code"),
    ]
    for key in ("symbols", "symbol_list"):
        value = (
            params.get(key)
            or _as_dict(config.get("data")).get(key)
            or _as_dict(config.get("live")).get(key)
        )
        if isinstance(value, (list, tuple, set)):
            candidates.extend(value)
    for source in (config, params, _as_dict(config.get("params")), _as_dict(config.get("live"))):
        for container_key in ("contract_metadata", "contracts", "contract_specs", "instrument_specs"):
            container = source.get(container_key) if isinstance(source, dict) else None
            if not isinstance(container, dict):
                continue
            candidates.extend(container.keys())
            for item in container.values():
                if isinstance(item, dict):
                    candidates.extend(
                        (
                            item.get("symbol"),
                            item.get("data_name"),
                            item.get("instrument"),
                            item.get("InstrumentID"),
                            item.get("REFERENCE_CODE"),
                        )
                    )
    result: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        text = str(item or "").strip()
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


def resolve_asset_specs(
    instance: dict[str, Any],
    strategy_dir: Path,
    gateway: dict[str, Any] | None = None,
    symbols: Iterable[str] | None = None,
) -> dict[str, dict[str, Any]]:
    config = load_runtime_config(strategy_dir)
    params = _as_dict(instance.get("params"))
    resolved: dict[str, dict[str, Any]] = {}
    for symbol in list(symbols or symbols_for_instance(instance, strategy_dir)):
        merged: dict[str, Any] = {}
        for source in (
            _extract_existing_metadata(config, symbol),
            _extract_existing_metadata(params, symbol),
            _query_local_futures_spec(symbol),
            query_gateway_asset_spec(gateway, symbol),
        ):
            if source:
                merged.update(source)
        last_price = query_gateway_last_price(gateway, symbol)
        if last_price and last_price > 0:
            merged["current_price"] = last_price
            merged["latest_price"] = last_price
        spec = normalize_asset_spec(
            merged, symbol=symbol, source=str(merged.get("source") or "resolved")
        )
        if spec:
            for key in _symbol_keys(symbol):
                resolved[key] = dict(spec)
    return resolved


def persist_asset_specs(
    strategy_dir: Path, instance: dict[str, Any], specs: dict[str, dict[str, Any]]
) -> None:
    if not specs:
        return
    serializable_specs = {
        str(key): _yaml_safe_value(value) for key, value in specs.items() if isinstance(value, dict)
    }
    if not serializable_specs:
        return
    config_path = strategy_dir / "config.yaml"
    config = load_runtime_config(strategy_dir)
    contract_metadata = dict(config.get("contract_metadata") or {})
    contract_metadata.update({key: dict(value) for key, value in serializable_specs.items()})
    config["contract_metadata"] = contract_metadata

    params = _as_dict(config.get("params"))
    params["contract_metadata"] = contract_metadata
    config["params"] = params

    live = _as_dict(config.get("live"))
    live["contract_metadata"] = contract_metadata
    config["live"] = live

    simulate = _as_dict(config.get("simulate"))
    simulate["contract_metadata"] = contract_metadata
    config["simulate"] = simulate

    first = next(iter(serializable_specs.values()))
    backtest = _as_dict(config.get("backtest"))
    if first.get("multiplier") is not None:
        backtest["multiplier"] = first["multiplier"]
    if first.get("margin_rate") is not None:
        backtest["margin"] = first["margin_rate"]
    if first.get("commission_rate") is not None:
        backtest["commission"] = first["commission_rate"]
    if backtest:
        config["backtest"] = backtest

    config_path.write_text(
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    inst_params = _as_dict(instance.get("params"))
    inst_metadata = dict(inst_params.get("contract_metadata") or {})
    inst_metadata.update({key: dict(value) for key, value in serializable_specs.items()})
    inst_params["contract_metadata"] = inst_metadata
    instance["params"] = inst_params


def _yaml_safe_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): _yaml_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_yaml_safe_value(item) for item in value]
    return value


def refresh_instance_asset_specs(
    instance: dict[str, Any],
    strategy_dir: Path,
    gateway: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    specs = resolve_asset_specs(instance, strategy_dir, gateway)
    persist_asset_specs(strategy_dir, instance, specs)
    return specs
