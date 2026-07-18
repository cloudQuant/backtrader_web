"""Local, gateway, and runtime asset-spec resolution helpers."""

# Asset helpers are composed by asset_info.__init__ after stage imports complete.
# mypy: disable-error-code=name-defined
# ruff: noqa: F403, F405
from app.services import trading_asset_info_service as _asset_info_service
from app.services.trading_asset_info_service import *

globals().update(
    {name: value for name, value in vars(_asset_info_service).items() if not name.startswith("__")}
)


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
    return _query_local_futures_spec(symbol) or _query_local_otc_spec(symbol)


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
    trader_client = _safe_getattr(adapter, "trader_client")
    if trader_client is not None:
        candidates.append(("gateway.trader_client", trader_client))
    feed_trader_client = _safe_getattr(feed, "trader_client") if feed is not None else None
    if feed_trader_client is not None:
        candidates.append(("gateway.feed.trader_client", feed_trader_client))
    client_feed = _safe_getattr(client, "feed") if client is not None else None
    if client_feed is not None:
        candidates.append(("gateway.client.feed", client_feed))
    client_feed_trader_client = (
        _safe_getattr(client_feed, "trader_client") if client_feed is not None else None
    )
    if client_feed_trader_client is not None:
        candidates.append(("gateway.client.feed.trader_client", client_feed_trader_client))

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


def _configured_runtime_asset_spec(config: dict[str, Any]) -> dict[str, Any]:
    """Return fee and margin defaults explicitly configured for a runtime.

    Gateway metadata is preferred when available, but a trading workspace can
    explicitly configure simulation/live commission and margin settings before
    a broker exposes per-symbol metadata.  Keep those values as a fallback so
    the preflight validator does not reject an otherwise configured strategy.
    """
    fields = (
        "commission",
        "commission_rate",
        "open_commission_rate",
        "close_commission_rate",
        "close_today_commission_rate",
        "close_yesterday_commission_rate",
        "commission_amount",
        "open_commission_amount",
        "close_commission_amount",
        "margin",
        "margin_rate",
        "margin_ratio",
        "long_margin_rate",
        "short_margin_rate",
        "margin_amount",
        "initial_margin_per_lot",
        "margin_initial",
        "leverage",
        "lever",
        "max_leverage",
    )
    raw: dict[str, Any] = {}
    for section in (
        _as_dict(config.get("unit_settings")),
        _as_dict(config.get("simulate")),
        _as_dict(config.get("live")),
        _as_dict(config.get("backtest")),
        config,
    ):
        for field in fields:
            value = section.get(field)
            if field not in raw and value not in (None, ""):
                raw[field] = value
    return normalize_asset_spec(raw, source="runtime_config") if raw else {}


def _gateway_exchange_type(gateway: dict[str, Any] | None) -> str:
    if not isinstance(gateway, dict):
        return ""
    config = gateway.get("config")
    value = (
        config.get("exchange_type")
        if isinstance(config, dict)
        else _safe_getattr(config, "exchange_type")
    )
    return str(value or gateway.get("exchange_type") or "").strip().upper()


def _gateway_account_leverage_spec(gateway: dict[str, Any] | None) -> dict[str, Any]:
    """Use the connected MT5 account leverage when symbol metadata omits it."""
    if not isinstance(gateway, dict):
        return {}
    if _gateway_exchange_type(gateway) != "MT5":
        return {}

    cached_leverage = _safe_float(gateway.get("_asset_spec_account_leverage"))
    if cached_leverage is not None and cached_leverage > 0:
        return normalize_asset_spec({"leverage": cached_leverage}, source="gateway.account_summary")

    adapter = _runtime_adapter(gateway)
    get_balance = _safe_getattr(adapter, "get_balance")
    if not callable(get_balance):
        return {}
    try:
        account = get_balance()
    except Exception:
        return {}
    leverage = _safe_float(_object_get(account, "leverage", "lever", "max_leverage"))
    if leverage is None or leverage <= 0:
        return {}
    gateway["_asset_spec_account_leverage"] = leverage
    return normalize_asset_spec({"leverage": leverage}, source="gateway.account_summary")


def _fill_missing_asset_spec(merged: dict[str, Any], fallback: dict[str, Any]) -> None:
    """Fill missing fields without replacing broker-provided specifications."""
    for key, value in fallback.items():
        if key != "source" and merged.get(key) in (None, "") and value not in (None, ""):
            merged[key] = value


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


