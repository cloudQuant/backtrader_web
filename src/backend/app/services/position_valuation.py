"""Position valuation helpers for trading snapshots and portfolio views."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.services.trading_asset_info_service import (
    LONG_POSITION_FIELD_KEYS,
    POSITION_SIZE_FIELD_KEYS,
    SHORT_POSITION_FIELD_KEYS,
    symbol_aliases,
)

EPSILON = 1e-12
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


def safe_float(value: Any, default: float | None = 0.0) -> float | None:
    if value in (None, ""):
        return default
    if isinstance(value, dict):
        for key in ("cost", "amount", "value", "balance", "total", "commission", "fee"):
            item = value.get(key)
            if item not in (None, ""):
                return safe_float(item, default)
        return default
    if isinstance(value, (list, tuple)):
        numbers = [safe_float(item, None) for item in value]
        valid_numbers = [number for number in numbers if number is not None]
        return sum(valid_numbers) if valid_numbers else default
    if isinstance(value, str):
        value = value.strip().replace(",", "")
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _first_number(*values: Any, default: float | None = None) -> float | None:
    for value in values:
        if value in (None, ""):
            continue
        number = safe_float(value, None)
        if number is not None:
            return number
    return default


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "signed"}


def _row_marks_pnl_as_net(row: dict[str, Any]) -> bool:
    return any(_truthy(row.get(key)) for key in NET_PNL_FLAG_KEYS)


def _explicit_inverse_flag(config: dict[str, Any]) -> bool | None:
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


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _uses_okx_fee_sign(row: dict[str, Any]) -> bool:
    text = " ".join(
        str(row.get(key) or "").strip().lower()
        for key in (
            "source",
            "asset_spec_source",
            "exchange",
            "exchange_id",
            "exchange_name",
            "exchange_nae",
            "gateway",
            "broker",
        )
    )
    return "okx" in text


def _first_number_with_key(
    row: dict[str, Any],
    keys: Iterable[str],
) -> tuple[str | None, float | None]:
    for key in keys:
        value = row.get(key)
        if value in (None, ""):
            continue
        number = safe_float(value, None)
        if number is not None:
            return key, number
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
        amount = safe_float(value, None)
        if amount is not None:
            total += amount
    return total


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _normalise_rate(value: Any, default: float = 0.0) -> float:
    number = safe_float(value, default)
    if number > 1.0:
        return number / 100.0
    return max(number, 0.0)


def _normalise_ctp_commission_rate(value: Any, default: float = 0.0) -> float:
    number = safe_float(value, default)
    if number > 0.01:
        return number / 10000.0
    return max(number, 0.0)


def _normalise_signed_rate(value: Any, default: float = 0.0) -> float:
    number = safe_float(value, default)
    if abs(number) > 1.0:
        return number / 100.0
    return number


def _commission_rate_from_keys(
    config: dict[str, Any],
    keys: Iterable[str],
    *,
    signed: bool = False,
) -> float | None:
    method = str(config.get("commission_method") or "").strip().lower()
    for key in keys:
        value = _first_number(config.get(key))
        if value is None:
            continue
        if signed:
            return _normalise_signed_rate(value)
        if (
            method == "percent_10k"
            or key.startswith("COMMISSION_")
            or key.endswith("RatioByMoney")
            and value > 0.01
        ):
            return _normalise_ctp_commission_rate(value)
        return _normalise_rate(value, 0.0)
    return None


def _commission_amount_from_keys(
    config: dict[str, Any],
    keys: Iterable[str],
) -> float | None:
    for key in keys:
        value = _first_number(config.get(key))
        if value is not None:
            return max(value, 0.0)
    return None


def _commission_rate_from_config(config: dict[str, Any]) -> float | None:
    method = str(config.get("commission_method") or "").strip().lower()
    for key in (
        "commission",
        "commission_rate",
        "fee_rate",
        "open_fee_rate",
        "open_commission_rate",
        "taker_commission_rate",
        "taker_fee_rate",
        "maker_commission_rate",
        "maker_fee_rate",
        "OPEN_FEE_RATE",
        "OpenRatioByMoney",
        "COMMISSION_OPEN_RATIO",
    ):
        value = _first_number(config.get(key))
        if value is None:
            continue
        if (
            method == "percent_10k"
            or key == "COMMISSION_OPEN_RATIO"
            or (key == "OpenRatioByMoney" and value > 0.01)
        ):
            return _normalise_ctp_commission_rate(value)
        return _normalise_rate(value, 0.0)
    return None


def _symbol_keys(symbol: str) -> set[str]:
    return set(symbol_aliases(symbol))


def _compact_symbol_text(value: str) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _compact_underlying_symbol(symbol: str) -> str:
    compact = _compact_symbol_text(symbol)
    if len(compact) >= 6:
        head = compact[:6]
        if head in _MT5_METAL_CONTRACT_SIZES:
            return head
        if head[:3] in _FIAT_CURRENCIES and head[3:6] in _FIAT_CURRENCIES:
            return head
    return compact


def _local_default_contract_spec(symbol: str) -> dict[str, Any]:
    compact = _compact_underlying_symbol(symbol)
    if compact in _MT5_METAL_CONTRACT_SIZES:
        return {
            "multiplier": _MT5_METAL_CONTRACT_SIZES[compact],
            "asset_type": "commodity",
            "source": "local_mt5_defaults",
        }
    if len(compact) == 6 and compact[:3] in _FIAT_CURRENCIES and compact[3:] in _FIAT_CURRENCIES:
        return {
            "multiplier": _MT5_FOREX_CONTRACT_SIZE,
            "asset_type": "forex",
            "source": "local_mt5_defaults",
        }
    return {}


def _allows_local_otc_default(config: dict[str, Any]) -> bool:
    asset_type_text = _first_text(
        config.get("asset_type"),
        config.get("assetClass"),
        config.get("category"),
        config.get("product_type"),
    ).lower()
    if asset_type_text in {
        "forex",
        "fx",
        "currency",
        "commodity",
        "metal",
        "metals",
        "cfd",
    }:
        return True

    context_text = " ".join(
        str(config.get(key) or "").strip().lower()
        for key in (
            "exchange",
            "exchange_id",
            "exchange_name",
            "gateway",
            "broker",
            "broker_type",
            "source",
            "asset_spec_source",
        )
    )
    return "mt5" in context_text or "metatrader" in context_text


def _contract_metadata(config: dict[str, Any], symbol: str) -> dict[str, Any]:
    keys = _symbol_keys(symbol)
    for container_key in ("contract_metadata", "contracts", "contract_specs", "instrument_specs"):
        container = config.get(container_key)
        if not isinstance(container, dict):
            continue
        for key in keys:
            item = container.get(key)
            if isinstance(item, dict):
                return dict(item)
    return {}


def _config_is_inverse_contract(
    config: dict[str, Any],
    *,
    contract_type: str = "",
    contract_value_currency: str = "",
    base_asset: str = "",
    quote_asset: str = "",
    settle_currency: str = "",
    fee_currency: str = "",
) -> bool:
    explicit_flag = _explicit_inverse_flag(config)
    if explicit_flag is not None:
        return explicit_flag

    type_text = _first_text(
        config.get("contract_type"),
        config.get("ctType"),
        contract_type,
    ).lower()
    if "inverse" in type_text:
        return True
    if "linear" in type_text:
        return False

    contract_ccy = _currency_code(
        _first_text(
            config.get("contract_value_currency"),
            config.get("contract_value_ccy"),
            config.get("ctValCcy"),
            config.get("contractValueCurrency"),
            contract_value_currency,
        )
    )
    base_ccy = _currency_code(
        _first_text(config.get("base_asset"), config.get("baseCcy"), base_asset)
    )
    quote_ccy = _currency_code(
        _first_text(config.get("quote_asset"), config.get("quoteCcy"), quote_asset)
    )
    settle_ccy = _currency_code(
        _first_text(
            config.get("settle_currency"),
            config.get("settleCcy"),
            settle_currency,
        )
    )
    fee_ccy = _currency_code(
        _first_text(config.get("fee_currency"), config.get("feeCcy"), fee_currency)
    )
    if contract_ccy and quote_ccy and contract_ccy == quote_ccy and contract_ccy != base_ccy:
        return True
    if contract_ccy and base_ccy and contract_ccy == base_ccy:
        return False
    if base_ccy and quote_ccy and settle_ccy == base_ccy and settle_ccy != quote_ccy:
        return True
    return bool(
        (contract_ccy or settle_ccy)
        and base_ccy
        and quote_ccy
        and fee_ccy == base_ccy
        and fee_ccy != quote_ccy
    )


def _iter_configs(configs: Iterable[dict[str, Any] | None]) -> Iterable[dict[str, Any]]:
    for config in configs:
        if isinstance(config, dict):
            yield config


@dataclass(frozen=True)
class PositionSpec:
    multiplier: float = 1.0
    margin_rate: float = 1.0
    margin_amount: float = 0.0
    long_margin_rate: float | None = None
    short_margin_rate: float | None = None
    long_margin_amount: float | None = None
    short_margin_amount: float | None = None
    commission_rate: float = 0.0
    commission_amount: float = 0.0
    open_commission_rate: float | None = None
    close_commission_rate: float | None = None
    close_today_commission_rate: float | None = None
    close_yesterday_commission_rate: float | None = None
    maker_commission_rate: float | None = None
    taker_commission_rate: float | None = None
    open_commission_amount: float | None = None
    close_commission_amount: float | None = None
    close_today_commission_amount: float | None = None
    close_yesterday_commission_amount: float | None = None
    asset_type: str = ""
    contract_type: str = ""
    contract_value_currency: str = ""
    base_asset: str = ""
    quote_asset: str = ""
    settle_currency: str = ""
    fee_currency: str = ""
    source: str = ""
    is_inverse: bool | None = None
    has_multiplier: bool = False
    has_margin_rate: bool = False
    has_margin_amount: bool = False
    has_commission: bool = False


@dataclass(frozen=True)
class ValuedPosition:
    data_name: str
    size: float
    direction: str
    entry_price: float
    current_price: float
    multiplier: float
    margin_rate: float
    market_value: float
    margin_value: float
    commission: float
    gross_pnl: float
    pnl: float


def contract_spec_for(
    symbol: str,
    *configs: dict[str, Any] | None,
) -> PositionSpec:
    """Extract contract multiplier, margin and commission settings.

    The UI stores these settings in several places depending on whether a unit
    came from a strategy template, a workspace override, or a live gateway
    instance. This helper intentionally accepts multiple dictionaries and uses
    the first explicit value it can find.
    """
    multiplier: float | None = None
    margin_rate: float | None = None
    margin_amount: float | None = None
    long_margin_rate: float | None = None
    short_margin_rate: float | None = None
    long_margin_amount: float | None = None
    short_margin_amount: float | None = None
    commission_rate: float | None = None
    commission_amount: float | None = None
    open_commission_rate: float | None = None
    close_commission_rate: float | None = None
    close_today_commission_rate: float | None = None
    close_yesterday_commission_rate: float | None = None
    maker_commission_rate: float | None = None
    taker_commission_rate: float | None = None
    open_commission_amount: float | None = None
    close_commission_amount: float | None = None
    close_today_commission_amount: float | None = None
    close_yesterday_commission_amount: float | None = None
    asset_type = ""
    contract_type = ""
    contract_value_currency = ""
    base_asset = ""
    quote_asset = ""
    settle_currency = ""
    fee_currency = ""
    source = ""
    is_inverse: bool | None = None
    has_multiplier = False
    has_margin_rate = False
    has_margin_amount = False
    has_commission = False
    allow_local_otc_default = False

    for config in _iter_configs(configs):
        if _allows_local_otc_default(config):
            allow_local_otc_default = True
        nested = [
            config,
            _as_dict(config.get("unit_settings")),
            _as_dict(config.get("params")),
            _as_dict(config.get("backtest")),
            _as_dict(config.get("simulate")),
            _as_dict(config.get("live")),
            _as_dict(config.get("gateway")),
            _as_dict(config.get("data")),
        ]
        meta = _contract_metadata(config, symbol)
        if meta:
            nested.insert(0, meta)
        for subconfig in nested:
            if not subconfig:
                continue
            if _allows_local_otc_default(subconfig):
                allow_local_otc_default = True
            subconfig_source = str(subconfig.get("source") or "").strip()
            if not asset_type:
                asset_type = _first_text(subconfig.get("asset_type"), subconfig.get("instType"))
            if not contract_type:
                contract_type = _first_text(subconfig.get("contract_type"), subconfig.get("ctType"))
            if not contract_value_currency:
                contract_value_currency = _first_text(
                    subconfig.get("contract_value_currency"),
                    subconfig.get("contract_value_ccy"),
                    subconfig.get("ctValCcy"),
                    subconfig.get("contractValueCurrency"),
                )
            if not base_asset:
                base_asset = _first_text(subconfig.get("base_asset"), subconfig.get("baseCcy"))
            if not quote_asset:
                quote_asset = _first_text(subconfig.get("quote_asset"), subconfig.get("quoteCcy"))
            if not settle_currency:
                settle_currency = _first_text(
                    subconfig.get("settle_currency"),
                    subconfig.get("settleCcy"),
                )
            if not fee_currency:
                fee_currency = _first_text(subconfig.get("fee_currency"), subconfig.get("feeCcy"))
            explicit_inverse = _explicit_inverse_flag(subconfig)
            if explicit_inverse is not None and is_inverse is None:
                is_inverse = explicit_inverse
            if multiplier is None:
                inverse_config = _config_is_inverse_contract(
                    subconfig,
                    contract_type=contract_type,
                    contract_value_currency=contract_value_currency,
                    base_asset=base_asset,
                    quote_asset=quote_asset,
                    settle_currency=settle_currency,
                    fee_currency=fee_currency,
                )
                if inverse_config and is_inverse is None:
                    is_inverse = True
                if inverse_config:
                    multiplier = _first_number(
                        subconfig.get("contract_value"),
                        subconfig.get("contractValue"),
                        subconfig.get("contract_value_amount"),
                        subconfig.get("contractValueAmount"),
                        subconfig.get("contract_notional_value"),
                        subconfig.get("okx_contract_value"),
                        subconfig.get("ctVal"),
                        subconfig.get("multiplier"),
                        subconfig.get("mult"),
                        subconfig.get("contract_size"),
                        subconfig.get("trade_contract_size"),
                        subconfig.get("contract_multiplier"),
                        subconfig.get("ctMult"),
                        subconfig.get("VolumeMultiple"),
                        subconfig.get("CONTRACT_MULTIPLIER"),
                    )
                else:
                    multiplier = _first_number(
                        subconfig.get("multiplier"),
                        subconfig.get("mult"),
                        subconfig.get("contract_size"),
                        subconfig.get("trade_contract_size"),
                        subconfig.get("contract_notional_value"),
                        subconfig.get("okx_contract_value"),
                        subconfig.get("contract_multiplier"),
                        subconfig.get("ctVal"),
                        subconfig.get("ctMult"),
                        subconfig.get("VolumeMultiple"),
                        subconfig.get("CONTRACT_MULTIPLIER"),
                    )
                if multiplier is not None:
                    has_multiplier = True
                    if subconfig_source and not source:
                        source = subconfig_source
            if margin_rate is None:
                margin_value = _first_number(
                    subconfig.get("margin"),
                    subconfig.get("margin_rate"),
                    subconfig.get("margin_ratio"),
                    subconfig.get("required_margin_percent"),
                    subconfig.get("require_margin_percent"),
                    subconfig.get("maintain_margin_percent"),
                    subconfig.get("MARGIN_RATIO"),
                )
                if margin_value is not None:
                    margin_rate = _normalise_rate(margin_value, 1.0)
                    has_margin_rate = True
                    if subconfig_source and not source:
                        source = subconfig_source
                else:
                    leverage = _first_number(
                        subconfig.get("leverage"),
                        subconfig.get("lever"),
                        subconfig.get("max_leverage"),
                    )
                    if leverage and leverage > 0:
                        margin_rate = 1.0 / leverage
                        has_margin_rate = True
                        if subconfig_source and not source:
                            source = subconfig_source
            if margin_amount is None:
                margin_amount = _first_number(
                    subconfig.get("margin_amount"),
                    subconfig.get("initial_margin_per_lot"),
                    subconfig.get("margin_initial"),
                    subconfig.get("initial_margin_amount"),
                    subconfig.get("SYMBOL_MARGIN_INITIAL"),
                    subconfig.get("MARGIN_PER_LOT"),
                    subconfig.get("LONG_MARGIN_AMOUNT"),
                    subconfig.get("LONG_MARGIN_PER_LOT"),
                )
                if margin_amount is not None and margin_amount > 0:
                    has_margin_amount = True
                    if subconfig_source and not source:
                        source = subconfig_source
            if long_margin_amount is None:
                long_amount_value = _first_number(
                    subconfig.get("long_margin_amount"),
                    subconfig.get("LongMarginRatioByVolume"),
                    subconfig.get("LONG_MARGIN_AMOUNT"),
                    subconfig.get("LONG_MARGIN_PER_LOT"),
                )
                if long_amount_value is not None and long_amount_value > 0:
                    long_margin_amount = long_amount_value
                    has_margin_amount = True
                    if subconfig_source and not source:
                        source = subconfig_source
            if short_margin_amount is None:
                short_amount_value = _first_number(
                    subconfig.get("short_margin_amount"),
                    subconfig.get("ShortMarginRatioByVolume"),
                    subconfig.get("SHORT_MARGIN_AMOUNT"),
                    subconfig.get("SHORT_MARGIN_PER_LOT"),
                )
                if short_amount_value is not None and short_amount_value > 0:
                    short_margin_amount = short_amount_value
                    has_margin_amount = True
                    if subconfig_source and not source:
                        source = subconfig_source
            if long_margin_rate is None:
                long_value = _first_number(
                    subconfig.get("long_margin_rate"),
                    subconfig.get("LongMarginRatio"),
                    subconfig.get("LongMarginRatioByMoney"),
                    subconfig.get("LONG_MARGIN_RATE"),
                    subconfig.get("MARGIN_BUY"),
                )
                if long_value is not None:
                    long_margin_rate = _normalise_rate(long_value, 1.0)
                    has_margin_rate = True
                    if subconfig_source and not source:
                        source = subconfig_source
            if short_margin_rate is None:
                short_value = _first_number(
                    subconfig.get("short_margin_rate"),
                    subconfig.get("ShortMarginRatio"),
                    subconfig.get("ShortMarginRatioByMoney"),
                    subconfig.get("SHORT_MARGIN_RATE"),
                    subconfig.get("MARGIN_SELL"),
                )
                if short_value is not None:
                    short_margin_rate = _normalise_rate(short_value, 1.0)
                    has_margin_rate = True
                    if subconfig_source and not source:
                        source = subconfig_source
            if commission_rate is None:
                commission_value = _commission_rate_from_config(subconfig)
                if commission_value is not None:
                    commission_rate = commission_value
                    has_commission = True
                    if subconfig_source and not source:
                        source = subconfig_source
            if open_commission_rate is None:
                open_value = _commission_rate_from_keys(
                    subconfig,
                    (
                        "open_commission_rate",
                        "open_fee_rate",
                        "OpenRatioByMoney",
                        "OPEN_FEE_RATE",
                        "COMMISSION_OPEN_RATIO",
                    ),
                )
                if open_value is not None:
                    open_commission_rate = open_value
                    has_commission = True
                    if subconfig_source and not source:
                        source = subconfig_source
            if close_commission_rate is None:
                close_value = _commission_rate_from_keys(
                    subconfig,
                    (
                        "close_commission_rate",
                        "close_fee_rate",
                        "CloseRatioByMoney",
                        "CLOSE_FEE_RATE",
                        "COMMISSION_CLOSE_RATIO",
                    ),
                )
                if close_value is not None:
                    close_commission_rate = close_value
                    has_commission = True
                    if subconfig_source and not source:
                        source = subconfig_source
            if close_today_commission_rate is None:
                close_today_value = _commission_rate_from_keys(
                    subconfig,
                    (
                        "close_today_commission_rate",
                        "close_today_fee_rate",
                        "CloseTodayRatioByMoney",
                        "CLOSETODAY_FEE_RATE",
                        "CLOSE_TODAY_FEE_RATE",
                        "COMMISSION_CLOSE_TODAY_RATIO",
                    ),
                )
                if close_today_value is not None:
                    close_today_commission_rate = close_today_value
                    has_commission = True
                    if subconfig_source and not source:
                        source = subconfig_source
            if close_yesterday_commission_rate is None:
                close_yesterday_value = _commission_rate_from_keys(
                    subconfig,
                    (
                        "close_yesterday_commission_rate",
                        "close_yesterday_fee_rate",
                        "CloseYesterdayRatioByMoney",
                        "CLOSEYESTERDAY_FEE_RATE",
                        "CLOSE_YESTERDAY_FEE_RATE",
                        "COMMISSION_CLOSE_YESTERDAY_RATIO",
                    ),
                )
                if close_yesterday_value is not None:
                    close_yesterday_commission_rate = close_yesterday_value
                    has_commission = True
                    if subconfig_source and not source:
                        source = subconfig_source
            if maker_commission_rate is None:
                maker_value = _commission_rate_from_keys(
                    subconfig,
                    ("maker_commission_rate", "maker_fee_rate"),
                    signed=True,
                )
                if maker_value is not None:
                    maker_commission_rate = maker_value
                    has_commission = True
                    if subconfig_source and not source:
                        source = subconfig_source
            if taker_commission_rate is None:
                taker_value = _commission_rate_from_keys(
                    subconfig,
                    ("taker_commission_rate", "taker_fee_rate"),
                    signed=True,
                )
                if taker_value is not None:
                    taker_commission_rate = taker_value
                    has_commission = True
                    if subconfig_source and not source:
                        source = subconfig_source
            if commission_amount is None:
                if str(subconfig.get("commission_method") or "").lower() == "fixed_per_lot":
                    commission_amount = _first_number(
                        subconfig.get("open_commission_amount"),
                        subconfig.get("open_fee_amount"),
                        subconfig.get("open_commission_rate"),
                        subconfig.get("OpenRatioByVolume"),
                        subconfig.get("OPEN_FEE_AMOUNT"),
                        subconfig.get("OPEN_FEE_PER_LOT"),
                        subconfig.get("COMMISSION_OPEN_AMOUNT"),
                    )
                    if commission_amount is not None:
                        has_commission = True
                        if subconfig_source and not source:
                            source = subconfig_source
                if commission_amount is None:
                    commission_amount = _first_number(
                        subconfig.get("commission_amount"),
                        subconfig.get("fee_amount"),
                        subconfig.get("commission_per_lot"),
                        subconfig.get("open_fee_amount"),
                        subconfig.get("open_commission_amount"),
                        subconfig.get("OpenRatioByVolume"),
                        subconfig.get("OPEN_FEE_AMOUNT"),
                        subconfig.get("OPEN_FEE_PER_LOT"),
                        subconfig.get("COMMISSION_OPEN_AMOUNT"),
                    )
                    if commission_amount is not None:
                        has_commission = True
                        if subconfig_source and not source:
                            source = subconfig_source
            if open_commission_amount is None:
                open_amount = _commission_amount_from_keys(
                    subconfig,
                    (
                        "open_commission_amount",
                        "open_fee_amount",
                        "OpenRatioByVolume",
                        "OPEN_FEE_AMOUNT",
                        "OPEN_FEE_PER_LOT",
                        "COMMISSION_OPEN_AMOUNT",
                    ),
                )
                if open_amount is not None:
                    open_commission_amount = open_amount
                    has_commission = True
                    if subconfig_source and not source:
                        source = subconfig_source
            if close_commission_amount is None:
                close_amount = _commission_amount_from_keys(
                    subconfig,
                    (
                        "close_commission_amount",
                        "close_fee_amount",
                        "CloseRatioByVolume",
                        "CLOSE_FEE_AMOUNT",
                        "CLOSE_FEE_PER_LOT",
                        "COMMISSION_CLOSE_AMOUNT",
                    ),
                )
                if close_amount is not None:
                    close_commission_amount = close_amount
                    has_commission = True
                    if subconfig_source and not source:
                        source = subconfig_source
            if close_today_commission_amount is None:
                close_today_amount = _commission_amount_from_keys(
                    subconfig,
                    (
                        "close_today_commission_amount",
                        "close_today_fee_amount",
                        "CloseTodayRatioByVolume",
                        "CLOSETODAY_FEE_AMOUNT",
                        "CLOSE_TODAY_FEE_AMOUNT",
                        "CLOSE_TODAY_FEE_PER_LOT",
                        "COMMISSION_CLOSE_TODAY_AMOUNT",
                    ),
                )
                if close_today_amount is not None:
                    close_today_commission_amount = close_today_amount
                    has_commission = True
                    if subconfig_source and not source:
                        source = subconfig_source
            if close_yesterday_commission_amount is None:
                close_yesterday_amount = _commission_amount_from_keys(
                    subconfig,
                    (
                        "close_yesterday_commission_amount",
                        "close_yesterday_fee_amount",
                        "CloseYesterdayRatioByVolume",
                        "CLOSEYESTERDAY_FEE_AMOUNT",
                        "CLOSE_YESTERDAY_FEE_AMOUNT",
                        "CLOSE_YESTERDAY_FEE_PER_LOT",
                        "COMMISSION_CLOSE_YESTERDAY_AMOUNT",
                    ),
                )
                if close_yesterday_amount is not None:
                    close_yesterday_commission_amount = close_yesterday_amount
                    has_commission = True
                    if subconfig_source and not source:
                        source = subconfig_source

    if multiplier is None and allow_local_otc_default:
        local_default = _local_default_contract_spec(symbol)
        if local_default:
            multiplier = _first_number(local_default.get("multiplier"))
            has_multiplier = multiplier is not None
            if not asset_type:
                asset_type = _first_text(local_default.get("asset_type"))
            if not source:
                source = _first_text(local_default.get("source"))

    if commission_rate is None and taker_commission_rate is not None:
        commission_rate = taker_commission_rate
    if commission_rate is None and maker_commission_rate is not None:
        commission_rate = maker_commission_rate
    if open_commission_rate is None:
        open_commission_rate = commission_rate
    if open_commission_amount is None:
        open_commission_amount = commission_amount

    return PositionSpec(
        multiplier=max(multiplier or 1.0, EPSILON),
        margin_rate=max(margin_rate if margin_rate is not None else 1.0, 0.0),
        margin_amount=max(margin_amount or 0.0, 0.0),
        long_margin_rate=long_margin_rate,
        short_margin_rate=short_margin_rate,
        long_margin_amount=long_margin_amount,
        short_margin_amount=short_margin_amount,
        commission_rate=max(commission_rate or 0.0, 0.0),
        commission_amount=max(commission_amount or 0.0, 0.0),
        open_commission_rate=(
            max(open_commission_rate, 0.0) if open_commission_rate is not None else None
        ),
        close_commission_rate=(
            max(close_commission_rate, 0.0) if close_commission_rate is not None else None
        ),
        close_today_commission_rate=(
            max(close_today_commission_rate, 0.0)
            if close_today_commission_rate is not None
            else None
        ),
        close_yesterday_commission_rate=(
            max(close_yesterday_commission_rate, 0.0)
            if close_yesterday_commission_rate is not None
            else None
        ),
        maker_commission_rate=maker_commission_rate,
        taker_commission_rate=taker_commission_rate,
        open_commission_amount=open_commission_amount,
        close_commission_amount=close_commission_amount,
        close_today_commission_amount=close_today_commission_amount,
        close_yesterday_commission_amount=close_yesterday_commission_amount,
        asset_type=asset_type,
        contract_type=contract_type,
        contract_value_currency=contract_value_currency,
        base_asset=base_asset,
        quote_asset=quote_asset,
        settle_currency=settle_currency,
        fee_currency=fee_currency,
        source=source,
        is_inverse=is_inverse,
        has_multiplier=has_multiplier,
        has_margin_rate=has_margin_rate,
        has_margin_amount=has_margin_amount,
        has_commission=has_commission,
    )


def _row_multiplier(
    row: dict[str, Any],
    spec: PositionSpec,
    *,
    inverse_contract: bool = False,
) -> float:
    values = (
        (
            row.get("contract_value"),
            row.get("contractValue"),
            row.get("contract_value_amount"),
            row.get("contractValueAmount"),
            row.get("contract_notional_value"),
            row.get("okx_contract_value"),
            row.get("ctVal"),
            row.get("multiplier"),
            row.get("mult"),
            row.get("contract_size"),
            row.get("trade_contract_size"),
            row.get("contract_multiplier"),
            row.get("ctMult"),
            row.get("VolumeMultiple"),
            row.get("CONTRACT_MULTIPLIER"),
        )
        if inverse_contract
        else (
            row.get("multiplier"),
            row.get("mult"),
            row.get("contract_size"),
            row.get("trade_contract_size"),
            row.get("contract_notional_value"),
            row.get("okx_contract_value"),
            row.get("contract_multiplier"),
            row.get("ctVal"),
            row.get("ctMult"),
            row.get("VolumeMultiple"),
            row.get("CONTRACT_MULTIPLIER"),
        )
    )
    return max(_first_number(*values, default=spec.multiplier) or spec.multiplier, EPSILON)


def _row_size(row: dict[str, Any]) -> float:
    long_position = _first_number(*(row.get(key) for key in LONG_POSITION_FIELD_KEYS))
    short_position = _first_number(*(row.get(key) for key in SHORT_POSITION_FIELD_KEYS))
    size_value = None
    for key in POSITION_SIZE_FIELD_KEYS:
        value = row.get(key)
        if value in (None, ""):
            continue
        size_value = value
        break
    size_number = _first_number(size_value)
    has_explicit_size = size_value not in (None, "") and size_number is not None
    size = safe_float(size_number, 0.0) or 0.0
    if (
        not has_explicit_size
        and abs(size) <= EPSILON
        and (long_position is not None or short_position is not None)
    ):
        long_size = max(long_position or 0.0, 0.0)
        short_size = max(short_position or 0.0, 0.0)
        if long_size > EPSILON or short_size > EPSILON:
            return long_size - short_size
    direction_key = ""
    direction_value = ""
    for key in (
        "direction",
        "side",
        "position_side",
        "positionSide",
        "PositionSide",
        "posSide",
        "positionIdx",
        "position_idx",
        "trade_action",
        "position_type",
        "type",
        "PosiDirection",
        "posi_direction",
        "position_direction",
    ):
        value = row.get(key)
        if value not in (None, ""):
            direction_key = key
            direction_value = str(value).strip()
            break
    direction = direction_value.lower()
    if direction in {"short", "sell", "sold", "position_type_sell", "deal_type_sell"}:
        return -abs(size)
    if direction == "flat":
        return 0.0
    try:
        code = int(float(direction_value))
    except (TypeError, ValueError):
        code = None
    if direction_key in {"trade_action", "position_type", "type"} and code == 1:
        return -abs(size)
    if direction_key in {"PosiDirection", "posi_direction", "position_direction"} and code == 3:
        return -abs(size)
    if direction_key in {"positionIdx", "position_idx"} and code == 2:
        return -abs(size)
    return size


def _row_margin_rate(row: dict[str, Any], spec: PositionSpec, size: float) -> float:
    margin_value = _first_number(
        row.get("margin"),
        row.get("margin_rate"),
        row.get("margin_ratio"),
        row.get("required_margin_percent"),
        row.get("require_margin_percent"),
        row.get("maintain_margin_percent"),
        row.get("MARGIN_RATIO"),
    )
    if margin_value is not None:
        return _normalise_rate(margin_value, spec.margin_rate)
    leverage = _first_number(
        row.get("leverage"),
        row.get("lever"),
        row.get("max_leverage"),
        row.get("maxLeverage"),
    )
    if leverage and leverage > 0:
        return 1.0 / leverage
    if size > 0:
        row_long_value = _first_number(
            row.get("long_margin_rate"),
            row.get("LongMarginRatio"),
            row.get("LongMarginRatioByMoney"),
            row.get("LONG_MARGIN_RATE"),
            row.get("MARGIN_BUY"),
        )
        if row_long_value is not None:
            return _normalise_rate(row_long_value, spec.margin_rate)
    if size < 0:
        row_short_value = _first_number(
            row.get("short_margin_rate"),
            row.get("ShortMarginRatio"),
            row.get("ShortMarginRatioByMoney"),
            row.get("SHORT_MARGIN_RATE"),
            row.get("MARGIN_SELL"),
        )
        if row_short_value is not None:
            return _normalise_rate(row_short_value, spec.margin_rate)
    if size > 0 and spec.long_margin_rate is not None:
        return spec.long_margin_rate
    if size < 0 and spec.short_margin_rate is not None:
        return spec.short_margin_rate
    return spec.margin_rate


def _currency_code(value: Any) -> str:
    return "".join(ch for ch in str(value or "").strip().upper() if ch.isalnum())


def _contract_value_currency(row: dict[str, Any], spec: PositionSpec) -> str:
    return _currency_code(
        _first_text(
            row.get("contract_value_currency"),
            row.get("contract_value_ccy"),
            row.get("ctValCcy"),
            row.get("contractValueCurrency"),
            spec.contract_value_currency,
        )
    )


def _row_contract_text(row: dict[str, Any], spec: PositionSpec, *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _is_inverse_contract(row: dict[str, Any], spec: PositionSpec) -> bool:
    explicit_flag = _explicit_inverse_flag(row)
    if explicit_flag is not None:
        return explicit_flag

    contract_type = _first_text(
        row.get("contract_type"),
        row.get("ctType"),
        row.get("contractType"),
        row.get("category"),
        spec.contract_type,
    ).lower()
    if "inverse" in contract_type:
        return True
    if "linear" in contract_type:
        return False
    if spec.is_inverse is not None:
        return spec.is_inverse

    contract_ccy = _contract_value_currency(row, spec)
    if not contract_ccy:
        return False
    base_ccy = _currency_code(
        _first_text(
            _row_contract_text(row, spec, "base_asset", "baseCcy"),
            spec.base_asset,
        )
    )
    quote_ccy = _currency_code(
        _first_text(
            _row_contract_text(row, spec, "quote_asset", "quoteCcy"),
            spec.quote_asset,
        )
    )
    settle_ccy = _currency_code(
        _first_text(
            _row_contract_text(row, spec, "settle_currency", "settleCcy"),
            _row_contract_text(row, spec, "fee_currency", "feeCcy"),
            spec.settle_currency,
            spec.fee_currency,
        )
    )
    if quote_ccy and contract_ccy == quote_ccy and contract_ccy != base_ccy:
        return True
    return bool(base_ccy and settle_ccy == base_ccy and contract_ccy != base_ccy)


def _position_notional(
    size: float,
    price: float,
    multiplier: float,
    *,
    inverse_contract: bool = False,
) -> float:
    abs_size = abs(float(size or 0.0))
    if abs_size <= EPSILON:
        return 0.0
    if inverse_contract:
        return abs_size * multiplier
    return abs_size * float(price or 0.0) * multiplier


def _calculated_gross_pnl(
    *,
    size: float,
    entry_price: float,
    current_price: float,
    multiplier: float,
    inverse_contract: bool = False,
) -> float:
    if inverse_contract:
        if entry_price <= EPSILON or current_price <= EPSILON:
            return 0.0
        return float(size or 0.0) * multiplier * ((current_price / entry_price) - 1.0)
    return (current_price - entry_price) * size * multiplier


def _commission_rate_for_role(spec: PositionSpec, role: str = "open") -> float:
    role_text = str(role or "open").strip().lower()
    if role_text == "open":
        if spec.open_commission_rate is not None:
            return spec.open_commission_rate
        if spec.taker_commission_rate is not None:
            return max(spec.taker_commission_rate, 0.0)
        return spec.commission_rate
    if role_text in {"close_today", "closetoday"}:
        if spec.close_today_commission_rate is not None:
            return spec.close_today_commission_rate
        if spec.close_commission_rate is not None:
            return spec.close_commission_rate
        if spec.taker_commission_rate is not None:
            return max(spec.taker_commission_rate, 0.0)
        return spec.commission_rate
    if role_text in {"close_yesterday", "closeyesterday"}:
        if spec.close_yesterday_commission_rate is not None:
            return spec.close_yesterday_commission_rate
        if spec.close_commission_rate is not None:
            return spec.close_commission_rate
        if spec.taker_commission_rate is not None:
            return max(spec.taker_commission_rate, 0.0)
        return spec.commission_rate
    if role_text == "close":
        if spec.close_commission_rate is not None:
            return spec.close_commission_rate
        if spec.taker_commission_rate is not None:
            return max(spec.taker_commission_rate, 0.0)
        return spec.commission_rate
    if role_text == "maker" and spec.maker_commission_rate is not None:
        return spec.maker_commission_rate
    if role_text == "taker" and spec.taker_commission_rate is not None:
        return spec.taker_commission_rate
    return spec.commission_rate


def _commission_amount_for_role(spec: PositionSpec, role: str = "open") -> float:
    role_text = str(role or "open").strip().lower()
    if role_text == "open":
        if spec.open_commission_amount is not None:
            return spec.open_commission_amount
        return spec.commission_amount
    if role_text in {"close_today", "closetoday"}:
        if spec.close_today_commission_amount is not None:
            return spec.close_today_commission_amount
        if spec.close_commission_amount is not None:
            return spec.close_commission_amount
        return spec.commission_amount
    if role_text in {"close_yesterday", "closeyesterday"}:
        if spec.close_yesterday_commission_amount is not None:
            return spec.close_yesterday_commission_amount
        if spec.close_commission_amount is not None:
            return spec.close_commission_amount
        return spec.commission_amount
    if role_text == "close" and spec.close_commission_amount is not None:
        return spec.close_commission_amount
    return spec.commission_amount


def _estimate_commission_for_role(
    *,
    size: float,
    price: float,
    multiplier: float,
    spec: PositionSpec,
    role: str,
    inverse_contract: bool = False,
) -> float:
    abs_size = abs(float(size or 0.0))
    if abs_size <= EPSILON:
        return 0.0
    notional = _position_notional(
        abs_size,
        price,
        multiplier,
        inverse_contract=inverse_contract,
    )
    return notional * _commission_rate_for_role(
        spec, role
    ) + abs_size * _commission_amount_for_role(spec, role)


def _compact_symbol(value: Any) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _row_symbol(row: dict[str, Any]) -> str:
    return _first_text(
        row.get("data_name"),
        row.get("symbol"),
        row.get("instrument"),
        row.get("InstrumentID"),
        row.get("contract"),
        row.get("instrument_id"),
        row.get("instId"),
        row.get("position_symbol_name"),
        row.get("symbol_name"),
    )


def _row_fee_currency(row: dict[str, Any]) -> str:
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
        _first_text(
            row.get("fee_currency"),
            row.get("trade_fee_currency"),
            row.get("commissionAsset"),
            row.get("commission_asset"),
            row.get("feeCurrency"),
            row.get("fillFeeCcy"),
            row.get("fill_fee_currency"),
            row.get("feeCcy"),
            row.get("fee_ccy"),
            fee_currency,
        )
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


def _row_pnl_currency(row: dict[str, Any]) -> str:
    return _currency_code(
        _first_text(
            row.get("pnl_currency"),
            row.get("pnlCurrency"),
            row.get("pnlCcy"),
            row.get("uplCcy"),
            row.get("unrealizedPnlCurrency"),
            row.get("unrealisedPnlCurrency"),
            row.get("profit_currency"),
            row.get("profitCurrency"),
            row.get("currency"),
            row.get("ccy"),
        )
    )


def _quote_currency_candidates(
    row: dict[str, Any],
    spec: PositionSpec,
    *,
    inverse_contract: bool = False,
) -> set[str]:
    candidates = {
        _currency_code(
            _first_text(
                row.get("quote_asset"),
                row.get("quoteCcy"),
                spec.quote_asset,
            )
        )
    }
    if inverse_contract:
        candidates.add(
            _currency_code(
                _first_text(
                    row.get("contract_value_currency"),
                    row.get("contract_value_ccy"),
                    row.get("ctValCcy"),
                    row.get("contractValueCurrency"),
                    spec.contract_value_currency,
                )
            )
        )
    compact = _compact_symbol(_row_symbol(row))
    for quote in _COMMON_QUOTE_SUFFIXES:
        if compact.endswith(quote) and len(compact) > len(quote):
            candidates.add(quote)
    return {item for item in candidates if item}


def _base_currency_candidates(
    row: dict[str, Any],
    spec: PositionSpec,
    *,
    inverse_contract: bool = False,
) -> set[str]:
    candidates = {
        _currency_code(
            _first_text(
                row.get("base_asset"),
                row.get("baseCcy"),
                spec.base_asset,
            )
        )
    }
    if inverse_contract:
        candidates.add(
            _currency_code(
                _first_text(
                    row.get("settle_currency"),
                    row.get("settleCcy"),
                    spec.settle_currency,
                )
            )
        )
    compact = _compact_symbol(_row_symbol(row))
    for quote in _COMMON_QUOTE_SUFFIXES:
        if compact.endswith(quote) and len(compact) > len(quote):
            candidates.add(compact[: -len(quote)])
    return {item for item in candidates if item}


def _fee_conversion_rate(
    row: dict[str, Any],
    spec: PositionSpec,
    *,
    entry_price: float | None = None,
    current_price: float | None = None,
    inverse_contract: bool = False,
) -> float | None:
    fee_currency = _row_fee_currency(row)
    if not fee_currency:
        return 1.0
    if fee_currency in _quote_currency_candidates(
        row,
        spec,
        inverse_contract=inverse_contract,
    ):
        return 1.0
    if fee_currency in _base_currency_candidates(
        row,
        spec,
        inverse_contract=inverse_contract,
    ):
        price = _first_number(
            row.get("fee_price"),
            row.get("fillPx"),
            row.get("fill_price"),
            row.get("execPrice"),
            row.get("exec_price"),
            row.get("price"),
            row.get("avgPx"),
            row.get("avg_price"),
            row.get("avgPrice"),
            entry_price,
            current_price,
        )
        if price is not None and price > EPSILON:
            return price
    return None


def _pnl_valuation_conversion_rate(
    row: dict[str, Any],
    spec: PositionSpec,
    *,
    current_price: float | None = None,
    inverse_contract: bool = False,
    field_key: str | None = None,
) -> float | None:
    pnl_currency = _row_pnl_currency(row)
    if pnl_currency:
        if pnl_currency in _quote_currency_candidates(
            row,
            spec,
            inverse_contract=inverse_contract,
        ):
            return 1.0
        if pnl_currency in _base_currency_candidates(
            row,
            spec,
            inverse_contract=inverse_contract,
        ):
            price = current_price or _first_number(
                row.get("markPx"),
                row.get("mark_price"),
                row.get("current_price"),
                row.get("last_price"),
                row.get("lastPrice"),
            )
            if price and price > EPSILON:
                return price
            return None
        return 1.0

    if inverse_contract and str(field_key or "") in _RAW_EXCHANGE_GROSS_PNL_KEYS:
        settlement_currency = _currency_code(
            _first_text(
                row.get("settle_currency"),
                row.get("settleCcy"),
                row.get("settleCoin"),
                spec.settle_currency,
            )
        )
        if settlement_currency and settlement_currency in _quote_currency_candidates(
            row,
            spec,
            inverse_contract=inverse_contract,
        ):
            return 1.0
        price = current_price or _first_number(
            row.get("markPx"),
            row.get("mark_price"),
            row.get("current_price"),
            row.get("last_price"),
            row.get("lastPrice"),
        )
        if price and price > EPSILON:
            return price
        return None
    return 1.0


def _normalized_pnl_amount(
    row: dict[str, Any],
    spec: PositionSpec,
    *,
    field_key: str | None,
    value: Any,
    current_price: float | None = None,
    inverse_contract: bool = False,
) -> float | None:
    amount = safe_float(value, None)
    if amount is None:
        return None
    conversion_rate = _pnl_valuation_conversion_rate(
        row,
        spec,
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
    current_price: float,
    multiplier: float,
    has_multiplier: bool,
) -> bool:
    if explicit_net_pnl_value not in (None, ""):
        return False
    if field_key not in _RECALCULABLE_POSITION_PNL_KEYS:
        return False
    if not has_multiplier:
        return False
    return (
        abs(size) > EPSILON
        and entry_price > EPSILON
        and current_price > EPSILON
        and multiplier > EPSILON
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
    current_price: float,
    multiplier: float,
    has_multiplier: bool,
    inverse_contract: bool,
) -> bool:
    if explicit_net_pnl_value not in (None, ""):
        return False
    if field_key not in _RAW_EXCHANGE_GROSS_PNL_KEYS:
        return False
    if inverse_contract or not has_multiplier or multiplier <= 1.0 + EPSILON:
        return False
    explicit = safe_float(explicit_gross_pnl_value, None)
    if (
        abs(size) <= EPSILON
        or entry_price <= EPSILON
        or current_price <= EPSILON
        or explicit is None
    ):
        return False
    scaled = (current_price - entry_price) * size * multiplier
    unscaled = (current_price - entry_price) * size
    if _numbers_close(explicit, scaled):
        return False
    return _numbers_close(explicit, unscaled)


def _row_commission(
    row: dict[str, Any],
    spec: PositionSpec,
    market_value: float,
    size: float,
    *,
    entry_market_value: float | None = None,
    multiplier: float | None = None,
    entry_price: float | None = None,
    current_price: float | None = None,
    inverse_contract: bool = False,
) -> float:
    explicit_key, explicit = _first_number_with_key(row, COMMISSION_FIELD_KEYS)
    if explicit is not None:
        explicit_commission: float | None = None
        if _truthy(row.get("commission_signed")):
            explicit_commission = explicit
        else:
            conversion_rate = _fee_conversion_rate(
                row,
                spec,
                entry_price=entry_price,
                current_price=current_price,
                inverse_contract=inverse_contract,
            )
            if conversion_rate is not None:
                if explicit_key in OKX_SIGNED_FEE_FIELD_KEYS and _uses_okx_fee_sign(row):
                    explicit_commission = -explicit * conversion_rate
                else:
                    explicit_commission = abs(explicit) * conversion_rate
        if explicit_commission is not None and not _zero_commission_needs_estimate(
            row,
            spec,
            explicit_commission,
        ):
            return explicit_commission
        # Incompatible fee currency, or an unconfirmed zero fee on an open
        # position. Fall back to a local asset-spec estimate.
    effective_multiplier = max(multiplier or spec.multiplier, EPSILON)
    if inverse_contract:
        effective_entry_price = float(entry_price or 0.0)
    else:
        fee_base = (
            entry_market_value if entry_market_value and entry_market_value > 0 else market_value
        )
        effective_entry_price = (
            fee_base / (abs(size) * effective_multiplier) if abs(size) > EPSILON else 0.0
        )
    return _estimate_commission_for_role(
        size=size,
        price=effective_entry_price,
        multiplier=effective_multiplier,
        spec=spec,
        role="open",
        inverse_contract=inverse_contract,
    )


def _row_margin_value(
    row: dict[str, Any],
    spec: PositionSpec,
    market_value: float,
    margin_rate: float,
    size: float,
) -> float:
    explicit = _first_number(
        row.get("margin_value"),
        row.get("use_margin"),
        row.get("initial_margin"),
        row.get("maintain_margin"),
        row.get("initialMargin"),
        row.get("maintMargin"),
        row.get("positionIM"),
        row.get("positionIMByMp"),
        row.get("positionMM"),
        row.get("positionMMByMp"),
        row.get("isolatedMargin"),
        row.get("isolated_margin"),
        row.get("imr"),
        row.get("mmr"),
    )
    if explicit is not None:
        return abs(explicit)
    row_margin_amount = _first_number(
        row.get("margin_amount"),
        row.get("initial_margin_per_lot"),
        row.get("margin_initial"),
        row.get("initial_margin_amount"),
        row.get("SYMBOL_MARGIN_INITIAL"),
        row.get("MARGIN_PER_LOT"),
    )
    if row_margin_amount is not None and row_margin_amount > 0:
        return abs(size) * row_margin_amount
    if size > 0:
        row_long_margin_amount = _first_number(
            row.get("long_margin_amount"),
            row.get("LongMarginRatioByVolume"),
            row.get("LONG_MARGIN_AMOUNT"),
            row.get("LONG_MARGIN_PER_LOT"),
        )
        if row_long_margin_amount is not None and row_long_margin_amount > 0:
            return abs(size) * row_long_margin_amount
        if spec.long_margin_amount is not None and spec.long_margin_amount > 0:
            return abs(size) * spec.long_margin_amount
    if size < 0:
        row_short_margin_amount = _first_number(
            row.get("short_margin_amount"),
            row.get("ShortMarginRatioByVolume"),
            row.get("SHORT_MARGIN_AMOUNT"),
            row.get("SHORT_MARGIN_PER_LOT"),
        )
        if row_short_margin_amount is not None and row_short_margin_amount > 0:
            return abs(size) * row_short_margin_amount
        if spec.short_margin_amount is not None and spec.short_margin_amount > 0:
            return abs(size) * spec.short_margin_amount
    if spec.margin_amount > 0:
        return abs(size) * spec.margin_amount
    return market_value * margin_rate


def _spec_has_nonzero_commission(spec: PositionSpec) -> bool:
    for value in (
        spec.commission_rate,
        spec.commission_amount,
        spec.open_commission_rate,
        spec.close_commission_rate,
        spec.close_today_commission_rate,
        spec.close_yesterday_commission_rate,
        spec.maker_commission_rate,
        spec.taker_commission_rate,
        spec.open_commission_amount,
        spec.close_commission_amount,
        spec.close_today_commission_amount,
        spec.close_yesterday_commission_amount,
    ):
        if value is not None and abs(float(value or 0.0)) > EPSILON:
            return True
    return False


def _zero_commission_needs_estimate(
    row: dict[str, Any],
    spec: PositionSpec,
    explicit_commission: float,
) -> bool:
    if abs(explicit_commission) > EPSILON:
        return False
    if str(row.get("commission_source") or "").strip().lower() == "gateway.trades":
        return False
    if _has_explicit_net_pnl(row):
        return False
    if not _spec_has_nonzero_commission(spec):
        return False
    return _has_any_gross_pnl(row) or _has_any_price(row)


def _has_explicit_net_pnl(row: dict[str, Any]) -> bool:
    return any(row.get(key) not in (None, "") for key in ("pnlcomm", "net_pnl", "netPnl", "netPNL"))


def _has_any_gross_pnl(row: dict[str, Any]) -> bool:
    return any(
        row.get(key) not in (None, "")
        for key in (
            "gross_pnl",
            "position_unrealized_pnl",
            "position_unrealised_pnl",
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
            "upl",
            "up",
            "position_profit",
            "PositionProfit",
            "position_pnl",
            "profit",
            "pnl",
        )
    )


def _has_any_price(row: dict[str, Any]) -> bool:
    return any(
        row.get(key) not in (None, "")
        for key in (
            "price",
            "avg_price",
            "average_price",
            "price_open",
            "avgCost",
            "avgPrice",
            "avgPx",
            "entryPrice",
            "current_price",
            "latest_price",
            "last_price",
            "mark_price",
            "markPrice",
            "markPx",
            "market_price",
            "lastPrice",
            "LastPrice",
        )
    )


def _row_explicit_market_value(row: dict[str, Any]) -> float | None:
    if _truthy(row.get("market_value_estimated")):
        return None

    exchange_value = _first_number(
        row.get("marketValue"),
        row.get("MarketValue"),
        row.get("mktValue"),
        row.get("positionValue"),
        row.get("position_value"),
        row.get("notionalUsd"),
        row.get("notional_usd"),
        row.get("notional"),
        row.get("notionalValue"),
        row.get("notional_value"),
        row.get("position_notional_usd"),
        row.get("position_notional"),
        row.get("positionNotional"),
    )
    if exchange_value is not None and abs(exchange_value) > EPSILON:
        return abs(exchange_value)

    source_text = " ".join(
        str(row.get(key) or "").strip().lower()
        for key in ("position_source", "source", "asset_spec_source")
    )
    if "gateway" not in source_text:
        return None

    value = _first_number(
        row.get("market_value"),
        row.get("mktValue"),
        row.get("positionValue"),
        row.get("position_value"),
        row.get("notionalUsd"),
        row.get("notional_usd"),
        row.get("notional"),
        row.get("notionalValue"),
        row.get("notional_value"),
        row.get("position_notional_usd"),
        row.get("position_notional"),
        row.get("positionNotional"),
        row.get("value"),
    )
    if value is None or abs(value) <= EPSILON:
        return None
    return abs(value)


def _current_price(
    row: dict[str, Any],
    size: float,
    entry_price: float,
    multiplier: float,
    *,
    inverse_contract: bool = False,
) -> float:
    explicit = _first_number(
        row.get("current_price"),
        row.get("latest_price"),
        row.get("last_price"),
        row.get("last"),
        row.get("mark_price"),
        row.get("markPrice"),
        row.get("markPx"),
        row.get("index_price"),
        row.get("indexPrice"),
        row.get("idxPx"),
        row.get("market_price"),
        row.get("lastPrice"),
        row.get("LastPrice"),
        row.get("price_current"),
        row.get("marketPrice"),
        row.get("mktPrice"),
        row.get("mp"),
        row.get("PriceCurrent"),
        row.get("CurrentPrice"),
        row.get("SettlementPrice"),
        row.get("settlement_price"),
    )
    if explicit is not None and explicit > 0:
        return explicit

    market_value = abs(
        _first_number(
            row.get("market_value"),
            row.get("marketValue"),
            row.get("mktValue"),
            row.get("positionValue"),
            row.get("position_value"),
            row.get("notionalUsd"),
            row.get("notional_usd"),
            row.get("notional"),
            row.get("notionalValue"),
            row.get("notional_value"),
            row.get("position_notional_usd"),
            row.get("position_notional"),
            row.get("positionNotional"),
            row.get("value"),
            default=0.0,
        )
        or 0.0
    )
    if market_value > 0 and abs(size) > EPSILON and not inverse_contract:
        plain = market_value / abs(size)
        with_multiplier = market_value / (abs(size) * multiplier)
        if entry_price > 0 and multiplier > 1.0:
            return (
                plain
                if abs(plain - entry_price) <= abs(with_multiplier - entry_price)
                else with_multiplier
            )
        return plain

    return entry_price


def value_position(
    row: dict[str, Any],
    *,
    spec: PositionSpec | None = None,
) -> ValuedPosition | None:
    """Return a valued position row, or ``None`` for zero-size positions."""
    data_name = str(
        row.get("data_name")
        or row.get("symbol")
        or row.get("instrument")
        or row.get("InstrumentID")
        or row.get("contract")
        or row.get("instrument_id")
        or row.get("instId")
        or row.get("position_symbol_name")
        or row.get("symbol_name")
        or ""
    ).strip()
    size = _row_size(row)
    if abs(size) <= EPSILON:
        return None

    row_spec = spec or PositionSpec()
    inverse_contract = _is_inverse_contract(row, row_spec)
    multiplier_keys = (
        (
            row.get("contract_value"),
            row.get("contractValue"),
            row.get("contract_value_amount"),
            row.get("contractValueAmount"),
            row.get("contract_notional_value"),
            row.get("okx_contract_value"),
            row.get("ctVal"),
            row.get("multiplier"),
            row.get("mult"),
            row.get("contract_size"),
            row.get("trade_contract_size"),
            row.get("contract_multiplier"),
            row.get("ctMult"),
            row.get("VolumeMultiple"),
            row.get("CONTRACT_MULTIPLIER"),
        )
        if inverse_contract
        else (
            row.get("multiplier"),
            row.get("mult"),
            row.get("contract_size"),
            row.get("trade_contract_size"),
            row.get("contract_notional_value"),
            row.get("okx_contract_value"),
            row.get("contract_multiplier"),
            row.get("ctVal"),
            row.get("ctMult"),
            row.get("VolumeMultiple"),
            row.get("CONTRACT_MULTIPLIER"),
        )
    )
    has_multiplier = row_spec.has_multiplier or _first_number(*multiplier_keys) is not None
    multiplier = _row_multiplier(row, row_spec, inverse_contract=inverse_contract)
    margin_rate = _row_margin_rate(row, row_spec, size)
    entry_price = safe_float(
        _first_number(
            row.get("price"),
            row.get("avg_price"),
            row.get("average_price"),
            row.get("price_open"),
            row.get("entry_price"),
            row.get("avgCost"),
            row.get("avgPrice"),
            row.get("avgPx"),
            row.get("avg_entry_price"),
            row.get("avgEntryPrice"),
            row.get("entryPrice"),
            row.get("ep"),
            row.get("open_avg_price"),
            row.get("openAvgPrice"),
            row.get("averageCost"),
            row.get("Price"),
            row.get("AveragePrice"),
            default=0.0,
        ),
        0.0,
    )
    if entry_price <= 0 and abs(size) > EPSILON and multiplier > 0 and not inverse_contract:
        position_cost = _first_number(
            row.get("PositionCost"),
            row.get("position_cost"),
            row.get("positionCost"),
            row.get("OpenCost"),
            row.get("open_cost"),
            row.get("openCost"),
        )
        if position_cost and position_cost > 0:
            entry_price = position_cost / (abs(size) * multiplier)
    current_price = _current_price(
        row,
        size,
        entry_price,
        multiplier,
        inverse_contract=inverse_contract,
    )
    calculated_entry_market_value = _position_notional(
        size,
        entry_price,
        multiplier,
        inverse_contract=inverse_contract,
    )
    calculated_market_value = _position_notional(
        size,
        current_price,
        multiplier,
        inverse_contract=inverse_contract,
    )
    explicit_market_value = _row_explicit_market_value(row)
    market_value = (
        explicit_market_value if explicit_market_value is not None else calculated_market_value
    )
    if (
        explicit_market_value is not None
        and not inverse_contract
        and current_price > EPSILON
        and entry_price > EPSILON
    ):
        entry_market_value = explicit_market_value * abs(entry_price / current_price)
    else:
        entry_market_value = calculated_entry_market_value
    margin_value = _row_margin_value(row, row_spec, market_value, margin_rate, size)
    direction = "long" if size > 0 else "short"

    explicit_net_pnl_key, explicit_net_pnl_value = _first_number_with_key(
        row,
        EXPLICIT_NET_PNL_FIELD_KEYS,
    )
    if explicit_net_pnl_value is None and _row_marks_pnl_as_net(row):
        explicit_net_pnl_key, explicit_net_pnl_value = _first_number_with_key(
            row,
            MARKABLE_NET_PNL_FIELD_KEYS,
        )
    explicit_net_pnl = (
        _normalized_pnl_amount(
            row,
            row_spec,
            field_key=explicit_net_pnl_key,
            value=explicit_net_pnl_value,
            current_price=current_price,
            inverse_contract=inverse_contract,
        )
        if explicit_net_pnl_value is not None
        else None
    )
    explicit_gross_pnl_key, explicit_gross_pnl_value = _first_number_with_key(
        row,
        (
            "gross_pnl",
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
            "position_pnl",
            "profit",
            "pnl",
        ),
    )
    explicit_gross_pnl = (
        _normalized_pnl_amount(
            row,
            row_spec,
            field_key=explicit_gross_pnl_key,
            value=explicit_gross_pnl_value,
            current_price=current_price,
            inverse_contract=inverse_contract,
        )
        if explicit_gross_pnl_value is not None
        else None
    )
    if explicit_net_pnl is not None and (
        explicit_net_pnl_key == explicit_gross_pnl_key
        or explicit_gross_pnl_key in MARKABLE_NET_PNL_FIELD_KEYS
    ):
        explicit_gross_pnl = None
    calculated_gross_pnl = _calculated_gross_pnl(
        size=size,
        entry_price=entry_price,
        current_price=current_price,
        multiplier=multiplier,
        inverse_contract=inverse_contract,
    )
    if _should_recalculate_generic_pnl(
        field_key=explicit_gross_pnl_key,
        explicit_net_pnl_value=explicit_net_pnl_value,
        size=size,
        entry_price=entry_price,
        current_price=current_price,
        multiplier=multiplier,
        has_multiplier=has_multiplier,
    ):
        explicit_gross_pnl = None
    if _should_recalculate_unscaled_exchange_pnl(
        field_key=explicit_gross_pnl_key,
        explicit_net_pnl_value=explicit_net_pnl_value,
        explicit_gross_pnl_value=explicit_gross_pnl_value,
        size=size,
        entry_price=entry_price,
        current_price=current_price,
        multiplier=multiplier,
        has_multiplier=has_multiplier,
        inverse_contract=inverse_contract,
    ):
        explicit_gross_pnl = None
    gross_pnl = explicit_gross_pnl if explicit_gross_pnl is not None else calculated_gross_pnl
    commission = _row_commission(
        row,
        row_spec,
        market_value,
        size,
        entry_market_value=entry_market_value,
        multiplier=multiplier,
        entry_price=entry_price,
        current_price=current_price,
        inverse_contract=inverse_contract,
    )
    swap = _sum_signed_amounts(row, CARRY_PNL_FIELD_KEYS)
    net_pnl = explicit_net_pnl if explicit_net_pnl is not None else gross_pnl + swap - commission

    return ValuedPosition(
        data_name=data_name,
        size=size,
        direction=direction,
        entry_price=entry_price,
        current_price=current_price,
        multiplier=multiplier,
        margin_rate=margin_rate,
        market_value=market_value,
        margin_value=margin_value,
        commission=commission,
        gross_pnl=gross_pnl,
        pnl=net_pnl,
    )
