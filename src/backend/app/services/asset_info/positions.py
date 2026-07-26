"""Gateway-position normalization for trading asset metadata."""

# Asset helpers are composed by asset_info.__init__ after stage imports complete.
# mypy: disable-error-code=name-defined
# ruff: noqa: F403, F405
from app.services import trading_asset_info_service as _asset_info_service
from app.services.trading_asset_info_service import *

globals().update(
    {name: value for name, value in vars(_asset_info_service).items() if not name.startswith("__")}
)


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
    multiplier_value = _first_number(
        _first_value(asset_spec or {}, *multiplier_keys),
        _first_value(row, *multiplier_keys),
    )
    has_multiplier = multiplier_value is not None
    multiplier = multiplier_value or 1.0
    price = (
        _safe_float(
            _first_value(
                row,
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
                "ep",
                "open_avg_price",
                "openAvgPrice",
                "Price",
                "AveragePrice",
            ),
            0.0,
        )
        or 0.0
    )
    if price <= 0 and abs(size) > 0 and multiplier > 0 and not inverse_contract:
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

    explicit_net_pnl_key, explicit_net_pnl_value = _first_value_with_key(
        row,
        *EXPLICIT_NET_PNL_FIELD_KEYS,
    )
    if explicit_net_pnl_value in (None, "") and _row_marks_pnl_as_net(row):
        explicit_net_pnl_key, explicit_net_pnl_value = _first_value_with_key(
            row,
            *MARKABLE_NET_PNL_FIELD_KEYS,
        )
    commission_key, commission_value = _first_value_with_key(row, *COMMISSION_FIELD_KEYS)
    has_commission = commission_value not in (None, "")
    carry_pnl = _sum_signed_amounts(row, CARRY_PNL_FIELD_KEYS)
    has_carry_pnl = any(
        key in row and row.get(key) not in (None, "") for key in CARRY_PNL_FIELD_KEYS
    )
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
            if (
                abs(commission) <= 1e-12
                and explicit_net_pnl_value in (None, "")
                and _asset_spec_has_nonzero_fee(asset_spec)
            ):
                has_commission = False
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
    gross_pnl_key, gross_pnl_value = _first_value_with_key(
        row,
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
        _normalized_pnl_amount(
            row,
            symbol,
            asset_spec,
            field_key=explicit_net_pnl_key,
            value=explicit_net_pnl_value,
            current_price=current_price_number,
            inverse_contract=inverse_contract,
        )
        if explicit_net_pnl_value is not None
        else None
    )
    gross_pnl = (
        _normalized_pnl_amount(
            row,
            symbol,
            asset_spec,
            field_key=gross_pnl_key,
            value=gross_pnl_value,
            current_price=current_price_number,
            inverse_contract=inverse_contract,
        )
        if gross_pnl_value is not None
        else None
    )
    if explicit_net_pnl_key and explicit_net_pnl_key == gross_pnl_key:
        gross_pnl = None
    generic_pnl_recalculated = _should_recalculate_generic_pnl(
        field_key=gross_pnl_key,
        explicit_net_pnl_value=explicit_net_pnl_value,
        size=size,
        entry_price=price,
        current_price=current_price,
        multiplier=multiplier,
        has_multiplier=has_multiplier,
    )
    exchange_pnl_recalculated = _should_recalculate_unscaled_exchange_pnl(
        field_key=gross_pnl_key,
        explicit_net_pnl_value=explicit_net_pnl_value,
        explicit_gross_pnl_value=gross_pnl_value,
        size=size,
        entry_price=price,
        current_price=current_price,
        multiplier=multiplier,
        has_multiplier=has_multiplier,
        inverse_contract=inverse_contract,
    )
    if generic_pnl_recalculated or exchange_pnl_recalculated:
        gross_pnl = None
    net_pnl = None
    if explicit_net_pnl is not None:
        net_pnl = explicit_net_pnl
    elif gross_pnl is not None and has_commission:
        net_pnl = gross_pnl + carry_pnl - commission
    explicit_margin = _safe_float(
        _first_value(
            row,
            "margin_value",
            "use_margin",
            "initial_margin",
            "maintain_margin",
            "initialMargin",
            "maintMargin",
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
    long_position = _first_number(*(row.get(key) for key in LONG_POSITION_FIELD_KEYS))
    if long_position is not None and long_position > 0:
        normalized["long_position"] = long_position
    short_position = _first_number(*(row.get(key) for key in SHORT_POSITION_FIELD_KEYS))
    if short_position is not None and short_position > 0:
        normalized["short_position"] = short_position
    long_market_value = _first_number(
        _first_value(
            row,
            "long_market_value",
            "longMarketValue",
            "long_position_value",
            "longPositionValue",
            "long_notional",
            "longNotional",
        )
    )
    if long_market_value is not None:
        normalized["long_market_value"] = abs(long_market_value)
    short_market_value = _first_number(
        _first_value(
            row,
            "short_market_value",
            "shortMarketValue",
            "short_position_value",
            "shortPositionValue",
            "short_notional",
            "shortNotional",
        )
    )
    if short_market_value is not None:
        normalized["short_market_value"] = abs(short_market_value)
    if has_commission:
        normalized["commission"] = commission
        normalized["commission_signed"] = True
        if commission_source:
            normalized["commission_source"] = commission_source
    if commission_unconfirmed_reason == "commission_currency_mismatch":
        normalized["commission_currency_mismatch"] = True
    if has_carry_pnl:
        normalized["swap"] = carry_pnl
    realized_pnl = _first_value(
        row, "realized_pnl", "position_realized_pnl", "realizedPnl", "realised_pnl"
    )
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
    if generic_pnl_recalculated:
        normalized["generic_pnl_recalculated"] = True
    if exchange_pnl_recalculated:
        normalized["exchange_pnl_recalculated"] = True
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
        normalized["market_value"] = (
            market_value_number if market_value_number is not None else market_value
        )
    if explicit_margin is not None:
        normalized["margin_value"] = abs(explicit_margin)
        normalized["use_margin"] = abs(explicit_margin)
    return {key: value for key, value in normalized.items() if value not in (None, "")}
