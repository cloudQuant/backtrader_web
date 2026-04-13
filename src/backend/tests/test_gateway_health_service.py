"""Tests for gateway health service."""

from unittest.mock import MagicMock, patch

from app.services.gateway_health_service import get_gateway_health


def _make_health_snap(**overrides):
    defaults = {
        "state": "running",
        "is_healthy": True,
        "exchange": "BINANCE",
        "asset_type": "SPOT",
        "account_id": "acc-1",
        "market_connection": "connected",
        "trade_connection": "connected",
        "uptime_sec": 120,
        "strategy_count": 1,
        "symbol_count": 5,
        "tick_count": 1000,
        "order_count": 3,
        "heartbeat_age_sec": 2,
        "recent_errors": [],
    }
    defaults.update(overrides)
    return defaults


class TestGetGatewayHealth:
    def test_empty_gateways(self):
        results = get_gateway_health(
            gateways={},
            load_instances=lambda: {},
            is_pid_alive=lambda pid: False,
            resolve_strategy_dir=lambda s: f"/strategies/{s}",
            load_strategy_config=lambda d: {},
            load_strategy_env=lambda d: {},
        )
        assert results == []

    def test_gateway_with_runtime(self):
        health_mock = MagicMock()
        health_mock.snapshot.return_value = _make_health_snap()
        runtime_mock = MagicMock()
        runtime_mock.health = health_mock

        gateways = {
            "binance:spot:acc1": {
                "runtime": runtime_mock,
                "ref_count": 2,
                "instances": {"inst-1", "inst-2"},
            }
        }

        results = get_gateway_health(
            gateways=gateways,
            load_instances=lambda: {},
            is_pid_alive=lambda pid: False,
            resolve_strategy_dir=lambda s: f"/strategies/{s}",
            load_strategy_config=lambda d: {},
            load_strategy_env=lambda d: {},
        )
        assert len(results) == 1
        assert results[0]["gateway_key"] == "binance:spot:acc1"
        assert results[0]["ref_count"] == 2
        assert sorted(results[0]["instances"]) == ["inst-1", "inst-2"]

    def test_gateway_with_runtime_connected_market_normalizes_trade_connection(self):
        health_mock = MagicMock()
        health_mock.snapshot.return_value = _make_health_snap(trade_connection="disconnected")
        runtime_mock = MagicMock()
        runtime_mock.health = health_mock

        gateways = {
            "manual:BINANCE:acc1": {
                "runtime": runtime_mock,
                "manual": True,
                "ref_count": 0,
                "instances": set(),
            }
        }

        results = get_gateway_health(
            gateways=gateways,
            load_instances=lambda: {},
            is_pid_alive=lambda pid: False,
            resolve_strategy_dir=lambda s: f"/strategies/{s}",
            load_strategy_config=lambda d: {},
            load_strategy_env=lambda d: {},
        )

        assert len(results) == 1
        assert results[0]["market_connection"] == "connected"
        assert results[0]["trade_connection"] == "connected"
        assert results[0]["ref_count"] == 1

    def test_gateway_with_runtime_derives_heartbeat_age_from_last_heartbeat(self):
        health_mock = MagicMock()
        health_mock.snapshot.return_value = _make_health_snap(
            heartbeat_age_sec=None,
            last_heartbeat=95.0,
        )
        runtime_mock = MagicMock()
        runtime_mock.health = health_mock

        gateways = {
            "binance:spot:acc1": {
                "runtime": runtime_mock,
                "ref_count": 0,
                "instances": {"inst-1", "inst-2"},
            }
        }

        with patch("app.services.gateway_health_service.time.time", return_value=100.0):
            results = get_gateway_health(
                gateways=gateways,
                load_instances=lambda: {},
                is_pid_alive=lambda pid: False,
                resolve_strategy_dir=lambda s: f"/strategies/{s}",
                load_strategy_config=lambda d: {},
                load_strategy_env=lambda d: {},
            )

        assert len(results) == 1
        assert results[0]["heartbeat_age_sec"] == 5
        assert results[0]["ref_count"] == 2

    def test_gateway_without_runtime_skipped(self):
        gateways = {"orphan": {"runtime": None}}
        results = get_gateway_health(
            gateways=gateways,
            load_instances=lambda: {},
            is_pid_alive=lambda pid: False,
            resolve_strategy_dir=lambda s: f"/strategies/{s}",
            load_strategy_config=lambda d: {},
            load_strategy_env=lambda d: {},
        )
        assert results == []

    def test_manual_gateway_without_runtime_reported_as_registered(self):
        gateways = {
            "manual:BINANCE:test-account": {
                "runtime": None,
                "manual": True,
                "exchange_type": "BINANCE",
                "asset_type": "SPOT",
                "account_id": "test-account",
                "ref_count": 0,
                "instances": set(),
            }
        }
        results = get_gateway_health(
            gateways=gateways,
            load_instances=lambda: {},
            is_pid_alive=lambda pid: False,
            resolve_strategy_dir=lambda s: f"/strategies/{s}",
            load_strategy_config=lambda d: {},
            load_strategy_env=lambda d: {},
        )
        assert len(results) == 1
        snap = results[0]
        assert snap["gateway_key"] == "manual:BINANCE:test-account"
        assert snap["state"] == "registered"
        assert snap["market_connection"] == "not_started"
        assert snap["trade_connection"] == "not_started"
        assert snap["exchange"] == "BINANCE"
        assert snap["asset_type"] == "SPOT"
        assert snap["account_id"] == "test-account"

    def test_malformed_gateway_state_is_skipped(self):
        health_mock = MagicMock()
        health_mock.snapshot.return_value = _make_health_snap()
        runtime_mock = MagicMock()
        runtime_mock.health = health_mock

        results = get_gateway_health(
            gateways={
                "malformed": object(),
                "manual:BINANCE:test-account": {
                    "runtime": runtime_mock,
                    "manual": True,
                    "exchange_type": "BINANCE",
                    "account_id": "test-account",
                    "instances": set(),
                    "ref_count": 0,
                },
            },
            load_instances=lambda: {},
            is_pid_alive=lambda pid: False,
            resolve_strategy_dir=lambda s: f"/strategies/{s}",
            load_strategy_config=lambda d: {},
            load_strategy_env=lambda d: {},
        )

        assert len(results) == 1
        assert results[0]["gateway_key"] == "manual:BINANCE:test-account"

    def test_non_dict_instances_payload_is_ignored(self):
        health_mock = MagicMock()
        health_mock.snapshot.return_value = _make_health_snap()
        runtime_mock = MagicMock()
        runtime_mock.health = health_mock

        results = get_gateway_health(
            gateways={
                "binance:spot:acc1": {
                    "runtime": runtime_mock,
                    "ref_count": 1,
                    "instances": {"inst-1"},
                }
            },
            load_instances=lambda: ["bad-payload"],
            is_pid_alive=lambda pid: False,
            resolve_strategy_dir=lambda s: f"/strategies/{s}",
            load_strategy_config=lambda d: {},
            load_strategy_env=lambda d: {},
        )

        assert len(results) == 1
        assert results[0]["gateway_key"] == "binance:spot:acc1"

    def test_direct_process_instance(self):
        """Running instances not attached to a gateway get a 'direct:' entry."""
        instances = {
            "inst-standalone": {
                "status": "running",
                "pid": 12345,
                "strategy_id": "ma_cross",
                "strategy_name": "MA Cross",
            }
        }

        results = get_gateway_health(
            gateways={},
            load_instances=lambda: instances,
            is_pid_alive=lambda pid: pid == 12345,
            resolve_strategy_dir=lambda s: f"/strategies/{s}",
            load_strategy_config=lambda d: {"ctp": {"investor_id": "inv-001"}},
            load_strategy_env=lambda d: {},
        )
        assert len(results) == 1
        r = results[0]
        assert r["gateway_key"] == "direct:ma_cross"
        assert r["is_healthy"] is True
        assert r["account_id"] == "inv-001"
        assert r["strategy_name"] == "MA Cross"
        assert "inst-standalone" in r["instances"]

    def test_direct_instance_skipped_if_not_running(self):
        instances = {"inst-1": {"status": "stopped", "pid": 12345, "strategy_id": "test"}}
        results = get_gateway_health(
            gateways={},
            load_instances=lambda: instances,
            is_pid_alive=lambda pid: True,
            resolve_strategy_dir=lambda s: f"/strategies/{s}",
            load_strategy_config=lambda d: {},
            load_strategy_env=lambda d: {},
        )
        assert results == []

    def test_direct_instance_skipped_if_pid_dead(self):
        instances = {
            "inst-1": {"status": "running", "pid": 99999, "strategy_id": "test"}
        }
        results = get_gateway_health(
            gateways={},
            load_instances=lambda: instances,
            is_pid_alive=lambda pid: False,
            resolve_strategy_dir=lambda s: f"/strategies/{s}",
            load_strategy_config=lambda d: {},
            load_strategy_env=lambda d: {},
        )
        assert results == []

    def test_direct_instance_skipped_if_already_in_gateway(self):
        """Instances already managed by a gateway should not get a duplicate entry."""
        health_mock = MagicMock()
        health_mock.snapshot.return_value = _make_health_snap()
        runtime_mock = MagicMock()
        runtime_mock.health = health_mock

        gateways = {
            "binance:spot:acc1": {
                "runtime": runtime_mock,
                "ref_count": 1,
                "instances": {"inst-1"},
            }
        }
        instances = {
            "inst-1": {"status": "running", "pid": 12345, "strategy_id": "test"}
        }

        results = get_gateway_health(
            gateways=gateways,
            load_instances=lambda: instances,
            is_pid_alive=lambda pid: True,
            resolve_strategy_dir=lambda s: f"/strategies/{s}",
            load_strategy_config=lambda d: {},
            load_strategy_env=lambda d: {},
        )
        assert len(results) == 1  # Only the gateway entry, no duplicate

    def test_env_account_id_precedence(self):
        """Environment CTP_INVESTOR_ID takes priority over config."""
        instances = {
            "inst-1": {"status": "running", "pid": 1, "strategy_id": "test"}
        }
        results = get_gateway_health(
            gateways={},
            load_instances=lambda: instances,
            is_pid_alive=lambda pid: True,
            resolve_strategy_dir=lambda s: f"/strategies/{s}",
            load_strategy_config=lambda d: {"ctp": {"investor_id": "from-config"}},
            load_strategy_env=lambda d: {"CTP_INVESTOR_ID": "from-env"},
        )
        assert results[0]["account_id"] == "from-env"

    def test_strategy_config_load_failure(self):
        """Config load failure should not crash; account_id defaults to empty."""
        instances = {
            "inst-1": {"status": "running", "pid": 1, "strategy_id": "test"}
        }
        results = get_gateway_health(
            gateways={},
            load_instances=lambda: instances,
            is_pid_alive=lambda pid: True,
            resolve_strategy_dir=lambda s: (_ for _ in ()).throw(ValueError("not found")),
            load_strategy_config=lambda d: {},
            load_strategy_env=lambda d: {},
        )
        assert len(results) == 1
        assert results[0]["account_id"] == ""

    def test_runtime_without_health_attribute(self):
        """Runtime with health=None should return empty snapshot."""
        runtime_mock = MagicMock()
        runtime_mock.health = None

        gateways = {"key": {"runtime": runtime_mock, "ref_count": 0, "instances": set()}}
        results = get_gateway_health(
            gateways=gateways,
            load_instances=lambda: {},
            is_pid_alive=lambda pid: False,
            resolve_strategy_dir=lambda s: "",
            load_strategy_config=lambda d: {},
            load_strategy_env=lambda d: {},
        )
        assert len(results) == 1
        assert results[0]["gateway_key"] == "key"

    def test_runtime_snapshot_error_degrades_to_error_entry(self):
        """Snapshot failures should not crash the entire health listing."""
        health_mock = MagicMock()
        health_mock.snapshot.side_effect = RuntimeError("adapter state unavailable")
        runtime_mock = MagicMock()
        runtime_mock.health = health_mock

        gateways = {
            "manual:CTP:089763": {
                "runtime": runtime_mock,
                "manual": True,
                "exchange_type": "CTP",
                "asset_type": "FUTURE",
                "account_id": "089763",
                "ref_count": 0,
                "instances": set(),
            }
        }

        results = get_gateway_health(
            gateways=gateways,
            load_instances=lambda: {},
            is_pid_alive=lambda pid: False,
            resolve_strategy_dir=lambda s: "",
            load_strategy_config=lambda d: {},
            load_strategy_env=lambda d: {},
        )

        assert len(results) == 1
        snap = results[0]
        assert snap["gateway_key"] == "manual:CTP:089763"
        assert snap["state"] == "error"
        assert snap["is_healthy"] is False
        assert snap["market_connection"] == "error"
        assert snap["trade_connection"] == "error"
        assert snap["recent_errors"] == [
            {
                "source": "health_snapshot",
                "message": "RuntimeError: adapter state unavailable",
            }
        ]

    def test_runtime_snapshot_non_dict_degrades_to_error_entry(self):
        """Unexpected snapshot types should be converted into an error entry."""
        health_mock = MagicMock()
        health_mock.snapshot.return_value = ["unexpected"]
        runtime_mock = MagicMock()
        runtime_mock.health = health_mock

        gateways = {
            "manual:BINANCE:acc-1": {
                "runtime": runtime_mock,
                "manual": True,
                "exchange_type": "BINANCE",
                "asset_type": "SPOT",
                "account_id": "acc-1",
                "ref_count": 1,
                "instances": {"inst-1"},
            }
        }

        results = get_gateway_health(
            gateways=gateways,
            load_instances=lambda: {},
            is_pid_alive=lambda pid: False,
            resolve_strategy_dir=lambda s: "",
            load_strategy_config=lambda d: {},
            load_strategy_env=lambda d: {},
        )

        assert len(results) == 1
        snap = results[0]
        assert snap["gateway_key"] == "manual:BINANCE:acc-1"
        assert snap["state"] == "error"
        assert snap["instances"] == ["inst-1"]
        assert snap["recent_errors"] == [
            {
                "source": "health_snapshot",
                "message": "TypeError: health.snapshot() returned list, expected dict",
            }
        ]

    def test_ib_web_health_uses_cached_quote_metrics_when_runtime_tick_count_is_zero(self):
        health_mock = MagicMock()
        health_mock.snapshot.return_value = _make_health_snap(
            exchange="IB_WEB",
            asset_type="STK",
            market_connection="connected",
            trade_connection="connected",
            symbol_count=0,
            tick_count=0,
            last_tick_time=None,
        )
        runtime_mock = MagicMock()
        runtime_mock.health = health_mock

        gateways = {
            "manual:IB_WEB:DU123": {
                "runtime": runtime_mock,
                "manual": True,
                "exchange_type": "IB_WEB",
                "asset_type": "STK",
                "account_id": "DU123",
                "ref_count": 1,
                "instances": set(),
            }
        }

        quote_service = MagicMock()
        quote_service.get_cached_tick_metrics.return_value = {
            "tick_count": 3,
            "last_tick_time": 1712840400,
        }

        with patch("app.services.quote_service.QuoteService", return_value=quote_service):
            results = get_gateway_health(
                gateways=gateways,
                load_instances=lambda: {},
                is_pid_alive=lambda pid: False,
                resolve_strategy_dir=lambda s: "",
                load_strategy_config=lambda d: {},
                load_strategy_env=lambda d: {},
            )

        assert len(results) == 1
        snap = results[0]
        assert snap["tick_count"] == 3
        assert snap["symbol_count"] == 3
        assert snap["last_tick_time"] == 1712840400

    def test_non_ib_web_health_does_not_use_cached_quote_metrics(self):
        health_mock = MagicMock()
        health_mock.snapshot.return_value = _make_health_snap(
            exchange="BINANCE",
            symbol_count=0,
            tick_count=0,
            last_tick_time=None,
        )
        runtime_mock = MagicMock()
        runtime_mock.health = health_mock

        gateways = {
            "manual:BINANCE:acc-1": {
                "runtime": runtime_mock,
                "manual": True,
                "exchange_type": "BINANCE",
                "asset_type": "SPOT",
                "account_id": "acc-1",
                "ref_count": 1,
                "instances": set(),
            }
        }

        with patch("app.services.quote_service.QuoteService") as quote_service_cls:
            results = get_gateway_health(
                gateways=gateways,
                load_instances=lambda: {},
                is_pid_alive=lambda pid: False,
                resolve_strategy_dir=lambda s: "",
                load_strategy_config=lambda d: {},
                load_strategy_env=lambda d: {},
            )

        assert len(results) == 1
        snap = results[0]
        assert snap["tick_count"] == 0
        assert snap["symbol_count"] == 0
        quote_service_cls.assert_not_called()
