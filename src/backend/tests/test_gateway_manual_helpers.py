from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.services import ctp_tunnel
from app.services.gateway import manual as manual_gateway_service
from app.services.gateway import manual_ctp_proxy, manual_ports


class _FakeOrderAdapter:
    def __init__(self, orders):
        self.orders = orders
        self.cancelled = []

    def get_open_orders(self):
        return list(self.orders)

    def cancel_order(self, payload):
        self.cancelled.append(dict(payload))
        return {"status": "ok"}


class _FakeRawOrderAdapter(_FakeOrderAdapter):
    def get_open_orders(self):
        return self.orders


class _FakePositionAdapter:
    def __init__(self, payload):
        self.payload = payload

    def get_positions(self):
        return self.payload


class _FakeTradeAdapter:
    def __init__(self, payload):
        self.payload = payload

    def get_trades(self, **_kwargs):
        return self.payload


class _FakePrivateTradeAdapter(_FakeTradeAdapter):
    def __init__(self, public_payload, private_payload):
        super().__init__(public_payload)
        self.private_payload = private_payload
        self.calls = []

    def get_trades(self, **_kwargs):
        self.calls.append("get_trades")
        return self.payload

    def get_deals(self, **_kwargs):
        self.calls.append("get_deals")
        return self.private_payload


class _FakeBalanceAdapter:
    def __init__(self, payload):
        self.payload = payload

    def get_balance(self):
        return self.payload


class _FakeBalanceContainer:
    def __init__(self, payload):
        self.payload = payload

    def get_all_data(self):
        return self.payload


class TestManualPorts:
    def test_parse_base_url_endpoint_defaults_https_port(self):
        assert manual_ports.parse_base_url_endpoint("https://LOCALHOST/v1/api") == (
            "localhost",
            443,
        )

    def test_parse_base_url_endpoint_uses_http_port(self):
        assert manual_ports.parse_base_url_endpoint("http://example.test/path") == (
            "example.test",
            80,
        )

    def test_is_tcp_endpoint_reachable_closes_connection(self):
        conn = Mock()
        create_connection = Mock(return_value=conn)

        assert manual_ports.is_tcp_endpoint_reachable(
            "127.0.0.1",
            5000,
            timeout=0.25,
            create_connection=create_connection,
        )

        create_connection.assert_called_once_with(("127.0.0.1", 5000), timeout=0.25)
        conn.close.assert_called_once()

    def test_wait_for_tcp_endpoint_uses_injected_probe(self):
        reachable = Mock(side_effect=[False, True])
        monotonic = Mock(side_effect=[0.0, 0.0, 0.4])
        sleep = Mock()

        assert manual_ports.wait_for_tcp_endpoint(
            "localhost",
            5000,
            1.0,
            is_reachable=reachable,
            monotonic=monotonic,
            sleep=sleep,
        )

        sleep.assert_called_once_with(0.5)


class TestManualCtpProxy:
    def test_count_utun_interfaces_falls_back_to_ifconfig(self):
        import builtins

        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "psutil":
                raise ImportError
            return original_import(name, *args, **kwargs)

        run_command = Mock(return_value=Mock(stdout="utun0\nutun1\n"))
        logger = Mock()

        with patch("builtins.__import__", side_effect=fake_import):
            assert manual_ctp_proxy.count_utun_interfaces(
                run_command=run_command,
                logger=logger,
            ) == 2

        run_command.assert_called_once_with(["ifconfig"], capture_output=True, text=True, timeout=5)

    def test_ensure_ctp_direct_routes_stops_after_clash_success(self):
        logger = Mock()
        add_route = Mock()

        manual_ctp_proxy.ensure_ctp_direct_routes(
            "tcp://1.2.3.4:30001",
            "tcp://1.2.3.5:30011",
            logger,
            is_tun_proxy_active=Mock(return_value=True),
            extract_ips=Mock(return_value=["1.2.3.4", "1.2.3.5"]),
            add_bypass_file=Mock(return_value=False),
            add_clash_rules=Mock(return_value=True),
            get_default_gateway=Mock(return_value=("192.168.1.1", "en0")),
            add_direct_route=add_route,
        )

        add_route.assert_not_called()

    def test_detect_system_tun_proxy_returns_hint_when_active(self):
        hint = manual_ctp_proxy.detect_system_tun_proxy(
            is_tun_proxy_active=Mock(return_value=True),
        )

        assert hint is not None
        assert "CTP" in hint


