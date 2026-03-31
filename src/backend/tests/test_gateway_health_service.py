"""Tests for gateway health service."""

from unittest.mock import MagicMock

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
