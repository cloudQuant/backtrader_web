"""Direct order service: executes trades via paper trading or live gateways.

Bridges the AI trading intent with actual order execution systems:
- Paper trading: uses PaperTradingService.submit_order()
- Live trading: uses bt_api_py gateway connections (future)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.schemas.ai_trading import OrderType, TradeAction, TradingIntent
from app.services.trading_asset_info_service import (
    normalize_asset_spec,
    query_gateway_asset_spec,
    symbol_aliases,
)

logger = logging.getLogger(__name__)


class DirectOrderService:
    """Executes trading intents against paper or live accounts."""

    async def execute_paper_trade(
        self,
        intent: TradingIntent,
        user_id: str,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute a trade against the paper trading system.

        Args:
            intent: The parsed trading intent.
            user_id: The user's ID.
            account_id: Optional paper trading account ID. If None, uses
                the user's first active account or creates one.

        Returns:
            Execution result dict with success status and order details.
        """
        from app.services.paper_trading_service import PaperTradingService

        service = PaperTradingService()

        try:
            # Resolve account
            resolved_account_id = await self._resolve_paper_account(service, user_id, account_id)

            if intent.action == TradeAction.QUERY:
                return await self._query_positions(service, resolved_account_id)

            if intent.action == TradeAction.CLOSE:
                return await self._close_position(service, resolved_account_id, intent)

            if intent.action not in (TradeAction.BUY, TradeAction.SELL):
                return {
                    "success": False,
                    "error": f"Unsupported action for paper trading: {intent.action.value}",
                }

            # Map intent to paper trading order params
            side = "buy" if intent.action == TradeAction.BUY else "sell"
            order_type_str = self._map_order_type(intent.order_type)
            size = self._normalise_order_size(intent.quantity, default=None)

            stop_price = intent.stop_loss if intent.order_type in {
                OrderType.STOP,
                OrderType.STOP_LIMIT,
            } else None

            order = await service.submit_order(
                account_id=resolved_account_id,
                symbol=intent.symbol or "UNKNOWN",
                order_type=order_type_str,
                side=side,
                size=size,
                price=intent.price,
                stop_price=stop_price,
                limit_price=intent.price if intent.order_type == OrderType.STOP_LIMIT else None,
            )

            return {
                "success": True,
                "type": "paper_trade",
                "order_id": order.id,
                "account_id": resolved_account_id,
                "action": intent.action.value,
                "symbol": intent.symbol,
                "quantity": size,
                "price": intent.price,
                "order_type": order_type_str,
                "side": side,
                "status": order.status if hasattr(order, "status") else "submitted",
                "executed_at": datetime.now(timezone.utc).isoformat(),
                "message": (
                    f"模拟订单已提交: {side} {size} {intent.symbol} @ {intent.price or '市价'}"
                ),
            }

        except ValueError as e:
            return {"success": False, "error": str(e), "message": f"下单失败: {e}"}
        except Exception as e:
            logger.error("Paper trade execution failed: %s", e, exc_info=True)
            return {"success": False, "error": str(e), "message": f"执行异常: {e}"}

    async def execute_live_trade(
        self,
        intent: TradingIntent,
        user_id: str,
        gateway_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute a trade against a live gateway via bt_api_py ZMQ protocol.

        Sends a place_order command to the gateway's ZMQ command endpoint.
        Supports CTP, Binance, OKX, and other bt_api_py gateways.

        Args:
            intent: The parsed trading intent.
            user_id: The user's ID.
            gateway_id: The gateway connection key (e.g. "manual:CTP:investor_id").

        Returns:
            Execution result dict with order details.
        """
        if not gateway_id:
            return {
                "success": False,
                "error": "no_gateway",
                "message": "实盘下单必须显式选择 gateway_id，禁止自动选择网关账户。",
            }

        # Get the gateway's command endpoint
        command_endpoint = self._get_gateway_command_endpoint(gateway_id)
        if not command_endpoint:
            return {
                "success": False,
                "error": "gateway_not_found",
                "message": f"网关 {gateway_id} 未连接或不可用。",
            }

        if intent.action == TradeAction.QUERY:
            return await self._query_live_positions(command_endpoint, gateway_id)

        if intent.action == TradeAction.CLOSE:
            return await self._close_live_position(command_endpoint, gateway_id, intent)

        if intent.action not in (TradeAction.BUY, TradeAction.SELL):
            return {
                "success": False,
                "error": "unsupported_action",
                "message": f"实盘不支持的操作: {intent.action.value}",
            }

        try:
            payload = self._build_order_payload(intent, gateway_id=gateway_id)
        except ValueError as e:
            return {
                "success": False,
                "error": "invalid_order",
                "gateway_id": gateway_id,
                "message": f"订单参数无效: {e}",
            }

        # Send order via ZMQ
        result = self._send_gateway_command(command_endpoint, "place_order", payload)
        success, error_message = self._gateway_order_result_ok(result)
        if success:
            return {
                "success": True,
                "type": "live_trade",
                "gateway_id": gateway_id,
                "action": intent.action.value,
                "symbol": intent.symbol,
                "quantity": intent.quantity,
                "price": intent.price,
                "order_type": intent.order_type.value,
                "order_result": result,
                "executed_at": datetime.now(timezone.utc).isoformat(),
                "message": (
                    f"实盘订单已提交: {intent.action.value} {intent.quantity} "
                    f"{intent.symbol} @ {intent.price or '市价'}"
                ),
            }
        message = error_message or "订单提交失败，网关未返回确认。请检查网关连接状态。"
        return {
            "success": False,
            "error": "order_failed",
            "gateway_id": gateway_id,
            "order_result": result,
            "message": message,
        }

    def _build_order_payload(
        self, intent: TradingIntent, gateway_id: str | None = None
    ) -> dict[str, Any]:
        """Build the ZMQ order payload for bt_api_py gateway."""
        import uuid as _uuid

        side = "buy" if intent.action == TradeAction.BUY else "sell"
        offset = "close" if intent.action == TradeAction.CLOSE else "open"
        order_type_str = self._map_order_type(intent.order_type)
        gateway_context = self._gateway_context_text(intent.exchange, gateway_id)
        self._validate_live_order_type_supported(
            intent,
            gateway_id,
            order_type_str,
            gateway_context=gateway_context,
        )
        self._validate_live_attached_protection_supported(
            intent,
            gateway_id,
            order_type_str,
            gateway_context=gateway_context,
        )
        asset_spec = self._gateway_asset_spec(gateway_id, intent.symbol)
        integer_required = self._requires_integer_lot(
            intent.exchange,
            gateway_id,
            gateway_context=gateway_context,
        )
        size = self._normalise_order_size(
            intent.quantity, default=None, integer_required=integer_required
        )
        self._validate_live_order_size(size, asset_spec, order_type=order_type_str)

        payload: dict[str, Any] = {
            "symbol": intent.symbol or "",
            "side": side,
            "size": size,
            "offset": offset,
            "order_type": order_type_str,
            "request_id": _uuid.uuid4().hex[:16],
            "strategy_id": "ai_trading",
        }

        # Price: 0 means market order (gateway uses last tick ± slippage).
        if intent.order_type == OrderType.MARKET:
            payload["price"] = 0  # Market order
        elif intent.order_type == OrderType.LIMIT:
            payload["price"] = self._normalise_order_price(
                intent.price, "limit order requires a positive price"
            )
        elif intent.order_type == OrderType.STOP:
            stop_price = self._normalise_order_price(
                intent.price if intent.price not in (None, "") else intent.stop_loss,
                "stop order requires a positive trigger price",
            )
            payload["price"] = stop_price
            payload["stop_price"] = stop_price
        elif intent.order_type == OrderType.STOP_LIMIT:
            payload["price"] = self._normalise_order_price(
                intent.price, "stop-limit order requires a positive limit price"
            )
            payload["stop_price"] = self._normalise_order_price(
                intent.stop_loss, "stop-limit order requires a positive stop price"
            )
        else:
            payload["price"] = 0

        if intent.stop_loss not in (None, ""):
            stop_loss = self._normalise_order_price(
                intent.stop_loss, "stop_loss must be a positive price"
            )
            payload["stop_loss"] = stop_loss
            payload["sl"] = stop_loss
        if intent.take_profit not in (None, ""):
            take_profit = self._normalise_order_price(
                intent.take_profit, "take_profit must be a positive price"
            )
            payload["take_profit"] = take_profit
            payload["tp"] = take_profit

        self._validate_live_order_prices(payload, asset_spec)

        # Exchange ID hint (optional, gateway can resolve from symbol)
        if intent.exchange:
            exchange_map = {
                "ctp": "",  # CTP resolves internally
                "binance": "BINANCE",
                "okx": "OKX",
            }
            exchange_id = exchange_map.get(intent.exchange.lower(), "")
            if exchange_id:
                payload["exchange_id"] = exchange_id

        return payload

    def _gateway_asset_spec(
        self,
        gateway_id: str | None,
        symbol: str | None,
    ) -> dict[str, Any]:
        if not gateway_id or not symbol:
            return {}
        try:
            gateway = self._get_gateways_dict().get(gateway_id)
        except Exception:
            gateway = None
        if not isinstance(gateway, dict):
            return {}

        merged: dict[str, Any] = {}
        for source in self._gateway_metadata_sources(gateway):
            spec = self._asset_spec_from_metadata(source, symbol)
            if spec:
                merged.update(spec)
        gateway_spec = query_gateway_asset_spec(gateway, symbol)
        if gateway_spec:
            merged.update(gateway_spec)
        return normalize_asset_spec(
            merged,
            symbol=symbol,
            source=str(merged.get("source") or "direct_order"),
        )

    @classmethod
    def _gateway_metadata_sources(cls, gateway: dict[str, Any]) -> list[Any]:
        sources: list[Any] = [gateway]
        config = gateway.get("config")
        if config is not None:
            sources.append(config)
        params = gateway.get("params")
        if isinstance(params, dict):
            sources.append(params)
        if config is not None:
            config_params = cls._source_field_value(config, "params")
            if isinstance(config_params, dict):
                sources.append(config_params)
        return sources

    @classmethod
    def _asset_spec_from_metadata(cls, source: Any, symbol: str) -> dict[str, Any]:
        aliases = symbol_aliases(symbol)
        for container_name in ("contract_metadata", "contracts", "contract_specs", "symbol_specs"):
            container = cls._source_field_value(source, container_name)
            if not isinstance(container, dict):
                continue
            for alias in aliases:
                item = container.get(alias)
                if isinstance(item, dict):
                    return dict(item)
        return {}

    @classmethod
    def _first_number(cls, *values: Any, default: float | None = None) -> float | None:
        for value in values:
            if value in (None, ""):
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return default

    @classmethod
    def _validate_live_order_size(
        cls,
        size: int | float,
        asset_spec: dict[str, Any],
        *,
        enforce_min: bool = True,
        order_type: str | None = None,
    ) -> None:
        if not asset_spec:
            return
        requested = abs(float(size or 0.0))
        min_order_size = cls._first_number(
            asset_spec.get("min_order_size"),
            asset_spec.get("min_order_qty"),
            asset_spec.get("min_size"),
            asset_spec.get("min_qty"),
            asset_spec.get("minQty"),
            asset_spec.get("minSz"),
            asset_spec.get("min_volume"),
            asset_spec.get("volume_min"),
            asset_spec.get("min_lot"),
            asset_spec.get("lot_min"),
            asset_spec.get("SYMBOL_VOLUME_MIN"),
        )
        if enforce_min and min_order_size and requested + 1e-12 < min_order_size:
            raise ValueError(
                f"quantity {size} is below the minimum allowed size {min_order_size}"
            )

        max_order_size = cls._max_live_order_size(asset_spec, order_type=order_type)
        if max_order_size and requested > max_order_size + 1e-12:
            raise ValueError(f"quantity {size} exceeds the maximum allowed size {max_order_size}")

        step = cls._first_number(
            asset_spec.get("order_size_step"),
            asset_spec.get("size_step"),
            asset_spec.get("qty_step"),
            asset_spec.get("qty_unit"),
            asset_spec.get("quantity_step"),
            asset_spec.get("volume_step"),
            asset_spec.get("lot_step"),
            asset_spec.get("step_size"),
            asset_spec.get("stepSize"),
            asset_spec.get("lotSz"),
            asset_spec.get("SYMBOL_VOLUME_STEP"),
        )
        if step and step > 0:
            scaled = requested / step
            if abs(round(scaled) - scaled) > 1e-9:
                raise ValueError(f"quantity {size} does not align with size step {step}")

    @classmethod
    def _max_live_order_size(
        cls,
        asset_spec: dict[str, Any],
        *,
        order_type: str | None = None,
    ) -> float | None:
        order_type_text = str(order_type or "").strip().lower()
        max_order_size = None
        if order_type_text == "market":
            max_order_size = cls._first_number(
                asset_spec.get("market_max_order_size"),
                asset_spec.get("max_market_order_size"),
                asset_spec.get("max_mkt_order_size"),
                asset_spec.get("maxMktSz"),
            )
        elif order_type_text == "limit":
            max_order_size = cls._first_number(
                asset_spec.get("limit_max_order_size"),
                asset_spec.get("max_limit_order_size"),
                asset_spec.get("max_lmt_order_size"),
                asset_spec.get("maxLmtSz"),
            )
        if max_order_size is not None:
            return max_order_size
        return cls._first_number(
            asset_spec.get("max_order_size"),
            asset_spec.get("max_order_qty"),
            asset_spec.get("max_size"),
            asset_spec.get("max_qty"),
            asset_spec.get("maxQty"),
            asset_spec.get("max_volume"),
            asset_spec.get("volume_max"),
            asset_spec.get("max_lot"),
            asset_spec.get("lot_max"),
            asset_spec.get("SYMBOL_VOLUME_MAX"),
        )

    @staticmethod
    def _split_close_plan_by_max_order_size(
        plan: dict[str, Any],
        max_order_size: float | None,
    ) -> list[dict[str, Any]]:
        size = abs(float(plan.get("size") or 0.0))
        if not max_order_size or max_order_size <= 0 or size <= max_order_size + 1e-12:
            return [plan]

        chunks: list[dict[str, Any]] = []
        remaining = size
        while remaining > 1e-12:
            chunk_size = min(remaining, max_order_size)
            chunk = dict(plan)
            chunk["size"] = chunk_size
            chunks.append(chunk)
            remaining -= chunk_size
        return chunks

    @classmethod
    def _validate_live_order_prices(
        cls,
        payload: dict[str, Any],
        asset_spec: dict[str, Any],
    ) -> None:
        if not asset_spec:
            return
        tick = cls._first_number(
            asset_spec.get("min_price_tick"),
            asset_spec.get("price_tick"),
            asset_spec.get("tick_size"),
            asset_spec.get("price_unit"),
            asset_spec.get("tickSize"),
        )
        if not tick or tick <= 0:
            return
        for field in ("price", "stop_price", "stop_loss", "take_profit"):
            value = payload.get(field)
            if value in (None, "", 0):
                continue
            scaled = float(value) / tick
            if abs(round(scaled) - scaled) > 1e-9:
                raise ValueError(f"{field} {value} does not align with tick size {tick}")

    @staticmethod
    def _normalise_order_price(value: Any, message: str) -> float:
        try:
            price = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(message) from exc
        if price <= 0:
            raise ValueError(message)
        return price

    def _gateway_context_text(
        self,
        exchange: str | None = None,
        gateway_id: str | None = None,
    ) -> str:
        values: list[Any] = [exchange, gateway_id]
        try:
            state = self._get_gateways_dict().get(gateway_id) if gateway_id else None
        except Exception:
            state = None
        values.extend(self._gateway_source_context_values(state))
        return " ".join(str(value) for value in values if value not in (None, ""))

    @classmethod
    def _gateway_source_context_values(cls, source: Any) -> list[Any]:
        if source is None:
            return []
        fields = ("exchange_type", "asset_type", "provider", "gateway_type", "type")
        values = [cls._source_field_value(source, field) for field in fields]
        config = cls._source_field_value(source, "config")
        if config is not None:
            values.extend(cls._source_field_value(config, field) for field in fields)
        return values

    @staticmethod
    def _source_field_value(source: Any, field: str) -> Any:
        if isinstance(source, dict):
            return source.get(field)
        return getattr(source, field, None)

    @staticmethod
    def _validate_live_order_type_supported(
        intent: TradingIntent,
        gateway_id: str | None,
        order_type: str,
        *,
        gateway_context: str | None = None,
    ) -> None:
        text = f"{intent.exchange or ''} {gateway_id or ''} {gateway_context or ''}".upper()
        if any(token in text for token in ("CTP", "CFFEX", "SHFE", "DCE", "CZCE", "INE", "GFEX")):
            if order_type not in {"market", "limit"}:
                raise ValueError("CTP gateway supports only market and limit direct orders")
        if "MT5" in text and order_type == "stop_limit":
            raise ValueError("MT5 gateway does not support stop-limit direct orders")
        if any(token in text for token in ("BINANCE", "OKX")) and order_type not in {
            "market",
            "limit",
        }:
            raise ValueError(
                f"{text.strip() or 'gateway'} direct conditional orders are not supported"
            )

    @staticmethod
    def _validate_live_attached_protection_supported(
        intent: TradingIntent,
        gateway_id: str | None,
        order_type: str,
        *,
        gateway_context: str | None = None,
    ) -> None:
        if order_type not in {"market", "limit"}:
            return
        if intent.stop_loss in (None, "") and intent.take_profit in (None, ""):
            return

        text = f"{intent.exchange or ''} {gateway_id or ''} {gateway_context or ''}".upper()
        if any(token in text for token in ("MT5", "METATRADER", "META_TRADER")):
            return
        raise ValueError(
            "attached stop-loss/take-profit is only supported for MT5 direct live orders"
        )

    @staticmethod
    def _requires_integer_lot(
        exchange: str | None = None,
        gateway_id: str | None = None,
        *,
        gateway_context: str | None = None,
    ) -> bool:
        text = f"{exchange or ''} {gateway_id or ''} {gateway_context or ''}".upper()
        return any(token in text for token in ("CTP", "CFFEX", "SHFE", "DCE", "CZCE", "INE", "GFEX"))

    @staticmethod
    def _normalise_order_size(
        value: Any, *, default: float | None = 1.0, integer_required: bool = False
    ) -> int | float:
        raw = default if value in (None, "") else value
        try:
            size = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("quantity must be a positive number") from exc
        if size <= 0:
            raise ValueError("quantity must be positive")
        if integer_required:
            if abs(size - round(size)) > 1e-12:
                raise ValueError("CTP/futures order quantity must be an integer lot size")
            return int(round(size))
        return int(round(size)) if abs(size - round(size)) <= 1e-12 else size

    @staticmethod
    def _gateway_order_result_ok(result: Any) -> tuple[bool, str | None]:
        result = DirectOrderService._unwrap_gateway_result(result)
        if result is None:
            return False, None
        if not isinstance(result, dict):
            return DirectOrderService._non_mapping_order_result_ok(result)
        if not result:
            return False, "empty gateway order response"
        status = str(result.get("status") or result.get("order_status") or "").strip().lower()
        lifecycle_success_statuses = {
            "submitted",
            "accepted",
            "completed",
            "complete",
            "partial",
            "partially_filled",
            "partially-filled",
            "filled",
            "live",
            "new",
            "open",
            "pending",
            "placed",
        }
        if status in {
            "error",
            "failed",
            "fail",
            "rejected",
            "reject",
            "cancelled",
            "canceled",
            "expired",
        }:
            error = (
                result.get("error")
                or result.get("message")
                or result.get("reason")
                or f"gateway order status: {status}"
            )
            return False, str(error)
        if status in lifecycle_success_statuses:
            return True, None

        retcode = result.get("retcode") or result.get("ret_code")
        if retcode not in (None, ""):
            try:
                retcode_int = int(retcode)
            except (TypeError, ValueError):
                retcode_int = None
            if retcode_int in {10008, 10009, 10010}:
                return True, None
            if retcode_int in {
                10004,
                10006,
                10007,
                10013,
                10014,
                10015,
                10016,
                10017,
                10018,
                10019,
                10030,
                10031,
            }:
                ret_message = (
                    result.get("retcode_external")
                    or result.get("comment")
                    or result.get("message")
                    or result.get("error")
                    or f"gateway retcode: {retcode}"
                )
                return False, str(ret_message)

        service_code = result.get("sCode") or result.get("scode")
        if service_code not in (None, "", 0, "0"):
            ret_message = (
                result.get("sMsg")
                or result.get("smsg")
                or result.get("message")
                or result.get("error")
                or f"gateway service code: {service_code}"
            )
            return False, str(ret_message)

        code = result.get("code")
        if code not in (None, "", 0, "0"):
            ret_message = (
                result.get("comment")
                or result.get("message")
                or result.get("error")
                or f"gateway code: {code}"
            )
            return False, str(ret_message)
        success_value = result.get("success")
        if isinstance(success_value, bool):
            if success_value:
                return True, None
            error = result.get("error") or result.get("message") or result.get("comment")
            return False, str(error or "gateway order success flag is false")
        if status in {"ok", "success"}:
            return True, None
        if DirectOrderService._gateway_order_result_has_identity(result):
            return True, None
        return False, "invalid gateway order response"

    @staticmethod
    def _non_mapping_order_result_ok(result: Any) -> tuple[bool, str | None]:
        if isinstance(result, bool):
            return False, "invalid gateway order response"
        if isinstance(result, str):
            return (True, None) if result.strip() else (False, "empty gateway order response")
        if isinstance(result, (int, float)):
            return (True, None) if result != 0 else (False, "invalid gateway order response")
        return False, "invalid gateway order response"

    @staticmethod
    def _gateway_order_result_has_identity(result: dict[str, Any]) -> bool:
        for key in (
            "order_id",
            "orderId",
            "OrderID",
            "ordId",
            "OrdID",
            "id",
            "ticket",
            "order",
            "order_ref",
            "orderRef",
            "OrderRef",
            "client_order_id",
            "clientOrderId",
            "newClientOrderId",
            "origClientOrderId",
            "orderLinkId",
            "origOrderLinkId",
            "clOrdId",
            "external_order_id",
            "externalOrderId",
            "venue_order_id",
            "venueOrderId",
            "deal",
            "deal_id",
            "dealId",
            "DealID",
        ):
            value = result.get(key)
            if value not in (None, ""):
                return True
        return False

    @staticmethod
    def _unwrap_gateway_result(result: Any) -> Any:
        current = result
        for _ in range(5):
            if not isinstance(current, dict):
                return current
            status = str(current.get("status") or "").strip().lower()
            code = current.get("code")
            if status in {"ok", "success"} or code in (0, "0"):
                nested = current.get("data", current.get("result"))
                if isinstance(nested, dict):
                    current = nested
                    continue
                if (
                    isinstance(nested, list)
                    and nested
                    and isinstance(nested[0], dict)
                ):
                    current = nested[0]
                    continue
            return current
        return current

    @staticmethod
    def _gateway_result_error_message(result: Any) -> str | None:
        current = DirectOrderService._unwrap_gateway_result(result)
        if not isinstance(current, dict):
            return None
        status = str(current.get("status") or current.get("order_status") or "").strip().lower()
        if status not in {
            "error",
            "failed",
            "fail",
            "rejected",
            "reject",
            "cancelled",
            "canceled",
            "expired",
        }:
            return None
        return str(
            current.get("error")
            or current.get("message")
            or current.get("reason")
            or f"gateway status: {status}"
        )

    @classmethod
    def _gateway_positions_payload(cls, result: Any) -> list[Any] | None:
        if isinstance(result, list):
            return result
        if not isinstance(result, dict):
            return None
        for key in ("positions", "data", "result"):
            nested = result.get(key)
            if isinstance(nested, list):
                return nested
            if isinstance(nested, dict):
                positions = cls._gateway_positions_payload(nested)
                if positions is not None:
                    return positions
                rows = [dict(item) for item in nested.values() if isinstance(item, dict)]
                if rows:
                    return rows
        if cls._looks_like_position_row(result):
            return [result]
        rows = [dict(item) for item in result.values() if isinstance(item, dict)]
        if rows:
            return rows
        return None

    @staticmethod
    def _looks_like_position_row(row: dict[str, Any]) -> bool:
        symbol_keys = {
            "data_name",
            "symbol",
            "instrument",
            "instrument_id",
            "InstrumentID",
            "instId",
            "contract_symbol",
            "position_symbol_name",
            "symbol_name",
            "localSymbol",
            "local_symbol",
            "contractDesc",
            "contract_desc",
            "description",
            "ticker",
            "conid",
        }
        size_keys = {
            "size",
            "volume",
            "position",
            "qty",
            "quantity",
            "trade_volume",
            "position_volume",
            "positionAmt",
            "pos",
            "availPos",
            "pa",
            "Position",
            "Volume",
            "Qty",
            "Quantity",
            "TradeVolume",
        }
        return any(key in row for key in symbol_keys) and any(key in row for key in size_keys)

    @staticmethod
    def _symbol_candidates(value: Any) -> set[str]:
        raw = str(value or "").strip()
        if not raw:
            return set()
        candidates = set(symbol_aliases(raw))
        if "." in raw:
            left, right = raw.split(".", 1)
            candidates.update({left, left.upper(), left.lower(), right, right.upper(), right.lower()})
        if "_" in raw:
            left, right = raw.split("_", 1)
            candidates.update({left, left.upper(), left.lower(), right, right.upper(), right.lower()})
        return {item.upper() for item in candidates if item}

    @staticmethod
    def _position_symbol(row: dict[str, Any]) -> str:
        return str(
            row.get("data_name")
            or row.get("symbol")
            or row.get("instrument")
            or row.get("instrument_id")
            or row.get("InstrumentID")
            or row.get("instId")
            or row.get("contract_symbol")
            or row.get("position_symbol_name")
            or row.get("symbol_name")
            or row.get("localSymbol")
            or row.get("local_symbol")
            or row.get("contractDesc")
            or row.get("contract_desc")
            or row.get("description")
            or row.get("ticker")
            or row.get("conid")
            or ""
        ).strip()

    @staticmethod
    def _position_size(row: dict[str, Any]) -> float:
        for key in (
            "size",
            "volume",
            "position",
            "qty",
            "quantity",
            "trade_volume",
            "position_volume",
            "positionAmt",
            "pos",
            "availPos",
            "pa",
            "Position",
            "Volume",
            "Qty",
            "Quantity",
            "TradeVolume",
        ):
            value = row.get(key)
            if value in (None, ""):
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return 0.0

    @classmethod
    def _position_direction(cls, row: dict[str, Any]) -> str:
        for key in (
            "direction",
            "side",
            "position_side",
            "position_direction",
            "positionSide",
            "posSide",
            "PositionSide",
            "PosiDirection",
            "posi_direction",
            "trade_action",
            "position_type",
            "type",
        ):
            direction = cls._position_direction_from_value(key, row.get(key))
            if direction:
                return direction
        size = cls._position_size(row)
        return "short" if size < 0 else "long"

    @staticmethod
    def _position_direction_from_value(key: str, value: Any) -> str | None:
        text = str(value or "").strip().lower()
        if not text:
            return None
        if text in {"short", "sell", "sold", "position_type_sell", "deal_type_sell"}:
            return "short"
        if text in {"long", "buy", "bought", "position_type_buy", "deal_type_buy"}:
            return "long"

        key_text = str(key or "").strip().lower()
        try:
            code = int(float(text))
        except (TypeError, ValueError):
            code = None
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
        return None

    @classmethod
    def _select_close_position(
        cls, positions: list[dict[str, Any]], symbol: str | None
    ) -> tuple[dict[str, Any] | None, str | None]:
        matches, error = cls._matching_close_positions(positions, symbol)
        if error:
            return None, error

        direction = cls._position_direction(matches[0])
        total_size = sum(abs(cls._position_size(pos)) for pos in matches)
        if total_size <= 0:
            return None, "no_position"
        target = dict(matches[0])
        target["direction"] = direction
        target["size"] = total_size
        target["volume"] = total_size
        target["symbol"] = cls._position_symbol(matches[0]) or symbol or ""
        return target, None

    @classmethod
    def _matching_close_positions(
        cls, positions: list[dict[str, Any]], symbol: str | None
    ) -> tuple[list[dict[str, Any]], str | None]:
        nonzero = [pos for pos in positions if abs(cls._position_size(pos)) > 0]
        if symbol:
            requested = cls._symbol_candidates(symbol)
            matches = [
                pos
                for pos in nonzero
                if requested and requested & cls._symbol_candidates(cls._position_symbol(pos))
            ]
        else:
            matches = nonzero

        if not matches:
            return [], "no_position"
        if not symbol and len(matches) > 1:
            return [], "ambiguous_position"

        directions = {cls._position_direction(pos) for pos in matches}
        if len(directions) > 1:
            return [], "ambiguous_position"
        return matches, None

    @staticmethod
    def _position_number(row: dict[str, Any], *keys: str) -> float | None:
        for key in keys:
            value = row.get(key)
            if value in (None, ""):
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return None

    @classmethod
    def _requested_close_size(cls, intent: TradingIntent, available_size: float) -> float:
        available = abs(float(available_size or 0.0))
        if available <= 0:
            raise ValueError("no available position size to close")
        if intent.quantity in (None, ""):
            return available
        requested = cls._first_number(intent.quantity)
        if requested is None or requested <= 0:
            raise ValueError("close quantity must be positive")
        if requested > available + 1e-12:
            raise ValueError(
                f"close quantity {requested} exceeds available position size {available}"
            )
        return min(requested, available)

    @staticmethod
    def _row_exchange_id(row: dict[str, Any]) -> str:
        return str(
            row.get("exchange_id") or row.get("exchange") or row.get("ExchangeID") or ""
        ).strip()

    @staticmethod
    def _position_id(row: dict[str, Any]) -> Any:
        for key in (
            "position_id",
            "position_ticket",
            "ticket",
            "PositionID",
            "POSITION_ID",
            "external_position_id",
        ):
            value = row.get(key)
            if value not in (None, ""):
                return value
        return None

    @classmethod
    def _is_ctp_close_context(
        cls,
        intent: TradingIntent,
        gateway_id: str,
        matches: list[dict[str, Any]],
    ) -> bool:
        values = [
            intent.exchange,
            gateway_id,
            *(row.get("gateway") for row in matches),
            *(row.get("exchange_type") for row in matches),
            *(row.get("provider") for row in matches),
        ]
        return any("CTP" in str(value or "").upper() for value in values)

    @classmethod
    def _is_mt5_close_context(
        cls,
        intent: TradingIntent,
        gateway_id: str,
        matches: list[dict[str, Any]],
    ) -> bool:
        values = [
            intent.exchange,
            gateway_id,
            *(row.get("gateway") for row in matches),
            *(row.get("exchange_type") for row in matches),
            *(row.get("provider") for row in matches),
            *(row.get("source") for row in matches),
        ]
        return any("MT5" in str(value or "").upper() for value in values)

    @classmethod
    def _close_position_plans(
        cls,
        matches: list[dict[str, Any]],
        intent: TradingIntent,
        gateway_id: str,
    ) -> list[dict[str, Any]]:
        target_size = cls._requested_close_size(
            intent,
            sum(abs(cls._position_size(pos)) for pos in matches),
        )
        if cls._is_ctp_close_context(intent, gateway_id, matches):
            plans = cls._ctp_close_position_plans(matches, intent, target_size)
            if plans:
                return plans

        if cls._is_mt5_close_context(intent, gateway_id, matches):
            return cls._mt5_close_position_plans(matches, intent, target_size)

        direction = cls._position_direction(matches[0])
        side = "sell" if direction == "long" else "buy"
        return [
            {
                "symbol": cls._position_symbol(matches[0]) or intent.symbol or "",
                "exchange_id": cls._row_exchange_id(matches[0]) or None,
                "side": side,
                "size": target_size,
                "offset": "close",
            }
        ]

    @classmethod
    def _ctp_close_position_plans(
        cls,
        matches: list[dict[str, Any]],
        intent: TradingIntent,
        target_size: float,
    ) -> list[dict[str, Any]]:
        direction = cls._position_direction(matches[0])
        side = "sell" if direction == "long" else "buy"
        grouped: dict[tuple[str, str, str, str | None], float] = {}
        symbol_by_exchange: dict[str | None, str] = {}
        for row in matches:
            exchange_id = cls._row_exchange_id(row) or None
            symbol_by_exchange.setdefault(exchange_id, cls._position_symbol(row) or intent.symbol or "")

        remaining_to_close = target_size
        for row in matches:
            if remaining_to_close <= 1e-12:
                break
            exchange_id = cls._row_exchange_id(row) or None
            symbol = symbol_by_exchange.get(exchange_id) or cls._position_symbol(row) or intent.symbol or ""
            row_size = min(abs(cls._position_size(row)), remaining_to_close)
            if row_size <= 0:
                continue
            today = cls._position_number(
                row,
                "today_position",
                "td_position",
                "today_size",
                "today_volume",
                "TodayPosition",
                "TdPosition",
                "tdPos",
                "todayPos",
                "TodayVolume",
            )
            yesterday = cls._position_number(
                row,
                "yd_position",
                "yesterday_position",
                "yesterday_size",
                "history_position",
                "history_volume",
                "YdPosition",
                "HistoryPosition",
                "ydPos",
                "historyPos",
                "HistoryVolume",
            )

            used = 0.0
            if today is not None and today > 0:
                qty = min(today, row_size) if row_size > 0 else today
                grouped[(symbol, side, "close_today", exchange_id)] = (
                    grouped.get((symbol, side, "close_today", exchange_id), 0.0) + qty
                )
                used += qty
                remaining_to_close -= qty
            if yesterday is not None and yesterday > 0:
                remaining = max(row_size - used, 0.0)
                if remaining <= 0:
                    continue
                qty = min(yesterday, remaining)
                qty = min(qty, remaining_to_close)
                grouped[(symbol, side, "close_yesterday", exchange_id)] = (
                    grouped.get((symbol, side, "close_yesterday", exchange_id), 0.0) + qty
                )
                used += qty
                remaining_to_close -= qty
            if today is None and yesterday is None and row_size > 0:
                grouped[(symbol, side, "close", exchange_id)] = (
                    grouped.get((symbol, side, "close", exchange_id), 0.0) + row_size
                )
                remaining_to_close -= row_size
            elif row_size > used:
                qty = min(row_size - used, remaining_to_close)
                grouped[(symbol, side, "close", exchange_id)] = (
                    grouped.get((symbol, side, "close", exchange_id), 0.0) + qty
                )
                remaining_to_close -= qty

        return [
            {
                "symbol": symbol,
                "side": side,
                "size": size,
                "offset": offset,
                "exchange_id": exchange_id,
            }
            for (symbol, side, offset, exchange_id), size in grouped.items()
            if size > 0
        ]

    @classmethod
    def _mt5_close_position_plans(
        cls,
        matches: list[dict[str, Any]],
        intent: TradingIntent,
        target_size: float,
    ) -> list[dict[str, Any]]:
        direction = cls._position_direction(matches[0])
        side = "sell" if direction == "long" else "buy"
        plans: list[dict[str, Any]] = []
        remaining_to_close = target_size
        for row in matches:
            if remaining_to_close <= 1e-12:
                break
            row_size = min(abs(cls._position_size(row)), remaining_to_close)
            if row_size <= 0:
                continue
            position_id = cls._position_id(row)
            if position_id in (None, ""):
                symbol = cls._position_symbol(row) or intent.symbol or "指定品种"
                raise ValueError(f"MT5 平仓缺少 {symbol} 的 position_id，无法安全提交平仓订单")
            plans.append(
                {
                    "symbol": cls._position_symbol(row) or intent.symbol or "",
                    "exchange_id": cls._row_exchange_id(row) or None,
                    "side": side,
                    "size": row_size,
                    "offset": "close",
                    "order_type": "close",
                    "position_id": position_id,
                }
            )
            remaining_to_close -= row_size
        return plans

    def _find_available_gateway(self, intent: TradingIntent) -> str | None:
        """Find an available gateway connection matching the intent's exchange."""
        try:
            from app.services.manual_gateway_service import list_connected_gateways

            gateways = self._get_gateways_dict()
            connected = list_connected_gateways(gateways)
            if not connected:
                return None

            # If exchange is specified, try to match
            if intent.exchange:
                target_exchange = intent.exchange.upper()
                for gw in connected:
                    if gw.get("exchange_type", "").upper() == target_exchange:
                        return gw.get("gateway_key")

            # Return first available gateway
            return connected[0].get("gateway_key") if connected else None
        except Exception:
            return None

    def _get_gateways_dict(self) -> dict[str, Any]:
        """Get the gateways dict from LiveTradingManager."""
        try:
            from app.services.live_trading_manager import get_live_trading_manager

            manager = get_live_trading_manager()
            return manager._gateways
        except Exception:
            return {}

    def _get_gateway_command_endpoint(self, gateway_id: str) -> str | None:
        """Get the ZMQ command endpoint for a gateway."""
        try:
            gateways = self._get_gateways_dict()
            state = gateways.get(gateway_id)
            if state is None:
                return None
            config = state.get("config")
            if config is None:
                return None
            return getattr(config, "command_endpoint", None)
        except Exception:
            return None

    async def _query_live_positions(self, command_endpoint: str, gateway_id: str) -> dict[str, Any]:
        """Query positions from a live gateway."""
        result = self._send_gateway_command(command_endpoint, "get_positions", {})
        error_message = self._gateway_result_error_message(result)
        if error_message:
            return {
                "success": False,
                "error": "query_failed",
                "gateway_id": gateway_id,
                "positions": [],
                "message": error_message,
            }
        positions = self._gateway_positions_payload(result)
        if positions is None:
            return {
                "success": False,
                "error": "query_failed",
                "gateway_id": gateway_id,
                "positions": [],
                "message": "无法解析网关持仓响应",
            }
        nonzero_positions = [
            pos
            for pos in positions
            if isinstance(pos, dict) and abs(self._position_size(pos)) > 0
        ]
        return {
            "success": True,
            "type": "live_query",
            "gateway_id": gateway_id,
            "positions": nonzero_positions,
            "message": (
                f"实盘持仓 {len(nonzero_positions)} 个品种"
                if nonzero_positions
                else "当前无实盘持仓"
            ),
        }

    async def _close_live_position(
        self, command_endpoint: str, gateway_id: str, intent: TradingIntent
    ) -> dict[str, Any]:
        """Close a live position via gateway."""
        # First query positions to find the target
        positions_result = self._send_gateway_command(command_endpoint, "get_positions", {})
        positions_payload = self._gateway_positions_payload(positions_result)
        if positions_payload is None:
            error_message = self._gateway_result_error_message(positions_result)
            return {
                "success": False,
                "error": "query_failed",
                "message": error_message or "无法查询持仓信息",
            }

        positions = [pos for pos in positions_payload if isinstance(pos, dict)]
        matches, select_error = self._matching_close_positions(positions, intent.symbol)

        if not matches:
            if select_error == "ambiguous_position":
                return {
                    "success": False,
                    "error": "ambiguous_position",
                    "message": f"{intent.symbol or '当前账户'} 存在多个可平持仓，请指定合约或方向",
                }
            return {
                "success": False,
                "error": "no_position",
                "message": f"未找到 {intent.symbol or '指定品种'} 的实盘持仓",
            }

        try:
            plans = self._close_position_plans(matches, intent, gateway_id)
        except ValueError as e:
            return {
                "success": False,
                "error": "invalid_order",
                "message": str(e),
            }
        if not plans:
            return {
                "success": False,
                "error": "no_position",
                "message": f"未找到 {intent.symbol or '指定品种'} 的可平持仓",
            }

        submitted: list[dict[str, Any]] = []
        for plan in plans:
            try:
                gateway_context = self._gateway_context_text(
                    intent.exchange or plan.get("exchange_id"),
                    gateway_id,
                )
                integer_required = self._requires_integer_lot(
                    intent.exchange or plan.get("exchange_id"),
                    gateway_id,
                    gateway_context=gateway_context,
                )
                asset_spec = self._gateway_asset_spec(
                    gateway_id,
                    str(plan.get("symbol") or intent.symbol or ""),
                )
                order_type_for_validation = str(plan.get("order_type") or "market").strip().lower()
                if order_type_for_validation not in {"market", "limit"}:
                    order_type_for_validation = "market"
                max_order_size = self._max_live_order_size(
                    asset_spec,
                    order_type=order_type_for_validation,
                )
                split_plans = self._split_close_plan_by_max_order_size(plan, max_order_size)
            except ValueError as e:
                return {"success": False, "error": "invalid_order", "message": str(e)}

            for split_plan in split_plans:
                try:
                    size = self._normalise_order_size(
                        abs(split_plan["size"]),
                        integer_required=integer_required,
                    )
                    self._validate_live_order_size(
                        size,
                        asset_spec,
                        enforce_min=False,
                        order_type=order_type_for_validation,
                    )
                except ValueError as e:
                    return {"success": False, "error": "invalid_order", "message": str(e)}

                payload = {
                    "symbol": split_plan.get("symbol") or intent.symbol,
                    "side": split_plan["side"],
                    "size": size,
                    "price": 0,  # Market order for close
                    "offset": split_plan.get("offset") or "close",
                    "order_type": split_plan.get("order_type") or "market",
                    "strategy_id": "ai_trading",
                }
                if split_plan.get("exchange_id"):
                    payload["exchange_id"] = split_plan["exchange_id"]
                if split_plan.get("position_id") not in (None, ""):
                    payload["position_id"] = split_plan["position_id"]

                result = self._send_gateway_command(command_endpoint, "place_order", payload)
                success, error_message = self._gateway_order_result_ok(result)
                submitted.append(
                    {
                        "payload": payload,
                        "order_result": result,
                        "success": success,
                        "message": error_message,
                    }
                )
                if not success:
                    return {
                        "success": False,
                        "error": "close_failed",
                        "submitted_orders": submitted,
                        "order_result": result,
                        "message": error_message or "平仓订单提交失败",
                    }

        total_size = sum(float(item["payload"]["size"] or 0.0) for item in submitted)
        first_payload = submitted[0]["payload"]
        if len(submitted) == 1:
            return {
                "success": True,
                "type": "live_close",
                "gateway_id": gateway_id,
                "symbol": intent.symbol,
                "size": first_payload["size"],
                "side": first_payload["side"],
                "offset": first_payload["offset"],
                "submitted_orders": submitted,
                "message": (
                    f"实盘平仓订单已提交: {first_payload['side']} "
                    f"{first_payload['size']} {intent.symbol}"
                ),
            }

        return {
            "success": True,
            "type": "live_close",
            "gateway_id": gateway_id,
            "symbol": intent.symbol,
            "size": total_size,
            "side": first_payload["side"],
            "submitted_orders": submitted,
            "message": f"实盘平仓订单已提交: {len(submitted)} 笔 / {total_size} {intent.symbol}",
        }

    @staticmethod
    def _send_gateway_command(
        command_endpoint: str,
        command: str,
        payload: dict[str, Any],
        send_timeout_ms: int = 3000,
        recv_timeout_ms: int = 5000,
    ) -> Any | None:
        """Send a command to the gateway via ZMQ DEALER socket.

        This replicates the pattern from quote_service.py for gateway communication.
        """
        import uuid as _uuid

        try:
            import zmq
        except ImportError:
            logger.warning("pyzmq not installed; cannot send %s", command)
            return None

        ctx = zmq.Context.instance()
        sock = ctx.socket(zmq.DEALER)
        sock.setsockopt(zmq.IDENTITY, _uuid.uuid4().hex.encode("utf-8"))
        sock.setsockopt(zmq.SNDTIMEO, send_timeout_ms)
        sock.setsockopt(zmq.RCVTIMEO, recv_timeout_ms)
        try:
            import json

            sock.connect(command_endpoint)
            request = {
                "request_id": _uuid.uuid4().hex,
                "command": command,
                "payload": payload,
            }
            sock.send(
                json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            )
            resp_raw = sock.recv()
            resp = json.loads(resp_raw.decode("utf-8"))
            if isinstance(resp, dict) and resp.get("status") == "ok":
                return resp.get("data")
            if isinstance(resp, dict):
                logger.warning("%s failed: %s", command, resp.get("error", "unknown error"))
                return resp
            return None
        except Exception as e:
            logger.warning("Gateway command %s failed: %s", command, e)
            return None
        finally:
            sock.close()

    async def _resolve_paper_account(
        self,
        service: Any,
        user_id: str,
        account_id: str | None,
    ) -> str:
        """Resolve or create a paper trading account for the user."""
        if account_id:
            return account_id

        # Try to find user's first active account
        accounts, _ = await service.list_accounts(
            filters={"user_id": user_id, "is_active": True},
            page=1,
            page_size=1,
        )
        if accounts:
            return accounts[0].id

        # Create a default AI trading account
        account = await service.create_account(
            user_id=user_id,
            name="AI Trading 模拟账户",
            initial_cash=100000.0,
            commission_rate=0.001,
            slippage_rate=0.001,
        )
        return account.id

    async def _query_positions(self, service: Any, account_id: str) -> dict[str, Any]:
        """Query current positions for an account."""
        try:
            positions, _ = await service.list_positions(
                filters={"account_id": account_id},
                page=1,
                page_size=50,
            )
            position_list = [
                {
                    "symbol": p.symbol,
                    "size": p.size,
                    "avg_price": p.avg_price,
                    "unrealized_pnl": p.unrealized_pnl,
                }
                for p in positions
            ]
            return {
                "success": True,
                "type": "query",
                "account_id": account_id,
                "positions": position_list,
                "message": (
                    f"当前持仓 {len(position_list)} 个品种" if position_list else "当前无持仓"
                ),
            }
        except Exception as e:
            return {"success": True, "type": "query", "positions": [], "message": f"查询持仓: {e}"}

    async def _close_position(
        self, service: Any, account_id: str, intent: TradingIntent
    ) -> dict[str, Any]:
        """Close a position by submitting a counter-order."""
        try:
            positions, _ = await service.list_positions(
                filters={"account_id": account_id},
                page=1,
                page_size=50,
            )
            target = None
            requested = self._symbol_candidates(intent.symbol)
            for p in positions:
                position_symbol = getattr(p, "symbol", "")
                if requested and requested & self._symbol_candidates(position_symbol):
                    target = p
                    break

            if not target:
                return {
                    "success": False,
                    "error": "no_position",
                    "message": f"未找到 {intent.symbol or '指定品种'} 的持仓",
                }

            # Submit counter-order to close
            side = "sell" if target.size > 0 else "buy"
            try:
                size = self._requested_close_size(intent, abs(target.size))
                size = self._normalise_order_size(size)
            except ValueError as e:
                return {"success": False, "error": "invalid_order", "message": str(e)}

            order = await service.submit_order(
                account_id=account_id,
                symbol=target.symbol,
                order_type="market",
                side=side,
                size=size,
            )

            return {
                "success": True,
                "type": "close_position",
                "order_id": order.id,
                "symbol": target.symbol,
                "size": size,
                "side": side,
                "message": f"平仓订单已提交: {side} {size} {target.symbol}",
            }
        except Exception as e:
            return {"success": False, "error": str(e), "message": f"平仓失败: {e}"}

    @staticmethod
    def _map_order_type(order_type: OrderType) -> str:
        """Map schema OrderType to paper trading order type string."""
        mapping = {
            OrderType.MARKET: "market",
            OrderType.LIMIT: "limit",
            OrderType.STOP: "stop",
            OrderType.STOP_LIMIT: "stop_limit",
        }
        return mapping.get(order_type, "market")