class TestCtpTunnel:
    def test_reads_env_http_proxy_with_basic_auth(self):
        endpoint = ctp_tunnel._get_http_proxy_endpoint(
            environ={"CTP_TUNNEL_PROXY": "http://user:p%40ss@127.0.0.1:7890"},
            system_getproxies=lambda: {},
            run_scutil=None,
        )

        assert endpoint is not None
        assert endpoint.host == "127.0.0.1"
        assert endpoint.port == 7890
        assert endpoint.authorization.startswith("Basic ")
        assert endpoint.source == "env:CTP_TUNNEL_PROXY"

    def test_can_disable_proxy_tunnel_detection(self):
        endpoint = ctp_tunnel._get_http_proxy_endpoint(
            environ={
                "CTP_TUNNEL_ENABLED": "0",
                "HTTP_PROXY": "http://127.0.0.1:7890",
            },
            system_getproxies=lambda: {"http": "http://127.0.0.1:7891"},
            run_scutil=None,
        )

        assert endpoint is None

    def test_uses_system_proxy_when_env_is_empty(self):
        endpoint = ctp_tunnel._get_http_proxy_endpoint(
            environ={},
            system_getproxies=lambda: {"http": "http://localhost:7890"},
            run_scutil=None,
        )

        assert endpoint is not None
        assert endpoint.host == "localhost"
        assert endpoint.port == 7890
        assert endpoint.source == "system:http"

    def test_skips_default_scutil_probe_when_not_macos(self, monkeypatch):
        run_scutil = Mock()
        monkeypatch.setattr(ctp_tunnel.sys, "platform", "linux")
        monkeypatch.setattr(ctp_tunnel.shutil, "which", Mock(return_value=None))
        monkeypatch.setattr(ctp_tunnel.subprocess, "run", run_scutil)

        endpoint = ctp_tunnel._get_http_proxy_endpoint(
            environ={},
            system_getproxies=lambda: {},
            run_scutil=ctp_tunnel.subprocess.run,
        )

        assert endpoint is None
        run_scutil.assert_not_called()

    def test_uses_injected_scutil_probe_on_non_macos(self, monkeypatch):
        monkeypatch.setattr(ctp_tunnel.sys, "platform", "linux")
        monkeypatch.setattr(ctp_tunnel.shutil, "which", Mock(return_value=None))
        run_scutil = Mock(
            return_value=Mock(
                stdout="HTTPEnable : 1\nHTTPProxy : 127.0.0.1\nHTTPPort : 7890\n"
            )
        )

        endpoint = ctp_tunnel._get_http_proxy_endpoint(
            environ={},
            system_getproxies=lambda: {},
            run_scutil=run_scutil,
        )

        assert endpoint is not None
        assert endpoint.host == "127.0.0.1"
        assert endpoint.port == 7890
        assert endpoint.source == "scutil"
        run_scutil.assert_called_once()

    def test_connect_request_includes_proxy_authorization(self):
        request = ctp_tunnel._build_connect_request(
            "182.254.243.31:40011",
            "Basic abc123",
        )

        assert b"CONNECT 182.254.243.31:40011 HTTP/1.1\r\n" in request
        assert b"Host: 182.254.243.31:40011\r\n" in request
        assert b"Proxy-Authorization: Basic abc123\r\n" in request
        assert request.endswith(b"\r\n\r\n")


