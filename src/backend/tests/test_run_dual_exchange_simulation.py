import importlib.util
import warnings
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest


def _load_script_module():
    script_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "run_dual_exchange_simulation.py"
    )
    spec = importlib.util.spec_from_file_location("run_dual_exchange_simulation_test", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_any_targets_running_detects_active_units():
    module = _load_script_module()

    assert module.any_targets_running({"futures": Counter({"running": 1})}) is True
    assert (
        module.any_targets_running({"futures": Counter({"idle": 50, "process_alive": 50})}) is True
    )
    assert module.any_targets_running({"futures": Counter({"idle": 50})}) is False


def test_stress_script_suppresses_default_admin_password_warning():
    module = _load_script_module()
    message = (
        "Insecure default admin password detected. "
        "Change ADMIN_PASSWORD before shared or production use."
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("default")
        module._suppress_default_admin_warning_for_stress_script()
        warnings.warn(message, UserWarning, stacklevel=2)

    assert caught == []


def test_stress_script_keeps_unrelated_user_warnings_visible():
    module = _load_script_module()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("default")
        module._suppress_default_admin_warning_for_stress_script()
        warnings.warn("different operational warning", UserWarning, stacklevel=2)

    assert len(caught) == 1


def test_configure_local_source_paths_prepends_local_sources(tmp_path):
    module = _load_script_module()
    backtrader_dir = tmp_path / "backtrader"
    bt_api_dir = tmp_path / "bt_api_py" / "bt_api_py"
    backtrader_dir.mkdir()
    bt_api_dir.mkdir(parents=True)
    env = {"PYTHONPATH": f"/existing{module.os.pathsep}{bt_api_dir}"}
    sys_path = ["/existing", str(backtrader_dir)]

    module.configure_local_source_paths(
        env=env,
        sys_path=sys_path,
        source_paths=[backtrader_dir, bt_api_dir],
    )

    assert env["PYTHONPATH"].split(module.os.pathsep) == [
        str(backtrader_dir),
        str(bt_api_dir),
        "/existing",
    ]
    assert sys_path[:2] == [str(backtrader_dir), str(bt_api_dir)]


def test_parse_args_supports_monitor_only(monkeypatch):
    module = _load_script_module()

    monkeypatch.setattr(
        module.sys,
        "argv",
        ["run_dual_exchange_simulation.py", "--monitor-only", "--no-monitor-after-hold"],
    )

    args = module.parse_args()

    assert args.monitor_only is True
    assert args.no_monitor_after_hold is True


def test_parse_args_supports_unit_id_filter(monkeypatch):
    module = _load_script_module()

    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "run_dual_exchange_simulation.py",
            "--targets",
            "futures",
            "--unit-ids",
            "unit-a, unit-b",
        ],
    )

    args = module.parse_args()

    assert args.targets == "futures"
    assert module.parse_unit_ids(args.unit_ids) == {"unit-a", "unit-b"}


def test_parse_target_keys_supports_all_three_gateway_workspaces():
    module = _load_script_module()

    assert module.parse_target_keys("futures,ib,mt5") == ("futures", "ib", "mt5")


def test_parse_args_supports_rolling_restart_options(monkeypatch):
    module = _load_script_module()

    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "run_dual_exchange_simulation.py",
            "--rolling-restart",
            "--rolling-batch-size",
            "3",
            "--rolling-batch-wait-seconds",
            "12",
            "--rolling-batch-start-attempts",
            "4",
            "--rolling-batch-retry-wait-seconds",
            "9",
            "--skip-fresh-heartbeats",
            "--skip-fresh-data-logs",
            "--no-stop-owned-on-signal",
        ],
    )

    args = module.parse_args()

    assert args.rolling_restart is True
    assert args.rolling_batch_size == 3
    assert args.rolling_batch_wait_seconds == 12
    assert args.rolling_batch_start_attempts == 4
    assert args.rolling_batch_retry_wait_seconds == 9
    assert args.skip_fresh_heartbeats is True
    assert args.skip_fresh_data_logs is True
    assert args.no_stop_owned_on_signal is True


def test_has_owned_started_units_detects_supervisor_owned_children():
    module = _load_script_module()

    assert module.has_owned_started_units({"futures": {"unit-a"}, "mt5": set()}) is True
    assert module.has_owned_started_units({"futures": set(), "mt5": set()}) is False


def test_chunked_units_never_uses_empty_batch_size():
    module = _load_script_module()
    units = [SimpleNamespace(id=str(index)) for index in range(3)]

    assert [[unit.id for unit in batch] for batch in module.chunked_units(units, 2)] == [
        ["0", "1"],
        ["2"],
    ]
    assert [[unit.id for unit in batch] for batch in module.chunked_units(units, 0)] == [
        ["0"],
        ["1"],
        ["2"],
    ]


