from unittest.mock import Mock, patch

from app.services import ctp_tunnel
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
