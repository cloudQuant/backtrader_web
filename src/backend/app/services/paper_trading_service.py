"""
Paper trading service.

Provides a Backtrader-based paper trading environment.
"""

import asyncio
import logging
import math
import os
from datetime import date, datetime, timedelta, timezone, tzinfo
from types import SimpleNamespace
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.db.sql_repository import SQLRepository
from app.models.paper_trading import (
    Account,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    PaperTrade,
    Position,
)
from app.services.position_valuation import PositionSpec, contract_spec_for
from app.services.trading_asset_info_service import query_local_asset_spec
from app.utils.tracing import business_span
from app.websocket_manager import MessageType
from app.websocket_manager import manager as ws_manager

logger = logging.getLogger(__name__)

_MIN_SIZE_KEYS = (
    "min_order_size",
    "min_order_qty",
    "min_size",
    "min_qty",
    "minQty",
    "minSz",
    "minOrderQty",
    "min_volume",
    "volume_min",
    "min_lot",
    "lot_min",
    "SYMBOL_VOLUME_MIN",
)
_MARKET_MAX_SIZE_KEYS = (
    "market_max_order_size",
    "max_market_order_size",
    "max_mkt_order_size",
    "maxMktSz",
    "maxMktOrderQty",
    "maxMarketOrderQty",
)
_LIMIT_MAX_SIZE_KEYS = (
    "limit_max_order_size",
    "max_limit_order_size",
    "max_lmt_order_size",
    "maxLmtSz",
    "maxLimitOrderQty",
)
_MAX_SIZE_KEYS = (
    "max_order_size",
    "max_order_qty",
    "max_size",
    "max_qty",
    "maxQty",
    "maxOrderQty",
    "max_volume",
    "volume_max",
    "max_lot",
    "lot_max",
    "SYMBOL_VOLUME_MAX",
)
_SIZE_STEP_KEYS = (
    "order_size_step",
    "size_step",
    "qty_step",
    "qty_unit",
    "quantity_step",
    "volume_step",
    "lot_step",
    "step_size",
    "stepSize",
    "qtyStep",
    "lotSz",
    "SYMBOL_VOLUME_STEP",
)
_PRICE_TICK_KEYS = (
    "min_price_tick",
    "price_tick",
    "tick_size",
    "price_unit",
    "tickSize",
    "tickSz",
    "PriceTick",
    "MIN_PRICE_CHANGE",
)

_DEFAULT_TRADING_TIMEZONE = "Asia/Shanghai"
_DEFAULT_TRADING_DAY_ROLLOVER_HOUR = 21