def _query_cached_gateway_asset_spec(gateway: dict[str, Any] | None, symbol: str) -> dict[str, Any]:
    """Read already-loaded gateway metadata without issuing a remote request."""
    adapter = _runtime_adapter(gateway)
    specs = _safe_getattr(adapter, "_symbol_specs")
    if not isinstance(specs, dict):
        return {}
    for key in _symbol_keys(symbol):
        item = specs.get(key)
        if isinstance(item, dict) and item:
            return normalize_asset_spec(item, symbol=symbol, source="gateway.symbol_cache")
    return {}


def _query_gateway_fee_spec(adapter: Any, symbol: str) -> dict[str, Any]:
    exchange_scoped_methods = {"query_instrument_commission_rate"}
    plural_fee_methods = {"get_trading_fees", "fetch_trading_fees"}
    for target_label, target in _gateway_asset_query_targets(adapter):
        for method_name in (
            "get_fee",
            "fetch_fee",
            "get_fee_rate",
            "fetch_fee_rate",
            "get_commission_rate",
            "fetch_commission_rate",
            "get_trading_fee",
            "fetch_trading_fee",
            "get_trading_fees",
            "fetch_trading_fees",
            "query_instrument_commission_rate",
        ):
            method = _safe_getattr(target, method_name)
            if not callable(method):
                continue
            query_symbols = _query_symbol_keys(symbol)
            if method_name not in exchange_scoped_methods:
                for query_symbol in query_symbols:
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
            attempts: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
            for query_symbol in query_symbols:
                attempts.extend(
                    _gateway_asset_method_attempts(
                        method_name,
                        query_symbol,
                        target,
                        adapter,
                        include_empty_call=method_name in plural_fee_methods,
                    )
                )
            attempted = {
                repr(((query_symbol,), {}))
                for query_symbol in query_symbols
                if method_name not in exchange_scoped_methods
            }
            for args, kwargs in attempts:
                if repr((args, kwargs)) in attempted:
                    continue
                try:
                    payload = method(*args, **kwargs)
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


def _merge_margin_spec(spec: dict[str, Any], margin_spec: dict[str, Any]) -> dict[str, Any]:
    if not margin_spec:
        return spec
    merged = dict(spec)
    source = str(merged.get("source") or "").strip()
    margin_source = str(margin_spec.get("source") or "").strip()
    for key, value in margin_spec.items():
        if key == "source":
            continue
        merged[key] = value
    if margin_source:
        merged["margin_source"] = margin_source
    if source:
        merged["source"] = source
    return merged