class TestManualGatewayAccount:
    def test_query_gateway_account_unwraps_bybit_v5_wallet_balance(self):
        adapter = _FakeBalanceAdapter(
            {
                "retCode": 0,
                "retMsg": "OK",
                "result": {
                    "list": [
                        {
                            "accountType": "UNIFIED",
                            "totalEquity": "1,250.5",
                            "totalWalletBalance": "1,200.0",
                            "totalAvailableBalance": "950.25",
                            "totalInitialMargin": "300.25",
                            "coin": [
                                {
                                    "coin": "USDT",
                                    "walletBalance": "1200",
                                    "equity": "1250.5",
                                }
                            ],
                        }
                    ]
                },
            }
        )
        gateways = {
            "gw-1": {
                "runtime": SimpleNamespace(adapter=adapter),
                "exchange_type": "BYBIT",
                "account_id": "unified",
            }
        }

        account = manual_gateway_service.query_gateway_account(gateways, "gw-1", strict=True)

        assert account["value"] == 1250.5
        assert account["equity"] == 1250.5
        assert account["cash"] == 950.25
        assert account["margin"] == 300.25
        assert account["accountType"] == "UNIFIED"
        assert account["account_source"] == "adapter.get_balance"

    def test_query_gateway_account_unwraps_okx_balance_data(self):
        adapter = _FakeBalanceAdapter(
            {
                "code": "0",
                "msg": "",
                "data": [
                    {
                        "uTime": "1760000000000",
                        "totalEq": "2500",
                        "availEq": "2100",
                        "imr": "400",
                        "details": [{"ccy": "USDT", "eq": "2500"}],
                    }
                ],
            }
        )
        gateways = {
            "gw-1": {
                "runtime": SimpleNamespace(adapter=adapter),
                "exchange_type": "OKX",
                "account_id": "main",
            }
        }

        account = manual_gateway_service.query_gateway_account(gateways, "gw-1", strict=True)

        assert account["value"] == 2500.0
        assert account["equity"] == 2500.0
        assert account["cash"] == 2100.0
        assert account["margin"] == 400.0
        assert account["account_source"] == "adapter.get_balance"

    def test_query_gateway_account_reads_balance_container(self):
        adapter = _FakeBalanceAdapter(
            _FakeBalanceContainer(
                {
                    "exchange_name": "OKX",
                    "total_margin": "2500",
                    "total_used_margin": "400",
                    "total_wallet_balance": "2500",
                }
            )
        )
        gateways = {
            "gw-1": {
                "runtime": SimpleNamespace(adapter=adapter),
                "exchange_type": "OKX",
                "account_id": "main",
            }
        }

        account = manual_gateway_service.query_gateway_account(gateways, "gw-1", strict=True)

        assert account["value"] == 2500.0
        assert account["cash"] == 2100.0
        assert account["margin"] == 400.0
        assert account["account_source"] == "adapter.get_balance"


class TestManualGatewayPositions:
    def test_query_gateway_positions_unwraps_nested_data_positions_in_strict_mode(self):
        adapter = _FakePositionAdapter(
            {"data": {"positions": [{"symbol": "BTCUSDT", "positionAmt": "0.25"}]}}
        )
        gateways = {"gw-1": {"runtime": SimpleNamespace(adapter=adapter)}}

        rows = manual_gateway_service.query_gateway_positions(gateways, "gw-1", strict=True)

        assert rows == [{"symbol": "BTCUSDT", "positionAmt": "0.25"}]

    def test_query_gateway_positions_unwraps_result_symbol_map(self):
        adapter = _FakePositionAdapter(
            {"result": {"BTCUSDT": {"symbol": "BTCUSDT", "size": 0.25}}}
        )
        gateways = {"gw-1": {"runtime": SimpleNamespace(adapter=adapter)}}

        rows = manual_gateway_service.query_gateway_positions(gateways, "gw-1")

        assert rows == [{"symbol": "BTCUSDT", "size": 0.25}]

    def test_query_gateway_positions_accepts_single_position_row(self):
        adapter = _FakePositionAdapter({"symbol": "IF2609", "Position": 1})
        gateways = {"gw-1": {"runtime": SimpleNamespace(adapter=adapter)}}

        rows = manual_gateway_service.query_gateway_positions(gateways, "gw-1", strict=True)

        assert rows == [{"symbol": "IF2609", "Position": 1}]

    def test_query_gateway_positions_accepts_okx_single_position_row(self):
        adapter = _FakePositionAdapter(
            {"instId": "BTC-USDT-SWAP", "pos": "1", "avgPx": "60000"}
        )
        gateways = {"gw-1": {"runtime": SimpleNamespace(adapter=adapter)}}

        rows = manual_gateway_service.query_gateway_positions(gateways, "gw-1", strict=True)

        assert rows == [{"instId": "BTC-USDT-SWAP", "pos": "1", "avgPx": "60000"}]

    def test_query_gateway_positions_unwraps_nested_ib_description_quantity_map(self):
        adapter = _FakePositionAdapter(
            {
                "accounts": {
                    "U1234567": {
                        "portfolio": {
                            "SPY": {
                                "description": "SPY",
                                "quantity": 5,
                                "mktPrice": 471.16,
                            }
                        }
                    }
                }
            }
        )
        gateways = {"gw-1": {"runtime": SimpleNamespace(adapter=adapter)}}

        rows = manual_gateway_service.query_gateway_positions(gateways, "gw-1", strict=True)

        assert rows == [{"description": "SPY", "quantity": 5, "mktPrice": 471.16}]


