"""Tests for DirectOrderService - trade execution bridge."""

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.ai_trading import OrderType, TradeAction, TradingIntent
from app.services.direct_order_service import DirectOrderService


class TestDirectOrderServiceMapOrderType:
    """Test order type mapping."""

    def test_market(self):
        assert DirectOrderService._map_order_type(OrderType.MARKET) == "market"

    def test_limit(self):
        assert DirectOrderService._map_order_type(OrderType.LIMIT) == "limit"

    def test_stop(self):
        assert DirectOrderService._map_order_type(OrderType.STOP) == "stop"

    def test_stop_limit(self):
        assert DirectOrderService._map_order_type(OrderType.STOP_LIMIT) == "stop_limit"


class TestDirectOrderServiceBuildOrderPayload:
    """Test ZMQ order payload building."""

    def test_buy_market_order(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=10,
            price=None,
            order_type=OrderType.MARKET,
            confidence=0.9,
        )
        payload = service._build_order_payload(intent)
        assert payload["symbol"] == "rb2501"
        assert payload["side"] == "buy"
        assert payload["size"] == 10
        assert payload["offset"] == "open"
        assert payload["order_type"] == "market"
        assert payload["price"] == 0  # Market order
        assert payload["strategy_id"] == "ai_trading"
        assert "request_id" in payload

    def test_sell_limit_order(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.SELL,
            symbol="i2501",
            quantity=5,
            price=800.0,
            order_type=OrderType.LIMIT,
            confidence=0.9,
        )
        payload = service._build_order_payload(intent)
        assert payload["symbol"] == "i2501"
        assert payload["side"] == "sell"
        assert payload["size"] == 5
        assert payload["price"] == 800.0
        assert payload["order_type"] == "limit"

    def test_limit_order_requires_positive_price(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.SELL,
            symbol="i2501",
            quantity=5,
            price=None,
            order_type=OrderType.LIMIT,
            confidence=0.9,
        )

        with pytest.raises(ValueError, match="limit order requires"):
            service._build_order_payload(intent)

    def test_stop_order_uses_stop_loss_trigger_and_protection_fields(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.SELL,
            symbol="XAUUSD",
            quantity=0.1,
            price=None,
            order_type=OrderType.STOP,
            stop_loss=2290.0,
            take_profit=2250.0,
            confidence=0.9,
        )

        payload = service._build_order_payload(intent, gateway_id="manual:MT5:demo")

        assert payload["order_type"] == "stop"
        assert payload["price"] == 2290.0
        assert payload["stop_price"] == 2290.0
        assert payload["stop_loss"] == 2290.0
        assert payload["sl"] == 2290.0
        assert payload["take_profit"] == 2250.0
        assert payload["tp"] == 2250.0

    def test_stop_order_uses_price_as_trigger_field(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.SELL,
            symbol="AAPL",
            quantity=10,
            price=190.0,
            order_type=OrderType.STOP,
            confidence=0.9,
        )

        payload = service._build_order_payload(intent, gateway_id="manual:IB_WEB:demo")

        assert payload["order_type"] == "stop"
        assert payload["price"] == 190.0
        assert payload["stop_price"] == 190.0

    def test_stop_limit_order_requires_stop_price(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.SELL,
            symbol="AAPL",
            quantity=10,
            price=189.5,
            order_type=OrderType.STOP_LIMIT,
            confidence=0.9,
        )

        with pytest.raises(ValueError, match="stop-limit order requires"):
            service._build_order_payload(intent, gateway_id="manual:IB_WEB:demo")

    def test_stop_limit_order_sets_limit_and_stop_price_fields(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.SELL,
            symbol="AAPL",
            quantity=10,
            price=189.5,
            order_type=OrderType.STOP_LIMIT,
            stop_loss=190.0,
            confidence=0.9,
        )

        payload = service._build_order_payload(intent, gateway_id="manual:IB_WEB:demo")

        assert payload["order_type"] == "stop_limit"
        assert payload["price"] == 189.5
        assert payload["stop_price"] == 190.0

    def test_close_action_sets_offset_close(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="rb2501",
            quantity=10,
            confidence=0.9,
        )
        payload = service._build_order_payload(intent)
        assert payload["offset"] == "close"

    def test_exchange_mapping_binance(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="BTCUSDT",
            exchange="binance",
            quantity=1,
            order_type=OrderType.MARKET,
            confidence=0.9,
        )
        payload = service._build_order_payload(intent)
        assert payload["exchange_id"] == "BINANCE"

    def test_exchange_mapping_okx(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="ETHUSDT",
            exchange="okx",
            quantity=1,
            order_type=OrderType.MARKET,
            confidence=0.9,
        )
        payload = service._build_order_payload(intent)
        assert payload["exchange_id"] == "OKX"

    def test_exchange_mapping_ctp_no_exchange_id(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            exchange="ctp",
            quantity=1,
            order_type=OrderType.MARKET,
            confidence=0.9,
        )
        payload = service._build_order_payload(intent)
        # CTP maps to empty string, so exchange_id should not be set
        assert "exchange_id" not in payload

    def test_no_exchange_no_exchange_id(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=1,
            order_type=OrderType.MARKET,
            confidence=0.9,
        )
        payload = service._build_order_payload(intent)
        assert "exchange_id" not in payload

    def test_live_quantity_is_required(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=None,
            order_type=OrderType.MARKET,
            confidence=0.9,
        )

        with pytest.raises(ValueError, match="quantity"):
            service._build_order_payload(intent)

    def test_fractional_crypto_quantity_is_preserved(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="BTCUSDT",
            exchange="binance",
            quantity=0.1,
            order_type=OrderType.MARKET,
            confidence=0.9,
        )

        payload = service._build_order_payload(intent, gateway_id="manual:BINANCE:spot")

        assert payload["size"] == 0.1

    def test_live_order_rejects_quantity_below_gateway_minimum(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="XAUUSD",
            quantity=0.05,
            order_type=OrderType.MARKET,
            confidence=0.9,
        )
        gateways = {
            "gw1": {
                "runtime": SimpleNamespace(
                    adapter=SimpleNamespace(
                        get_symbol_info=lambda _symbol: {
                            "symbol": "XAUUSD",
                            "volume_min": 0.1,
                            "volume_step": 0.1,
                            "tick_size": 0.01,
                        }
                    )
                )
            }
        }

        with patch.object(service, "_get_gateways_dict", return_value=gateways):
            with pytest.raises(ValueError, match="minimum allowed"):
                service._build_order_payload(intent, gateway_id="gw1")

    def test_live_order_rejects_quantity_step_mismatch_from_gateway_spec(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="XAUUSD",
            quantity=0.15,
            order_type=OrderType.MARKET,
            confidence=0.9,
        )
        gateways = {
            "gw1": {
                "runtime": SimpleNamespace(
                    adapter=SimpleNamespace(
                        get_symbol_info=lambda _symbol: {
                            "symbol": "XAUUSD",
                            "volume_min": 0.1,
                            "volume_step": 0.1,
                            "tick_size": 0.01,
                        }
                    )
                )
            }
        }

        with patch.object(service, "_get_gateways_dict", return_value=gateways):
            with pytest.raises(ValueError, match="size step"):
                service._build_order_payload(intent, gateway_id="gw1")

    def test_live_order_rejects_limit_price_tick_mismatch_from_gateway_spec(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="XAUUSD",
            quantity=0.2,
            price=2331.005,
            order_type=OrderType.LIMIT,
            confidence=0.9,
        )
        gateways = {
            "gw1": {
                "runtime": SimpleNamespace(
                    adapter=SimpleNamespace(
                        get_symbol_info=lambda _symbol: {
                            "symbol": "XAUUSD",
                            "volume_min": 0.1,
                            "volume_step": 0.1,
                            "tick_size": 0.01,
                        }
                    )
                )
            }
        }

        with patch.object(service, "_get_gateways_dict", return_value=gateways):
            with pytest.raises(ValueError, match="tick size"):
                service._build_order_payload(intent, gateway_id="gw1")

    def test_live_order_uses_okx_market_specific_max_size(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="BTC-USDT-SWAP",
            exchange="okx",
            quantity=600,
            order_type=OrderType.MARKET,
            confidence=0.9,
        )
        gateways = {
            "gw1": {
                "config": {
                    "exchange_type": "OKX",
                    "asset_type": "SWAP",
                    "contract_metadata": {
                        "BTC-USDT-SWAP": {
                            "instType": "SWAP",
                            "ctVal": "0.01",
                            "lotSz": "1",
                            "minSz": "1",
                            "maxLmtSz": "1000",
                            "maxMktSz": "500",
                        }
                    },
                }
            }
        }

        with patch.object(service, "_get_gateways_dict", return_value=gateways):
            with pytest.raises(ValueError, match="maximum allowed size 500"):
                service._build_order_payload(intent, gateway_id="gw1")

    def test_live_order_size_validation_accepts_raw_bybit_v5_aliases(self):
        asset_spec = {
            "symbol": "BTCUSDT",
            "minOrderQty": "0.001",
            "maxOrderQty": "100",
            "maxMktOrderQty": "50",
            "qtyStep": "0.001",
        }

        with pytest.raises(ValueError, match="minimum allowed size 0.001"):
            DirectOrderService._validate_live_order_size(
                0.0005,
                asset_spec,
                order_type="market",
            )
        with pytest.raises(ValueError, match="size step 0.001"):
            DirectOrderService._validate_live_order_size(
                0.0015,
                asset_spec,
                order_type="market",
            )
        with pytest.raises(ValueError, match="maximum allowed size 50.0"):
            DirectOrderService._validate_live_order_size(
                60,
                asset_spec,
                order_type="market",
            )

    def test_stop_limit_order_uses_limit_specific_max_size(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="AAPL",
            quantity=150,
            price=189.5,
            order_type=OrderType.STOP_LIMIT,
            stop_loss=190.0,
            confidence=0.9,
        )
        gateways = {
            "manual:IB_WEB:demo": {
                "config": {
                    "contract_metadata": {
                        "AAPL": {
                            "limit_max_order_size": 100,
                            "max_order_size": 200,
                        }
                    }
                }
            }
        }

        with patch.object(service, "_get_gateways_dict", return_value=gateways):
            with pytest.raises(ValueError, match="maximum allowed size 100"):
                service._build_order_payload(intent, gateway_id="manual:IB_WEB:demo")

    def test_live_order_uses_raw_okx_min_size_and_lot_step(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="BTC-USDT-SWAP",
            exchange="okx",
            quantity=0.5,
            order_type=OrderType.LIMIT,
            price=60000.0,
            confidence=0.9,
        )
        gateways = {
            "gw1": {
                "config": {
                    "exchange_type": "OKX",
                    "asset_type": "SWAP",
                    "contract_metadata": {
                        "BTC-USDT-SWAP": {
                            "instType": "SWAP",
                            "ctVal": "0.01",
                            "lotSz": "1",
                            "minSz": "1",
                            "maxLmtSz": "1000",
                        }
                    },
                }
            }
        }

        with patch.object(service, "_get_gateways_dict", return_value=gateways):
            with pytest.raises(ValueError, match="minimum allowed size 1"):
                service._build_order_payload(intent, gateway_id="gw1")

    def test_ctp_fractional_quantity_is_rejected(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="IF2609",
            exchange="ctp",
            quantity=1.5,
            order_type=OrderType.MARKET,
            confidence=0.9,
        )

        with pytest.raises(ValueError, match="integer lot"):
            service._build_order_payload(intent, gateway_id="manual:CTP:089763")

    def test_ctp_fractional_quantity_is_rejected_from_gateway_config(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="IF2609",
            quantity=1.5,
            order_type=OrderType.MARKET,
            confidence=0.9,
        )
        gateways = {
            "gw1": {
                "config": SimpleNamespace(exchange_type="CTP", asset_type="FUTURE"),
            }
        }

        with patch.object(service, "_get_gateways_dict", return_value=gateways):
            with pytest.raises(ValueError, match="integer lot"):
                service._build_order_payload(intent, gateway_id="gw1")

    def test_ctp_stop_order_is_rejected_before_gateway_send(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.SELL,
            symbol="IF2609",
            exchange="ctp",
            quantity=1,
            order_type=OrderType.STOP,
            stop_loss=4900.0,
            confidence=0.9,
        )

        with pytest.raises(ValueError, match="CTP gateway supports only"):
            service._build_order_payload(intent, gateway_id="manual:CTP:089763")

    def test_ctp_stop_order_is_rejected_from_gateway_config(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.SELL,
            symbol="IF2609",
            quantity=1,
            order_type=OrderType.STOP,
            stop_loss=4900.0,
            confidence=0.9,
        )
        gateways = {
            "gw1": {
                "exchange_type": "CTP",
                "config": SimpleNamespace(asset_type="FUTURE"),
            }
        }

        with patch.object(service, "_get_gateways_dict", return_value=gateways):
            with pytest.raises(ValueError, match="CTP gateway supports only"):
                service._build_order_payload(intent, gateway_id="gw1")

    def test_mt5_stop_limit_order_is_rejected_before_gateway_send(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="XAUUSD",
            exchange="mt5",
            quantity=0.1,
            price=2320.0,
            order_type=OrderType.STOP_LIMIT,
            stop_loss=2310.0,
            confidence=0.9,
        )

        with pytest.raises(ValueError, match="MT5 gateway does not support"):
            service._build_order_payload(intent, gateway_id="manual:MT5:demo")

    def test_mt5_stop_limit_order_is_rejected_from_gateway_config(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="XAUUSD",
            quantity=0.1,
            price=2320.0,
            order_type=OrderType.STOP_LIMIT,
            stop_loss=2310.0,
            confidence=0.9,
        )
        gateways = {
            "gw1": {
                "config": SimpleNamespace(exchange_type="MT5", asset_type="FOREX"),
            }
        }

        with patch.object(service, "_get_gateways_dict", return_value=gateways):
            with pytest.raises(ValueError, match="MT5 gateway does not support"):
                service._build_order_payload(intent, gateway_id="gw1")

    def test_binance_stop_order_is_rejected_until_adapter_mapping_exists(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.SELL,
            symbol="BTCUSDT",
            exchange="binance",
            quantity=0.1,
            order_type=OrderType.STOP,
            stop_loss=50000.0,
            confidence=0.9,
        )

        with pytest.raises(ValueError, match="conditional orders are not supported"):
            service._build_order_payload(intent, gateway_id="manual:BINANCE:spot")

    def test_binance_market_order_rejects_attached_stop_loss_before_gateway_send(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="BTCUSDT",
            exchange="binance",
            quantity=0.1,
            order_type=OrderType.MARKET,
            stop_loss=50000.0,
            confidence=0.9,
        )

        with pytest.raises(ValueError, match="attached stop-loss/take-profit"):
            service._build_order_payload(intent, gateway_id="manual:BINANCE:spot")

    def test_okx_limit_order_rejects_attached_take_profit_from_gateway_config(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.SELL,
            symbol="BTC-USDT-SWAP",
            quantity=1,
            price=62000.0,
            order_type=OrderType.LIMIT,
            take_profit=61000.0,
            confidence=0.9,
        )
        gateways = {
            "gw1": {
                "config": SimpleNamespace(exchange_type="OKX", asset_type="SWAP"),
            }
        }

        with patch.object(service, "_get_gateways_dict", return_value=gateways):
            with pytest.raises(ValueError, match="attached stop-loss/take-profit"):
                service._build_order_payload(intent, gateway_id="gw1")

    def test_mt5_market_order_keeps_attached_stop_loss_take_profit_fields(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="XAUUSD",
            exchange="mt5",
            quantity=0.1,
            order_type=OrderType.MARKET,
            stop_loss=2290.0,
            take_profit=2320.0,
            confidence=0.9,
        )

        payload = service._build_order_payload(intent, gateway_id="manual:MT5:demo")

        assert payload["order_type"] == "market"
        assert payload["stop_loss"] == 2290.0
        assert payload["sl"] == 2290.0
        assert payload["take_profit"] == 2320.0
        assert payload["tp"] == 2320.0

    def test_gateway_order_result_rejects_error_statuses(self):
        assert DirectOrderService._gateway_order_result_ok(
            {"status": "error", "error": "limit order requires price"}
        ) == (False, "limit order requires price")
        assert DirectOrderService._gateway_order_result_ok(
            {"order_status": "rejected", "message": "exchange rejected"}
        ) == (False, "exchange rejected")

    def test_gateway_order_result_rejects_nonzero_retcode(self):
        ok, message = DirectOrderService._gateway_order_result_ok(
            {"retcode": 10030, "comment": "Invalid filling mode"}
        )

        assert ok is False
        assert message == "Invalid filling mode"

    def test_gateway_order_result_accepts_mt5_success_retcodes(self):
        assert DirectOrderService._gateway_order_result_ok(
            {"status": "completed", "retcode": 10009, "success": False, "order_id": 123}
        ) == (True, None)
        assert DirectOrderService._gateway_order_result_ok(
            {"retcode": 10008, "comment": "Request executed", "order_id": 456}
        ) == (True, None)

    def test_gateway_order_result_rejects_ambiguous_empty_or_false_payloads(self):
        assert DirectOrderService._gateway_order_result_ok(False) == (
            False,
            "invalid gateway order response",
        )
        assert DirectOrderService._gateway_order_result_ok("") == (
            False,
            "empty gateway order response",
        )
        assert DirectOrderService._gateway_order_result_ok([]) == (
            False,
            "invalid gateway order response",
        )
        assert DirectOrderService._gateway_order_result_ok({}) == (
            False,
            "empty gateway order response",
        )
        assert DirectOrderService._gateway_order_result_ok({"comment": "queued"}) == (
            False,
            "invalid gateway order response",
        )

    def test_gateway_order_result_accepts_order_identity_without_status(self):
        assert DirectOrderService._gateway_order_result_ok({"order_id": "live-123"}) == (
            True,
            None,
        )
        assert DirectOrderService._gateway_order_result_ok(
            {"newClientOrderId": "binance-client-123"}
        ) == (True, None)
        assert DirectOrderService._gateway_order_result_ok({"orderLinkId": "bybit-client-123"}) == (
            True,
            None,
        )
        assert DirectOrderService._gateway_order_result_ok("live-123") == (True, None)

    def test_gateway_order_result_accepts_bybit_v5_ret_code_success(self):
        assert DirectOrderService._gateway_order_result_ok(
            {
                "retCode": 0,
                "retMsg": "OK",
                "result": {"orderId": "bybit-123", "orderLinkId": "client-123"},
            }
        ) == (True, None)
        assert DirectOrderService._gateway_order_result_ok(
            {
                "status": "ok",
                "data": {
                    "retCode": "0",
                    "retMsg": "OK",
                    "result": {"orderId": "bybit-456"},
                },
            }
        ) == (True, None)

    def test_gateway_order_result_rejects_bybit_v5_ret_code_error(self):
        assert DirectOrderService._gateway_order_result_ok(
            {
                "retCode": 10001,
                "retMsg": "position idx not match position mode",
                "result": {},
            }
        ) == (False, "position idx not match position mode")
        assert (
            DirectOrderService._gateway_result_error_message(
                {
                    "status": "ok",
                    "data": {
                        "retCode": 10001,
                        "retMsg": "request parameter error",
                        "result": {},
                    },
                }
            )
            == "request parameter error"
        )

    def test_gateway_order_result_accepts_okx_order_aliases(self):
        assert DirectOrderService._gateway_order_result_ok(
            {"ordId": "okx-123", "clOrdId": "client-123", "sCode": "0"}
        ) == (True, None)
        assert DirectOrderService._gateway_order_result_ok(
            {
                "code": "0",
                "data": [
                    {
                        "ordId": "okx-456",
                        "clOrdId": "client-456",
                        "sCode": "0",
                        "sMsg": "",
                    }
                ],
            }
        ) == (True, None)

    def test_gateway_order_result_rejects_okx_service_error(self):
        assert DirectOrderService._gateway_order_result_ok(
            {"ordId": "okx-123", "sCode": "51008", "sMsg": "Insufficient balance"}
        ) == (False, "Insufficient balance")
        assert DirectOrderService._gateway_order_result_ok(
            {
                "code": "0",
                "data": [
                    {
                        "ordId": "",
                        "sCode": "51000",
                        "sMsg": "Parameter error",
                    }
                ],
            }
        ) == (False, "Parameter error")

    def test_gateway_order_result_rejects_generic_nonzero_code(self):
        assert DirectOrderService._gateway_order_result_ok(
            {"code": "51008", "message": "Insufficient balance"}
        ) == (False, "Insufficient balance")

    def test_gateway_order_result_rejects_nested_error_payload(self):
        assert DirectOrderService._gateway_order_result_ok(
            {
                "status": "ok",
                "data": {"status": "error", "error": "exchange rejected"},
            }
        ) == (False, "exchange rejected")
        assert DirectOrderService._gateway_order_result_ok(
            {
                "status": "success",
                "result": {"retcode": 10030, "comment": "Invalid filling mode"},
            }
        ) == (False, "Invalid filling mode")

    def test_send_gateway_command_preserves_runtime_error_payload(self, monkeypatch):
        class FakeSocket:
            def setsockopt(self, *_args):
                return None

            def connect(self, _endpoint):
                return None

            def send(self, _payload):
                return None

            def recv(self):
                return b'{"request_id":"req-1","status":"error","error":"adapter not connected"}'

            def close(self):
                return None

        class FakeContext:
            @staticmethod
            def instance():
                return FakeContext()

            def socket(self, _socket_type):
                return FakeSocket()

        fake_zmq = SimpleNamespace(
            Context=FakeContext,
            DEALER=1,
            IDENTITY=2,
            SNDTIMEO=3,
            RCVTIMEO=4,
        )
        monkeypatch.setitem(sys.modules, "zmq", fake_zmq)

        result = DirectOrderService._send_gateway_command("tcp://localhost:5555", "place_order", {})

        assert result == {
            "request_id": "req-1",
            "status": "error",
            "error": "adapter not connected",
        }