def test_filter_units_for_rolling_restart_skips_only_fresh_heartbeats(monkeypatch):
    module = _load_script_module()
    units = [
        SimpleNamespace(id="fresh"),
        SimpleNamespace(id="stale"),
        SimpleNamespace(id="missing"),
        SimpleNamespace(id="not-running"),
    ]
    states = {
        "fresh": "fresh",
        "stale": "stale",
        "missing": "missing",
        "not-running": "not_running",
    }

    monkeypatch.setattr(
        module,
        "unit_heartbeat_state",
        lambda unit, **_kwargs: states[unit.id],
    )

    selected = module.filter_units_for_rolling_restart(
        units,
        skip_fresh_heartbeats=True,
        live_processes={},
    )

    assert [unit.id for unit in selected] == ["stale", "missing", "not-running"]
    assert (
        module.filter_units_for_rolling_restart(
            units,
            skip_fresh_heartbeats=False,
            live_processes={},
        )
        == units
    )


def test_filter_units_for_rolling_restart_skips_fresh_data_logs(monkeypatch):
    module = _load_script_module()
    units = [
        SimpleNamespace(id="fresh"),
        SimpleNamespace(id="quiet"),
        SimpleNamespace(id="warmup"),
        SimpleNamespace(id="stale"),
        SimpleNamespace(id="missing"),
        SimpleNamespace(id="not-running"),
    ]
    states = {
        "fresh": "fresh",
        "quiet": "quiet",
        "warmup": "warmup",
        "stale": "stale",
        "missing": "missing",
        "not-running": "not_running",
    }

    monkeypatch.setattr(
        module,
        "unit_data_log_state",
        lambda unit, **_kwargs: states[unit.id],
    )

    selected = module.filter_units_for_rolling_restart(
        units,
        skip_fresh_heartbeats=False,
        skip_fresh_data_logs=True,
        live_processes={},
    )

    assert [unit.id for unit in selected] == ["stale", "missing", "not-running"]


@pytest.mark.asyncio
async def test_rolling_restart_targets_batches_and_checks_each_batch(monkeypatch):
    module = _load_script_module()
    monkeypatch.setattr(module, "TARGET_WORKSPACE_KEYS", ("futures",))
    units = [
        SimpleNamespace(id="unit-a", strategy_name="strategy-a"),
        SimpleNamespace(id="unit-b", strategy_name="strategy-b"),
    ]
    workspace = SimpleNamespace(id="ws-futures", user_id="user-1")
    restarted: list[tuple[str, list[str]]] = []
    slept: list[int] = []
    status_calls: list[tuple[set[str] | None, tuple[str, ...] | None]] = []
    printed: list[tuple[str, tuple[str, ...] | None]] = []

    async def fake_load_target_units(_workspace, _specs, unit_ids=None):
        assert unit_ids == {"requested"}
        return units, []

    async def fake_restart_target_batch(key, _workspace, batch, **kwargs):
        assert kwargs == {"start_attempts": 2, "retry_wait_seconds": 30}
        restarted.append((key, [unit.id for unit in batch]))
        return Counter({"running": len(batch)}), {unit.id for unit in batch}

    async def fake_status_summary(_workspaces, _specs_by_key, unit_ids=None, target_keys=None):
        status_calls.append((set(unit_ids or set()), target_keys))
        return {"futures": Counter({"running": len(unit_ids or set())})}

    def fake_print_status(prefix, _summaries, *, target_keys=None):
        printed.append((prefix, target_keys))

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(module, "running_unit_processes", lambda: {})
    monkeypatch.setattr(module, "load_target_units", fake_load_target_units)
    monkeypatch.setattr(module, "restart_target_batch", fake_restart_target_batch)
    monkeypatch.setattr(module, "status_summary", fake_status_summary)
    monkeypatch.setattr(module, "print_status", fake_print_status)
    monkeypatch.setattr(module.asyncio, "sleep", fake_sleep)

    summaries, owned = await module.rolling_restart_targets(
        {"期货模拟工作区": workspace},
        {"futures": [{"strategy_name": "strategy-a"}, {"strategy_name": "strategy-b"}]},
        {"requested"},
        batch_size=1,
        batch_wait_seconds=7,
    )

    assert restarted == [
        ("futures", ["unit-a"]),
        ("futures", ["unit-b"]),
    ]
    assert slept == [7, 7]
    assert status_calls == [
        ({"unit-a"}, ("futures",)),
        ({"unit-b"}, ("futures",)),
    ]
    assert printed == [
        ("rolling batch 1 check", ("futures",)),
        ("rolling batch 2 check", ("futures",)),
    ]
    assert summaries["futures"]["running"] == 2
    assert owned == {"futures": {"unit-a", "unit-b"}}