def _has_margin_spec(spec: dict[str, Any]) -> bool:
    return any(
        spec.get(key) not in (None, "")
        for key in (
            "margin",
            "margin_rate",
            "margin_ratio",
            "long_margin_rate",
            "short_margin_rate",
            "margin_amount",
            "long_margin_amount",
            "short_margin_amount",
            "initial_margin_per_lot",
            "margin_initial",
            "initial_margin_amount",
            "LongMarginRatioByMoney",
            "ShortMarginRatioByMoney",
            "LongMarginRatioByVolume",
            "ShortMarginRatioByVolume",
            "leverage",
            "lever",
            "max_leverage",
            "maxLeverage",
        )
    )


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
    exchange_scoped_method = method_name in {
        "query_instrument",
        "query_instrument_margin_rate",
        "query_instrument_commission_rate",
        "get_instrument_margin_rate",
        "fetch_instrument_margin_rate",
    }
    if query_symbol:
        instrument, exchange_id = _split_symbol_exchange(query_symbol)
        if exchange_scoped_method and instrument and exchange_id:
            attempts.extend(
                (
                    ((instrument,), {"exchange_id": exchange_id, "timeout": 2}),
                    ((instrument,), {"exchange_id": exchange_id}),
                    (
                        (),
                        {"instrument_id": instrument, "exchange_id": exchange_id, "timeout": 2},
                    ),
                    ((), {"instrument_id": instrument, "exchange_id": exchange_id}),
                )
            )
        if instrument_method and asset_type:
            attempts.append(((), {"asset_type": asset_type, "inst_id": query_symbol}))
        if instrument_method:
            attempts.extend(
                (
                    ((), {"inst_id": query_symbol}),
                    ((), {"instId": query_symbol}),
                    ((), {"instrument": query_symbol}),
                    ((), {"instrument_id": query_symbol}),
                )
            )
        attempts.extend(
            (
                ((query_symbol,), {}),
                ((), {"symbol": query_symbol}),
                ((), {"inst_id": query_symbol}),
                ((), {"instId": query_symbol}),
                ((), {"instrument": query_symbol}),
                ((), {"instrument_id": query_symbol}),
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


def _query_gateway_margin_spec(adapter: Any, symbol: str) -> dict[str, Any]:
    for target_label, target in _gateway_asset_query_targets(adapter):
        for method_name in (
            "get_margin",
            "fetch_margin",
            "get_margin_rate",
            "fetch_margin_rate",
            "get_leverage",
            "fetch_leverage",
            "get_leverage_tiers",
            "fetch_leverage_tiers",
            "fetch_market_leverage_tiers",
            "get_instrument_margin_rate",
            "fetch_instrument_margin_rate",
            "query_instrument_margin_rate",
        ):
            method = _safe_getattr(target, method_name)
            if not callable(method):
                continue
            attempts: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
            for query_symbol in _query_symbol_keys(symbol):
                attempts.extend(
                    _gateway_asset_method_attempts(method_name, query_symbol, target, adapter)
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
                if _has_margin_spec(spec):
                    return spec
    return {}


def _query_gateway_common_asset_spec(
    adapter: Any,
    symbol: str,
    fee_spec: dict[str, Any],
    margin_spec: dict[str, Any],
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
        "query_instrument",
        "market",
        "get_market",
        "fetch_market",
        "load_markets",
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
                    return _merge_fee_spec(_merge_margin_spec(spec, margin_spec), fee_spec)
        for attr_name in ("markets", "_markets", "market_cache", "_market_cache"):
            payload = _safe_getattr(target, attr_name)
            if not isinstance(payload, dict):
                continue
            spec = normalize_asset_spec(
                payload,
                symbol=symbol,
                source=f"{target_label}.{attr_name}",
            )
            if _has_asset_metadata(spec):
                return _merge_fee_spec(_merge_margin_spec(spec, margin_spec), fee_spec)
    return {}


def query_gateway_asset_spec(gateway: dict[str, Any] | None, symbol: str) -> dict[str, Any]:
    adapter = _runtime_adapter(gateway)
    if adapter is None:
        return {}

    fee_spec = _query_gateway_fee_spec(adapter, symbol)
    margin_spec = _query_gateway_margin_spec(adapter, symbol)
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
                            return _merge_fee_spec(
                                _merge_margin_spec(spec, margin_spec),
                                fee_spec,
                            )

    cached_spec = _query_cached_gateway_asset_spec(gateway, symbol)
    if cached_spec:
        return _merge_fee_spec(_merge_margin_spec(cached_spec, margin_spec), fee_spec)

    spec = _query_gateway_common_asset_spec(adapter, symbol, fee_spec, margin_spec)
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
            return _merge_fee_spec(_merge_margin_spec(spec, margin_spec), fee_spec)

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
                return _merge_fee_spec(_merge_margin_spec(spec, margin_spec), fee_spec)

    return _merge_fee_spec(margin_spec, fee_spec)


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
        for container_key in (
            "contract_metadata",
            "contracts",
            "contract_specs",
            "instrument_specs",
        ):
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
    configured_runtime_spec = _configured_runtime_asset_spec(config)
    resolved: dict[str, dict[str, Any]] = {}
    for symbol in list(symbols or symbols_for_instance(instance, strategy_dir)):
        merged: dict[str, Any] = {}
        local_spec = query_local_asset_spec(symbol)
        gateway_spec = (
            _query_cached_gateway_asset_spec(gateway, symbol)
            if local_spec and _gateway_exchange_type(gateway) == "MT5"
            else query_gateway_asset_spec(gateway, symbol)
        )
        for source in (
            _extract_existing_metadata(config, symbol),
            _extract_existing_metadata(params, symbol),
            local_spec,
            gateway_spec,
        ):
            if source:
                merged.update(source)
        _fill_missing_asset_spec(merged, configured_runtime_spec)
        _fill_missing_asset_spec(merged, _gateway_account_leverage_spec(gateway))
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