class TestDirectOrderServicePaperTrade:
    """Test paper trade execution."""

    @pytest.mark.asyncio
    async def test_query_action(self):
        """QUERY action should query positions."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.QUERY,
            confidence=0.9,
        )

        mock_paper_service = AsyncMock()
        mock_paper_service.list_accounts = AsyncMock(return_value=([MagicMock(id="acc1")], 1))
        mock_paper_service.list_positions = AsyncMock(return_value=([], 0))

        with patch(
            "app.services.paper_trading_service.PaperTradingService",
            return_value=mock_paper_service,
        ):
            result = await service.execute_paper_trade(intent, user_id="user1")
            assert result["success"] is True
            assert result["type"] == "query"

    @pytest.mark.asyncio
    async def test_query_action_uses_paper_service_limit_offset_signature(self):
        """Direct paper queries must call the real PaperTradingService signature."""
        service = DirectOrderService()
        intent = TradingIntent(action=TradeAction.QUERY, confidence=0.9)

        class StrictPaperService:
            async def list_accounts(self, user_id, limit=20, offset=0):
                assert user_id == "user1"
                assert limit == 1
                assert offset == 0
                return [SimpleNamespace(id="acc1")], 1

            async def list_positions(self, filters, limit=20, offset=0):
                assert filters == {"account_id": "acc1"}
                assert limit == 50
                assert offset == 0
                return [
                    SimpleNamespace(
                        symbol="BTCUSDT",
                        size=0.25,
                        avg_price=50000.0,
                        unrealized_pnl=125.0,
                    )
                ], 1

        with patch(
            "app.services.paper_trading_service.PaperTradingService",
            return_value=StrictPaperService(),
        ):
            result = await service.execute_paper_trade(intent, user_id="user1")

        assert result["success"] is True
        assert result["positions"] == [
            {
                "symbol": "BTCUSDT",
                "size": 0.25,
                "avg_price": 50000.0,
                "unrealized_pnl": 125.0,
            }
        ]

    @pytest.mark.asyncio
    async def test_query_action_reports_paper_position_query_error(self):
        service = DirectOrderService()
        intent = TradingIntent(action=TradeAction.QUERY, confidence=0.9)

        class FailingPaperService:
            async def list_accounts(self, user_id, limit=20, offset=0):
                return [SimpleNamespace(id="acc1")], 1

            async def list_positions(self, filters, limit=20, offset=0):
                raise RuntimeError("paper db unavailable")

        with patch(
            "app.services.paper_trading_service.PaperTradingService",
            return_value=FailingPaperService(),
        ):
            result = await service.execute_paper_trade(intent, user_id="user1")

        assert result["success"] is False
        assert result["error"] == "paper db unavailable"
        assert result["positions"] == []

    @pytest.mark.asyncio
    async def test_unsupported_action(self):
        """Unsupported actions return error."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CANCEL,
            confidence=0.9,
        )

        mock_paper_service = AsyncMock()
        mock_paper_service.list_accounts = AsyncMock(return_value=([MagicMock(id="acc1")], 1))

        with patch(
            "app.services.paper_trading_service.PaperTradingService",
            return_value=mock_paper_service,
        ):
            result = await service.execute_paper_trade(intent, user_id="user1")
            assert result["success"] is False
            assert "Unsupported action" in result["error"]

    @pytest.mark.asyncio
    async def test_buy_order_success(self):
        """Successful buy order execution."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=10,
            price=3500.0,
            order_type=OrderType.LIMIT,
            confidence=0.9,
        )

        mock_order = MagicMock()
        mock_order.id = "order123"
        mock_order.status = "submitted"

        mock_paper_service = AsyncMock()
        mock_paper_service.list_accounts = AsyncMock(return_value=([MagicMock(id="acc1")], 1))
        mock_paper_service.submit_order = AsyncMock(return_value=mock_order)

        with patch(
            "app.services.paper_trading_service.PaperTradingService",
            return_value=mock_paper_service,
        ):
            result = await service.execute_paper_trade(intent, user_id="user1")
            assert result["success"] is True
            assert result["type"] == "paper_trade"
            assert result["order_id"] == "order123"
            assert result["symbol"] == "rb2501"
            assert result["quantity"] == 10
            assert result["side"] == "buy"

    @pytest.mark.asyncio
    async def test_fractional_paper_quantity_is_preserved(self):
        """Paper trades must not truncate fractional crypto quantities."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="BTC/USDT",
            quantity=0.25,
            price=50000.0,
            order_type=OrderType.LIMIT,
            confidence=0.9,
        )

        mock_order = MagicMock()
        mock_order.id = "order123"
        mock_order.status = "submitted"

        mock_paper_service = AsyncMock()
        mock_paper_service.list_accounts = AsyncMock(return_value=([MagicMock(id="acc1")], 1))
        mock_paper_service.submit_order = AsyncMock(return_value=mock_order)

        with patch(
            "app.services.paper_trading_service.PaperTradingService",
            return_value=mock_paper_service,
        ):
            result = await service.execute_paper_trade(intent, user_id="user1")

        assert result["success"] is True
        assert result["quantity"] == pytest.approx(0.25)
        assert mock_paper_service.submit_order.await_args.kwargs["size"] == pytest.approx(0.25)

    @pytest.mark.asyncio
    async def test_sell_order_success(self):
        """Successful sell order execution."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.SELL,
            symbol="BTCUSDT",
            quantity=1,
            price=50000.0,
            order_type=OrderType.LIMIT,
            confidence=0.9,
        )

        mock_order = MagicMock()
        mock_order.id = "order456"
        mock_order.status = "submitted"

        mock_paper_service = AsyncMock()
        mock_paper_service.list_accounts = AsyncMock(return_value=([MagicMock(id="acc1")], 1))
        mock_paper_service.submit_order = AsyncMock(return_value=mock_order)

        with patch(
            "app.services.paper_trading_service.PaperTradingService",
            return_value=mock_paper_service,
        ):
            result = await service.execute_paper_trade(intent, user_id="user1")
            assert result["success"] is True
            assert result["side"] == "sell"

    @pytest.mark.asyncio
    async def test_value_error_handled(self):
        """ValueError from paper trading service is handled gracefully."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=10,
            confidence=0.9,
        )

        mock_paper_service = AsyncMock()
        mock_paper_service.list_accounts = AsyncMock(return_value=([MagicMock(id="acc1")], 1))
        mock_paper_service.submit_order = AsyncMock(side_effect=ValueError("Insufficient balance"))

        with patch(
            "app.services.paper_trading_service.PaperTradingService",
            return_value=mock_paper_service,
        ):
            result = await service.execute_paper_trade(intent, user_id="user1")
            assert result["success"] is False
            assert "Insufficient balance" in result["error"]

    @pytest.mark.asyncio
    async def test_generic_exception_handled(self):
        """Generic exceptions are handled gracefully."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=10,
            confidence=0.9,
        )

        mock_paper_service = AsyncMock()
        mock_paper_service.list_accounts = AsyncMock(
            side_effect=RuntimeError("DB connection failed")
        )

        with patch(
            "app.services.paper_trading_service.PaperTradingService",
            return_value=mock_paper_service,
        ):
            result = await service.execute_paper_trade(intent, user_id="user1")
            assert result["success"] is False
            assert "DB connection failed" in result["error"]

    @pytest.mark.asyncio
    async def test_creates_account_when_none_exists(self):
        """Creates a new account when user has no active accounts."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.QUERY,
            confidence=0.9,
        )

        mock_account = MagicMock()
        mock_account.id = "new_acc"

        mock_paper_service = AsyncMock()
        mock_paper_service.list_accounts = AsyncMock(return_value=([], 0))
        mock_paper_service.create_account = AsyncMock(return_value=mock_account)
        mock_paper_service.list_positions = AsyncMock(return_value=([], 0))

        with patch(
            "app.services.paper_trading_service.PaperTradingService",
            return_value=mock_paper_service,
        ):
            result = await service.execute_paper_trade(intent, user_id="user1")
            assert result["success"] is True
            mock_paper_service.create_account.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_position_success(self):
        """Close position submits counter-order."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="rb2501",
            confidence=0.9,
        )

        mock_position = MagicMock()
        mock_position.symbol = "RB2501"
        mock_position.size = 10

        mock_order = MagicMock()
        mock_order.id = "close_order"

        mock_paper_service = AsyncMock()
        mock_paper_service.list_accounts = AsyncMock(return_value=([MagicMock(id="acc1")], 1))
        mock_paper_service.list_positions = AsyncMock(return_value=([mock_position], 1))
        mock_paper_service.submit_order = AsyncMock(return_value=mock_order)

        with patch(
            "app.services.paper_trading_service.PaperTradingService",
            return_value=mock_paper_service,
        ):
            result = await service.execute_paper_trade(intent, user_id="user1")
            assert result["success"] is True
            assert result["type"] == "close_position"
            assert result["side"] == "sell"
            assert result["size"] == 10

    @pytest.mark.asyncio
    async def test_close_position_uses_paper_service_limit_offset_signature(self):
        """Direct paper closes must use the real list_positions arguments."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="BTC/USDT",
            quantity=0.1,
            confidence=0.9,
        )
        submitted: dict[str, object] = {}

        class StrictPaperService:
            async def list_accounts(self, user_id, limit=20, offset=0):
                assert user_id == "user1"
                assert limit == 1
                assert offset == 0
                return [SimpleNamespace(id="acc1")], 1

            async def list_positions(self, filters, limit=20, offset=0):
                assert filters == {"account_id": "acc1"}
                assert limit == 50
                assert offset == 0
                return [SimpleNamespace(symbol="BTCUSDT", size=0.25)], 1

            async def submit_order(self, **kwargs):
                submitted.update(kwargs)
                return SimpleNamespace(id="close_order")

        with patch(
            "app.services.paper_trading_service.PaperTradingService",
            return_value=StrictPaperService(),
        ):
            result = await service.execute_paper_trade(intent, user_id="user1")

        assert result["success"] is True
        assert result["side"] == "sell"
        assert result["size"] == pytest.approx(0.1)
        assert submitted == {
            "account_id": "acc1",
            "symbol": "BTCUSDT",
            "order_type": "market",
            "side": "sell",
            "size": 0.1,
        }

    @pytest.mark.asyncio
    async def test_close_position_respects_explicit_quantity(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="rb2501",
            quantity=3,
            confidence=0.9,
        )

        mock_position = MagicMock()
        mock_position.symbol = "RB2501"
        mock_position.size = 10
        mock_order = MagicMock()
        mock_order.id = "close_order"

        mock_paper_service = AsyncMock()
        mock_paper_service.list_accounts = AsyncMock(return_value=([MagicMock(id="acc1")], 1))
        mock_paper_service.list_positions = AsyncMock(return_value=([mock_position], 1))
        mock_paper_service.submit_order = AsyncMock(return_value=mock_order)

        with patch(
            "app.services.paper_trading_service.PaperTradingService",
            return_value=mock_paper_service,
        ):
            result = await service.execute_paper_trade(intent, user_id="user1")

        assert result["success"] is True
        assert result["size"] == 3
        assert mock_paper_service.submit_order.await_args.kwargs["size"] == 3

    @pytest.mark.asyncio
    async def test_close_position_rejects_quantity_above_position(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="rb2501",
            quantity=11,
            confidence=0.9,
        )

        mock_position = MagicMock()
        mock_position.symbol = "RB2501"
        mock_position.size = 10

        mock_paper_service = AsyncMock()
        mock_paper_service.list_accounts = AsyncMock(return_value=([MagicMock(id="acc1")], 1))
        mock_paper_service.list_positions = AsyncMock(return_value=([mock_position], 1))
        mock_paper_service.submit_order = AsyncMock()

        with patch(
            "app.services.paper_trading_service.PaperTradingService",
            return_value=mock_paper_service,
        ):
            result = await service.execute_paper_trade(intent, user_id="user1")

        assert result["success"] is False
        assert result["error"] == "invalid_order"
        assert "exceeds available" in result["message"]
        mock_paper_service.submit_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_close_position_matches_compact_exchange_symbol(self):
        """Paper close should use the same symbol aliases as live portfolio risk."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="BTC/USDT",
            confidence=0.9,
        )

        mock_position = MagicMock()
        mock_position.symbol = "BTCUSDT"
        mock_position.size = 0.25

        mock_order = MagicMock()
        mock_order.id = "close_order"

        mock_paper_service = AsyncMock()
        mock_paper_service.list_accounts = AsyncMock(return_value=([MagicMock(id="acc1")], 1))
        mock_paper_service.list_positions = AsyncMock(return_value=([mock_position], 1))
        mock_paper_service.submit_order = AsyncMock(return_value=mock_order)

        with patch(
            "app.services.paper_trading_service.PaperTradingService",
            return_value=mock_paper_service,
        ):
            result = await service.execute_paper_trade(intent, user_id="user1")

        assert result["success"] is True
        assert result["symbol"] == "BTCUSDT"
        mock_paper_service.submit_order.assert_awaited_once()
        assert mock_paper_service.submit_order.await_args.kwargs["symbol"] == "BTCUSDT"

    @pytest.mark.asyncio
    async def test_close_position_rejects_hedged_symbol_without_requested_side(self):
        """Paper close should match live close ambiguity checks for hedged symbols."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="BTCUSDT",
            confidence=0.9,
        )

        long_position = SimpleNamespace(symbol="BTCUSDT", size=0.25, position_side="long")
        short_position = SimpleNamespace(symbol="BTCUSDT", size=-0.2, position_side="short")

        mock_paper_service = AsyncMock()
        mock_paper_service.list_accounts = AsyncMock(return_value=([MagicMock(id="acc1")], 1))
        mock_paper_service.list_positions = AsyncMock(
            return_value=([long_position, short_position], 2)
        )
        mock_paper_service.submit_order = AsyncMock()

        with patch(
            "app.services.paper_trading_service.PaperTradingService",
            return_value=mock_paper_service,
        ):
            result = await service.execute_paper_trade(intent, user_id="user1")

        assert result["success"] is False
        assert result["error"] == "ambiguous_position"
        assert "请指定合约或方向" in result["message"]
        mock_paper_service.submit_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_close_position_uses_explicit_position_side_for_hedged_symbol(self):
        """Paper close-short intents should close only the short leg."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="BTCUSDT",
            quantity=0.1,
            confidence=0.9,
            additional_params={"position_side": "short"},
        )

        long_position = SimpleNamespace(symbol="BTCUSDT", size=0.25, position_side="long")
        short_position = SimpleNamespace(symbol="BTCUSDT", size=-0.2, position_side="short")
        mock_order = SimpleNamespace(id="close_short")

        mock_paper_service = AsyncMock()
        mock_paper_service.list_accounts = AsyncMock(return_value=([MagicMock(id="acc1")], 1))
        mock_paper_service.list_positions = AsyncMock(
            return_value=([long_position, short_position], 2)
        )
        mock_paper_service.submit_order = AsyncMock(return_value=mock_order)

        with patch(
            "app.services.paper_trading_service.PaperTradingService",
            return_value=mock_paper_service,
        ):
            result = await service.execute_paper_trade(intent, user_id="user1")

        assert result["success"] is True
        assert result["symbol"] == "BTCUSDT"
        assert result["side"] == "buy"
        assert result["size"] == pytest.approx(0.1)
        assert mock_paper_service.submit_order.await_args.kwargs == {
            "account_id": "acc1",
            "symbol": "BTCUSDT",
            "order_type": "market",
            "side": "buy",
            "size": 0.1,
        }

    @pytest.mark.asyncio
    async def test_close_position_not_found(self):
        """Close position fails when no matching position exists."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="i2501",
            confidence=0.9,
        )

        mock_paper_service = AsyncMock()
        mock_paper_service.list_accounts = AsyncMock(return_value=([MagicMock(id="acc1")], 1))
        mock_paper_service.list_positions = AsyncMock(return_value=([], 0))

        with patch(
            "app.services.paper_trading_service.PaperTradingService",
            return_value=mock_paper_service,
        ):
            result = await service.execute_paper_trade(intent, user_id="user1")
            assert result["success"] is False
            assert "no_position" in result["error"]


