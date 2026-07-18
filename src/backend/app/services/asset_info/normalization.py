"""Canonical asset-spec normalization across broker payload formats."""

# Asset helpers are composed by asset_info.__init__ after stage imports complete.
# mypy: disable-error-code=name-defined
# ruff: noqa: F403, F405
from app.services import trading_asset_info_service as _asset_info_service
from app.services.trading_asset_info_service import *

globals().update(
    {name: value for name, value in vars(_asset_info_service).items() if not name.startswith("__")}
)


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
    if isinstance(raw, dict):
        selected = _select_symbol_keyed_payload(raw, symbol)
        if selected is not None:
            raw = selected

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

    asset_type_text = _first_text(
        data.get("asset_type"), data.get("instType"), data.get("category"), data.get("type")
    )
    contract_type_text = _first_text(
        data.get("contract_type"),
        data.get("ctType"),
        data.get("contractType"),
    )
    if not contract_type_text:
        if _truthy(data.get("inverse")):
            contract_type_text = "inverse"
        elif _truthy(data.get("linear")):
            contract_type_text = "linear"
    contract_value_currency = _first_text(
        data.get("contract_value_currency"),
        data.get("contract_value_ccy"),
        data.get("ctValCcy"),
        data.get("contractValueCurrency"),
    )
    base_asset = _first_text(
        data.get("base_asset"), data.get("baseCcy"), data.get("baseCoin"), data.get("base")
    )
    quote_asset = _first_text(
        data.get("quote_asset"), data.get("quoteCcy"), data.get("quoteCoin"), data.get("quote")
    )
    settle_currency = _first_text(
        data.get("settle_currency"),
        data.get("settleCcy"),
        data.get("settleCoin"),
        data.get("settle"),
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
        data.get("contractMultiplier"),
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
            data.get("contractSize"),
            data.get("trade_contract_size"),
            data.get("tradeContractSize"),
            contract_multiplier,
            data.get("VolumeMultiple"),
            data.get("volume_multiple"),
            data.get("VolumeMultiplier"),
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
                    data.get("contractSize"),
                    data.get("trade_contract_size"),
                    data.get("tradeContractSize"),
                    contract_multiplier,
                    data.get("VolumeMultiple"),
                    data.get("volume_multiple"),
                    data.get("VolumeMultiplier"),
                    data.get("CONTRACT_MULTIPLIER"),
                    okx_contract_value,
                )
            )
        if (
            multiplier is None
            and is_derivative
            and "linear" in (f"{asset_type_text} {contract_type_text}".lower())
        ):
            multiplier = 1.0
    price_tick = _first_number(
        data.get("price_tick"),
        data.get("priceTick"),
        data.get("tick_size"),
        data.get("min_price_change"),
        data.get("minPriceChange"),
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
            data.get("longMarginRatio"),
            data.get("LongMarginRatioByMoney"),
            data.get("longMarginRatioByMoney"),
            data.get("LONG_MARGIN_RATE"),
            data.get("MARGIN_BUY"),
        )
    )
    short_margin_rate = _normalize_decimal_rate(
        _first_number(
            data.get("short_margin_rate"),
            data.get("ShortMarginRatio"),
            data.get("shortMarginRatio"),
            data.get("ShortMarginRatioByMoney"),
            data.get("shortMarginRatioByMoney"),
            data.get("SHORT_MARGIN_RATE"),
            data.get("MARGIN_SELL"),
        )
    )
    margin_rate = _normalize_decimal_rate(
        _first_number(
            data.get("margin"),
            data.get("margin_rate"),
            data.get("marginRate"),
            data.get("margin_ratio"),
            data.get("marginRatio"),
            data.get("required_margin_percent"),
            data.get("require_margin_percent"),
            data.get("maintain_margin_percent"),
            data.get("initialMarginRatio"),
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
            (1.0 / leverage) if leverage and leverage > 0 else long_margin_rate or short_margin_rate
        )
    margin_amount = _first_number(
        data.get("margin_amount"),
        data.get("marginAmount"),
        data.get("initial_margin_per_lot"),
        data.get("margin_initial"),
        data.get("marginInitial"),
        data.get("initial_margin_amount"),
        data.get("initialMargin"),
        data.get("SYMBOL_MARGIN_INITIAL"),
        data.get("MARGIN_PER_LOT"),
        data.get("LONG_MARGIN_AMOUNT"),
        data.get("LONG_MARGIN_PER_LOT"),
    )
    long_margin_amount = _first_number(
        data.get("long_margin_amount"),
        data.get("LongMarginRatioByVolume"),
        data.get("longMarginRatioByVolume"),
        data.get("LONG_MARGIN_AMOUNT"),
        data.get("LONG_MARGIN_PER_LOT"),
    )
    short_margin_amount = _first_number(
        data.get("short_margin_amount"),
        data.get("ShortMarginRatioByVolume"),
        data.get("shortMarginRatioByVolume"),
        data.get("SHORT_MARGIN_AMOUNT"),
        data.get("SHORT_MARGIN_PER_LOT"),
    )

    source_text = f"{source or ''} {data.get('source') or ''}".lower()
    commission_rate_key, commission_rate_raw = _first_value_with_key(
        data,
        "commission",
        "commission_rate",
        "commissionRate",
        "fee_rate",
        "feeRate",
        "open_fee_rate",
        "openFeeRate",
        "open_commission_rate",
        "openCommissionRate",
        "OpenRatioByMoney",
        "openRatioByMoney",
        "OPEN_FEE_RATE",
        "COMMISSION_OPEN_RATIO",
    )
    commission_rate = _safe_float(commission_rate_raw)
    close_rate_key, close_rate_raw = _first_value_with_key(
        data,
        "close_commission_rate",
        "closeCommissionRate",
        "close_fee_rate",
        "closeFeeRate",
        "CloseRatioByMoney",
        "closeRatioByMoney",
        "CLOSE_FEE_RATE",
        "COMMISSION_CLOSE_RATIO",
    )
    close_commission_rate = _safe_float(close_rate_raw)
    close_today_rate_key, close_today_rate_raw = _first_value_with_key(
        data,
        "close_today_commission_rate",
        "closeTodayCommissionRate",
        "close_today_fee_rate",
        "closeTodayFeeRate",
        "CloseTodayRatioByMoney",
        "closeTodayRatioByMoney",
        "CLOSE_TODAY_FEE_RATE",
        "CLOSETODAY_FEE_RATE",
        "COMMISSION_CLOSE_TODAY_RATIO",
    )
    close_today_commission_rate = _safe_float(close_today_rate_raw)
    close_yesterday_rate_key, close_yesterday_rate_raw = _first_value_with_key(
        data,
        "close_yesterday_commission_rate",
        "closeYesterdayCommissionRate",
        "close_yesterday_fee_rate",
        "closeYesterdayFeeRate",
        "CloseYesterdayRatioByMoney",
        "closeYesterdayRatioByMoney",
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
        "makerFeeRate",
        "makerCommissionRate",
        "makerCommission",
        "makerU",
        "maker",
    )
    taker_rate_key, taker_rate_raw = _first_value_with_key(
        data,
        "taker_commission_rate",
        "taker_fee_rate",
        "takerFeeRate",
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
            taker_commission_rate if taker_commission_rate is not None else maker_commission_rate
        )
    commission_amount_key, commission_amount_raw = _first_value_with_key(
        data,
        "commission_amount",
        "commissionAmount",
        "fee_amount",
        "feeAmount",
        "commission_per_lot",
        "open_fee_amount",
        "openFeeAmount",
        "open_commission_amount",
        "openCommissionAmount",
        "OpenRatioByVolume",
        "openRatioByVolume",
        "OPEN_FEE_AMOUNT",
        "OPEN_FEE_PER_LOT",
        "COMMISSION_OPEN_AMOUNT",
    )
    commission_amount = _safe_float(commission_amount_raw)
    _close_amount_key, close_amount_raw = _first_value_with_key(
        data,
        "close_commission_amount",
        "closeCommissionAmount",
        "close_fee_amount",
        "closeFeeAmount",
        "CloseRatioByVolume",
        "closeRatioByVolume",
        "CLOSE_FEE_AMOUNT",
        "CLOSE_FEE_PER_LOT",
        "COMMISSION_CLOSE_AMOUNT",
    )
    close_commission_amount = _safe_float(close_amount_raw)
    _close_today_amount_key, close_today_amount_raw = _first_value_with_key(
        data,
        "close_today_commission_amount",
        "closeTodayCommissionAmount",
        "close_today_fee_amount",
        "closeTodayFeeAmount",
        "CloseTodayRatioByVolume",
        "closeTodayRatioByVolume",
        "CLOSE_TODAY_FEE_AMOUNT",
        "CLOSETODAY_FEE_AMOUNT",
        "CLOSE_TODAY_FEE_PER_LOT",
        "COMMISSION_CLOSE_TODAY_AMOUNT",
    )
    close_today_commission_amount = _safe_float(close_today_amount_raw)
    _close_yesterday_amount_key, close_yesterday_amount_raw = _first_value_with_key(
        data,
        "close_yesterday_commission_amount",
        "closeYesterdayCommissionAmount",
        "close_yesterday_fee_amount",
        "closeYesterdayFeeAmount",
        "CloseYesterdayRatioByVolume",
        "closeYesterdayRatioByVolume",
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
        normalized_commission_rate = (
            _normalize_role_commission_rate(
                commission_rate_key,
                commission_rate,
            )
            or 0.0
        )
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