@pytest.mark.asyncio
async def test_restart_target_batch_retries_only_failed_units(monkeypatch):
    module = _load_script_module()
    units = [
        SimpleNamespace(id="unit-a"),
        SimpleNamespace(id="unit-b"),
    ]
    workspace = SimpleNamespace(id="ws-futures", user_id="user-1")
    run_calls: list[list[str]] = []
    slept: list[int] = []

    class FakeWorkspaceService:
        async def stop_units(self, _workspace_id, _user_id, unit_ids):
            return [{"unit_id": unit_id, "cancelled": True} for unit_id in unit_ids]

        async def run_units(self, _workspace_id, _user_id, unit_ids, *, parallel):
            assert parallel is True
            run_calls.append(list(unit_ids))
            if run_calls == [["unit-a", "unit-b"]]:
                return [
                    {"unit_id": "unit-a", "status": "running", "already_running": False},
                    {"unit_id": "unit-b", "status": "failed", "error": "market not ready"},
                ]
            return [
                {"unit_id": "unit-b", "status": "running", "already_running": False},
            ]

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(module, "WorkspaceService", FakeWorkspaceService)
    monkeypatch.setattr(module.asyncio, "sleep", fake_sleep)

    counter, owned = await module.restart_target_batch(
        "futures",
        workspace,
        units,
        start_attempts=2,
        retry_wait_seconds=6,
    )

    assert run_calls == [["unit-a", "unit-b"], ["unit-b"]]
    assert slept == [6]
    assert counter["running"] == 2
    assert counter["failed"] == 0
    assert owned == {"unit-a", "unit-b"}


def test_runtime_health_counter_checks_live_process_log_heartbeats(monkeypatch):
    module = _load_script_module()
    units = [
        SimpleNamespace(id="fresh"),
        SimpleNamespace(id="stale"),
        SimpleNamespace(id="missing"),
    ]

    monkeypatch.setattr(
        module,
        "unit_run_path",
        lambda unit: Path(f"/tmp/{unit.id}/run.py"),
    )
    monkeypatch.setattr(
        module,
        "unit_log_dir",
        lambda unit: Path(f"/tmp/{unit.id}/logs"),
    )

    def fake_latest_log_age(log_dir, now=None, since_timestamp=None):
        if "fresh" in str(log_dir):
            return 10.0
        if "stale" in str(log_dir):
            return 181.0
        return None

    monkeypatch.setattr(module, "latest_log_age_seconds", fake_latest_log_age)

    counter = module.runtime_health_counter(
        units,
        live_run_paths={
            Path("/tmp/fresh/run.py").resolve(),
            Path("/tmp/stale/run.py").resolve(),
        },
        stale_heartbeat_seconds=180,
    )

    assert counter["process_alive"] == 2
    assert counter["heartbeat_fresh"] == 1
    assert counter["heartbeat_stale"] == 1
    assert counter["heartbeat_missing"] == 0


def test_runtime_health_counter_ignores_heartbeats_without_live_process(monkeypatch):
    module = _load_script_module()
    unit = SimpleNamespace(id="stopped")

    monkeypatch.setattr(module, "unit_run_path", lambda _unit: Path("/tmp/stopped/run.py"))
    monkeypatch.setattr(module, "unit_log_dir", lambda _unit: Path("/tmp/stopped/logs"))
    monkeypatch.setattr(module, "log_bytes", lambda *_args, **_kwargs: 2 * 1024 * 1024)
    monkeypatch.setattr(
        module,
        "latest_log_age_seconds",
        lambda _log_dir, now=None, since_timestamp=None: 1.0,
    )

    counter = module.runtime_health_counter([unit], live_processes={})

    assert counter["process_alive"] == 0
    assert counter["heartbeat_fresh"] == 0
    assert counter["heartbeat_stale"] == 0
    assert counter["heartbeat_missing"] == 0
    assert counter["log_mb_total"] == 0.0
    assert counter["log_disk_mb_total"] > 0.0


