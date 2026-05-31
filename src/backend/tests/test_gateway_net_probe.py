"""Unit tests for ``app.services.gateway.net_probe`` (iteration 179 §B).

These cover the pure network-probe helpers extracted from ``gateway/manual.py``
(P1#4 slice 1) plus the psutil-first utun interface count (slice 4).
"""

from unittest.mock import Mock, patch

from app.services.gateway import manual, net_probe


class TestExtractPortFromZmqError:
    def test_parses_port_from_address_in_use(self):
        msg = "zmq.error.ZMQError: Address already in use (tcp://127.0.0.1:58583)"
        assert net_probe.extract_port_from_zmq_error(msg) == 58583

    def test_returns_none_when_no_port(self):
        assert net_probe.extract_port_from_zmq_error("no port here") is None

    def test_facade_in_manual_is_same_callable(self):
        assert manual._extract_port_from_zmq_error is net_probe.extract_port_from_zmq_error


class TestErrorMessageHelpers:
    def test_extract_from_dict_entry(self):
        assert net_probe.extract_err_msg_from_error_entry({"message": "  boom  "}) == "boom"

    def test_extract_from_plain_string(self):
        assert net_probe.extract_err_msg_from_error_entry("  oops ") == "oops"

    def test_is_address_in_use_true(self):
        assert net_probe.is_address_in_use_error("Address already in use") is True
        assert net_probe.is_address_in_use_error("address in use") is True

    def test_is_address_in_use_false(self):
        assert net_probe.is_address_in_use_error("connection refused") is False
        assert net_probe.is_address_in_use_error("") is False

    def test_find_recent_bind_error_returns_latest_match(self):
        snapshot = {
            "recent_errors": [
                "connection refused",
                {"message": "Address already in use (tcp://x:5001)"},
                "timeout",
            ]
        }
        assert "5001" in net_probe.find_recent_bind_error(snapshot)

    def test_find_recent_bind_error_handles_bad_shapes(self):
        assert net_probe.find_recent_bind_error(None) == ""
        assert net_probe.find_recent_bind_error({"recent_errors": "nope"}) == ""
        assert net_probe.find_recent_bind_error({}) == ""


class TestFrontEndpointParsing:
    def test_parse_tcp_front_endpoint(self):
        assert net_probe.parse_tcp_front_endpoint("tcp://1.2.3.4:5678") == ("1.2.3.4", 5678)

    def test_parse_lowercases_host(self):
        assert net_probe.parse_tcp_front_endpoint("tcp://Host.EXAMPLE:9") == ("host.example", 9)

    def test_parse_returns_none_pair_on_bad_input(self):
        assert net_probe.parse_tcp_front_endpoint("") == (None, None)
        assert net_probe.parse_tcp_front_endpoint("not-a-url") == (None, None)

    def test_extract_ips_dedups_and_skips_loopback_and_hostnames(self):
        ips = net_probe.extract_ips_from_fronts(
            "tcp://1.2.3.4:1",
            "tcp://1.2.3.4:2",  # duplicate IP
            "tcp://127.0.0.1:3",  # loopback skipped
            "tcp://example.com:4",  # hostname skipped (not an IP)
        )
        assert ips == ["1.2.3.4"]


class TestUtunCountSlice4:
    def test_prefers_psutil_no_subprocess(self):
        fake_psutil = Mock()
        fake_psutil.net_if_addrs.return_value = {"en0": [], "utun0": [], "utun1": []}
        with (
            patch.dict("sys.modules", {"psutil": fake_psutil}),
            patch.object(manual.subprocess, "run") as mock_run,
        ):
            assert manual._count_utun_interfaces() == 2
        mock_run.assert_not_called()

    def test_falls_back_to_ifconfig_when_psutil_missing(self):
        import builtins

        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "psutil":
                raise ImportError
            return original_import(name, *args, **kwargs)

        with (
            patch("builtins.__import__", side_effect=fake_import),
            patch.object(
                manual.subprocess,
                "run",
                return_value=Mock(stdout="utun0\nutun1\nutun2\n"),
            ) as mock_run,
        ):
            assert manual._count_utun_interfaces() == 3
        assert mock_run.call_args.args[0] == ["ifconfig"]