class TestManualGatewayTrades:
    def test_query_gateway_trades_prefers_private_deals_over_public_trades(self):
        adapter = _FakePrivateTradeAdapter(
            public_payload=[
                {
                    "symbol": "BTCUSDT",
                    "side": "Buy",
                    "qty": "1",
                    "price": "1",
                }
            ],
            private_payload=[
                {
                    "symbol": "BTCUSDT",
                    "side": "Sell",
                    "execQty": "0.1",
                    "execPrice": "60000",
                    "execFee": "3",
                    "feeCurrency": "USDT",
                    "execTime": "1672282722429",
                }
            ],
        )
        gateways = {"gw-1": {"runtime": SimpleNamespace(adapter=adapter)}}

        rows = manual_gateway_service.query_gateway_trades(
            gateways,
            "gw-1",
            symbol="BTCUSDT",
            strict=True,
        )

        assert adapter.calls == ["get_deals"]
        assert rows == [
            {
                "symbol": "BTCUSDT",
                "side": "Sell",
                "execQty": "0.1",
                "execPrice": "60000",
                "execFee": "3",
                "feeCurrency": "USDT",
                "execTime": "1672282722429",
            }
        ]

    def test_query_gateway_trades_unwraps_bybit_v5_result_list(self):
        adapter = _FakeTradeAdapter(
            {
                "retCode": 0,
                "retMsg": "OK",
                "result": {
                    "category": "linear",
                    "list": [
                        {
                            "symbol": "BTCUSDT",
                            "side": "Sell",
                            "execQty": "0.1",
                            "execPrice": "60000",
                            "execFee": "3",
                            "feeCurrency": "USDT",
                            "execTime": "1672282722429",
                        }
                    ],
                },
            }
        )
        gateways = {"gw-1": {"runtime": SimpleNamespace(adapter=adapter)}}

        rows = manual_gateway_service.query_gateway_trades(
            gateways,
            "gw-1",
            symbol="BTCUSDT",
            strict=True,
        )

        assert rows == [
            {
                "symbol": "BTCUSDT",
                "side": "Sell",
                "execQty": "0.1",
                "execPrice": "60000",
                "execFee": "3",
                "feeCurrency": "USDT",
                "execTime": "1672282722429",
            }
        ]

    def test_query_gateway_trades_does_not_return_result_wrapper_as_trade(self):
        adapter = _FakeTradeAdapter({"result": {"category": "linear", "nextPageCursor": ""}})
        gateways = {"gw-1": {"runtime": SimpleNamespace(adapter=adapter)}}

        rows = manual_gateway_service.query_gateway_trades(gateways, "gw-1")

        assert rows == []