def test_runtime_health_counter_reports_resource_and_log_pressure(monkeypatch):
    module = _load_script_module()
    units = [
        SimpleNamespace(id="alpha"),
        SimpleNamespace(id="beta"),
    ]

    monkeypatch.setattr(
        module,
        "unit_run_path",
        lambda unit: Path(f"/tmp/{unit.id}/run.py"),
    )
    monkeypatch.setattr(
        module,
        "unit_log_dir",
        lambda unit: Path(f"/tmp/{unit.id}/logs"),
    )
    monkeypatch.setattr(
        module,
        "latest_log_age_seconds",
        lambda _log_dir, now=None, since_timestamp=None: 1.0,
    )

    resources = {
        101: module.ProcessResource(
            pid=101,
            cpu_pct=12.34,
            rss_mb=64.5,
            pss_mb=48.25,
            uss_mb=40.0,
            started_at_epoch=100.0,
        ),
        202: module.ProcessResource(
            pid=202,
            cpu_pct=7.66,
            rss_mb=32.25,
            pss_mb=24.5,
            uss_mb=20.0,
            started_at_epoch=200.0,
        ),
    }
    monkeypatch.setattr(module, "read_process_resource", lambda pid, **_kwargs: resources[pid])

    seen_since: list[float | None] = []

    def fake_log_bytes(log_dir, pattern="*.log", *, since_timestamp=None):
        seen_since.append(since_timestamp)
        is_disk_total = since_timestamp is None
        if "alpha" in str(log_dir):
            if pattern == "*.log":
                return (12 if is_disk_total else 10) * 1024 * 1024
            return (9 if is_disk_total else 8) * 1024 * 1024
        if pattern == "*.log":
            return (6 if is_disk_total else 4) * 1024 * 1024
        return (2 if is_disk_total else 1) * 1024 * 1024

    monkeypatch.setattr(module, "log_bytes", fake_log_bytes)

    counter = module.runtime_health_counter(
        units,
        live_processes={
            Path("/tmp/alpha/run.py").resolve(): [101],
            Path("/tmp/beta/run.py").resolve(): [202],
        },
    )

    assert counter["process_alive"] == 2
    assert counter["heartbeat_fresh"] == 2
    assert counter["cpu_pct_total"] == 20.0
    assert counter["cpu_pct_max"] == 12.3
    assert counter["rss_mb_total"] == 96.8
    assert counter["rss_mb_max"] == 64.5
    assert counter["pss_mb_total"] == 72.8
    assert counter["pss_mb_max"] == 48.2
    assert counter["uss_mb_total"] == 60.0
    assert counter["uss_mb_max"] == 40.0
    assert counter["log_mb_total"] == 14.0
    assert counter["tick_log_mb_total"] == 9.0
    assert counter["tick_log_mb_max"] == 8.0
    assert counter["log_disk_mb_total"] == 18.0
    assert counter["tick_log_disk_mb_total"] == 11.0
    assert counter["tick_log_disk_mb_max"] == 9.0
    assert seen_since == [100.0, 100.0, None, None, 200.0, 200.0, None, None]


