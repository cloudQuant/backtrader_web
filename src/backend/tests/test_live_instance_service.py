"""Tests for live_instance_service module."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.live_trading.instance import (
    add_instance,
    get_instance,
    list_instances,
    remove_instance,
    sync_status_on_boot,
)


def _make_deps(**overrides):
    """Build a standard dependency dict for live_instance_service functions."""
    defaults = {
        "load_instances": MagicMock(return_value={}),
        "save_instances": MagicMock(),
        "is_pid_alive": MagicMock(return_value=True),
        "resolve_strategy_dir": MagicMock(return_value=MagicMock()),
        "find_latest_log_dir": MagicMock(return_value="/logs/2024"),
        "scan_running_strategy_pids": MagicMock(return_value={}),
    }
    defaults.update(overrides)
    return defaults


class TestSyncStatusOnBoot:
    def test_marks_dead_processes_as_stopped(self):
        instances = {
            "inst-1": {"status": "running", "pid": 123},
            "inst-2": {"status": "stopped", "pid": None},
        }
        save_fn = MagicMock()
        sync_status_on_boot(
            load_instances=MagicMock(return_value=instances),
            save_instances=save_fn,
            is_pid_alive=MagicMock(return_value=False),
        )
        assert instances["inst-1"]["status"] == "stopped"
        assert instances["inst-1"]["pid"] is None
        save_fn.assert_called_once()

    def test_no_save_when_nothing_changed(self):
        instances = {
            "inst-1": {
                "id": "inst-1",
                "status": "stopped",
                "pid": None,
                "gateway_type": "",
                "updated_at": "2026-06-24 01:00:00",
            }
        }
        save_fn = MagicMock()
        sync_status_on_boot(
            load_instances=MagicMock(return_value=instances),
            save_instances=save_fn,
            is_pid_alive=MagicMock(return_value=True),
        )
        save_fn.assert_not_called()

    def test_keeps_alive_process_running(self):
        instances = {"inst-1": {"status": "running", "pid": 123}}
        sync_status_on_boot(
            load_instances=MagicMock(return_value=instances),
            save_instances=MagicMock(),
            is_pid_alive=MagicMock(return_value=True),
        )
        assert instances["inst-1"]["status"] == "running"


class TestListInstances:
    def test_empty_instances(self):
        deps = _make_deps()
        result = list_instances(user_id=None, **deps)
        assert result == []

    def test_filters_by_user_id(self):
        instances = {
            "inst-1": {"strategy_id": "s1", "user_id": "user-a", "status": "stopped"},
            "inst-2": {"strategy_id": "s2", "user_id": "user-b", "status": "stopped"},
        }
        deps = _make_deps(load_instances=MagicMock(return_value=instances))
        result = list_instances(user_id="user-a", **deps)
        assert len(result) == 1
        assert result[0]["user_id"] == "user-a"

    def test_detects_orphan_running_process(self):
        from pathlib import Path

        strategy_dir = Path("/strategies/ma_cross")
        instances = {
            "inst-1": {"strategy_id": "ma_cross", "status": "stopped", "pid": None},
        }
        deps = _make_deps(
            load_instances=MagicMock(return_value=instances),
            resolve_strategy_dir=MagicMock(return_value=strategy_dir),
            scan_running_strategy_pids=MagicMock(return_value={str(strategy_dir / "run.py"): 9999}),
        )
        result = list_instances(user_id=None, **deps)
        assert result[0]["status"] == "running"
        assert result[0]["pid"] == 9999

    def test_marks_dead_running_instance_as_stopped(self):
        instances = {
            "inst-1": {"strategy_id": "s1", "status": "running", "pid": 123},
        }
        deps = _make_deps(
            load_instances=MagicMock(return_value=instances),
            is_pid_alive=MagicMock(return_value=False),
        )
        result = list_instances(user_id=None, **deps)
        assert result[0]["status"] == "stopped"

    def test_refreshes_updated_at_for_running_instance_when_day_changes(self, monkeypatch):
        instances = {
            "inst-1": {
                "strategy_id": "s1",
                "status": "running",
                "pid": 123,
                "updated_at": "2026-06-23 09:00:00",
            },
        }
        save_instances = MagicMock()
        monkeypatch.setattr(
            "app.services.live_trading.instance.instance_timestamp",
            lambda: "2026-06-24 10:00:00",
        )
        deps = _make_deps(
            load_instances=MagicMock(return_value=instances),
            save_instances=save_instances,
            is_pid_alive=MagicMock(return_value=True),
        )
        list_instances(user_id=None, **deps)
        assert instances["inst-1"]["updated_at"] == "2026-06-24 10:00:00"
        save_instances.assert_called_once()

    def test_does_not_refresh_updated_at_if_same_day(self, monkeypatch):
        instances = {
            "inst-1": {
                "strategy_id": "s1",
                "status": "running",
                "pid": 123,
                "updated_at": "2026-06-24 09:00:00",
            },
        }
        save_instances = MagicMock()
        monkeypatch.setattr(
            "app.services.live_trading.instance.instance_timestamp",
            lambda: "2026-06-24 10:00:00",
        )
        deps = _make_deps(
            load_instances=MagicMock(return_value=instances),
            save_instances=save_instances,
            is_pid_alive=MagicMock(return_value=True),
        )
        list_instances(user_id=None, **deps)
        assert instances["inst-1"]["updated_at"] == "2026-06-24 09:00:00"
        assert save_instances.call_count == 1

    def test_marks_orphan_running_process_as_started_now(self, monkeypatch):
        from pathlib import Path

        instances = {
            "inst-1": {
                "strategy_id": "s1",
                "status": "stopped",
                "pid": None,
                "started_at": "2024-01-01 00:00:00",
                "updated_at": "2026-06-23 09:00:00",
            },
        }
        save_instances = MagicMock()
        monkeypatch.setattr(
            "app.services.live_trading.instance.instance_timestamp",
            lambda: "2026-06-24 10:00:00",
        )
        deps = _make_deps(
            load_instances=MagicMock(return_value=instances),
            save_instances=save_instances,
            is_pid_alive=MagicMock(return_value=True),
            resolve_strategy_dir=MagicMock(return_value=Path("/strategies/s1")),
            scan_running_strategy_pids=MagicMock(return_value={str(Path("/strategies/s1/run.py")): 9001}),
        )
        result = list_instances(user_id=None, **deps)
        assert result[0]["status"] == "running"
        assert result[0]["started_at"] == "2026-06-24 10:00:00"
        assert save_instances.called

    def test_deduplicates_running_instances_for_same_runtime_dir(self, tmp_path):
        runtime_dir = tmp_path / "runtime"
        runtime_dir.mkdir()
        run_py = runtime_dir / "run.py"
        run_py.write_text("print('ok')", encoding="utf-8")
        instances = {
            "old-inst": {
                "strategy_id": "s1",
                "runtime_dir": str(runtime_dir),
                "status": "running",
                "pid": 111,
                "error": "old error",
                "created_at": "2026-06-24 01:00:00",
            },
            "new-inst": {
                "strategy_id": "s1",
                "runtime_dir": str(runtime_dir),
                "status": "running",
                "pid": 111,
                "error": None,
                "created_at": "2026-06-24 02:00:00",
            },
        }
        save_instances = MagicMock()
        deps = _make_deps(
            load_instances=MagicMock(return_value=instances),
            save_instances=save_instances,
            resolve_strategy_dir=MagicMock(return_value=runtime_dir),
        )

        result = list_instances(user_id=None, **deps)

        assert len(result) == 1
        assert result[0]["id"] == "new-inst"
        assert "old-inst" not in instances
        save_instances.assert_called()

    def test_running_instance_without_matched_process_keeps_running_when_pid_alive(self, tmp_path):
        from pathlib import Path

        strategy_dir = tmp_path / "strategy"
        strategy_dir.mkdir()
        (strategy_dir / "run.py").write_text("print('ok')", encoding="utf-8")
        instances = {
            "inst-1": {
                "strategy_id": "s1",
                "status": "running",
                "pid": 123,
                "updated_at": "2026-06-24 09:00:00",
            },
        }
        save_instances = MagicMock()
        deps = _make_deps(
            load_instances=MagicMock(return_value=instances),
            save_instances=save_instances,
            is_pid_alive=MagicMock(return_value=True),
            resolve_strategy_dir=MagicMock(return_value=Path(strategy_dir)),
            scan_running_strategy_pids=MagicMock(return_value={str(Path("/other/run.py")): 999}),
        )

        result = list_instances(user_id=None, **deps)

        assert result[0]["status"] == "running"
        assert result[0]["pid"] == 123
        save_instances.assert_called()

    def test_running_instance_refreshes_stale_started_at(self, tmp_path):
        from pathlib import Path

        strategy_dir = tmp_path / "strategy"
        strategy_dir.mkdir()
        (strategy_dir / "run.py").write_text("print('ok')", encoding="utf-8")
        instances = {
            "inst-1": {
                "strategy_id": "s1",
                "status": "running",
                "pid": 9999,
                "started_at": "2024-01-01 00:00:00",
                "updated_at": "2026-06-24 09:00:00",
            },
        }
        save_instances = MagicMock()
        deps = _make_deps(
            load_instances=MagicMock(return_value=instances),
            save_instances=save_instances,
            is_pid_alive=MagicMock(return_value=True),
            resolve_strategy_dir=MagicMock(return_value=Path(strategy_dir)),
            scan_running_strategy_pids=MagicMock(return_value={str(Path("/other/run.py")): 111}),
        )

        with patch(
            "app.services.live_trading.instance._infer_started_at_from_pid",
            return_value="2026-06-20 10:00:00",
        ):
            result = list_instances(user_id=None, **deps)

        assert result[0]["status"] == "running"
        assert result[0]["pid"] == 9999
        assert result[0]["started_at"] == "2026-06-20 10:00:00"
        assert save_instances.called

    def test_running_instance_pid_mismatch_is_corrected_by_process_scan(self, tmp_path):
        from pathlib import Path

        strategy_dir = tmp_path / "strategy"
        strategy_dir.mkdir()
        run_py = strategy_dir / "run.py"
        run_py.write_text("print('ok')", encoding="utf-8")
        instances = {
            "inst-1": {
                "strategy_id": "s1",
                "status": "running",
                "pid": 123,
                "updated_at": "2026-06-23 09:00:00",
            },
        }
        save_instances = MagicMock()
        deps = _make_deps(
            load_instances=MagicMock(return_value=instances),
            save_instances=save_instances,
            is_pid_alive=MagicMock(return_value=True),
            resolve_strategy_dir=MagicMock(return_value=Path(strategy_dir)),
            scan_running_strategy_pids=MagicMock(return_value={str(run_py): 9001}),
        )

        result = list_instances(user_id=None, **deps)

        assert result[0]["status"] == "running"
        assert result[0]["pid"] == 9001
        assert "started_at" in result[0]
        save_instances.assert_called()


class TestAddInstance:
    def test_creates_instance_with_defaults(self):
        run_py = MagicMock()
        run_py.is_file.return_value = True
        strategy_dir_mock = MagicMock()
        strategy_dir_mock.__truediv__ = MagicMock(return_value=run_py)

        result = add_instance(
            strategy_id="test_strat",
            params=None,
            user_id="user-1",
            load_instances=MagicMock(return_value={}),
            save_instances=MagicMock(),
            resolve_strategy_dir=MagicMock(return_value=strategy_dir_mock),
            get_template_by_id=MagicMock(return_value=None),
            infer_gateway_params=MagicMock(return_value=None),
            find_latest_log_dir=MagicMock(return_value=None),
        )
        assert result["strategy_id"] == "test_strat"
        assert result["user_id"] == "user-1"
        assert result["status"] == "stopped"
        assert result["pid"] is None
        assert "id" in result
        assert result["updated_at"] == result["created_at"]
        assert result["gateway_type"] == ""

    def test_list_backfills_legacy_metadata(self):
        instances = {
            "inst-1": {
                "strategy_id": "s1",
                "status": "stopped",
                "created_at": "2026-06-24 01:00:00",
                "params": {"gateway": {"provider": "ctp_gateway"}},
            },
        }
        save_instances = MagicMock()
        deps = _make_deps(
            load_instances=MagicMock(return_value=instances),
            save_instances=save_instances,
        )

        result = list_instances(user_id=None, **deps)

        assert result[0]["updated_at"] == "2026-06-24 01:00:00"
        assert result[0]["gateway_type"] == "ctp_gateway"
        save_instances.assert_called_once()

    def test_raises_on_invalid_strategy(self):
        with pytest.raises(ValueError, match="Invalid strategy_id"):
            add_instance(
                strategy_id="bad",
                params=None,
                user_id=None,
                load_instances=MagicMock(),
                save_instances=MagicMock(),
                resolve_strategy_dir=MagicMock(side_effect=ValueError("not found")),
                get_template_by_id=MagicMock(),
                infer_gateway_params=MagicMock(),
                find_latest_log_dir=MagicMock(),
            )

    def test_merges_inferred_gateway_params(self):
        strategy_dir = MagicMock()
        run_py_mock = MagicMock()
        run_py_mock.is_file.return_value = True
        strategy_dir.__truediv__ = MagicMock(return_value=run_py_mock)

        inferred = {"enabled": True, "provider": "ctp_gateway"}
        result = add_instance(
            strategy_id="strat",
            params={},
            user_id=None,
            load_instances=MagicMock(return_value={}),
            save_instances=MagicMock(),
            resolve_strategy_dir=MagicMock(return_value=strategy_dir),
            get_template_by_id=MagicMock(return_value=None),
            infer_gateway_params=MagicMock(return_value=inferred),
            find_latest_log_dir=MagicMock(return_value=None),
        )
        assert result["params"]["gateway"] == inferred
        assert result["gateway_type"] == "ctp_gateway"
        assert result["updated_at"] == result["created_at"]

    def test_allows_runtime_dir_without_resolving_strategy_path(self, tmp_path):
        runtime_dir = tmp_path / "runtime"
        runtime_dir.mkdir()
        (runtime_dir / "run.py").write_text("print('ok')", encoding="utf-8")

        result = add_instance(
            strategy_id="simulate/gateway_dual_ma",
            params={},
            user_id="user-1",
            runtime_dir=str(runtime_dir),
            load_instances=MagicMock(return_value={}),
            save_instances=MagicMock(),
            resolve_strategy_dir=MagicMock(side_effect=ValueError("should not be used")),
            get_template_by_id=MagicMock(return_value=None),
            infer_gateway_params=MagicMock(return_value=None),
            find_latest_log_dir=MagicMock(return_value=None),
        )

        assert result["runtime_dir"] == str(runtime_dir)

    def test_reuses_running_instance_for_same_runtime_dir(self, tmp_path):
        runtime_dir = tmp_path / "runtime"
        runtime_dir.mkdir()
        (runtime_dir / "run.py").write_text("print('ok')", encoding="utf-8")
        instances = {
            "old-inst": {
                "strategy_id": "simulate/gateway_dual_ma",
                "runtime_dir": str(runtime_dir),
                "user_id": "user-1",
                "status": "running",
                "pid": 123,
                "error": "old error",
                "created_at": "2026-06-24 01:00:00",
            },
            "new-inst": {
                "strategy_id": "simulate/gateway_dual_ma",
                "runtime_dir": str(runtime_dir),
                "user_id": "user-1",
                "status": "running",
                "pid": 123,
                "error": None,
                "created_at": "2026-06-24 02:00:00",
            },
        }
        save_instances = MagicMock()

        result = add_instance(
            strategy_id="simulate/gateway_dual_ma",
            params={"fast_period": 3},
            user_id="user-1",
            runtime_dir=str(runtime_dir),
            load_instances=MagicMock(return_value=instances),
            save_instances=save_instances,
            resolve_strategy_dir=MagicMock(side_effect=ValueError("should not be used")),
            get_template_by_id=MagicMock(return_value=None),
            infer_gateway_params=MagicMock(return_value=None),
            find_latest_log_dir=MagicMock(return_value=None),
        )

        assert result["id"] == "new-inst"
        assert "old-inst" not in instances
        assert len(instances) == 1
        save_instances.assert_called_once()


class TestRemoveInstance:
    def test_returns_false_when_not_found(self):
        result = remove_instance(
            instance_id="missing",
            user_id=None,
            load_instances=MagicMock(return_value={}),
            save_instances=MagicMock(),
            kill_pid=MagicMock(),
            release_gateway_for_instance=MagicMock(),
            processes={},
        )
        assert result is False

    def test_removes_stopped_instance(self):
        instances = {"inst-1": {"status": "stopped", "pid": None, "user_id": None}}
        save_fn = MagicMock()
        result = remove_instance(
            instance_id="inst-1",
            user_id=None,
            load_instances=MagicMock(return_value=instances),
            save_instances=save_fn,
            kill_pid=MagicMock(),
            release_gateway_for_instance=MagicMock(),
            processes={},
        )
        assert result is True
        save_fn.assert_called_once()

    def test_kills_running_process(self):
        instances = {"inst-1": {"status": "running", "pid": 999, "user_id": None}}
        kill_fn = MagicMock()
        remove_instance(
            instance_id="inst-1",
            user_id=None,
            load_instances=MagicMock(return_value=instances),
            save_instances=MagicMock(),
            kill_pid=kill_fn,
            release_gateway_for_instance=MagicMock(),
            processes={},
        )
        kill_fn.assert_called_once_with(999)

    def test_respects_user_id_ownership(self):
        instances = {"inst-1": {"status": "stopped", "pid": None, "user_id": "owner"}}
        result = remove_instance(
            instance_id="inst-1",
            user_id="other-user",
            load_instances=MagicMock(return_value=instances),
            save_instances=MagicMock(),
            kill_pid=MagicMock(),
            release_gateway_for_instance=MagicMock(),
            processes={},
        )
        assert result is False

    def test_releases_gateway(self):
        instances = {"inst-1": {"status": "stopped", "pid": None, "user_id": None}}
        release_fn = MagicMock()
        remove_instance(
            instance_id="inst-1",
            user_id=None,
            load_instances=MagicMock(return_value=instances),
            save_instances=MagicMock(),
            kill_pid=MagicMock(),
            release_gateway_for_instance=release_fn,
            processes={},
        )
        release_fn.assert_called_once_with("inst-1")


class TestGetInstance:
    def test_returns_none_when_not_found(self):
        result = get_instance(
            instance_id="missing",
            user_id=None,
            load_instances=MagicMock(return_value={}),
            save_instances=MagicMock(),
            is_pid_alive=MagicMock(),
            scan_running_strategy_pids=MagicMock(return_value={}),
            resolve_strategy_dir=MagicMock(),
            find_latest_log_dir=MagicMock(),
        )
        assert result is None

    def test_returns_instance_with_log_dir(self):
        instances = {
            "inst-1": {"strategy_id": "s1", "status": "stopped", "pid": None},
        }
        from pathlib import Path

        result = get_instance(
            instance_id="inst-1",
            user_id=None,
            load_instances=MagicMock(return_value=instances),
            save_instances=MagicMock(),
            is_pid_alive=MagicMock(),
            scan_running_strategy_pids=MagicMock(return_value={}),
            resolve_strategy_dir=MagicMock(return_value=Path("/strats/s1")),
            find_latest_log_dir=MagicMock(return_value="/strats/s1/logs/latest"),
        )
        assert result is not None
        assert result["id"] == "inst-1"
        assert result["log_dir"] == "/strats/s1/logs/latest"

    def test_marks_dead_running_as_stopped(self):
        instances = {
            "inst-1": {"strategy_id": "s1", "status": "running", "pid": 123},
        }
        from pathlib import Path

        result = get_instance(
            instance_id="inst-1",
            user_id=None,
            load_instances=MagicMock(return_value=instances),
            save_instances=MagicMock(),
            is_pid_alive=MagicMock(return_value=False),
            scan_running_strategy_pids=MagicMock(return_value={}),
            resolve_strategy_dir=MagicMock(return_value=Path("/s")),
            find_latest_log_dir=MagicMock(return_value=None),
        )
        assert result["status"] == "stopped"

    def test_refreshes_updated_at_for_running_instance_when_day_changes(self, monkeypatch):
        instances = {
            "inst-1": {
                "strategy_id": "s1",
                "status": "running",
                "pid": 123,
                "updated_at": "2026-06-23 09:00:00",
            },
        }
        save_instances = MagicMock()
        monkeypatch.setattr(
            "app.services.live_trading.instance.instance_timestamp",
            lambda: "2026-06-24 10:00:00",
        )
        from pathlib import Path

        result = get_instance(
            instance_id="inst-1",
            user_id=None,
            load_instances=MagicMock(return_value=instances),
            save_instances=save_instances,
            is_pid_alive=MagicMock(return_value=True),
            scan_running_strategy_pids=MagicMock(return_value={}),
            resolve_strategy_dir=MagicMock(return_value=Path("/s")),
            find_latest_log_dir=MagicMock(return_value=None),
        )
        assert result["updated_at"] == "2026-06-24 10:00:00"
        save_instances.assert_called_once()

    def test_does_not_refresh_updated_at_if_same_day(self, monkeypatch):
        instances = {
            "inst-1": {
                "strategy_id": "s1",
                "status": "running",
                "pid": 123,
                "updated_at": "2026-06-24 09:00:00",
            },
        }
        save_instances = MagicMock()
        monkeypatch.setattr(
            "app.services.live_trading.instance.instance_timestamp",
            lambda: "2026-06-24 10:00:00",
        )
        from pathlib import Path

        result = get_instance(
            instance_id="inst-1",
            user_id=None,
            load_instances=MagicMock(return_value=instances),
            save_instances=save_instances,
            is_pid_alive=MagicMock(return_value=True),
            scan_running_strategy_pids=MagicMock(return_value={}),
            resolve_strategy_dir=MagicMock(return_value=Path("/s")),
            find_latest_log_dir=MagicMock(return_value=None),
        )
        assert result["updated_at"] == "2026-06-24 09:00:00"
        assert save_instances.call_count == 1

    def test_restores_started_at_when_instance_becomes_running(self, monkeypatch):
        instances = {
            "inst-1": {
                "strategy_id": "s1",
                "status": "stopped",
                "pid": None,
                "started_at": "2024-01-01 00:00:00",
                "updated_at": "2026-06-23 09:00:00",
            },
        }
        save_instances = MagicMock()
        monkeypatch.setattr(
            "app.services.live_trading.instance.instance_timestamp",
            lambda: "2026-06-24 10:00:00",
        )
        from pathlib import Path

        result = get_instance(
            instance_id="inst-1",
            user_id=None,
            load_instances=MagicMock(return_value=instances),
            save_instances=save_instances,
            is_pid_alive=MagicMock(return_value=True),
            scan_running_strategy_pids=MagicMock(return_value={str(Path("/s/run.py")): 9001}),
            resolve_strategy_dir=MagicMock(return_value=Path("/s")),
            find_latest_log_dir=MagicMock(return_value=None),
        )
        assert result["status"] == "running"
        assert result["started_at"] == "2026-06-24 10:00:00"
        assert save_instances.called

    def test_running_instance_with_mismatched_pid_is_corrected_by_scan(self, tmp_path, monkeypatch):
        strategy_dir = tmp_path / "strategy"
        strategy_dir.mkdir()
        run_py = strategy_dir / "run.py"
        run_py.write_text("print('ok')", encoding="utf-8")
        instances = {
            "inst-1": {
                "strategy_id": "s1",
                "status": "running",
                "pid": 123,
                "updated_at": "2026-06-23 09:00:00",
            },
        }
        save_instances = MagicMock()
        monkeypatch.setattr(
            "app.services.live_trading.instance.instance_timestamp",
            lambda: "2026-06-24 10:00:00",
        )

        result = get_instance(
            instance_id="inst-1",
            user_id=None,
            load_instances=MagicMock(return_value=instances),
            save_instances=save_instances,
            is_pid_alive=MagicMock(return_value=True),
            scan_running_strategy_pids=MagicMock(return_value={str(run_py): 9001}),
            resolve_strategy_dir=MagicMock(return_value=tmp_path / "strategy"),
            find_latest_log_dir=MagicMock(return_value=None),
        )

        assert result is not None
        assert result["status"] == "running"
        assert result["pid"] == 9001
        assert result["started_at"] == "2026-06-24 10:00:00"
        save_instances.assert_called_once()

    def test_running_instance_with_no_scan_match_keeps_running_when_pid_alive(self, monkeypatch, tmp_path):
        from pathlib import Path

        strategy_dir = tmp_path / "strategy"
        strategy_dir.mkdir()
        (strategy_dir / "run.py").write_text("print('ok')", encoding="utf-8")
        instances = {
            "inst-1": {
                "strategy_id": "s1",
                "status": "running",
                "pid": 123,
                "updated_at": "2026-06-23 09:00:00",
            },
        }
        save_instances = MagicMock()
        monkeypatch.setattr(
            "app.services.live_trading.instance.instance_timestamp",
            lambda: "2026-06-24 10:00:00",
        )

        result = get_instance(
            instance_id="inst-1",
            user_id=None,
            load_instances=MagicMock(return_value=instances),
            save_instances=save_instances,
            is_pid_alive=MagicMock(return_value=True),
            scan_running_strategy_pids=MagicMock(return_value={str(Path("/other/run.py")): 9001}),
            resolve_strategy_dir=MagicMock(return_value=tmp_path / "strategy"),
            find_latest_log_dir=MagicMock(return_value=None),
        )

        assert result is not None
        assert result["status"] == "running"
        assert result["pid"] == 123
        save_instances.assert_called_once()

    def test_running_instance_refreshes_stale_started_at_from_pid(self, tmp_path):
        from pathlib import Path

        strategy_dir = tmp_path / "strategy"
        strategy_dir.mkdir()
        (strategy_dir / "run.py").write_text("print('ok')", encoding="utf-8")
        instances = {
            "inst-1": {
                "strategy_id": "s1",
                "status": "running",
                "pid": 9999,
                "started_at": "2024-01-01 00:00:00",
                "updated_at": "2026-06-23 09:00:00",
            },
        }
        save_instances = MagicMock()
        with patch(
            "app.services.live_trading.instance._infer_started_at_from_pid",
            return_value="2026-06-20 10:00:00",
        ):
            result = get_instance(
                instance_id="inst-1",
                user_id=None,
                load_instances=MagicMock(return_value=instances),
                save_instances=save_instances,
                is_pid_alive=MagicMock(return_value=True),
                scan_running_strategy_pids=MagicMock(return_value={str(Path("/other/run.py")): 9001}),
                resolve_strategy_dir=MagicMock(return_value=tmp_path / "strategy"),
                find_latest_log_dir=MagicMock(return_value=None),
            )

        assert result is not None
        assert result["status"] == "running"
        assert result["pid"] == 9999
        assert result["started_at"] == "2026-06-20 10:00:00"
        assert save_instances.call_count == 1

    def test_recovers_non_running_instance_when_runtime_process_exists(self, tmp_path):
        runtime_dir = tmp_path / "workspace_units" / "ws-1" / "unit-1"
        runtime_dir.mkdir(parents=True)
        run_py = runtime_dir / "run.py"
        run_py.write_text("print('ok')", encoding="utf-8")
        instances = {
            "inst-1": {
                "strategy_id": "simulate/gateway_dual_ma",
                "runtime_dir": str(runtime_dir),
                "status": "error",
                "pid": None,
                "error": "stale stderr",
            },
        }
        save_instances = MagicMock()

        result = get_instance(
            instance_id="inst-1",
            user_id=None,
            load_instances=MagicMock(return_value=instances),
            save_instances=save_instances,
            is_pid_alive=MagicMock(return_value=True),
            scan_running_strategy_pids=MagicMock(return_value={str(run_py): 4321}),
            resolve_strategy_dir=MagicMock(),
            find_latest_log_dir=MagicMock(return_value=str(runtime_dir / "logs")),
        )

        assert result["status"] == "running"
        assert result["pid"] == 4321
        assert result["error"] is None
        assert result["updated_at"]
        save_instances.assert_called()

    def test_prefers_runtime_dir_for_log_lookup(self, tmp_path):
        runtime_dir = tmp_path / "runtime"
        runtime_dir.mkdir()
        instances = {
            "inst-1": {
                "strategy_id": "simulate/gateway_dual_ma",
                "runtime_dir": str(runtime_dir),
                "status": "stopped",
                "pid": None,
            },
        }

        resolve_strategy_dir = MagicMock()
        find_latest_log_dir = MagicMock(return_value=str(runtime_dir / "logs"))

        result = get_instance(
            instance_id="inst-1",
            user_id=None,
            load_instances=MagicMock(return_value=instances),
            save_instances=MagicMock(),
            is_pid_alive=MagicMock(),
            scan_running_strategy_pids=MagicMock(return_value={}),
            resolve_strategy_dir=resolve_strategy_dir,
            find_latest_log_dir=find_latest_log_dir,
        )

        assert result is not None
        assert result["log_dir"] == str(runtime_dir / "logs")
        resolve_strategy_dir.assert_not_called()

    def test_denies_access_to_other_user(self):
        instances = {
            "inst-1": {"strategy_id": "s1", "status": "stopped", "user_id": "owner"},
        }
        result = get_instance(
            instance_id="inst-1",
            user_id="intruder",
            load_instances=MagicMock(return_value=instances),
            save_instances=MagicMock(),
            is_pid_alive=MagicMock(),
            scan_running_strategy_pids=MagicMock(return_value={}),
            resolve_strategy_dir=MagicMock(),
            find_latest_log_dir=MagicMock(),
        )
        assert result is None