class TestDirectOrderServiceLiveTrade:
    """Test live trade execution."""

    @pytest.mark.asyncio
    async def test_no_gateway_available(self):
        """Returns error when no gateway is connected."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=1,
            confidence=0.9,
        )

        with patch.object(service, "_find_available_gateway", return_value=None):
            result = await service.execute_live_trade(intent, user_id="user1")
            assert result["success"] is False
            assert result["error"] == "no_gateway"

    @pytest.mark.asyncio
    async def test_live_trade_requires_explicit_gateway_id(self):
        """Live orders must not auto-select the first connected gateway/account."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=1,
            confidence=0.9,
        )

        with patch.object(
            service, "_find_available_gateway", return_value="manual:CTP:real"
        ) as find:
            result = await service.execute_live_trade(intent, user_id="user1")

        assert result["success"] is False
        assert result["error"] == "no_gateway"
        assert "显式选择 gateway_id" in result["message"]
        find.assert_not_called()

    @pytest.mark.asyncio
    async def test_gateway_not_found(self):
        """Returns error when specified gateway is not connected."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=1,
            confidence=0.9,
        )

        with patch.object(service, "_get_gateway_command_endpoint", return_value=None):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="invalid_gw"
            )
            assert result["success"] is False
            assert result["error"] == "gateway_not_found"

    @pytest.mark.asyncio
    async def test_unsupported_action_live(self):
        """Unsupported actions return error for live trading."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CANCEL,
            confidence=0.9,
        )

        with patch.object(
            service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
        ):
            result = await service.execute_live_trade(intent, user_id="user1", gateway_id="gw1")
            assert result["success"] is False
            assert "unsupported_action" in result["error"]

    @pytest.mark.asyncio
    async def test_live_buy_success(self):
        """Successful live buy order."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=5,
            price=3500.0,
            order_type=OrderType.LIMIT,
            confidence=0.9,
        )

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(
                service, "_send_gateway_command", return_value={"order_id": "live_123"}
            ) as send_cmd,
        ):
            result = await service.execute_live_trade(intent, user_id="user1", gateway_id="gw1")
            assert result["success"] is True
            assert result["type"] == "live_trade"
            assert result["gateway_id"] == "gw1"
            _, command, payload = send_cmd.call_args.args
            assert command == "place_order"
            assert payload["order_type"] == "limit"
            assert payload["price"] == 3500.0

    @pytest.mark.asyncio
    async def test_live_order_failed(self):
        """Live order fails when gateway returns None."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=5,
            confidence=0.9,
        )

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(service, "_send_gateway_command", return_value=None),
        ):
            result = await service.execute_live_trade(intent, user_id="user1", gateway_id="gw1")
            assert result["success"] is False
            assert result["error"] == "order_failed"

    @pytest.mark.asyncio
    async def test_live_order_rejects_false_gateway_payload(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=5,
            confidence=0.9,
        )

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(service, "_send_gateway_command", return_value=False),
        ):
            result = await service.execute_live_trade(intent, user_id="user1", gateway_id="gw1")

        assert result["success"] is False
        assert result["error"] == "order_failed"
        assert result["order_result"] is False
        assert result["message"] == "invalid gateway order response"

    @pytest.mark.asyncio
    async def test_live_order_rejects_gateway_error_payload(self):
        """Live order fails when adapter returns an error payload inside ok data."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="EURUSD",
            quantity=0.1,
            price=None,
            order_type=OrderType.MARKET,
            confidence=0.9,
        )

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(
                service,
                "_send_gateway_command",
                return_value={"status": "error", "error": "market closed"},
            ),
        ):
            result = await service.execute_live_trade(intent, user_id="user1", gateway_id="gw1")

        assert result["success"] is False
        assert result["error"] == "order_failed"
        assert result["order_result"]["status"] == "error"
        assert result["message"] == "market closed"

    @pytest.mark.asyncio
    async def test_live_order_accepts_mt5_completed_retcode(self):
        """MT5 returns non-zero success retcodes for placed/completed orders."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="EURUSD",
            quantity=0.1,
            order_type=OrderType.MARKET,
            confidence=0.9,
        )

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(
                service,
                "_send_gateway_command",
                return_value={
                    "status": "completed",
                    "retcode": 10009,
                    "success": False,
                    "order_id": 123456,
                },
            ),
        ):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="manual:MT5:demo"
            )

        assert result["success"] is True
        assert result["order_result"]["retcode"] == 10009

    @pytest.mark.asyncio
    async def test_live_order_rejects_unsupported_type_before_gateway_send(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="XAUUSD",
            exchange="mt5",
            quantity=0.1,
            price=2320.0,
            order_type=OrderType.STOP_LIMIT,
            stop_loss=2310.0,
            confidence=0.9,
        )

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(service, "_send_gateway_command") as send_cmd,
        ):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="manual:MT5:demo"
            )

        assert result["success"] is False
        assert result["error"] == "invalid_order"
        assert "stop-limit" in result["message"]
        send_cmd.assert_not_called()

    @pytest.mark.asyncio
    async def test_live_order_rejects_unsupported_type_from_gateway_config_before_send(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.SELL,
            symbol="IF2609",
            quantity=1,
            order_type=OrderType.STOP,
            stop_loss=4900.0,
            confidence=0.9,
        )
        gateways = {
            "gw1": {
                "config": SimpleNamespace(
                    exchange_type="CTP",
                    asset_type="FUTURE",
                    command_endpoint="tcp://localhost:5555",
                ),
            }
        }

        with (
            patch.object(service, "_get_gateways_dict", return_value=gateways),
            patch.object(service, "_send_gateway_command") as send_cmd,
        ):
            result = await service.execute_live_trade(intent, user_id="user1", gateway_id="gw1")

        assert result["success"] is False
        assert result["error"] == "invalid_order"
        assert "CTP gateway supports only" in result["message"]
        send_cmd.assert_not_called()

    @pytest.mark.asyncio
    async def test_live_order_rejects_unsupported_attached_protection_before_send(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="BTC-USDT-SWAP",
            exchange="okx",
            quantity=1,
            order_type=OrderType.MARKET,
            stop_loss=58000.0,
            confidence=0.9,
        )

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(service, "_send_gateway_command") as send_cmd,
        ):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="manual:OKX:swap"
            )

        assert result["success"] is False
        assert result["error"] == "invalid_order"
        assert "attached stop-loss/take-profit" in result["message"]
        send_cmd.assert_not_called()

    @pytest.mark.asyncio
    async def test_live_order_requires_explicit_quantity_before_gateway_send(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="XAUUSD",
            exchange="mt5",
            quantity=None,
            order_type=OrderType.MARKET,
            confidence=0.9,
        )

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(service, "_send_gateway_command") as send_cmd,
        ):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="manual:MT5:demo"
            )

        assert result["success"] is False
        assert result["error"] == "invalid_order"
        assert "quantity" in result["message"]
        send_cmd.assert_not_called()

    @pytest.mark.asyncio
    async def test_live_query_positions(self):
        """Query positions from live gateway."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.QUERY,
            confidence=0.9,
        )

        positions = [{"symbol": "rb2501", "size": 10}]
        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(service, "_send_gateway_command", return_value=positions),
        ):
            result = await service.execute_live_trade(intent, user_id="user1", gateway_id="gw1")
            assert result["success"] is True
            assert result["type"] == "live_query"
            assert len(result["positions"]) == 1

    @pytest.mark.asyncio
    async def test_live_query_positions_accepts_wrapped_payload(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.QUERY,
            confidence=0.9,
        )

        positions = [{"symbol": "BTCUSDT", "size": 0.25}]
        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(service, "_send_gateway_command", return_value={"positions": positions}),
        ):
            result = await service.execute_live_trade(intent, user_id="user1", gateway_id="gw1")

        assert result["success"] is True
        assert result["positions"] == positions

    @pytest.mark.asyncio
    async def test_live_query_positions_hides_explicit_zero_position(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.QUERY,
            confidence=0.9,
        )

        positions = [
            "not-a-position-row",
            {"symbol": "rb2501", "size": 0, "volume": 2, "direction": "long"},
            {"symbol": "i2501", "volume": 1, "direction": "short"},
        ]
        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(service, "_send_gateway_command", return_value={"positions": positions}),
        ):
            result = await service.execute_live_trade(intent, user_id="user1", gateway_id="gw1")

        assert result["success"] is True
        assert result["positions"] == [{"symbol": "i2501", "volume": 1, "direction": "short"}]
        assert result["message"] == "实盘持仓 1 个品种"

    @pytest.mark.asyncio
    async def test_live_query_positions_rejects_gateway_error_payload(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.QUERY,
            confidence=0.9,
        )

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(
                service,
                "_send_gateway_command",
                return_value={"status": "error", "error": "gateway auth expired"},
            ),
        ):
            result = await service.execute_live_trade(intent, user_id="user1", gateway_id="gw1")

        assert result["success"] is False
        assert result["error"] == "query_failed"
        assert result["positions"] == []
        assert result["message"] == "gateway auth expired"

    @pytest.mark.asyncio
    async def test_live_query_positions_rejects_missing_gateway_response(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.QUERY,
            confidence=0.9,
        )

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(service, "_send_gateway_command", return_value=None),
        ):
            result = await service.execute_live_trade(intent, user_id="user1", gateway_id="gw1")

        assert result["success"] is False
        assert result["error"] == "query_failed"
        assert result["positions"] == []
        assert result["message"] == "无法解析网关持仓响应"

    @pytest.mark.asyncio
    async def test_live_close_ignores_explicit_zero_position_with_stale_volume(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="rb2501",
            exchange="ctp",
            confidence=0.9,
        )
        positions = [{"InstrumentID": "rb2501", "size": 0, "Volume": 2, "PosiDirection": "2"}]

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(service, "_send_gateway_command", return_value=positions) as send_cmd,
        ):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="manual:CTP:089763"
            )

        assert result["success"] is False
        assert result["error"] == "no_position"
        assert send_cmd.call_count == 1

    @pytest.mark.asyncio
    async def test_live_close_does_not_prefix_match_wrong_contract(self):
        """Closing rb25 must not accidentally close rb2501."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="rb25",
            confidence=0.9,
        )
        positions = [{"symbol": "rb2501", "volume": 2, "direction": "long"}]

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(service, "_send_gateway_command", return_value=positions) as send_cmd,
        ):
            result = await service.execute_live_trade(intent, user_id="user1", gateway_id="gw1")

        assert result["success"] is False
        assert result["error"] == "no_position"
        assert send_cmd.call_count == 1

    @pytest.mark.asyncio
    async def test_live_close_matches_compact_exchange_symbol(self):
        """Closing BTC/USDT must match a gateway position returned as BTCUSDT."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="BTC/USDT",
            exchange="binance",
            confidence=0.9,
        )
        positions = [
            {"symbol": "BTCUSDT", "volume": 0.25, "direction": "long"},
            {"symbol": "ETHUSDT", "volume": 2.0, "direction": "long"},
        ]

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(
                service,
                "_send_gateway_command",
                side_effect=[positions, {"order_id": "close-btc"}],
            ) as send_cmd,
        ):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="manual:BINANCE:spot"
            )

        assert result["success"] is True
        _, command, payload = send_cmd.call_args_list[1].args
        assert command == "place_order"
        assert payload["symbol"] == "BTCUSDT"
        assert payload["side"] == "sell"
        assert payload["size"] == 0.25
        assert payload["order_type"] == "market"

    @pytest.mark.asyncio
    async def test_live_close_handles_binance_gateway_position_aliases(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="BTC/USDT",
            exchange="binance",
            confidence=0.9,
        )
        positions = [
            {
                "position_symbol_name": "BTCUSDT",
                "position_volume": "0.25",
                "positionSide": "LONG",
                "entryPrice": "65000",
                "markPrice": "65100",
            }
        ]

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(
                service,
                "_send_gateway_command",
                side_effect=[positions, {"order_id": "close-btc"}],
            ) as send_cmd,
        ):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="manual:BINANCE:future"
            )

        assert result["success"] is True
        _, command, payload = send_cmd.call_args_list[1].args
        assert command == "place_order"
        assert payload["symbol"] == "BTCUSDT"
        assert payload["side"] == "sell"
        assert payload["size"] == pytest.approx(0.25)

    @pytest.mark.asyncio
    async def test_live_close_handles_dict_mapped_gateway_positions(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="BTC/USDT",
            exchange="binance",
            confidence=0.9,
        )
        positions = {
            "status": "ok",
            "data": {
                "BTCUSDT": {"symbol": "BTCUSDT", "positionAmt": "-0.2"},
                "ETHUSDT": {"symbol": "ETHUSDT", "positionAmt": "1.0"},
            },
        }

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(
                service,
                "_send_gateway_command",
                side_effect=[positions, {"order_id": "close-btc"}],
            ) as send_cmd,
        ):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="manual:BINANCE:future"
            )

        assert result["success"] is True
        _, command, payload = send_cmd.call_args_list[1].args
        assert command == "place_order"
        assert payload["symbol"] == "BTCUSDT"
        assert payload["side"] == "buy"
        assert payload["size"] == pytest.approx(0.2)

    @pytest.mark.asyncio
    async def test_live_close_respects_explicit_quantity(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="BTC/USDT",
            exchange="binance",
            quantity=0.1,
            confidence=0.9,
        )
        positions = [{"symbol": "BTCUSDT", "volume": 0.25, "direction": "long"}]

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(
                service,
                "_send_gateway_command",
                side_effect=[positions, {"order_id": "close-btc"}],
            ) as send_cmd,
        ):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="manual:BINANCE:spot"
            )

        assert result["success"] is True
        _, command, payload = send_cmd.call_args_list[1].args
        assert command == "place_order"
        assert payload["symbol"] == "BTCUSDT"
        assert payload["side"] == "sell"
        assert payload["size"] == pytest.approx(0.1)

    @pytest.mark.asyncio
    async def test_live_close_rejects_quantity_above_position(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="BTC/USDT",
            exchange="binance",
            quantity=0.3,
            confidence=0.9,
        )
        positions = [{"symbol": "BTCUSDT", "volume": 0.25, "direction": "long"}]

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(service, "_send_gateway_command", return_value=positions) as send_cmd,
        ):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="manual:BINANCE:spot"
            )

        assert result["success"] is False
        assert result["error"] == "invalid_order"
        assert "exceeds available" in result["message"]
        assert send_cmd.call_count == 1

    @pytest.mark.asyncio
    async def test_live_close_matches_ib_client_portal_contract_description(self):
        """IB Client Portal positions can identify stock rows by contractDesc."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="SPY",
            exchange="ib_web",
            confidence=0.9,
        )
        positions = [
            {
                "acctId": "U1234567",
                "contractDesc": "SPY",
                "assetClass": "STK",
                "position": 5.0,
                "avgPrice": 434.93,
                "mktPrice": 471.16,
            },
            {
                "acctId": "U1234567",
                "contractDesc": "AAPL",
                "assetClass": "STK",
                "position": 10.0,
            },
        ]

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(
                service,
                "_send_gateway_command",
                side_effect=[positions, {"order_id": "close-spy"}],
            ) as send_cmd,
        ):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="manual:IB_WEB:paper"
            )

        assert result["success"] is True
        _, command, payload = send_cmd.call_args_list[1].args
        assert command == "place_order"
        assert payload["symbol"] == "SPY"
        assert payload["side"] == "sell"
        assert payload["size"] == pytest.approx(5.0)
        assert payload["order_type"] == "market"

    @pytest.mark.asyncio
    async def test_live_close_accepts_wrapped_positions_payload(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="BTC/USDT",
            exchange="binance",
            confidence=0.9,
        )
        positions = [{"symbol": "BTCUSDT", "volume": 0.25, "direction": "long"}]

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(
                service,
                "_send_gateway_command",
                side_effect=[{"positions": positions}, {"order_id": "close-btc"}],
            ) as send_cmd,
        ):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="manual:BINANCE:spot"
            )

        assert result["success"] is True
        _, command, payload = send_cmd.call_args_list[1].args
        assert command == "place_order"
        assert payload["symbol"] == "BTCUSDT"
        assert payload["size"] == 0.25

    @pytest.mark.asyncio
    async def test_live_close_rejects_size_step_mismatch_before_gateway_send(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="BTC/USDT",
            exchange="binance",
            confidence=0.9,
        )
        positions = [{"symbol": "BTCUSDT", "volume": 0.15, "direction": "long"}]
        gateways = {
            "manual:BINANCE:spot": {
                "runtime": SimpleNamespace(
                    adapter=SimpleNamespace(
                        get_symbol_info=lambda _symbol: {
                            "symbol": "BTCUSDT",
                            "volume_min": 0.1,
                            "volume_step": 0.1,
                        }
                    )
                )
            }
        }

        with (
            patch.object(service, "_get_gateways_dict", return_value=gateways),
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(service, "_send_gateway_command", return_value=positions) as send_cmd,
        ):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="manual:BINANCE:spot"
            )

        assert result["success"] is False
        assert result["error"] == "invalid_order"
        assert "size step" in result["message"]
        assert send_cmd.call_count == 1

    @pytest.mark.asyncio
    async def test_live_close_allows_below_minimum_position_to_reduce_risk(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="BTC/USDT",
            exchange="binance",
            confidence=0.9,
        )
        positions = [{"symbol": "BTCUSDT", "volume": 0.05, "direction": "long"}]
        gateways = {
            "manual:BINANCE:spot": {
                "runtime": SimpleNamespace(
                    adapter=SimpleNamespace(
                        get_symbol_info=lambda _symbol: {
                            "symbol": "BTCUSDT",
                            "volume_min": 0.1,
                            "volume_step": 0.01,
                        }
                    )
                )
            }
        }

        with (
            patch.object(service, "_get_gateways_dict", return_value=gateways),
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(
                service,
                "_send_gateway_command",
                side_effect=[positions, {"order_id": "close-dust"}],
            ) as send_cmd,
        ):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="manual:BINANCE:spot"
            )

        assert result["success"] is True
        _, command, payload = send_cmd.call_args_list[1].args
        assert command == "place_order"
        assert payload["symbol"] == "BTCUSDT"
        assert payload["side"] == "sell"
        assert payload["size"] == pytest.approx(0.05)

    @pytest.mark.asyncio
    async def test_live_close_splits_market_orders_by_exchange_max_mkt_size(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="BTC-USDT-SWAP",
            exchange="okx",
            confidence=0.9,
        )
        positions = [{"instId": "BTC-USDT-SWAP", "posSide": "long", "pos": "1200"}]
        gateways = {
            "manual:OKX:swap": {
                "runtime": SimpleNamespace(
                    adapter=SimpleNamespace(
                        get_symbol_info=lambda _symbol: {
                            "instId": "BTC-USDT-SWAP",
                            "instType": "SWAP",
                            "ctVal": "0.01",
                            "lotSz": "1",
                            "minSz": "1",
                            "maxMktSz": "500",
                            "maxLmtSz": "2000",
                            "source": "okx_get_instruments",
                        }
                    )
                )
            }
        }

        with (
            patch.object(service, "_get_gateways_dict", return_value=gateways),
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(
                service,
                "_send_gateway_command",
                side_effect=[
                    positions,
                    {"order_id": "close-1"},
                    {"order_id": "close-2"},
                    {"order_id": "close-3"},
                ],
            ) as send_cmd,
        ):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="manual:OKX:swap"
            )

        assert result["success"] is True
        assert result["type"] == "live_close"
        assert len(result["submitted_orders"]) == 3
        close_payloads = [call.args[2] for call in send_cmd.call_args_list[1:]]
        assert [payload["size"] for payload in close_payloads] == [500, 500, 200]
        assert all(payload["order_type"] == "market" for payload in close_payloads)
        assert all(payload["offset"] == "close" for payload in close_payloads)
        assert all(payload["posSide"] == "long" for payload in close_payloads)
        assert all(payload["position_side"] == "long" for payload in close_payloads)

    @pytest.mark.asyncio
    async def test_live_close_aggregates_same_direction_contract_rows(self):
        """CTP may return same-symbol long rows split by today/yesterday."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="rb2501",
            exchange="ctp",
            confidence=0.9,
        )
        positions = [
            {"symbol": "SHFE.rb2501", "volume": 1, "direction": "long", "exchange_id": "SHFE"},
            {"symbol": "rb2501", "volume": 2, "direction": "long", "exchange_id": "SHFE"},
        ]

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(
                service,
                "_send_gateway_command",
                side_effect=[positions, {"order_id": "close-1"}],
            ) as send_cmd,
        ):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="manual:CTP:089763"
            )

        assert result["success"] is True
        _, command, payload = send_cmd.call_args_list[1].args
        assert command == "place_order"
        assert payload["symbol"] == "SHFE.rb2501"
        assert payload["side"] == "sell"
        assert payload["offset"] == "close"
        assert payload["size"] == 3
        assert payload["order_type"] == "market"

    @pytest.mark.asyncio
    async def test_live_close_splits_ctp_today_and_yesterday_offsets(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="rb2501",
            exchange="ctp",
            confidence=0.9,
        )
        positions = [
            {
                "symbol": "SHFE.rb2501",
                "volume": 3,
                "direction": "long",
                "exchange_id": "SHFE",
                "today_position": 1,
                "yd_position": 2,
            },
        ]

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(
                service,
                "_send_gateway_command",
                side_effect=[
                    positions,
                    {"order_id": "close-today"},
                    {"order_id": "close-yesterday"},
                ],
            ) as send_cmd,
        ):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="manual:CTP:089763"
            )

        assert result["success"] is True
        assert result["size"] == 3
        assert len(result["submitted_orders"]) == 2
        _, command_today, payload_today = send_cmd.call_args_list[1].args
        _, command_yesterday, payload_yesterday = send_cmd.call_args_list[2].args
        assert command_today == "place_order"
        assert payload_today["symbol"] == "SHFE.rb2501"
        assert payload_today["side"] == "sell"
        assert payload_today["offset"] == "close_today"
        assert payload_today["size"] == 1
        assert payload_today["exchange_id"] == "SHFE"
        assert payload_today["order_type"] == "market"
        assert command_yesterday == "place_order"
        assert payload_yesterday["symbol"] == "SHFE.rb2501"
        assert payload_yesterday["side"] == "sell"
        assert payload_yesterday["offset"] == "close_yesterday"
        assert payload_yesterday["size"] == 2
        assert payload_yesterday["exchange_id"] == "SHFE"
        assert payload_yesterday["order_type"] == "market"

    @pytest.mark.asyncio
    async def test_live_close_splits_ctp_td_and_history_position_aliases(self):
        """CTP close planning must understand raw TdPosition/HistoryPosition aliases."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="rb2501",
            exchange="ctp",
            confidence=0.9,
        )
        positions = [
            {
                "InstrumentID": "rb2501",
                "Position": 3,
                "PosiDirection": "2",
                "ExchangeID": "SHFE",
                "TdPosition": 1,
                "HistoryPosition": 2,
            },
        ]

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(
                service,
                "_send_gateway_command",
                side_effect=[
                    positions,
                    {"order_id": "close-today"},
                    {"order_id": "close-yesterday"},
                ],
            ) as send_cmd,
        ):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="manual:CTP:089763"
            )

        assert result["success"] is True
        assert result["size"] == 3
        assert len(result["submitted_orders"]) == 2
        _, _, payload_today = send_cmd.call_args_list[1].args
        _, _, payload_yesterday = send_cmd.call_args_list[2].args
        assert payload_today["offset"] == "close_today"
        assert payload_today["size"] == 1
        assert payload_today["side"] == "sell"
        assert payload_today["exchange_id"] == "SHFE"
        assert payload_yesterday["offset"] == "close_yesterday"
        assert payload_yesterday["size"] == 2
        assert payload_yesterday["side"] == "sell"
        assert payload_yesterday["exchange_id"] == "SHFE"

    @pytest.mark.asyncio
    async def test_live_close_partial_ctp_quantity_splits_today_then_yesterday(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="rb2501",
            exchange="ctp",
            quantity=2,
            confidence=0.9,
        )
        positions = [
            {
                "symbol": "SHFE.rb2501",
                "volume": 3,
                "direction": "long",
                "exchange_id": "SHFE",
                "today_position": 1,
                "yd_position": 2,
            },
        ]

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(
                service,
                "_send_gateway_command",
                side_effect=[
                    positions,
                    {"order_id": "close-today"},
                    {"order_id": "close-yesterday"},
                ],
            ) as send_cmd,
        ):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="manual:CTP:089763"
            )

        assert result["success"] is True
        assert result["size"] == 2
        _, _, payload_today = send_cmd.call_args_list[1].args
        _, _, payload_yesterday = send_cmd.call_args_list[2].args
        assert payload_today["offset"] == "close_today"
        assert payload_today["size"] == 1
        assert payload_yesterday["offset"] == "close_yesterday"
        assert payload_yesterday["size"] == 1

    @pytest.mark.asyncio
    async def test_live_close_handles_raw_mt5_short_trade_action(self):
        """MT5 raw trade_action='1' is a short position and must close with buy."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="EURUSD",
            exchange="mt5",
            confidence=0.9,
        )
        positions = [
            {
                "symbol": "EURUSD",
                "volume": 0.1,
                "trade_action": "1",
                "position_id": 123456,
            }
        ]

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(
                service,
                "_send_gateway_command",
                side_effect=[positions, {"retcode": 10009, "order_id": "close-1"}],
            ) as send_cmd,
        ):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="manual:MT5:demo"
            )

        assert result["success"] is True
        _, command, payload = send_cmd.call_args_list[1].args
        assert command == "place_order"
        assert payload["side"] == "buy"
        assert payload["size"] == 0.1
        assert payload["order_type"] == "close"
        assert payload["position_id"] == 123456

    @pytest.mark.asyncio
    async def test_live_close_rejects_mt5_position_without_position_id(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="EURUSD",
            exchange="mt5",
            confidence=0.9,
        )
        positions = [{"symbol": "EURUSD", "volume": 0.1, "direction": "long"}]

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(service, "_send_gateway_command", return_value=positions) as send_cmd,
        ):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="manual:MT5:demo"
            )

        assert result["success"] is False
        assert result["error"] == "invalid_order"
        assert "position_id" in result["message"]
        assert send_cmd.call_count == 1

    @pytest.mark.asyncio
    async def test_live_close_splits_mt5_positions_by_position_id(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="EURUSD",
            exchange="mt5",
            confidence=0.9,
        )
        positions = [
            {"symbol": "EURUSD", "volume": 0.1, "direction": "long", "position_id": 11},
            {"symbol": "EURUSD", "volume": 0.2, "direction": "long", "position_id": 12},
        ]

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(
                service,
                "_send_gateway_command",
                side_effect=[
                    positions,
                    {"retcode": 10009, "order_id": "close-11"},
                    {"retcode": 10009, "order_id": "close-12"},
                ],
            ) as send_cmd,
        ):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="manual:MT5:demo"
            )

        assert result["success"] is True
        assert result["size"] == pytest.approx(0.3)
        _, command_first, payload_first = send_cmd.call_args_list[1].args
        _, command_second, payload_second = send_cmd.call_args_list[2].args
        assert command_first == "place_order"
        assert command_second == "place_order"
        assert payload_first["size"] == 0.1
        assert payload_first["position_id"] == 11
        assert payload_first["order_type"] == "close"
        assert payload_second["size"] == 0.2
        assert payload_second["position_id"] == 12
        assert payload_second["order_type"] == "close"

    @pytest.mark.asyncio
    async def test_live_close_partial_mt5_quantity_splits_by_position_id(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="EURUSD",
            exchange="mt5",
            quantity=0.15,
            confidence=0.9,
        )
        positions = [
            {"symbol": "EURUSD", "volume": 0.1, "direction": "long", "position_id": 11},
            {"symbol": "EURUSD", "volume": 0.2, "direction": "long", "position_id": 12},
        ]

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(
                service,
                "_send_gateway_command",
                side_effect=[
                    positions,
                    {"retcode": 10009, "order_id": "close-11"},
                    {"retcode": 10009, "order_id": "close-12"},
                ],
            ) as send_cmd,
        ):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="manual:MT5:demo"
            )

        assert result["success"] is True
        assert result["size"] == pytest.approx(0.15)
        _, _, payload_first = send_cmd.call_args_list[1].args
        _, _, payload_second = send_cmd.call_args_list[2].args
        assert payload_first["size"] == pytest.approx(0.1)
        assert payload_first["position_id"] == 11
        assert payload_second["size"] == pytest.approx(0.05)
        assert payload_second["position_id"] == 12

    @pytest.mark.asyncio
    async def test_live_close_handles_raw_ctp_short_position_direction(self):
        """CTP raw PosiDirection='3' is a short position and must close with buy."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="rb2501",
            exchange="ctp",
            confidence=0.9,
        )
        positions = [{"InstrumentID": "rb2501", "Position": 2, "PosiDirection": "3"}]

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(
                service,
                "_send_gateway_command",
                side_effect=[positions, {"order_id": "close-1"}],
            ) as send_cmd,
        ):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="manual:CTP:089763"
            )

        assert result["success"] is True
        _, command, payload = send_cmd.call_args_list[1].args
        assert command == "place_order"
        assert payload["side"] == "buy"
        assert payload["offset"] == "close"

    @pytest.mark.asyncio
    async def test_live_close_handles_float_string_ctp_short_position_direction(self):
        """CTP numeric direction aliases like '3.0' must still close shorts with buy."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="rb2501",
            exchange="ctp",
            confidence=0.9,
        )
        positions = [{"InstrumentID": "rb2501", "Position": 2, "PosiDirection": "3.0"}]

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(
                service,
                "_send_gateway_command",
                side_effect=[positions, {"order_id": "close-1"}],
            ) as send_cmd,
        ):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="manual:CTP:089763"
            )

        assert result["success"] is True
        _, command, payload = send_cmd.call_args_list[1].args
        assert command == "place_order"
        assert payload["side"] == "buy"
        assert payload["offset"] == "close"

    @pytest.mark.asyncio
    async def test_live_close_handles_bybit_position_idx_short_position(self):
        """Bybit positionIdx=2 is a short leg and must close with buy/short."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="BTCUSDT",
            exchange="bybit",
            confidence=0.9,
        )
        positions = [{"symbol": "BTCUSDT", "positionIdx": "2", "size": "0.5"}]

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(
                service,
                "_send_gateway_command",
                side_effect=[positions, {"order_id": "close-1"}],
            ) as send_cmd,
        ):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="manual:BYBIT:demo"
            )

        assert result["success"] is True
        _, command, payload = send_cmd.call_args_list[1].args
        assert command == "place_order"
        assert payload["side"] == "buy"
        assert payload["offset"] == "close"
        assert payload["position_side"] == "short"
        assert payload["posSide"] == "short"

    @pytest.mark.asyncio
    async def test_live_close_rejects_hedged_symbol_without_requested_side(self):
        """Hedged long/short legs must not be closed without an explicit side."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="BTCUSDT",
            exchange="bybit",
            confidence=0.9,
        )
        positions = [
            {"symbol": "BTCUSDT", "positionIdx": "1", "size": "0.4"},
            {"symbol": "BTCUSDT", "positionIdx": "2", "size": "0.5"},
        ]

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(service, "_send_gateway_command", return_value=positions) as send_cmd,
        ):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="manual:BYBIT:demo"
            )

        assert result["success"] is False
        assert result["error"] == "ambiguous_position"
        assert "方向" in result["message"]
        assert send_cmd.call_count == 1

    @pytest.mark.asyncio
    async def test_live_close_uses_explicit_position_side_for_hedged_symbol(self):
        """A close-short intent must close only the short leg in hedge mode."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="BTCUSDT",
            exchange="bybit",
            quantity=0.25,
            confidence=0.9,
            additional_params={"position_side": "short"},
        )
        positions = [
            {"symbol": "BTCUSDT", "positionIdx": "1", "size": "0.4"},
            {"symbol": "BTCUSDT", "positionIdx": "2", "size": "0.5"},
        ]

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(
                service,
                "_send_gateway_command",
                side_effect=[positions, {"order_id": "close-short"}],
            ) as send_cmd,
        ):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="manual:BYBIT:demo"
            )

        assert result["success"] is True
        _, command, payload = send_cmd.call_args_list[1].args
        assert command == "place_order"
        assert payload["side"] == "buy"
        assert payload["size"] == pytest.approx(0.25)
        assert payload["position_side"] == "short"
        assert payload["posSide"] == "short"

    @pytest.mark.asyncio
    async def test_live_close_infers_short_side_from_raw_instruction(self):
        """Raw Chinese close-short wording should disambiguate hedged legs."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="BTCUSDT",
            exchange="bybit",
            confidence=0.9,
            raw_input="平掉BTCUSDT空单",
        )
        positions = [
            {"symbol": "BTCUSDT", "positionIdx": "1", "size": "0.4"},
            {"symbol": "BTCUSDT", "positionIdx": "2", "size": "0.5"},
        ]

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(
                service,
                "_send_gateway_command",
                side_effect=[positions, {"order_id": "close-short"}],
            ) as send_cmd,
        ):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="manual:BYBIT:demo"
            )

        assert result["success"] is True
        _, command, payload = send_cmd.call_args_list[1].args
        assert command == "place_order"
        assert payload["side"] == "buy"
        assert payload["size"] == pytest.approx(0.5)
        assert payload["position_side"] == "short"

    @pytest.mark.asyncio
    async def test_live_close_rejects_gateway_error_payload(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="EURUSD",
            exchange="mt5",
            confidence=0.9,
        )
        positions = [{"symbol": "EURUSD", "volume": 0.1, "direction": "long", "position_id": 88}]

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(
                service,
                "_send_gateway_command",
                side_effect=[
                    positions,
                    {"retcode": 10030, "comment": "Invalid filling mode"},
                ],
            ),
        ):
            result = await service.execute_live_trade(intent, user_id="user1", gateway_id="gw1")

        assert result["success"] is False
        assert result["error"] == "close_failed"
        assert result["message"] == "Invalid filling mode"


class TestDirectOrderServiceFindGateway:
    """Test gateway discovery."""

    def test_find_gateway_exception_returns_none(self):
        service = DirectOrderService()
        intent = TradingIntent(action=TradeAction.BUY, confidence=0.9)

        with patch.object(service, "_get_gateways_dict", side_effect=ImportError("no module")):
            result = service._find_available_gateway(intent)
            assert result is None