def test_runtime_health_counter_marks_live_process_with_stale_logs(monkeypatch):
    module = _load_script_module()
    unit = SimpleNamespace(id="stale")

    monkeypatch.setattr(
        module,
        "unit_run_path",
        lambda _unit: Path("/tmp/stale/run.py"),
    )
    monkeypatch.setattr(
        module,
        "unit_log_dir",
        lambda _unit: Path("/tmp/stale/logs"),
    )
    monkeypatch.setattr(
        module,
        "read_process_resource",
        lambda pid, **_kwargs: module.ProcessResource(pid=pid, started_at_epoch=100.0),
    )
    monkeypatch.setattr(module, "log_bytes", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(
        module,
        "latest_log_age_seconds",
        lambda _log_dir, now=None, since_timestamp=None: 600.0,
    )

    counter = module.runtime_health_counter(
        [unit],
        live_processes={Path("/tmp/stale/run.py").resolve(): [123]},
        stale_heartbeat_seconds=180,
    )

    assert counter["process_alive"] == 1
    assert counter["heartbeat_fresh"] == 0
    assert counter["heartbeat_stale"] == 1


def test_runtime_health_counter_flags_missing_data_logs_after_warmup(monkeypatch, tmp_path):
    module = _load_script_module()
    unit = SimpleNamespace(id="no-data")
    unit_dir = tmp_path / "no-data"
    log_dir = unit_dir / "logs"
    log_dir.mkdir(parents=True)
    heartbeat = log_dir / "heartbeat.json"
    heartbeat.write_text("{}")
    module.os.utime(heartbeat, (490.0, 490.0))
    for name in module.DATA_ACTIVITY_LOG_NAMES:
        path = log_dir / name
        path.write_text("")
        module.os.utime(path, (120.0, 120.0))

    monkeypatch.setattr(module, "unit_run_path", lambda _unit: unit_dir / "run.py")
    monkeypatch.setattr(module, "unit_log_dir", lambda _unit: log_dir)
    monkeypatch.setattr(module.time, "time", lambda: 500.0)
    monkeypatch.setattr(
        module,
        "read_process_resource",
        lambda pid, **_kwargs: module.ProcessResource(pid=pid, started_at_epoch=100.0),
    )

    counter = module.runtime_health_counter(
        [unit],
        live_processes={(unit_dir / "run.py").resolve(): [123]},
        stale_heartbeat_seconds=180,
    )

    assert counter["heartbeat_fresh"] == 1
    assert counter["data_log_missing"] == 1
    assert "data_log_missing" in module.resource_alerts(counter)


def test_ctp_data_quiet_time_respects_product_breaks():
    module = _load_script_module()
    break_time = datetime(
        2026,
        6,
        25,
        10,
        20,
        tzinfo=timezone(timedelta(hours=8)),
    ).timestamp()

    assert module.is_ctp_data_quiet_time("au2608", break_time) is True
    assert module.is_ctp_data_quiet_time("IF2609", break_time) is False
    assert module.is_ctp_data_quiet_time("EURUSD", break_time) is False


def test_runtime_health_counter_suppresses_ctp_quiet_data_gap(monkeypatch, tmp_path):
    module = _load_script_module()
    unit = SimpleNamespace(id="quiet-data")
    unit_dir = tmp_path / "quiet-data"
    log_dir = unit_dir / "logs"
    log_dir.mkdir(parents=True)
    now = datetime(
        2026,
        6,
        25,
        10,
        20,
        tzinfo=timezone(timedelta(hours=8)),
    ).timestamp()
    heartbeat = log_dir / "heartbeat.json"
    heartbeat.write_text("{}")
    module.os.utime(heartbeat, (now - 10.0, now - 10.0))
    for name in module.DATA_ACTIVITY_LOG_NAMES:
        path = log_dir / name
        path.write_text("")
        module.os.utime(path, (now - 400.0, now - 400.0))

    monkeypatch.setattr(module, "unit_run_path", lambda _unit: unit_dir / "run.py")
    monkeypatch.setattr(module, "unit_log_dir", lambda _unit: log_dir)
    monkeypatch.setattr(module, "unit_live_symbol", lambda _unit: "au2608")
    monkeypatch.setattr(module.time, "time", lambda: now)
    monkeypatch.setattr(
        module,
        "read_process_resource",
        lambda pid, **_kwargs: module.ProcessResource(pid=pid, started_at_epoch=now - 400.0),
    )

    counter = module.runtime_health_counter(
        [unit],
        live_processes={(unit_dir / "run.py").resolve(): [123]},
        stale_heartbeat_seconds=180,
    )

    assert counter["heartbeat_fresh"] == 1
    assert counter["data_log_quiet"] == 1
    assert counter["data_log_missing"] == 0
    assert "data_log_missing" not in module.resource_alerts(counter)


def test_runtime_health_counter_flags_stale_data_logs(monkeypatch, tmp_path):
    module = _load_script_module()
    unit = SimpleNamespace(id="stale-data")
    unit_dir = tmp_path / "stale-data"
    log_dir = unit_dir / "logs"
    log_dir.mkdir(parents=True)
    heartbeat = log_dir / "heartbeat.json"
    heartbeat.write_text("{}")
    module.os.utime(heartbeat, (490.0, 490.0))
    bar_log = log_dir / "bar.log"
    bar_log.write_text("{}\n")
    module.os.utime(bar_log, (200.0, 200.0))

    monkeypatch.setattr(module, "unit_run_path", lambda _unit: unit_dir / "run.py")
    monkeypatch.setattr(module, "unit_log_dir", lambda _unit: log_dir)
    monkeypatch.setattr(module.time, "time", lambda: 500.0)
    monkeypatch.setattr(
        module,
        "read_process_resource",
        lambda pid, **_kwargs: module.ProcessResource(pid=pid, started_at_epoch=100.0),
    )

    counter = module.runtime_health_counter(
        [unit],
        live_processes={(unit_dir / "run.py").resolve(): [123]},
        stale_heartbeat_seconds=180,
    )

    assert counter["heartbeat_fresh"] == 1
    assert counter["data_log_stale"] == 1
    assert "data_log_stale" in module.resource_alerts(counter)


def test_runtime_health_counter_reports_prior_session_disk_logs(monkeypatch, tmp_path):
    module = _load_script_module()
    unit = SimpleNamespace(id="alpha")
    unit_dir = tmp_path / "alpha"
    log_dir = unit_dir / "logs"
    log_dir.mkdir(parents=True)
    tick_log = log_dir / "tick.log"
    tick_log.write_bytes(b"x" * 2 * 1024 * 1024)
    module.os.utime(tick_log, (100.0, 100.0))

    monkeypatch.setattr(module, "unit_run_path", lambda _unit: unit_dir / "run.py")
    monkeypatch.setattr(module, "unit_log_dir", lambda _unit: log_dir)
    monkeypatch.setattr(
        module,
        "read_process_resource",
        lambda pid, **_kwargs: module.ProcessResource(pid=pid, started_at_epoch=200.0),
    )

    counter = module.runtime_health_counter(
        [unit],
        live_processes={(unit_dir / "run.py").resolve(): [123]},
    )

    assert counter["tick_log_mb_total"] == 0.0
    assert counter["tick_log_disk_mb_total"] == 2.0
    assert counter["tick_log_disk_mb_max"] == 2.0


def test_log_bytes_can_ignore_logs_from_prior_sessions(tmp_path):
    module = _load_script_module()
    old_log = tmp_path / "old.log"
    new_log = tmp_path / "new.log"
    old_log.write_bytes(b"x" * 8)
    new_log.write_bytes(b"y" * 16)
    old_time = 100.0
    new_time = 200.0
    old_log.touch()
    new_log.touch()
    module.os.utime(old_log, (old_time, old_time))
    module.os.utime(new_log, (new_time, new_time))

    assert module.log_bytes(tmp_path, since_timestamp=150.0) == 16
    assert module.log_bytes(tmp_path) == 24


def test_read_process_memory_rollup_reports_pss_and_uss(tmp_path):
    module = _load_script_module()
    (tmp_path / "smaps_rollup").write_text(
        "\n".join(
            [
                "Rss:                4096 kB",
                "Pss:                2048 kB",
                "Private_Clean:       512 kB",
                "Private_Dirty:      1024 kB",
                "Private_Hugetlb:     512 kB",
            ]
        ),
        encoding="utf-8",
    )

    assert module.read_process_memory_rollup(tmp_path) == (2.0, 2.0)
    assert module.read_process_memory_rollup(tmp_path / "missing") == (0.0, 0.0)


def test_process_cpu_pct_uses_interval_delta_after_first_sample():
    module = _load_script_module()
    samples: dict[int, tuple[float, float]] = {}

    first = module.process_cpu_pct(
        123,
        5.0,
        10.0,
        sample_time=100.0,
        cpu_samples=samples,
    )
    second = module.process_cpu_pct(
        123,
        8.0,
        20.0,
        sample_time=110.0,
        cpu_samples=samples,
    )

    assert first == 50.0
    assert second == 30.0
    assert samples == {123: (110.0, 8.0)}


def test_prune_process_cpu_samples_removes_exited_pids():
    module = _load_script_module()
    module._PROCESS_CPU_SAMPLES.clear()
    module._PROCESS_CPU_SAMPLES.update({101: (1.0, 2.0), 202: (1.0, 3.0)})

    module.prune_process_cpu_samples({202})

    assert module._PROCESS_CPU_SAMPLES == {202: (1.0, 3.0)}


def test_resource_alerts_flag_runtime_and_resource_pressure():
    module = _load_script_module()

    alerts = module.resource_alerts(
        Counter(
            {
                "running": 50,
                "process_alive": 49,
                "failed": 1,
                "idle": 1,
                "missing": 1,
                "heartbeat_stale": 1,
                "heartbeat_missing": 1,
                "data_log_stale": 1,
                "data_log_missing": 1,
                "cpu_pct_max": 35.0,
                "rss_mb_total": 12_000.0,
                "pss_mb_total": 11_000.0,
                "log_mb_total": 2_000.0,
                "tick_log_mb_total": 300.0,
                "log_disk_mb_total": 2_500.0,
                "tick_log_disk_mb_total": 350.0,
            }
        )
    )

    assert alerts == [
        "process_missing",
        "unit_failed",
        "unit_idle",
        "unit_missing",
        "heartbeat_stale",
        "heartbeat_missing",
        "data_log_stale",
        "data_log_missing",
        "cpu_high",
        "pss_high",
        "log_high",
        "tick_log_high",
        "log_disk_high",
        "tick_log_disk_high",
    ]
    assert module.resource_alerts(
        Counter(
            {
                "running": 1,
                "process_alive": 1,
                "rss_mb_total": 12_000.0,
            }
        )
    ) == ["rss_high"]
    assert module.resource_alerts(Counter({"idle": 50, "process_alive": 50})) == [
        "process_orphaned",
        "unit_idle",
    ]
    assert module.resource_alerts(Counter({"running": 1, "process_alive": 1})) == []


def test_print_status_includes_resource_alerts(monkeypatch, capsys):
    module = _load_script_module()
    monkeypatch.setattr(module, "TARGET_WORKSPACE_KEYS", ("futures",))
    now = datetime(2026, 6, 25, 1, 35, 0, tzinfo=timezone(timedelta(hours=8), "CST"))

    module.print_status(
        "monitor",
        {
            "futures": Counter(
                {
                    "running": 50,
                    "process_alive": 50,
                    "heartbeat_fresh": 50,
                    "data_log_fresh": 50,
                    "cpu_pct_total": 1694.2,
                    "cpu_pct_max": 35.4,
                    "rss_mb_total": 12_783.9,
                    "pss_mb_total": 10_783.9,
                    "uss_mb_total": 10_123.4,
                    "log_mb_total": 401.3,
                    "tick_log_mb_total": 390.0,
                    "tick_log_mb_max": 9.6,
                    "log_disk_mb_total": 1_200.5,
                    "tick_log_disk_mb_total": 425.0,
                    "tick_log_disk_mb_max": 10.2,
                }
            )
        },
        now=now,
    )

    output = capsys.readouterr().out
    assert output.startswith("2026-06-25 01:35:00 CST monitor: ")
    assert "alerts=cpu_high,pss_high,tick_log_high,log_disk_high,tick_log_disk_high" in output
    assert "cpu=1694.2%" in output
    assert "data_log=50 data_stale=0 data_missing=0" in output
    assert "pss=10783.9MB" in output
    assert "uss=10123.4MB" in output
    assert "tick=390.0MB" in output
    assert "log_disk=1200.5MB" in output
    assert "tick_disk=425.0MB" in output


def test_print_log_includes_timestamp(capsys):
    module = _load_script_module()
    now = datetime(2026, 6, 25, 1, 36, 0, tzinfo=timezone(timedelta(hours=8), "CST"))

    module.print_log("monitor holding for 604800s", now=now)

    assert capsys.readouterr().out == "2026-06-25 01:36:00 CST monitor holding for 604800s\n"


@pytest.mark.asyncio
async def test_start_targets_tracks_only_newly_started_units(monkeypatch):
    module = _load_script_module()
    monkeypatch.setattr(module, "TARGET_WORKSPACE_KEYS", ("futures",))

    async def fake_start_target_workspace(key, workspace, specs, unit_ids=None):
        assert key == "futures"
        assert workspace.name == "期货模拟工作区"
        assert unit_ids == {"requested"}
        return (
            key,
            [
                {"unit_id": "new-unit", "status": "running", "already_running": False},
                {"unit_id": "existing-unit", "status": "running", "already_running": True},
                {"unit_id": "failed-unit", "status": "failed", "error": "boom"},
            ],
            [],
            {"new-unit"},
        )

    monkeypatch.setattr(module, "start_target_workspace", fake_start_target_workspace)

    summaries, owned = await module.start_targets(
        {"期货模拟工作区": SimpleNamespace(name="期货模拟工作区")},
        {"futures": []},
        {"requested"},
    )

    assert summaries["futures"]["running"] == 2
    assert summaries["futures"]["failed"] == 1
    assert owned == {"futures": {"new-unit"}}


@pytest.mark.asyncio
async def test_stop_owned_targets_stops_only_owned_unit_ids(monkeypatch):
    module = _load_script_module()
    monkeypatch.setattr(module, "TARGET_WORKSPACE_KEYS", ("futures", "mt5"))

    seen_unit_ids: list[set[str]] = []
    stopped: list[tuple[str, list[str]]] = []

    async def fake_load_target_units(workspace, specs, unit_ids=None):
        seen_unit_ids.append(set(unit_ids or set()))
        return [SimpleNamespace(id=unit_id) for unit_id in sorted(unit_ids or set())], []

    class FakeWorkspaceService:
        async def stop_units(self, workspace_id, user_id, unit_ids):
            stopped.append((workspace_id, list(unit_ids)))
            return [{"unit_id": unit_id, "cancelled": True} for unit_id in unit_ids]

    monkeypatch.setattr(module, "load_target_units", fake_load_target_units)
    monkeypatch.setattr(module, "WorkspaceService", FakeWorkspaceService)
    monkeypatch.setattr(module, "unit_has_process_owned_by_pid", lambda *_args: True)

    await module.stop_owned_targets(
        {
            "期货模拟工作区": SimpleNamespace(id="ws-futures", user_id="user-1"),
            "MT5模拟工作区": SimpleNamespace(id="ws-mt5", user_id="user-1"),
        },
        {"futures": [], "mt5": []},
        {"futures": {"owned-a", "owned-b"}, "mt5": set()},
    )

    assert seen_unit_ids == [{"owned-a", "owned-b"}]
    assert stopped == [("ws-futures", ["owned-a", "owned-b"])]


@pytest.mark.asyncio
async def test_stop_owned_targets_skips_units_reowned_by_another_supervisor(monkeypatch, capsys):
    module = _load_script_module()
    monkeypatch.setattr(module, "TARGET_WORKSPACE_KEYS", ("futures",))
    stopped: list[list[str]] = []

    async def fake_load_target_units(_workspace, _specs, unit_ids=None):
        return [SimpleNamespace(id=unit_id) for unit_id in sorted(unit_ids or set())], []

    class FakeWorkspaceService:
        async def stop_units(self, _workspace_id, _user_id, unit_ids):
            stopped.append(list(unit_ids))
            return [{"unit_id": unit_id, "cancelled": True} for unit_id in unit_ids]

    monkeypatch.setattr(module, "load_target_units", fake_load_target_units)
    monkeypatch.setattr(module, "WorkspaceService", FakeWorkspaceService)
    monkeypatch.setattr(module, "unit_has_process_owned_by_pid", lambda *_args: False)
    monkeypatch.setattr(module, "running_unit_processes", lambda: {})

    summaries = await module.stop_owned_targets(
        {"期货模拟工作区": SimpleNamespace(id="ws-futures", user_id="user-1")},
        {"futures": []},
        {"futures": {"owned-a"}},
        owner_pid=100,
    )

    assert summaries == {}
    assert stopped == []
    assert "owned stop skipped: no current owned processes" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_handle_stop_signal_stops_owned_units_by_default(monkeypatch):
    module = _load_script_module()
    stop_event = module.asyncio.Event()
    stop_event.set()
    stopped: list[dict[str, set[str]]] = []

    async def fake_stop_owned_targets(_workspaces, _specs_by_key, owned_unit_ids_by_key):
        stopped.append(owned_unit_ids_by_key)
        return {}

    monkeypatch.setattr(module, "stop_owned_targets", fake_stop_owned_targets)

    await module.handle_stop_signal(
        stop_event,
        {},
        {},
        {"futures": {"owned-a"}},
    )

    assert stopped == [{"futures": {"owned-a"}}]


@pytest.mark.asyncio
async def test_handle_stop_signal_ignores_deprecated_no_stop_flag(monkeypatch, capsys):
    module = _load_script_module()
    stop_event = module.asyncio.Event()
    stop_event.set()
    stopped: list[dict[str, set[str]]] = []

    async def fake_stop_owned_targets(_workspaces, _specs_by_key, owned_unit_ids_by_key):
        stopped.append(owned_unit_ids_by_key)
        return {}

    monkeypatch.setattr(module, "stop_owned_targets", fake_stop_owned_targets)

    await module.handle_stop_signal(
        stop_event,
        {},
        {},
        {"futures": {"owned-a"}},
        stop_owned_on_signal=False,
    )

    assert stopped == [{"futures": {"owned-a"}}]
    output = capsys.readouterr().out
    assert "--no-stop-owned-on-signal is ignored" in output


@pytest.mark.asyncio
async def test_hold_monitor_continues_reporting_after_hold_when_units_still_run(
    monkeypatch,
    capsys,
):
    module = _load_script_module()
    stop_event = module.asyncio.Event()
    printed: list[str] = []
    wait_calls = 0
    monotonic_values = iter([0.0, 0.0, 2.0])

    async def fake_status_summary(_workspaces, _specs_by_key, _unit_ids=None):
        return {"futures": Counter({"running": 1})}

    def fake_print_status(prefix, _summaries):
        printed.append(prefix)

    async def fake_wait_for(awaitable, timeout):
        nonlocal wait_calls
        wait_calls += 1
        awaitable.close()
        if wait_calls >= 2:
            stop_event.set()
        raise module.asyncio.TimeoutError()

    monkeypatch.setattr(module, "TARGET_WORKSPACE_KEYS", ("futures",))
    monkeypatch.setattr(module, "status_summary", fake_status_summary)
    monkeypatch.setattr(module, "print_status", fake_print_status)
    monkeypatch.setattr(module.asyncio, "wait_for", fake_wait_for)
    monkeypatch.setattr(module.time, "monotonic", lambda: next(monotonic_values, 2.0))

    await module.hold_monitor(
        {},
        {"futures": []},
        hold_seconds=1,
        status_interval=30,
        stop_event=stop_event,
    )

    assert "status" in printed
    assert wait_calls >= 2
    assert "continuing status monitor" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_hold_monitor_keeps_reporting_when_processes_outlive_db_state(
    monkeypatch,
    capsys,
):
    module = _load_script_module()
    stop_event = module.asyncio.Event()
    printed: list[tuple[str, dict[str, Counter[str]]]] = []
    wait_calls = 0
    monotonic_values = iter([0.0, 0.0, 2.0])

    async def fake_status_summary(_workspaces, _specs_by_key, _unit_ids=None):
        return {"futures": Counter({"idle": 50, "process_alive": 50, "heartbeat_fresh": 50})}

    def fake_print_status(prefix, summaries):
        printed.append((prefix, summaries))

    async def fake_wait_for(awaitable, timeout):
        nonlocal wait_calls
        wait_calls += 1
        awaitable.close()
        if wait_calls >= 2:
            stop_event.set()
        raise module.asyncio.TimeoutError()

    monkeypatch.setattr(module, "TARGET_WORKSPACE_KEYS", ("futures",))
    monkeypatch.setattr(module, "status_summary", fake_status_summary)
    monkeypatch.setattr(module, "print_status", fake_print_status)
    monkeypatch.setattr(module.asyncio, "wait_for", fake_wait_for)
    monkeypatch.setattr(module.time, "monotonic", lambda: next(monotonic_values, 2.0))

    await module.hold_monitor(
        {},
        {"futures": []},
        hold_seconds=1,
        status_interval=30,
        stop_event=stop_event,
    )

    assert len([prefix for prefix, _summaries in printed if prefix == "status"]) >= 1
    assert wait_calls >= 2
    assert "continuing status monitor" in capsys.readouterr().out
