from unittest.mock import Mock, patch

from app.services.gateway import manual_ctp_proxy, manual_ports


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
