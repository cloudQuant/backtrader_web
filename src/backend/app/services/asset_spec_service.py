"""Asset specification resolution service."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.market_data_trust import AssetSpecModel
from app.schemas.market_data_trust import AssetSpecCreate, AssetSpecResponse
from app.services.trading_asset_info_service import normalize_asset_spec, query_local_asset_spec

_FUTURES_DEFAULTS: dict[str, dict[str, Any]] = {
    "RB": {
        "name": "Rebar continuous futures",
        "exchange": "SHFE",
        "contract_multiplier": 10.0,
        "margin_rate": 0.1,
        "tick_size": 1.0,
        "lot_size": 1.0,
        "min_order_size": 1.0,
        "commission_rate": 0.0001,
        "currency": "CNY",
    },
    "SC": {
        "name": "Crude oil continuous futures",
        "exchange": "INE",
        "contract_multiplier": 1000.0,
        "margin_rate": 0.12,
        "tick_size": 0.1,
        "lot_size": 1.0,
        "min_order_size": 1.0,
        "commission_fixed": 20.0,
        "currency": "CNY",
    },
    "SA": {
        "name": "Soda ash futures",
        "exchange": "CZCE",
        "contract_multiplier": 20.0,
        "margin_rate": 0.12,
        "tick_size": 1.0,
        "lot_size": 1.0,
        "min_order_size": 1.0,
        "commission_fixed": 3.5,
        "currency": "CNY",
    },
    "T": {
        "name": "Treasury futures",
        "exchange": "CFFEX",
        "contract_multiplier": 10000.0,
        "margin_rate": 0.02,
        "tick_size": 0.005,
        "lot_size": 1.0,
        "min_order_size": 1.0,
        "commission_fixed": 3.0,
        "currency": "CNY",
    },
}


def infer_asset_type(symbol: str, explicit: str | None = None) -> str:
    """Infer asset type from symbol when the request does not provide one."""
    if explicit:
        return explicit
    text = str(symbol or "").strip().upper()
    compact = re.sub(r"[^0-9A-Z]", "", text)
    if re.match(r"^[A-Z]{1,4}\d{0,4}$", compact) and not compact[:6].isdigit():
        return "futures"
    if text.startswith(("SH11", "SH12", "SZ12", "110", "113", "127", "128")):
        return "bond"
    if text.endswith((".OF", ".ETF")) or text.startswith(("51", "15", "16")):
        return "fund"
    if len(compact) == 6 and compact.isdigit() or text.endswith((".SH", ".SZ", ".BJ")):
        return "stock"
    if len(compact) == 6 and compact[:3].isalpha() and compact[3:].isalpha():
        return "fx"
    if compact.endswith(("USDT", "USDC", "BTC", "ETH")):
        return "crypto"
    return "stock"


def _product_code(symbol: str) -> str:
    match = re.match(r"([A-Za-z]+)", re.sub(r"[^0-9A-Za-z]", "", symbol or ""))
    return match.group(1).upper() if match else ""


def _defaults_for(asset_type: str, symbol: str) -> dict[str, Any]:
    if asset_type == "futures":
        product = _product_code(symbol)
        if product in _FUTURES_DEFAULTS:
            return {**_FUTURES_DEFAULTS[product], "source": "local_defaults"}
        return {
            "exchange": "CN",
            "currency": "CNY",
            "contract_multiplier": 1.0,
            "margin_rate": 0.1,
            "tick_size": 1.0,
            "lot_size": 1.0,
            "min_order_size": 1.0,
            "commission_rate": 0.0001,
            "source": "generic_futures_defaults",
        }
    if asset_type == "stock":
        return {
            "exchange": "CN",
            "currency": "CNY",
            "contract_multiplier": 1.0,
            "tick_size": 0.01,
            "lot_size": 100.0,
            "min_order_size": 100.0,
            "commission_rate": 0.0003,
            "source": "generic_stock_defaults",
        }
    if asset_type == "bond":
        return {
            "exchange": "CN",
            "currency": "CNY",
            "contract_multiplier": 1.0,
            "tick_size": 0.001,
            "lot_size": 10.0,
            "min_order_size": 10.0,
            "commission_rate": 0.00002,
            "source": "generic_bond_defaults",
        }
    if asset_type == "fund":
        return {
            "exchange": "CN",
            "currency": "CNY",
            "contract_multiplier": 1.0,
            "tick_size": 0.001,
            "lot_size": 100.0,
            "min_order_size": 100.0,
            "commission_rate": 0.0003,
            "source": "generic_fund_defaults",
        }
    return {
        "exchange": "GLOBAL",
        "currency": "USD",
        "contract_multiplier": 1.0,
        "tick_size": 0.0001,
        "lot_size": 1.0,
        "min_order_size": 1.0,
        "commission_rate": 0.0005,
        "source": "generic_asset_defaults",
    }


def _model_from_payload(payload: AssetSpecCreate) -> AssetSpecModel:
    values = payload.model_dump(mode="python")
    metadata = values.pop("metadata", {})
    return AssetSpecModel(**values, metadata_json=metadata)


class AssetSpecService:
    """Resolve, normalize, and persist tradable asset specifications."""

    async def get_or_create(
        self,
        *,
        symbol: str,
        asset_type: str | None = None,
        exchange: str | None = None,
    ) -> AssetSpecResponse:
        resolved_type = infer_asset_type(symbol, asset_type)
        existing = await self.get(symbol=symbol, asset_type=resolved_type, exchange=exchange)
        if existing is not None:
            return existing

        payload = self.resolve(symbol=symbol, asset_type=resolved_type, exchange=exchange)
        return await self.upsert(payload)

    async def get(
        self,
        *,
        symbol: str,
        asset_type: str | None = None,
        exchange: str | None = None,
    ) -> AssetSpecResponse | None:
        resolved_type = infer_asset_type(symbol, asset_type)
        async with async_session_maker() as session:
            query = select(AssetSpecModel).where(
                AssetSpecModel.asset_type == resolved_type,
                AssetSpecModel.symbol == symbol,
            )
            if exchange is not None:
                query = query.where(AssetSpecModel.exchange == exchange)
            result = await session.execute(query.order_by(AssetSpecModel.updated_at.desc()))
            model = result.scalars().first()
        return AssetSpecResponse.model_validate(model) if model is not None else None

    def resolve(
        self,
        *,
        symbol: str,
        asset_type: str | None = None,
        exchange: str | None = None,
    ) -> AssetSpecCreate:
        resolved_type = infer_asset_type(symbol, asset_type)
        defaults = _defaults_for(resolved_type, symbol)
        local = query_local_asset_spec(symbol)
        normalized = normalize_asset_spec(
            {**defaults, **local, "symbol": symbol},
            symbol=symbol,
            source=str(local.get("source") or defaults.get("source") or "resolved"),
        )
        metadata = dict(normalized)
        return AssetSpecCreate(
            asset_type=resolved_type,
            symbol=symbol,
            name=str(
                normalized.get("name")
                or normalized.get("product_name")
                or defaults.get("name")
                or symbol
            ),
            exchange=str(exchange or normalized.get("exchange") or defaults.get("exchange") or ""),
            currency=str(
                normalized.get("currency")
                or normalized.get("quote_asset")
                or defaults.get("currency")
                or "CNY"
            ),
            contract_multiplier=_float_or_none(
                normalized.get("contract_multiplier") or normalized.get("multiplier")
            ),
            margin_rate=_float_or_none(normalized.get("margin_rate") or normalized.get("margin")),
            tick_size=_float_or_none(normalized.get("tick_size") or normalized.get("price_tick")),
            lot_size=_float_or_none(
                normalized.get("lot_size") or normalized.get("volume_step") or defaults.get("lot_size")
            ),
            min_order_size=_float_or_none(normalized.get("min_order_size") or defaults.get("min_order_size")),
            commission_rate=_float_or_none(normalized.get("commission_rate") or defaults.get("commission_rate")),
            commission_fixed=_float_or_none(
                normalized.get("commission_fixed")
                or normalized.get("commission_amount")
                or defaults.get("commission_fixed")
            ),
            slippage_model=str(normalized.get("slippage_model") or "bps"),
            trading_calendar=str(
                normalized.get("trading_calendar") or defaults.get("trading_calendar") or "CN"
            ),
            metadata=metadata,
            source=str(normalized.get("source") or defaults.get("source") or "resolved"),
        )

    async def upsert(self, payload: AssetSpecCreate) -> AssetSpecResponse:
        async with async_session_maker() as session:
            result = await session.execute(
                select(AssetSpecModel).where(
                    AssetSpecModel.asset_type == payload.asset_type,
                    AssetSpecModel.symbol == payload.symbol,
                    AssetSpecModel.exchange == payload.exchange,
                )
            )
            model = result.scalars().first()
            if model is None:
                model = _model_from_payload(payload)
                session.add(model)
            else:
                values = payload.model_dump(mode="python")
                metadata = values.pop("metadata", {})
                for key, value in values.items():
                    setattr(model, key, value)
                model.metadata_json = metadata
            await session.commit()
            await session.refresh(model)
        return AssetSpecResponse.model_validate(model)


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@lru_cache
def get_asset_spec_service() -> AssetSpecService:
    return AssetSpecService()