class PaperTradingService:
    """Paper trading service.

    This service provides:
    1. Create and manage paper trading accounts
    2. Submit and manage paper orders
    3. Simulate order execution
    4. Calculate positions and PnL
    5. Real-time WebSocket notifications
    """

    def __init__(self) -> None:
        """Initialize the paper trading service."""
        self.account_repo = SQLRepository(Account)
        self.position_repo = SQLRepository(Position)
        self.order_repo = SQLRepository(Order)
        self.trade_repo = SQLRepository(PaperTrade)

    async def create_account(
        self,
        user_id: str,
        name: str,
        initial_cash: float = 100000.0,
        commission_rate: float = 0.001,
        slippage_rate: float = 0.001,
    ) -> Account:
        """Create a paper trading account.

        Args:
            user_id: The user ID.
            name: Account name.
            initial_cash: Initial cash amount.
            commission_rate: Commission rate.
            slippage_rate: Slippage rate.

        Returns:
            The created account.
        """
        account = Account(
            user_id=user_id,
            name=name,
            initial_cash=initial_cash,
            current_cash=initial_cash,
            total_equity=initial_cash,
            profit_loss=0.0,
            profit_loss_pct=0.0,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
        )

        account = await self.account_repo.create(account)

        logger.info(f"Created paper trading account: {account.id} for user {user_id}")

        # Send notification
        await self._notify_account_update(account)

        return account

    def _local_asset_spec_for_symbol(self, symbol: str) -> dict:
        try:
            spec = query_local_asset_spec(symbol)
        except Exception:
            return {}
        return dict(spec) if isinstance(spec, dict) else {}

    def _contract_spec_for_symbol(
        self,
        symbol: str,
        account: Account | None = None,
        *,
        asset_spec: dict | None = None,
    ) -> PositionSpec:
        """Resolve paper trading contract metadata from local asset specs."""
        local_spec = (
            asset_spec
            if isinstance(asset_spec, dict)
            else self._local_asset_spec_for_symbol(symbol)
        )
        account_spec = {}
        if account is not None:
            account_spec["commission_rate"] = self._safe_float(
                getattr(account, "commission_rate", 0.0),
                0.0,
            )
        return contract_spec_for(symbol, local_spec, account_spec)

    @staticmethod
    def _uses_margin_accounting(spec: PositionSpec) -> bool:
        return (
            spec.margin_amount > 0
            or spec.long_margin_amount is not None
            or spec.short_margin_amount is not None
            or spec.margin_rate < 1.0
            or spec.long_margin_rate is not None
            or spec.short_margin_rate is not None
            or abs(spec.multiplier - 1.0) > 1e-12
        )

    @staticmethod
    def _safe_float(value: object, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _first_asset_number(cls, asset_spec: dict | None, *keys: str) -> float | None:
        for key in keys:
            for value in cls._iter_asset_values(asset_spec, key):
                if value in (None, ""):
                    continue
                try:
                    return float(value)
                except (TypeError, ValueError):
                    continue
        return None

    @classmethod
    def _iter_asset_values(cls, value: object, key: str):
        if isinstance(value, dict):
            if key in value:
                yield value.get(key)
            for child in value.values():
                yield from cls._iter_asset_values(child, key)
        elif isinstance(value, list):
            for item in value:
                yield from cls._iter_asset_values(item, key)

    @staticmethod
    def _asset_spec_requires_integer_lot(asset_spec: dict | None) -> bool:
        if not isinstance(asset_spec, dict) or not asset_spec:
            return False
        source_text = " ".join(
            str(asset_spec.get(key) or "")
            for key in (
                "source",
                "asset_spec_source",
                "asset_type",
                "type",
                "exchange",
                "exchange_id",
                "ExchangeID",
            )
        ).upper()
        futures_tokens = (
            "LOCAL_FUTURES",
            "FUTURE",
            "FUTURES",
            "CTP",
            "CFFEX",
            "SHFE",
            "DCE",
            "CZCE",
            "INE",
            "GFEX",
        )
        if any(token in source_text for token in futures_tokens):
            return True
        return any(
            asset_spec.get(key) not in (None, "")
            for key in (
                "VolumeMultiple",
                "LongMarginRatioByMoney",
                "ShortMarginRatioByMoney",
                "LongMarginRatioByVolume",
                "ShortMarginRatioByVolume",
            )
        )

    @classmethod
    def _validate_asset_order_size(
        cls,
        symbol: str,
        size: float,
        asset_spec: dict | None,
        *,
        order_type: str | OrderType | None = None,
    ) -> None:
        if not isinstance(asset_spec, dict) or not asset_spec:
            return
        requested = abs(float(size or 0.0))
        integer_required = cls._asset_spec_requires_integer_lot(asset_spec)
        min_size = cls._first_asset_number(asset_spec, *_MIN_SIZE_KEYS)
        if min_size is None and integer_required:
            min_size = 1.0
        if min_size and requested + 1e-12 < min_size:
            raise ValueError(f"{symbol} quantity {size} is below the minimum allowed size {min_size}")

        order_type_value = cls._order_type_value(order_type or "").strip().lower()
        max_size_keys: tuple[str, ...] = ()
        if order_type_value in {OrderType.MARKET.value, OrderType.STOP.value}:
            max_size_keys = _MARKET_MAX_SIZE_KEYS
        elif order_type_value in {OrderType.LIMIT.value, OrderType.STOP_LIMIT.value}:
            max_size_keys = _LIMIT_MAX_SIZE_KEYS
        max_size = cls._first_asset_number(asset_spec, *max_size_keys, *_MAX_SIZE_KEYS)
        if max_size and requested > max_size + 1e-12:
            raise ValueError(f"{symbol} quantity {size} exceeds the maximum allowed size {max_size}")

        step = cls._first_asset_number(asset_spec, *_SIZE_STEP_KEYS)
        if step is None and integer_required:
            step = 1.0
        if step and step > 0:
            scaled = requested / step
            if abs(round(scaled) - scaled) > 1e-9:
                raise ValueError(f"{symbol} quantity {size} does not align with size step {step}")

    @classmethod
    def _validate_asset_order_prices(
        cls,
        *,
        symbol: str,
        price: float | None = None,
        stop_price: float | None = None,
        limit_price: float | None = None,
        asset_spec: dict | None = None,
    ) -> None:
        if not isinstance(asset_spec, dict) or not asset_spec:
            return
        tick = cls._first_asset_number(asset_spec, *_PRICE_TICK_KEYS)
        if not tick or tick <= 0:
            return
        for field_name, value in (
            ("price", price),
            ("stop_price", stop_price),
            ("limit_price", limit_price),
        ):
            if value in (None, "", 0):
                continue
            scaled = float(value) / tick
            if abs(round(scaled) - scaled) > 1e-9:
                raise ValueError(f"{symbol} {field_name} {value} does not align with tick size {tick}")

    @classmethod
    def _validate_asset_order_constraints(
        cls,
        *,
        symbol: str,
        size: float,
        price: float | None = None,
        stop_price: float | None = None,
        limit_price: float | None = None,
        order_type: str | OrderType | None = None,
        asset_spec: dict | None = None,
    ) -> None:
        cls._validate_asset_order_size(symbol, size, asset_spec, order_type=order_type)
        cls._validate_asset_order_prices(
            symbol=symbol,
            price=price,
            stop_price=stop_price,
            limit_price=limit_price,
            asset_spec=asset_spec,
        )

    @staticmethod
    def _currency_code(value: object) -> str:
        return "".join(ch for ch in str(value or "").strip().upper() if ch.isalnum())

    @classmethod
    def _is_inverse_contract(cls, spec: PositionSpec) -> bool:
        if spec.is_inverse is not None:
            return spec.is_inverse
        contract_type = str(spec.contract_type or "").strip().lower()
        if "inverse" in contract_type:
            return True
        if "linear" in contract_type:
            return False

        contract_ccy = cls._currency_code(spec.contract_value_currency)
        if not contract_ccy:
            return False
        base_ccy = cls._currency_code(spec.base_asset)
        quote_ccy = cls._currency_code(spec.quote_asset)
        settle_ccy = cls._currency_code(spec.settle_currency or spec.fee_currency)
        if quote_ccy and contract_ccy == quote_ccy and contract_ccy != base_ccy:
            return True
        return bool(base_ccy and settle_ccy == base_ccy and contract_ccy != base_ccy)

    @classmethod
    def _notional_value(cls, size: float, price: float, spec: PositionSpec) -> float:
        if cls._is_inverse_contract(spec):
            signed_size = float(size or 0.0)
            return signed_size * spec.multiplier
        return float(size or 0.0) * float(price or 0.0) * spec.multiplier

    @classmethod
    def _margin_value(cls, size: float, price: float, spec: PositionSpec) -> float:
        abs_size = abs(float(size or 0.0))
        if abs_size <= 1e-12:
            return 0.0
        if size > 0 and spec.long_margin_amount is not None and spec.long_margin_amount > 0:
            return abs_size * spec.long_margin_amount
        if size < 0 and spec.short_margin_amount is not None and spec.short_margin_amount > 0:
            return abs_size * spec.short_margin_amount
        if spec.margin_amount > 0:
            return abs_size * spec.margin_amount
        margin_rate = spec.margin_rate
        if size > 0 and spec.long_margin_rate is not None:
            margin_rate = spec.long_margin_rate
        elif size < 0 and spec.short_margin_rate is not None:
            margin_rate = spec.short_margin_rate
        return abs(cls._notional_value(size, price, spec)) * max(margin_rate, 0.0)

    @staticmethod
    def _commission_rate_for_role(spec: PositionSpec, role: str = "open") -> float:
        role_value = str(role or "open").strip().lower()
        if role_value == "open":
            if spec.open_commission_rate is not None:
                return spec.open_commission_rate
            if spec.taker_commission_rate is not None:
                return max(spec.taker_commission_rate, 0.0)
            return spec.commission_rate
        if role_value in {"close_today", "closetoday"}:
            if spec.close_today_commission_rate is not None:
                return spec.close_today_commission_rate
            if spec.close_commission_rate is not None:
                return spec.close_commission_rate
            if spec.taker_commission_rate is not None:
                return max(spec.taker_commission_rate, 0.0)
            return spec.commission_rate
        if role_value in {"close_yesterday", "closeyesterday"}:
            if spec.close_yesterday_commission_rate is not None:
                return spec.close_yesterday_commission_rate
            if spec.close_commission_rate is not None:
                return spec.close_commission_rate
            if spec.taker_commission_rate is not None:
                return max(spec.taker_commission_rate, 0.0)
            return spec.commission_rate
        if role_value == "close":
            if spec.close_commission_rate is not None:
                return spec.close_commission_rate
            if spec.taker_commission_rate is not None:
                return max(spec.taker_commission_rate, 0.0)
            return spec.commission_rate
        if role_value == "maker" and spec.maker_commission_rate is not None:
            return spec.maker_commission_rate
        if role_value == "taker" and spec.taker_commission_rate is not None:
            return spec.taker_commission_rate
        return spec.commission_rate

    @staticmethod
    def _commission_amount_for_role(spec: PositionSpec, role: str = "open") -> float:
        role_value = str(role or "open").strip().lower()
        if role_value == "open":
            if spec.open_commission_amount is not None:
                return spec.open_commission_amount
            return spec.commission_amount
        if role_value in {"close_today", "closetoday"}:
            if spec.close_today_commission_amount is not None:
                return spec.close_today_commission_amount
            if spec.close_commission_amount is not None:
                return spec.close_commission_amount
            return spec.commission_amount
        if role_value in {"close_yesterday", "closeyesterday"}:
            if spec.close_yesterday_commission_amount is not None:
                return spec.close_yesterday_commission_amount
            if spec.close_commission_amount is not None:
                return spec.close_commission_amount
            return spec.commission_amount
        if role_value == "close" and spec.close_commission_amount is not None:
            return spec.close_commission_amount
        return spec.commission_amount

    @classmethod
    def _commission_value(
        cls,
        size: float,
        price: float,
        spec: PositionSpec,
        *,
        role: str = "open",
    ) -> float:
        abs_size = abs(float(size or 0.0))
        if abs_size <= 1e-12:
            return 0.0
        notional = abs(cls._notional_value(abs_size, price, spec))
        return notional * cls._commission_rate_for_role(spec, role) + (
            abs_size * cls._commission_amount_for_role(spec, role)
        )

    @staticmethod
    def _trading_day_timezone() -> tzinfo:
        tz_name = (
            os.getenv("PAPER_TRADING_TIMEZONE")
            or os.getenv("BT_STORE_LOCAL_TIMEZONE")
            or _DEFAULT_TRADING_TIMEZONE
        )
        try:
            return ZoneInfo(str(tz_name))
        except (ZoneInfoNotFoundError, ValueError):
            return timezone(timedelta(hours=8))

    @staticmethod
    def _trading_day_rollover_hour() -> int:
        try:
            hour = int(os.getenv("PAPER_TRADING_DAY_ROLLOVER_HOUR", ""))
        except (TypeError, ValueError):
            hour = _DEFAULT_TRADING_DAY_ROLLOVER_HOUR
        return min(max(hour, 0), 24)

    @classmethod
    def _local_trading_day(cls, value: datetime) -> date:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        local_value = value.astimezone(cls._trading_day_timezone())
        trading_day = local_value.date()
        rollover_hour = cls._trading_day_rollover_hour()
        if rollover_hour < 24 and local_value.hour >= rollover_hour:
            trading_day += timedelta(days=1)
        return trading_day

    @classmethod
    def _close_commission_role_for_position(
        cls,
        position: Position | None,
        *,
        as_of: datetime | None = None,
    ) -> str:
        entry_time = getattr(position, "entry_time", None) if position is not None else None
        if isinstance(entry_time, datetime):
            fill_time = as_of or datetime.now(timezone.utc)
            if cls._local_trading_day(entry_time) == cls._local_trading_day(fill_time):
                return "close_today"
        return "close"

    @classmethod
    def _fill_commission_breakdown(
        cls,
        position: Position | None,
        signed_fill_size: float,
        price: float,
        spec: PositionSpec,
        *,
        as_of: datetime | None = None,
    ) -> dict[str, float | str]:
        old_size = cls._safe_float(getattr(position, "size", 0.0), 0.0) if position else 0.0
        closed_size, opening_signed_size = cls._split_fill(old_size, signed_fill_size)
        close_role = cls._close_commission_role_for_position(position, as_of=as_of)
        closing_commission = (
            cls._commission_value(closed_size, price, spec, role=close_role)
            if closed_size > 1e-12
            else 0.0
        )
        opening_commission = (
            cls._commission_value(abs(opening_signed_size), price, spec, role="open")
            if abs(opening_signed_size) > 1e-12
            else 0.0
        )
        return {
            "closing_commission": closing_commission,
            "opening_commission": opening_commission,
            "total_commission": closing_commission + opening_commission,
            "close_role": close_role,
        }

    @staticmethod
    def _split_fill(old_size: float, signed_fill_size: float) -> tuple[float, float]:
        """Return closed absolute size and newly opened signed size."""
        old_size = float(old_size or 0.0)
        signed_fill_size = float(signed_fill_size or 0.0)
        if abs(old_size) <= 1e-12 or old_size * signed_fill_size > 0:
            return 0.0, signed_fill_size
        closed_size = min(abs(old_size), abs(signed_fill_size))
        opening_abs = max(abs(signed_fill_size) - abs(old_size), 0.0)
        opening_signed = (1.0 if signed_fill_size > 0 else -1.0) * opening_abs
        return closed_size, opening_signed

    @classmethod
    def _realized_gross_pnl(
        cls,
        old_size: float,
        old_avg_price: float,
        close_price: float,
        closed_size: float,
        spec: PositionSpec,
    ) -> float:
        if closed_size <= 1e-12:
            return 0.0
        if cls._is_inverse_contract(spec):
            if old_avg_price <= 1e-12 or close_price <= 1e-12:
                return 0.0
            direction = 1.0 if old_size > 0 else -1.0
            return direction * closed_size * spec.multiplier * ((close_price / old_avg_price) - 1.0)
        if old_size > 0:
            return (close_price - old_avg_price) * closed_size * spec.multiplier
        return (old_avg_price - close_price) * closed_size * spec.multiplier

    @classmethod
    def _unrealized_gross_pnl(
        cls,
        size: float,
        avg_price: float,
        current_price: float,
        spec: PositionSpec,
    ) -> float:
        if abs(float(size or 0.0)) <= 1e-12:
            return 0.0
        if cls._is_inverse_contract(spec):
            if avg_price <= 1e-12 or current_price <= 1e-12:
                return 0.0
            return float(size or 0.0) * spec.multiplier * ((current_price / avg_price) - 1.0)
        return (current_price - avg_price) * size * spec.multiplier

    @classmethod
    def _pnl_denominator(cls, size: float, price: float, spec: PositionSpec) -> float:
        if abs(float(size or 0.0)) <= 1e-12:
            return 0.0
        if cls._is_inverse_contract(spec):
            return abs(float(size or 0.0) * spec.multiplier)
        return abs(float(size or 0.0) * float(price or 0.0) * spec.multiplier)

    @classmethod
    def _average_entry_price(
        cls,
        old_size: float,
        old_avg_price: float,
        fill_size: float,
        fill_price: float,
        spec: PositionSpec,
    ) -> float:
        if cls._is_inverse_contract(spec):
            old_abs = abs(float(old_size or 0.0))
            fill_abs = abs(float(fill_size or 0.0))
            if old_abs <= 1e-12:
                return float(fill_price or 0.0)
            if old_avg_price <= 1e-12 or fill_price <= 1e-12:
                return float(fill_price or old_avg_price or 0.0)
            denominator = old_abs / old_avg_price + fill_abs / fill_price
            return (old_abs + fill_abs) / denominator if denominator > 1e-12 else fill_price

        total_value = abs(old_size) * old_avg_price + abs(fill_size) * fill_price
        total_size = abs(old_size) + abs(fill_size)
        return total_value / total_size if total_size > 1e-12 else fill_price

    @classmethod
    def _margin_required_cash_before_fill(
        cls,
        position: Position | None,
        signed_fill_size: float,
        price: float,
        commission: float,
        spec: PositionSpec,
    ) -> float:
        """Return cash needed before a margin/futures fill can be accepted."""
        old_size = cls._safe_float(getattr(position, "size", 0.0), 0.0) if position else 0.0
        old_avg_price = (
            cls._safe_float(getattr(position, "avg_price", 0.0), 0.0) if position else 0.0
        )
        closed_size, opening_signed_size = cls._split_fill(old_size, signed_fill_size)
        old_margin_value = 0.0
        if position is not None and abs(old_size) > 1e-12:
            old_margin_value = cls._safe_float(
                getattr(position, "margin_value", None),
                cls._margin_value(old_size, old_avg_price or price, spec),
            )
        released_margin = (
            old_margin_value * (closed_size / abs(old_size))
            if abs(old_size) > 1e-12 and closed_size > 0
            else 0.0
        )
        realized_gross_pnl = cls._realized_gross_pnl(
            old_size,
            old_avg_price or price,
            price,
            closed_size,
            spec,
        )
        opening_margin = cls._margin_value(opening_signed_size, price, spec)
        return max(opening_margin + abs(float(commission or 0.0)) - released_margin - realized_gross_pnl, 0.0)

    @classmethod
    def _cash_required_before_fill(
        cls,
        position: Position | None,
        signed_fill_size: float,
        price: float,
        commission: float,
        spec: PositionSpec,
    ) -> float:
        """Return cash needed before a non-margin paper fill can be accepted."""
        old_size = cls._safe_float(getattr(position, "size", 0.0), 0.0) if position else 0.0
        fill_notional = abs(cls._notional_value(signed_fill_size, price, spec))
        commission = abs(float(commission or 0.0))
        if signed_fill_size > 0:
            return fill_notional + commission

        closed_size, opening_signed_size = cls._split_fill(old_size, signed_fill_size)
        opening_short_notional = (
            abs(cls._notional_value(opening_signed_size, price, spec))
            if opening_signed_size < 0
            else 0.0
        )
        closing_long_proceeds = (
            abs(cls._notional_value(closed_size, price, spec))
            if old_size > 0 and closed_size > 0
            else 0.0
        )
        return max(opening_short_notional + commission - closing_long_proceeds, 0.0)

    @classmethod
    def _position_equity_component(cls, position: object) -> float:
        market_value = cls._safe_float(getattr(position, "market_value", 0.0), 0.0)
        margin_value = cls._safe_float(getattr(position, "margin_value", 0.0), 0.0)
        unrealized_pnl = cls._safe_float(getattr(position, "unrealized_pnl", 0.0), 0.0)
        multiplier = cls._safe_float(getattr(position, "multiplier", 1.0), 1.0)
        margin_rate = cls._safe_float(getattr(position, "margin_rate", 1.0), 1.0)
        uses_margin_accounting = (
            margin_value > 0
            and (
                abs(multiplier - 1.0) > 1e-12
                or margin_rate < 1.0
                or abs(margin_value - abs(market_value)) > 1e-9
            )
        )
        if uses_margin_accounting:
            return margin_value + unrealized_pnl
        return market_value

    @classmethod
    def _is_open_position(cls, position: object) -> bool:
        return abs(cls._safe_float(getattr(position, "size", 0.0), 0.0)) > 1e-12

    @classmethod
    def _merge_position_snapshot(
        cls,
        positions: list[object],
        snapshot: object | None,
    ) -> list[object]:
        if snapshot is None:
            return positions

        snapshot_id = getattr(snapshot, "id", None)
        snapshot_account_id = getattr(snapshot, "account_id", None)
        snapshot_symbol = getattr(snapshot, "symbol", None)
        merged: list[object] = []
        replaced = False
        for position in positions:
            same_id = (
                snapshot_id is not None
                and getattr(position, "id", None) is not None
                and str(getattr(position, "id")) == str(snapshot_id)
            )
            same_symbol = (
                snapshot_account_id is not None
                and snapshot_symbol is not None
                and getattr(position, "account_id", None) is not None
                and getattr(position, "symbol", None) is not None
                and str(getattr(position, "account_id")) == str(snapshot_account_id)
                and str(getattr(position, "symbol")) == str(snapshot_symbol)
            )
            if same_id or same_symbol:
                merged.append(snapshot)
                replaced = True
            else:
                merged.append(position)

        if not replaced and cls._is_open_position(snapshot):
            merged.append(snapshot)
        return merged

    @staticmethod
    def _position_snapshot(
        position: Position,
        updates: dict[str, object],
    ) -> object:
        data = {
            "id": getattr(position, "id", None),
            "account_id": getattr(position, "account_id", None),
            "symbol": getattr(position, "symbol", None),
            "size": getattr(position, "size", 0.0),
            "avg_price": getattr(position, "avg_price", 0.0),
            "market_value": getattr(position, "market_value", 0.0),
            "margin_value": getattr(position, "margin_value", 0.0),
            "multiplier": getattr(position, "multiplier", 1.0),
            "margin_rate": getattr(position, "margin_rate", 1.0),
            "unrealized_pnl": getattr(position, "unrealized_pnl", 0.0),
        }
        data.update(updates)
        return SimpleNamespace(**data)

    @classmethod
    def _positive_finite(cls, value: object, field_name: str) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must be a positive finite number") from exc
        if not math.isfinite(number) or number <= 0:
            raise ValueError(f"{field_name} must be a positive finite number")
        return number

    @classmethod
    def _optional_order_number(cls, order: Order, field_name: str) -> float | None:
        value = getattr(order, field_name, None)
        if value in (None, ""):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    @classmethod
    def _validate_order_request(
        cls,
        *,
        order_type: str | OrderType,
        side: str | OrderSide,
        size: float,
        price: float | None = None,
        stop_price: float | None = None,
        limit_price: float | None = None,
    ) -> tuple[str, str, float]:
        order_type_value = cls._order_type_value(order_type).strip().lower()
        side_value = cls._order_side_value(side).strip().lower()
        if order_type_value not in {item.value for item in OrderType}:
            raise ValueError("order_type must be one of: market, limit, stop, stop_limit")
        if side_value not in {item.value for item in OrderSide}:
            raise ValueError("side must be one of: buy, sell")

        normalized_size = cls._positive_finite(size, "size")
        if price is not None:
            cls._positive_finite(price, "price")
        if stop_price is not None:
            cls._positive_finite(stop_price, "stop_price")
        if limit_price is not None:
            cls._positive_finite(limit_price, "limit_price")

        if order_type_value == OrderType.LIMIT.value and price is None and limit_price is None:
            raise ValueError("limit orders require price or limit_price")
        if order_type_value == OrderType.STOP.value and stop_price is None and price is None:
            raise ValueError("stop orders require stop_price or price")
        if order_type_value == OrderType.STOP_LIMIT.value and (
            stop_price is None or limit_price is None
        ):
            raise ValueError("stop_limit orders require stop_price and limit_price")
        return order_type_value, side_value, normalized_size

    async def submit_order(
        self,
        account_id: str,
        symbol: str,
        order_type: str,
        side: str,
        size: float,
        price: float | None = None,
        stop_price: float | None = None,
        limit_price: float | None = None,
    ) -> Order:
        """Submit a paper trading order.

        Args:
            account_id: Account ID.
            symbol: Trading symbol.
            order_type: Order type (market, limit, stop, etc.).
            side: Order side (buy/sell).
            size: Order size.
            price: Limit price (for limit orders).
            stop_price: Stop price (for stop orders).
            limit_price: Limit price (for stop-limit orders).

        Returns:
            The created order.
        """
        # Iteration 175 §5.4 — backtrader.live.place_order business span.
        with business_span(
            "backtrader.live.place_order",
            symbol=symbol,
        ):
            # Get account
            account = await self.account_repo.get_by_id(account_id)
            if not account:
                raise ValueError(f"Account not found: {account_id}")

            order_type, side, size = self._validate_order_request(
                order_type=order_type,
                side=side,
                size=size,
                price=price,
                stop_price=stop_price,
                limit_price=limit_price,
            )
            asset_spec = self._local_asset_spec_for_symbol(symbol)
            self._validate_asset_order_constraints(
                symbol=symbol,
                size=size,
                price=price,
                stop_price=stop_price,
                limit_price=limit_price,
                order_type=order_type,
                asset_spec=asset_spec,
            )
            spec = self._contract_spec_for_symbol(symbol, account, asset_spec=asset_spec)
            commission = self._commission_value(size, price, spec, role="open") if price else 0

            # Create order
            order = Order(
                account_id=account_id,
                symbol=symbol,
                order_type=order_type,
                side=side,
                size=size,
                price=price,
                stop_price=stop_price,
                limit_price=limit_price,
                status=OrderStatus.PENDING,
                commission=commission,
            )

            order = await self.order_repo.create(order)

            logger.info(f"Submitted paper order: {order.id} for account {account_id}")

            # Send order creation notification
            await self._notify_order_update(account_id, order)

            # Immediate paper fills must finish before the API returns; otherwise
            # clients can observe a filled order before the trade/position/cash
            # writes complete. Unit tests often replace repositories with mocks,
            # so keep their historical fire-and-forget behavior.
            if all(
                isinstance(repo, SQLRepository)
                for repo in (
                    self.account_repo,
                    self.position_repo,
                    self.order_repo,
                    self.trade_repo,
                )
            ):
                await self._process_order(order.id, account_id, account)
                order = await self.order_repo.get_by_id(order.id) or order
            else:
                asyncio.create_task(self._process_order(order.id, account_id, account))

            return order

    async def _process_order(self, order_id: str, account_id: str, account: Account) -> None:
        """Process order execution (simulated).

        Args:
            order_id: Order ID.
            account_id: Account ID.
            account: Account object.
        """
        # Get order
        order = await self.order_repo.get_by_id(order_id)
        if not order:
            logger.error(f"Order not found: {order_id}")
            return
        if self._order_status_value(order.status) != OrderStatus.PENDING.value:
            logger.info("Skip paper order processing for non-pending order: %s", order_id)
            return
        try:
            order_type, side, normalized_size = self._validate_order_request(
                order_type=order.order_type,
                side=order.side,
                size=order.size,
                price=self._optional_order_number(order, "price"),
                stop_price=self._optional_order_number(order, "stop_price"),
                limit_price=self._optional_order_number(order, "limit_price"),
            )
            asset_spec = self._local_asset_spec_for_symbol(order.symbol)
            self._validate_asset_order_constraints(
                symbol=order.symbol,
                size=normalized_size,
                price=self._optional_order_number(order, "price"),
                stop_price=self._optional_order_number(order, "stop_price"),
                limit_price=self._optional_order_number(order, "limit_price"),
                order_type=order_type,
                asset_spec=asset_spec,
            )
        except ValueError as exc:
            await self._reject_order(order, str(exc))
            return

        # Get current price (simulated)
        current_price = await self._get_simulated_price(order.symbol)

        fill_price = self._execution_price(order, current_price, account.slippage_rate)
        if fill_price is None:
            return

        spec = self._contract_spec_for_symbol(order.symbol, account, asset_spec=asset_spec)
        # Check sufficient funds
        position = await self._get_position(account_id, order.symbol)
        fill_size = float(order.size or 0.0)
        side_value = side
        signed_fill_size = fill_size if side_value == OrderSide.BUY.value else -fill_size
        fill_time = datetime.now(timezone.utc)
        commission_breakdown = self._fill_commission_breakdown(
            position,
            signed_fill_size,
            fill_price,
            spec,
            as_of=fill_time,
        )
        commission = float(commission_breakdown["total_commission"] or 0.0)
        if self._uses_margin_accounting(spec):
            required_cash = self._margin_required_cash_before_fill(
                position,
                signed_fill_size,
                fill_price,
                commission,
                spec,
            )
        else:
            required_cash = self._cash_required_before_fill(
                position,
                signed_fill_size,
                fill_price,
                commission,
                spec,
            )
        if account.current_cash < required_cash:
            await self._reject_order(order, "Insufficient funds")
            return

        # Execute fill
        await self._fill_order(order, fill_price, commission, filled_at=fill_time)

        # Update position
        position_event = await self._update_position(
            account,
            order,
            fill_price,
            commission,
            spec=spec,
            current_position=position,
            commission_breakdown=commission_breakdown,
            fill_time=fill_time,
        )

        # Update account
        await self._update_account(
            account,
            order,
            fill_price,
            commission,
            spec=spec,
            position_event=position_event,
        )

        logger.info(f"Order filled: {order_id} at {fill_price}")

    async def _fill_order(
        self,
        order: Order,
        price: float,
        commission: float,
        *,
        filled_at: datetime | None = None,
        order_repo: SQLRepository[Order] | None = None,
        trade_repo: SQLRepository[PaperTrade] | None = None,
    ) -> None:
        """Fill an order.

        Args:
            order: Order object.
            price: Fill price.
            commission: Commission amount.
        """
        # Iteration 175 §5.4 — backtrader.live.on_fill business span.
        with business_span(
            "backtrader.live.on_fill",
            symbol=order.symbol,
            order_id=order.id,
        ):
            # Update order status
            order.status = OrderStatus.FILLED
            order.filled_size = order.size
            order.avg_fill_price = price
            order.commission = commission
            order.filled_at = filled_at or datetime.now(timezone.utc)

            order_repo = order_repo or self.order_repo
            trade_repo = trade_repo or self.trade_repo

            await order_repo.update(
                order.id,
                {
                    "status": order.status,
                    "filled_size": order.filled_size,
                    "avg_fill_price": order.avg_fill_price,
                    "commission": order.commission,
                    "filled_at": order.filled_at,
                },
            )

            # Create trade record
            trade = PaperTrade(
                account_id=order.account_id,
                order_id=order.id,
                symbol=order.symbol,
                side=order.side,
                size=order.size,
                price=price,
                commission=commission,
                slippage=0.0,  # Slippage already included in price
                pnl=0.0,  # Will be calculated when updating position
                pnl_pct=0.0,
            )

            await trade_repo.create(trade)

    async def _reject_order(
        self,
        order: Order,
        reason: str,
        *,
        order_repo: SQLRepository[Order] | None = None,
    ) -> None:
        """Reject an order.

        Args:
            order: Order object.
            reason: Rejection reason.
        """
        order.status = OrderStatus.REJECTED
        order.rejected_reason = reason

        order_repo = order_repo or self.order_repo
        await order_repo.update(
            order.id,
            {
                "status": order.status,
                "rejected_reason": order.rejected_reason,
            },
        )

        # Send order update
        account_id = order.account_id
        await self._notify_order_update(account_id, order)

    async def _get_position(
        self,
        account_id: str,
        symbol: str,
        *,
        position_repo: SQLRepository[Position] | None = None,
    ) -> Position | None:
        """Get position by account and symbol.

        Args:
            account_id: Account ID.
            symbol: Trading symbol.

        Returns:
            Position or None.
        """
        position_repo = position_repo or self.position_repo
        positions = await position_repo.list(
            filters={"account_id": account_id, "symbol": symbol},
            limit=50,
            sort_by="updated_at",
            sort_order="desc",
        )

        for position in positions:
            if self._is_open_position(position):
                return position
        return positions[0] if positions else None

    async def _update_position(
        self,
        account: Account,
        order: Order,
        price: float,
        commission: float,
        *,
        spec: PositionSpec | None = None,
        current_position: Position | None = None,
        commission_breakdown: dict[str, float | str] | None = None,
        fill_time: datetime | None = None,
        position_repo: SQLRepository[Position] | None = None,
        trade_repo: SQLRepository[PaperTrade] | None = None,
    ) -> dict[str, object]:
        """Update position after order fill.

        Args:
            account: Account object.
            order: Order object.
            price: Fill price.
            commission: Commission amount.
        """
        spec = spec or self._contract_spec_for_symbol(order.symbol, account)
        position_repo = position_repo or self.position_repo
        trade_repo = trade_repo or self.trade_repo
        position = current_position or await self._get_position(
            account.id,
            order.symbol,
            position_repo=position_repo,
        )
        fill_size = float(order.size or 0.0)
        side_value = self._order_side_value(order.side)
        signed_fill_size = fill_size if side_value == OrderSide.BUY.value else -fill_size
        old_size = float(getattr(position, "size", 0.0) or 0.0) if position else 0.0
        old_avg_price = float(getattr(position, "avg_price", 0.0) or 0.0) if position else 0.0
        closed_size, opening_signed_size = self._split_fill(old_size, signed_fill_size)
        margin_accounting = self._uses_margin_accounting(spec)
        fill_commission = abs(float(commission or 0.0))
        if commission_breakdown is not None:
            closing_commission = abs(
                float(commission_breakdown.get("closing_commission", 0.0) or 0.0)
            )
            opening_commission = abs(
                float(commission_breakdown.get("opening_commission", 0.0) or 0.0)
            )
            fill_commission = closing_commission + opening_commission
        else:
            closing_commission = (
                fill_commission * (closed_size / fill_size) if fill_size > 1e-12 else 0.0
            )
            opening_commission = fill_commission - closing_commission
        realized_gross_pnl = self._realized_gross_pnl(
            old_size,
            old_avg_price,
            price,
            closed_size,
            spec,
        )
        old_margin_value = 0.0
        if position is not None and abs(old_size) > 1e-12:
            old_margin_value = self._safe_float(
                getattr(position, "margin_value", None),
                self._margin_value(old_size, old_avg_price, spec),
            )
        released_margin = (
            old_margin_value * (closed_size / abs(old_size))
            if abs(old_size) > 1e-12 and closed_size > 0
            else 0.0
        )
        opening_margin = self._margin_value(opening_signed_size, price, spec)

        if not position:
            position_size = signed_fill_size
            final_margin_value = self._margin_value(position_size, price, spec)
            now = fill_time or datetime.now(timezone.utc)
            # Create new position
            position = Position(
                account_id=account.id,
                symbol=order.symbol,
                size=position_size,
                avg_price=price,
                market_value=self._notional_value(position_size, price, spec),
                margin_value=final_margin_value,
                multiplier=spec.multiplier,
                margin_rate=spec.margin_rate,
                commission_rate=spec.commission_rate,
                commission_amount=spec.commission_amount,
                unrealized_pnl=0.0,
                unrealized_pnl_pct=0.0,
                entry_price=price,
                entry_time=now,
            )

            await position_repo.create(position)
            position_snapshot = position

        else:
            # Update existing position
            new_size = old_size + signed_fill_size

            same_direction_fill = old_size == 0 or old_size * signed_fill_size > 0
            if abs(new_size) <= 1e-12:
                new_avg_price = 0.0
            elif same_direction_fill:
                new_avg_price = self._average_entry_price(
                    old_size,
                    old_avg_price,
                    fill_size,
                    price,
                    spec,
                )
            elif old_size * new_size > 0:
                new_avg_price = old_avg_price
            else:
                new_avg_price = price

            # Calculate new market value
            new_market_value = self._notional_value(new_size, price, spec)
            new_margin_value = self._margin_value(new_size, price, spec)
            final_margin_value = new_margin_value

            # Calculate unrealized PnL
            unrealized_pnl = self._unrealized_gross_pnl(new_size, new_avg_price, price, spec)

            pnl_denominator = self._pnl_denominator(new_size, new_avg_price, spec)
            unrealized_pnl_pct = (
                (unrealized_pnl / pnl_denominator * 100)
                if pnl_denominator > 1e-12
                else 0
            )

            now = fill_time or datetime.now(timezone.utc)
            position_update = {
                "size": new_size,
                "avg_price": new_avg_price,
                "market_value": new_market_value,
                "margin_value": new_margin_value,
                "multiplier": spec.multiplier,
                "margin_rate": spec.margin_rate,
                "commission_rate": spec.commission_rate,
                "commission_amount": spec.commission_amount,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pnl_pct": unrealized_pnl_pct,
                "updated_at": now,
            }
            if abs(new_size) <= 1e-12:
                position_update["entry_price"] = 0.0
                position_update["entry_time"] = None
            elif abs(old_size) <= 1e-12 or old_size * new_size < 0:
                position_update["entry_price"] = new_avg_price
                position_update["entry_time"] = now

            await position_repo.update(
                position.id,
                position_update,
            )
            position_snapshot = self._position_snapshot(position, position_update)

            # Update trade record PnL (if closing position)
            if old_size * signed_fill_size < 0:
                pnl = realized_gross_pnl - closing_commission

                pnl_denominator = self._pnl_denominator(closed_size, old_avg_price, spec)
                pnl_pct = (
                    (pnl / pnl_denominator * 100)
                    if pnl_denominator > 1e-12
                    else 0
                )

                # Update trade record
                trade = await self._get_last_trade(order.id, trade_repo=trade_repo)
                if trade:
                    await trade_repo.update(
                        trade.id,
                        {
                            "pnl": pnl,
                            "pnl_pct": pnl_pct,
                        },
                    )

        if margin_accounting:
            cash_delta = old_margin_value + realized_gross_pnl - final_margin_value - fill_commission
        else:
            if side_value == OrderSide.BUY.value:
                cash_delta = -(self._notional_value(fill_size, price, spec) + fill_commission)
            else:
                cash_delta = abs(self._notional_value(fill_size, price, spec)) - fill_commission

        return {
            "cash_delta": cash_delta,
            "closed_size": closed_size,
            "opening_size": abs(opening_signed_size),
            "released_margin": released_margin,
            "opening_margin": opening_margin,
            "realized_gross_pnl": realized_gross_pnl,
            "closing_commission": closing_commission,
            "opening_commission": opening_commission,
            "margin_accounting": margin_accounting,
            "position_snapshot": position_snapshot,
        }

    async def _update_account(
        self,
        account: Account,
        order: Order,
        price: float,
        commission: float,
        *,
        spec: PositionSpec | None = None,
        position_event: dict[str, object] | None = None,
        account_repo: SQLRepository[Account] | None = None,
        position_repo: SQLRepository[Position] | None = None,
    ) -> None:
        """Update account after order fill.

        Args:
            account: Account object.
            order: Order object.
            price: Fill price.
            commission: Commission amount.
        """
        account_repo = account_repo or self.account_repo
        position_repo = position_repo or self.position_repo
        positions = await position_repo.list(filters={"account_id": account.id})
        if position_event is not None:
            positions = self._merge_position_snapshot(
                positions,
                position_event.get("position_snapshot"),
            )

        # Update cash
        if position_event is not None:
            account.current_cash += float(position_event.get("cash_delta", 0.0) or 0.0)
        else:
            spec = spec or self._contract_spec_for_symbol(order.symbol, account)
            side_value = self._order_side_value(order.side)
            if side_value == OrderSide.BUY.value:
                account.current_cash -= self._notional_value(order.size, price, spec) + commission
            else:
                account.current_cash += abs(self._notional_value(order.size, price, spec)) - commission

        # Update total equity
        account.total_equity = account.current_cash + sum(
            self._position_equity_component(position) for position in positions
        )

        # Update PnL
        profit_loss = account.total_equity - account.initial_cash
        account.profit_loss = profit_loss
        account.profit_loss_pct = (profit_loss / account.initial_cash) * 100

        await account_repo.update(
            account.id,
            {
                "current_cash": account.current_cash,
                "total_equity": account.total_equity,
                "profit_loss": account.profit_loss,
                "profit_loss_pct": account.profit_loss_pct,
                "updated_at": datetime.now(timezone.utc),
            },
        )

        # Send account update
        await self._notify_account_update(account)

        # Send position updates
        for position in positions:
            await self._notify_position_update(position)

    async def _get_last_trade(
        self,
        order_id: str,
        *,
        trade_repo: SQLRepository[PaperTrade] | None = None,
    ) -> PaperTrade | None:
        """Get the last trade for an order.

        Args:
            order_id: Order ID.

        Returns:
            PaperTrade or None.
        """
        trade_repo = trade_repo or self.trade_repo
        trades = await trade_repo.list(
            filters={"order_id": order_id},
            limit=1,
            sort_by="created_at",
            sort_order="desc",
        )

        return trades[0] if trades else None

    async def get_account(self, account_id: str) -> Account | None:
        """Get account by ID.

        Args:
            account_id: Account ID.

        Returns:
            Account or None.
        """
        return await self.account_repo.get_by_id(account_id)

    async def list_accounts(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Account], int]:
        """List user's paper trading accounts.

        Args:
            user_id: User ID.
            limit: Items per page.
            offset: Offset for pagination.

        Returns:
            Tuple of (accounts list, total count).
        """
        accounts = await self.account_repo.list(
            filters={"user_id": user_id, "is_active": True},
            skip=offset,
            limit=limit,
            sort_by="created_at",
            sort_order="desc",
        )
        total = await self.account_repo.count(filters={"user_id": user_id, "is_active": True})

        return accounts, total

    async def get_order(self, order_id: str) -> Order | None:
        """Get order by ID.

        Args:
            order_id: Order ID.

        Returns:
            Order or None.
        """
        return await self.order_repo.get_by_id(order_id)

    async def list_orders(
        self,
        filters: dict,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[Order], int]:
        """List orders with filtering.

        Args:
            filters: Filter conditions.
            limit: Items per page.
            offset: Offset for pagination.
            sort_by: Sort field.
            sort_order: Sort direction.

        Returns:
            Tuple of (orders list, total count).
        """
        scoped_filters = await self._scope_filters_to_user_accounts(filters)
        if scoped_filters is None:
            return [], 0
        orders = await self.order_repo.list(
            filters=scoped_filters,
            skip=offset,
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        total = await self.order_repo.count(filters=scoped_filters)

        return orders, total

    async def list_positions(
        self,
        filters: dict,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[Position], int]:
        """List positions with filtering.

        Args:
            filters: Filter conditions.
            limit: Items per page.
            offset: Offset for pagination.
            sort_by: Sort field.
            sort_order: Sort direction.

        Returns:
            Tuple of (positions list, total count).
        """
        scoped_filters = await self._scope_filters_to_user_accounts(filters)
        if scoped_filters is None:
            return [], 0
        raw_total = await self.position_repo.count(filters=scoped_filters)
        fetch_limit = max(int(raw_total or 0), int(offset or 0) + int(limit or 0), 1)
        positions = await self.position_repo.list(
            filters=scoped_filters,
            skip=0,
            limit=fetch_limit,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        open_positions = [position for position in positions if self._is_open_position(position)]
        total = len(open_positions)

        return open_positions[offset : offset + limit], total

    async def list_trades(
        self,
        filters: dict,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[PaperTrade], int]:
        """List trades with filtering.

        Args:
            filters: Filter conditions.
            limit: Items per page.
            offset: Offset for pagination.
            sort_by: Sort field.
            sort_order: Sort direction.

        Returns:
            Tuple of (trades list, total count).
        """
        scoped_filters = await self._scope_filters_to_user_accounts(filters)
        if scoped_filters is None:
            return [], 0
        trades = await self.trade_repo.list(
            filters=scoped_filters,
            skip=offset,
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        total = await self.trade_repo.count(filters=scoped_filters)

        return trades, total

    async def _scope_filters_to_user_accounts(self, filters: dict | None) -> dict | None:
        """Convert API user filters to account_id filters understood by paper tables."""
        scoped_filters = dict(filters or {})
        user_id = scoped_filters.pop("user_id", None)
        if not user_id:
            return scoped_filters

        requested_account_id = scoped_filters.get("account_id")
        account_count = await self.account_repo.count(filters={"user_id": user_id})
        if account_count <= 0:
            return None
        accounts = await self.account_repo.list(
            filters={"user_id": user_id},
            limit=account_count,
        )
        account_ids = [str(account.id) for account in accounts if getattr(account, "id", None)]
        if not account_ids:
            return None

        if requested_account_id:
            if str(requested_account_id) not in account_ids:
                return None
            scoped_filters["account_id"] = str(requested_account_id)
        else:
            scoped_filters["account_id"] = account_ids
        return scoped_filters

    async def delete_account(self, account_id: str, user_id: str) -> bool:
        """Delete a paper trading account.

        Args:
            account_id: Account ID.
            user_id: User ID for authorization.

        Returns:
            True if deleted successfully, False otherwise.
        """
        account = await self.account_repo.get_by_id(account_id)
        if not account or account.user_id != user_id:
            return False

        # Soft delete: mark as inactive
        await self.account_repo.update(account_id, {"is_active": False})
        return True

    async def cancel_order(self, order_id: str, user_id: str) -> bool:
        """Cancel an order.

        Args:
            order_id: Order ID.
            user_id: User ID for authorization.

        Returns:
            True if cancelled successfully, False otherwise.
        """
        # Iteration 175 §5.4 — backtrader.live.cancel_order business span.
        with business_span(
            "backtrader.live.cancel_order",
            user_id=user_id,
            order_id=order_id,
        ):
            order = await self.order_repo.get_by_id(order_id)
            if not order:
                return False

            # Check permission
            account = await self.account_repo.get_by_id(order.account_id)
            if not account or account.user_id != user_id:
                return False

            # Only pending orders can be cancelled
            if self._order_status_value(order.status) != OrderStatus.PENDING.value:
                return False

            # Mark as cancelled
            await self.order_repo.update(order_id, {"status": OrderStatus.CANCELLED})
            order.status = OrderStatus.CANCELLED

            # Send update
            await self._notify_order_update(order.account_id, order)

            return True

    async def get_position(self, position_id: str) -> Position | None:
        """Get position by ID.

        Args:
            position_id: Position ID.

        Returns:
            Position or None.
        """
        return await self.position_repo.get_by_id(position_id)

    def _calculate_slippage(
        self,
        order_price: float | None,
        market_price: float,
        slippage_rate: float,
        side: str,
        order_type: str,
    ) -> float:
        """Calculate slippage amount.

        Args:
            order_price: Order price.
            market_price: Current market price.
            slippage_rate: Slippage rate.
            side: Order side (buy/sell).
            order_type: Order type.

        Returns:
            Slippage amount.
        """
        order_type_value = str(order_type.value if isinstance(order_type, OrderType) else order_type)
        side_value = str(side.value if isinstance(side, OrderSide) else side)
        if order_type_value == OrderType.MARKET.value:
            # Market order, calculate directly from rate
            if side_value == OrderSide.BUY.value:
                return market_price * slippage_rate
            else:
                return -market_price * slippage_rate
        elif order_type_value == OrderType.LIMIT.value:
            # Limit order, fill only when market is inside the limit price.
            if order_price and side_value == OrderSide.BUY.value:
                if market_price <= order_price:
                    return market_price * slippage_rate
            elif order_price and side_value == OrderSide.SELL.value:
                if market_price >= order_price:
                    return -market_price * slippage_rate
            return 0.0
        else:
            # Other types, no slippage for now
            return 0.0

    @staticmethod
    def _order_type_value(order_type: str | OrderType) -> str:
        return str(order_type.value if isinstance(order_type, OrderType) else order_type)

    @staticmethod
    def _order_side_value(side: str | OrderSide) -> str:
        return str(side.value if isinstance(side, OrderSide) else side)

    @staticmethod
    def _order_status_value(status: str | OrderStatus) -> str:
        return str(status.value if isinstance(status, OrderStatus) else status)

    @classmethod
    def _signed_slippage(cls, side: str | OrderSide, market_price: float, slippage_rate: float) -> float:
        if cls._order_side_value(side) == OrderSide.BUY.value:
            return market_price * slippage_rate
        return -market_price * slippage_rate

    @classmethod
    def _limit_price(cls, order: Order) -> float | None:
        return (
            cls._safe_float(getattr(order, "limit_price", None), 0.0)
            or cls._safe_float(getattr(order, "price", None), 0.0)
            or None
        )

    @classmethod
    def _stop_price(cls, order: Order) -> float | None:
        return (
            cls._safe_float(getattr(order, "stop_price", None), 0.0)
            or cls._safe_float(getattr(order, "price", None), 0.0)
            or None
        )

    @classmethod
    def _execution_price(
        cls,
        order: Order,
        market_price: float,
        slippage_rate: float,
    ) -> float | None:
        """Return the simulated fill price, or None when the order is not triggered."""
        order_type = cls._order_type_value(order.order_type)
        side = cls._order_side_value(order.side)

        if order_type == OrderType.MARKET.value:
            return market_price + cls._signed_slippage(side, market_price, slippage_rate)

        if order_type == OrderType.LIMIT.value:
            limit_price = cls._limit_price(order)
            if limit_price is None:
                return None
            if side == OrderSide.BUY.value:
                if market_price > limit_price:
                    return None
                return min(market_price + cls._signed_slippage(side, market_price, slippage_rate), limit_price)
            if market_price < limit_price:
                return None
            return max(market_price + cls._signed_slippage(side, market_price, slippage_rate), limit_price)

        if order_type == OrderType.STOP.value:
            stop_price = cls._stop_price(order)
            if stop_price is None:
                return None
            if side == OrderSide.BUY.value and market_price < stop_price:
                return None
            if side == OrderSide.SELL.value and market_price > stop_price:
                return None
            return market_price + cls._signed_slippage(side, market_price, slippage_rate)

        if order_type == OrderType.STOP_LIMIT.value:
            stop_price = cls._stop_price(order)
            limit_price = cls._limit_price(order)
            if stop_price is None or limit_price is None:
                return None
            if side == OrderSide.BUY.value:
                if market_price < stop_price or market_price > limit_price:
                    return None
                return min(market_price + cls._signed_slippage(side, market_price, slippage_rate), limit_price)
            if market_price > stop_price or market_price < limit_price:
                return None
            return max(market_price + cls._signed_slippage(side, market_price, slippage_rate), limit_price)

        return None

    async def _get_simulated_price(self, symbol: str) -> float:
        """Get simulated price for trading.

        In production, this should fetch from real-time data source.
        Currently returns simulated price for testing.

        Args:
            symbol: Trading symbol.

        Returns:
            Simulated price.
        """
        # This should integrate with real-time market data
        # Currently returns fixed price for testing
        if "000001" in symbol:
            return 10.5
        elif "600000" in symbol:
            return 10.8
        else:
            return 10.0

    async def _notify_account_update(self, account: Account) -> None:
        """Send account update notification via WebSocket.

        Args:
            account: Account object.
        """
        await ws_manager.send_to_task(
            f"account:{account.id}",
            {
                "type": MessageType.PROGRESS,
                "account_id": account.id,
                "data": {
                    "current_cash": account.current_cash,
                    "total_equity": account.total_equity,
                    "profit_loss": account.profit_loss,
                    "profit_loss_pct": account.profit_loss_pct,
                },
            },
        )

    async def _notify_position_update(self, position: Position) -> None:
        """Send position update notification via WebSocket.

        Args:
            position: Position object.
        """
        await ws_manager.send_to_task(
            f"position:{position.id}",
            {
                "type": MessageType.PROGRESS,
                "position_id": position.id,
                "data": {
                    "symbol": position.symbol,
                    "size": position.size,
                    "avg_price": position.avg_price,
                    "market_value": position.market_value,
                    "margin_value": position.margin_value,
                    "multiplier": position.multiplier,
                    "margin_rate": position.margin_rate,
                    "commission_rate": position.commission_rate,
                    "commission_amount": position.commission_amount,
                    "unrealized_pnl": position.unrealized_pnl,
                    "unrealized_pnl_pct": position.unrealized_pnl_pct,
                },
            },
        )

    async def _notify_order_update(self, account_id: str, order: Order) -> None:
        """Send order update notification via WebSocket.

        Args:
            account_id: Account ID.
            order: Order object.
        """
        await ws_manager.send_to_task(
            f"account:{account_id}",
            {
                "type": MessageType.PROGRESS,
                "order_id": order.id,
                "data": {
                    "symbol": order.symbol,
                    "side": order.side,
                    "size": order.size,
                    "price": order.price,
                    "status": order.status,
                    "filled_size": order.filled_size,
                },
            },
        )
