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
            size = int(intent.quantity or 1)

            order = await service.submit_order(
                account_id=resolved_account_id,
                symbol=intent.symbol or "UNKNOWN",
                order_type=order_type_str,
                side=side,
                size=size,
                price=intent.price,
                stop_price=intent.stop_loss if intent.order_type == OrderType.STOP else None,
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
            # Try to find any connected gateway
            gateway_id = self._find_available_gateway(intent)
            if not gateway_id:
                return {
                    "success": False,
                    "error": "no_gateway",
                    "message": "未找到可用的网关连接。请先在实盘交易页面连接网关。",
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

        # Build CTP order payload
        payload = self._build_order_payload(intent)

        # Send order via ZMQ
        result = self._send_gateway_command(command_endpoint, "place_order", payload)

        if result is not None:
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
        else:
            return {
                "success": False,
                "error": "order_failed",
                "gateway_id": gateway_id,
                "message": "订单提交失败，网关未返回确认。请检查网关连接状态。",
            }

    def _build_order_payload(self, intent: TradingIntent) -> dict[str, Any]:
        """Build the ZMQ order payload for bt_api_py gateway."""
        import uuid as _uuid

        side = "buy" if intent.action == TradeAction.BUY else "sell"
        # For CTP: opening a new position
        offset = "open"
        if intent.action == TradeAction.CLOSE:
            offset = "close"

        payload: dict[str, Any] = {
            "symbol": intent.symbol or "",
            "side": side,
            "size": int(intent.quantity or 1),
            "offset": offset,
            "request_id": _uuid.uuid4().hex[:16],
            "strategy_id": "ai_trading",
        }

        # Price: 0 means market order (gateway uses last tick ± slippage)
        if intent.price and intent.order_type == OrderType.LIMIT:
            payload["price"] = intent.price
        else:
            payload["price"] = 0  # Market order

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
        positions = result if isinstance(result, list) else []
        return {
            "success": True,
            "type": "live_query",
            "gateway_id": gateway_id,
            "positions": positions,
            "message": (f"实盘持仓 {len(positions)} 个品种" if positions else "当前无实盘持仓"),
        }

    async def _close_live_position(
        self, command_endpoint: str, gateway_id: str, intent: TradingIntent
    ) -> dict[str, Any]:
        """Close a live position via gateway."""
        # First query positions to find the target
        positions_result = self._send_gateway_command(command_endpoint, "get_positions", {})
        if not isinstance(positions_result, list):
            return {
                "success": False,
                "error": "query_failed",
                "message": "无法查询持仓信息",
            }

        # Find matching position
        target = None
        for pos in positions_result:
            pos_symbol = pos.get("symbol", "") or pos.get("instrument_id", "")
            if intent.symbol and pos_symbol.upper().startswith(intent.symbol.upper()):
                target = pos
                break

        if not target:
            return {
                "success": False,
                "error": "no_position",
                "message": f"未找到 {intent.symbol or '指定品种'} 的实盘持仓",
            }

        # Determine close direction
        volume = target.get("volume", 0) or target.get("size", 0)
        direction = target.get("direction", "")
        side = "sell" if direction in ("long", "buy", "") else "buy"

        payload = {
            "symbol": target.get("symbol", intent.symbol),
            "side": side,
            "size": abs(int(volume)),
            "price": 0,  # Market order for close
            "offset": "close",
            "strategy_id": "ai_trading",
        }

        result = self._send_gateway_command(command_endpoint, "place_order", payload)
        if result is not None:
            return {
                "success": True,
                "type": "live_close",
                "gateway_id": gateway_id,
                "symbol": intent.symbol,
                "size": abs(int(volume)),
                "side": side,
                "message": f"实盘平仓订单已提交: {side} {abs(int(volume))} {intent.symbol}",
            }
        return {
            "success": False,
            "error": "close_failed",
            "message": "平仓订单提交失败",
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
            for p in positions:
                if intent.symbol and p.symbol.upper() == intent.symbol.upper():
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
            size = abs(target.size)

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