class TestManualGatewayOrderCancellation:
    def test_cancel_gateway_open_orders_cancels_unowned_when_exclusive(self):
        adapter = _FakeOrderAdapter(
            [{"order_ref": "ref-1", "data_name": "IF2609", "remaining": 1}]
        )
        gateways = {"gw-1": {"runtime": SimpleNamespace(adapter=adapter)}}

        result = manual_gateway_service.cancel_gateway_open_orders(
            gateways,
            "gw-1",
            owner_ids={"inst-1"},
            cancel_unowned=True,
        )

        assert result["status"] == "ok"
        assert result["cancelled_count"] == 1
        assert adapter.cancelled[0]["order_ref"] == "ref-1"
        assert adapter.cancelled[0]["symbol"] == "IF2609"

    def test_cancel_gateway_open_orders_skips_unknown_owner_on_shared_gateway(self):
        adapter = _FakeOrderAdapter(
            [{"order_ref": "ref-2", "data_name": "IF2609", "remaining": 1}]
        )
        gateways = {"gw-1": {"runtime": SimpleNamespace(adapter=adapter)}}

        result = manual_gateway_service.cancel_gateway_open_orders(
            gateways,
            "gw-1",
            owner_ids={"inst-1"},
            cancel_unowned=False,
        )

        assert result["status"] == "warning"
        assert result["cancelled_count"] == 0
        assert result["skipped_count"] == 1
        assert result["unknown_owner_count"] == 1
        assert result["skipped_orders"][0]["skip_reason"] == "unknown_owner"
        assert adapter.cancelled == []

    def test_cancel_gateway_open_orders_uses_order_map_owner(self):
        adapter = _FakeOrderAdapter(
            [{"order_ref": "ref-3", "data_name": "IF2609", "remaining": 1}]
        )
        order_map = SimpleNamespace(
            by_client=lambda value: SimpleNamespace(strategy_id="unit-1")
            if value == "ref-3"
            else None
        )
        gateways = {
            "gw-1": {"runtime": SimpleNamespace(adapter=adapter, order_map=order_map)}
        }

        result = manual_gateway_service.cancel_gateway_open_orders(
            gateways,
            "gw-1",
            owner_ids={"unit-1"},
            cancel_unowned=False,
        )

        assert result["status"] == "ok"
        assert result["cancelled_count"] == 1
        assert result["cancelled_orders"][0]["owner_id"] == "unit-1"

    def test_cancel_gateway_open_orders_uses_venue_order_map_owner(self):
        adapter = _FakeOrderAdapter(
            [{"external_order_id": "venue-1", "data_name": "IF2609", "remaining": 1}]
        )
        order_map = SimpleNamespace(
            strategy_for_venue=lambda value: "unit-1" if value == "venue-1" else None
        )
        gateways = {
            "gw-1": {"runtime": SimpleNamespace(adapter=adapter, order_map=order_map)}
        }

        result = manual_gateway_service.cancel_gateway_open_orders(
            gateways,
            "gw-1",
            owner_ids={"unit-1"},
            cancel_unowned=False,
        )

        assert result["status"] == "ok"
        assert result["cancelled_count"] == 1
        assert result["cancelled_orders"][0]["owner_id"] == "unit-1"

    def test_cancel_gateway_open_orders_uses_exchange_client_order_alias_owner(self):
        adapter = _FakeOrderAdapter(
            [{"instId": "BTC-USDT-SWAP", "clOrdId": "client-1", "remaining": 1}]
        )
        order_map = SimpleNamespace(
            by_client=lambda value: SimpleNamespace(strategy_id="unit-1")
            if value == "client-1"
            else None
        )
        gateways = {
            "gw-1": {"runtime": SimpleNamespace(adapter=adapter, order_map=order_map)}
        }

        result = manual_gateway_service.cancel_gateway_open_orders(
            gateways,
            "gw-1",
            owner_ids={"unit-1"},
            cancel_unowned=False,
        )

        assert result["status"] == "ok"
        assert result["cancelled_count"] == 1
        assert result["cancelled_orders"][0]["owner_id"] == "unit-1"

    def test_cancel_gateway_open_orders_uses_order_link_id_owner(self):
        adapter = _FakeOrderAdapter(
            [{"symbol": "ETHUSDT", "orderLinkId": "client-link-1", "remaining": 1}]
        )
        order_map = SimpleNamespace(
            by_client=lambda value: SimpleNamespace(strategy_id="unit-1")
            if value == "client-link-1"
            else None
        )
        gateways = {
            "gw-1": {"runtime": SimpleNamespace(adapter=adapter, order_map=order_map)}
        }

        result = manual_gateway_service.cancel_gateway_open_orders(
            gateways,
            "gw-1",
            owner_ids={"unit-1"},
            cancel_unowned=False,
        )

        assert result["status"] == "ok"
        assert result["cancelled_count"] == 1
        assert adapter.cancelled[0]["client_order_id"] == "client-link-1"
        assert adapter.cancelled[0]["order_ref"] == "client-link-1"

    def test_cancel_gateway_open_orders_leaves_other_owner_orders_as_ok(self):
        adapter = _FakeOrderAdapter(
            [{"order_ref": "ref-4", "data_name": "IF2609", "remaining": 1}]
        )
        order_map = SimpleNamespace(
            by_client=lambda value: SimpleNamespace(strategy_id="unit-2")
            if value == "ref-4"
            else None
        )
        gateways = {
            "gw-1": {"runtime": SimpleNamespace(adapter=adapter, order_map=order_map)}
        }

        result = manual_gateway_service.cancel_gateway_open_orders(
            gateways,
            "gw-1",
            owner_ids={"unit-1"},
            cancel_unowned=False,
        )

        assert result["status"] == "ok"
        assert result["cancelled_count"] == 0
        assert result["other_owner_count"] == 1
        assert result["skipped_orders"][0]["skip_reason"] == "different_owner"
        assert adapter.cancelled == []

    def test_cancel_gateway_open_orders_normalizes_exchange_order_aliases(self):
        adapter = _FakeOrderAdapter(
            [
                {
                    "instId": "BTC-USDT-SWAP",
                    "ordId": "okx-order-1",
                    "clOrdId": "okx-client-1",
                    "state": "live",
                    "remaining": 1,
                }
            ]
        )
        gateways = {"gw-1": {"runtime": SimpleNamespace(adapter=adapter)}}

        result = manual_gateway_service.cancel_gateway_open_orders(
            gateways,
            "gw-1",
            owner_ids={"inst-1"},
            cancel_unowned=True,
        )

        assert result["status"] == "ok"
        assert result["cancelled_count"] == 1
        assert adapter.cancelled[0]["symbol"] == "BTC-USDT-SWAP"
        assert adapter.cancelled[0]["data_name"] == "BTC-USDT-SWAP"
        assert adapter.cancelled[0]["order_id"] == "okx-order-1"
        assert adapter.cancelled[0]["client_order_id"] == "okx-client-1"
        assert adapter.cancelled[0]["order_ref"] == "okx-client-1"

    def test_cancel_gateway_open_orders_unwraps_nested_exchange_payload(self):
        adapter = _FakeRawOrderAdapter(
            {
                "status": "ok",
                "data": {
                    "BTC-USDT-SWAP": [
                        {
                            "instId": "BTC-USDT-SWAP",
                            "ordId": "okx-order-2",
                            "clOrdId": "okx-client-2",
                            "state": "live",
                            "remaining": 1,
                        },
                        {
                            "instId": "BTC-USDT-SWAP",
                            "ordId": "okx-order-closed",
                            "state": "filled",
                        },
                    ]
                },
            }
        )
        gateways = {"gw-1": {"runtime": SimpleNamespace(adapter=adapter)}}

        result = manual_gateway_service.cancel_gateway_open_orders(
            gateways,
            "gw-1",
            owner_ids={"inst-1"},
            cancel_unowned=True,
        )

        assert result["status"] == "ok"
        assert result["open_order_count"] == 1
        assert result["cancelled_count"] == 1
        assert adapter.cancelled[0]["symbol"] == "BTC-USDT-SWAP"
        assert adapter.cancelled[0]["order_id"] == "okx-order-2"
        assert adapter.cancelled[0]["client_order_id"] == "okx-client-2"

    def test_cancel_gateway_open_orders_reports_query_error_payload(self):
        adapter = _FakeRawOrderAdapter({"status": "error", "message": "auth failed"})
        gateways = {"gw-1": {"runtime": SimpleNamespace(adapter=adapter)}}

        result = manual_gateway_service.cancel_gateway_open_orders(
            gateways,
            "gw-1",
            owner_ids={"inst-1"},
            cancel_unowned=True,
        )

        assert result["status"] == "error"
        assert "auth failed" in result["message"]
        assert result["cancelled_count"] == 0
        assert adapter.cancelled == []

    def test_cancel_gateway_open_orders_ignores_terminal_exchange_status_aliases(self):
        adapter = _FakeOrderAdapter(
            [
                {
                    "instId": "BTC-USDT-SWAP",
                    "ordId": "terminal-1",
                    "state": "partially_filled_canceled",
                },
                {
                    "symbol": "IF2609",
                    "order_ref": "terminal-2",
                    "status": "partial-canceled",
                },
                {
                    "symbol": "IF2609",
                    "order_ref": "terminal-3",
                    "status": "expired in match",
                },
                {
                    "symbol": "IF2609",
                    "order_ref": "open-1",
                    "status": "live",
                },
            ]
        )
        gateways = {"gw-1": {"runtime": SimpleNamespace(adapter=adapter)}}

        result = manual_gateway_service.cancel_gateway_open_orders(
            gateways,
            "gw-1",
            owner_ids={"unit-1"},
            cancel_unowned=True,
        )

        assert result["status"] == "ok"
        assert result["open_order_count"] == 1
        assert result["cancelled_count"] == 1
        assert adapter.cancelled == [
            {
                "symbol": "IF2609",
                "order_ref": "open-1",
                "status": "live",
                "data_name": "IF2609",
                "order_id": None,
                "client_order_id": None,
            }
        ]
