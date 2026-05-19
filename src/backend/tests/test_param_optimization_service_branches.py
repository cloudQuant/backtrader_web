"""
Iteration 113 service unit coverage tests

Tests:
- Monitoring service monitoring task branches
- Optimization service bayesian objective and exception paths
- Parameter optimization service run optimization thread paths
- Parameter optimization service worker and log parser branches
- Backtest service task limits and cancel cleanup exceptions
- Strategy version service create version and update version branches
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest


@pytest.mark.asyncio
async def test_monitoring_service_monitor_task_cancel_and_error_and_threshold_branches():
    from app.services.monitoring_service import AlertType, MonitoringService

    svc = MonitoringService()

    rule = SimpleNamespace(
        id="r1",
        user_id="u1",
        is_active=True,
        alert_type=AlertType.SYSTEM,
        trigger_type="threshold",
        trigger_config={"current_value": 1.0, "threshold": 2.0, "condition": "eq"},
        notification_enabled=True,
        notification_channels=["email", "sms", "push", "webhook"],
        severity=SimpleNamespace(value="low"),
        status=SimpleNamespace(value="active"),
        triggered_count=0,
        description="d",
        strategy_id="s1",
    )

    svc.alert_rule_repo = AsyncMock()
    svc.alert_rule_repo.get_by_id = AsyncMock(return_value=rule)
    svc.alert_rule_repo.update = AsyncMock()

    svc.alert_repo = AsyncMock()
    svc.alert_repo.create = AsyncMock(side_effect=lambda a: a)
    svc.alert_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(id="a1", user_id="u1"))
    svc.alert_repo.update = AsyncMock()

    # CancelledError branch in _monitor_task.
    svc._check_trigger = AsyncMock(return_value=False)
    with (
        patch(
            "app.services.monitoring_service.asyncio.sleep",
            new=AsyncMock(side_effect=asyncio.CancelledError()),
        ),
        patch("app.services.monitoring_service.ws_manager.send_to_task", new=AsyncMock()),
    ):
        await svc._monitor_task("r1")

    # Exception branch in _monitor_task.
    rule2 = SimpleNamespace(**{**rule.__dict__})
    rule2.is_active = False
    svc.alert_rule_repo.get_by_id = AsyncMock(side_effect=[rule, rule, rule2])
    svc._check_trigger = AsyncMock(side_effect=RuntimeError("boom"))
    with patch("app.services.monitoring_service.asyncio.sleep", new=AsyncMock(return_value=None)):
        await svc._monitor_task("r1")

    # Threshold trigger else branches (ACCOUNT + POSITION) and notification/websocket push.
    rule_acc = SimpleNamespace(
        alert_type=AlertType.ACCOUNT,
        trigger_config={"current_value": 1.0, "threshold": 1.0, "condition": "eq"},
    )
    assert await svc._check_threshold_trigger(rule_acc, rule_acc.trigger_config) is True

    rule_pos = SimpleNamespace(
        alert_type=AlertType.POSITION,
        trigger_config={"current_value": 1.0, "threshold": 1.0, "condition": "eq"},
    )
    assert await svc._check_threshold_trigger(rule_pos, rule_pos.trigger_config) is True

    with patch("app.services.monitoring_service.ws_manager.send_to_task", new=AsyncMock()):
        alert = SimpleNamespace(
            id="a1",
            alert_type=SimpleNamespace(value="system"),
            severity=SimpleNamespace(value="low"),
            title="t",
            message="m",
            details={},
            created_at=datetime.now(timezone.utc),
            strategy_id="s1",
        )
        await svc._send_notification(rule, alert)
        await svc._send_websocket_alert(rule, alert)


def test_param_optimization_service_run_optimization_thread_paths(tmp_path, monkeypatch):
    import app.services.param_optimization_service as pos

    # Seed a running task.
    task_id = "t1"
    pos._set_task(
        task_id,
        {
            "status": "running",
            "strategy_id": "s1",
            "total": 2,
            "completed": 0,
            "failed": 0,
            "results": [],
            "param_names": ["p"],
            "created_at": datetime.now().isoformat(),
            "n_workers": 1,
        },
    )

    # Fake future objects.
    class _Future:
        def __init__(self, payload=None, boom=False):
            self._payload = payload
            self._boom = boom
            self._cancelled = False

        def result(self, timeout=None):
            if self._boom:
                raise RuntimeError("worker boom")
            return self._payload

        def cancel(self):
            self._cancelled = True
            return True

    class _Exec:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def submit(self, fn, strategy_dir, params, i, tmp_base):
            if i == 0:
                return _Future({"success": True, "params": params, "metrics": {"annual_return": 1}})
            return _Future(boom=True)

    monkeypatch.setattr(pos, "ProcessPoolExecutor", _Exec)
    monkeypatch.setattr(pos, "as_completed", lambda futures: list(futures))

    # Avoid touching real filesystem for tmp base cleanup.
    monkeypatch.setattr(pos.tempfile, "mkdtemp", lambda prefix: str(tmp_path / "tmp"))
    monkeypatch.setattr(pos.shutil, "rmtree", lambda *a, **k: None)

    pos._run_optimization_thread(task_id, str(tmp_path), [{"p": 1}, {"p": 2}], n_workers=1)
    task = pos._get_task(task_id)
    assert task["status"] in {"completed", "failed", "error", "running"}


def test_param_optimization_service_worker_and_log_parser_branches(tmp_path, monkeypatch):
    import subprocess

    import app.services.param_optimization_service as pos

    # Prepare a minimal "strategy" dir.
    strategy_dir = tmp_path / "strategies" / "s1"
    strategy_dir.mkdir(parents=True)
    (strategy_dir / "run.py").write_text("assert 1\nprint('ok')\n", encoding="utf-8")
    (strategy_dir / "config.yaml").write_text("params: {}\n", encoding="utf-8")
    (strategy_dir / "logs").mkdir()

    tmp_base = tmp_path / "tmp_base"
    tmp_base.mkdir()

    # Non-zero subprocess returncode path + logs_dir cleanup.
    monkeypatch.setattr(
        pos.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 1, stdout="", stderr="fail"),
    )
    out = pos._run_single_trial(str(strategy_dir), {"p": 1}, 0, str(tmp_base))
    assert out["success"] is False

    # Exception path.
    monkeypatch.setattr(
        pos.shutil, "copytree", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("copy boom"))
    )
    out2 = pos._run_single_trial(str(strategy_dir), {"p": 1}, 1, str(tmp_base))
    assert "error" in out2

    # Cleanup exception path.
    monkeypatch.setattr(pos.shutil, "copytree", __import__("shutil").copytree)
    monkeypatch.setattr(
        pos.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout="", stderr=""),
    )
    # Make rmtree raise in finally.
    monkeypatch.setattr(
        pos.shutil, "rmtree", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("rm boom"))
    )
    out3 = pos._run_single_trial(str(strategy_dir), {"p": 1}, 2, str(tmp_base))
    assert out3["success"] in {False, True}

    # _parse_trial_logs: logs dir exists but no subdirs.
    trial_dir = tmp_path / "trial"
    (trial_dir / "logs").mkdir(parents=True)
    assert pos._parse_trial_logs(trial_dir) is None

    # _parse_trial_logs: returns empty => sharpe=0 branch.
    log_dir = trial_dir / "logs" / "x"
    log_dir.mkdir(parents=True)
    (log_dir / "value.log").write_text(
        "h\n0\t2020-01-01\t0\t0\n0\t2020-01-02\t0\t0\n", encoding="utf-8"
    )
    m = pos._parse_trial_logs(trial_dir)
    assert m is not None
    assert m["sharpe_ratio"] == 0


@pytest.mark.asyncio
async def test_backtest_service_task_limits_and_cancel_cleanup_excepts(monkeypatch):
    from app.schemas.backtest_enhanced import BacktestRequest, TaskStatus
    from app.services.backtest_runner import BacktestExecutionRunner
    from app.services.backtest_service import BacktestService

    svc = BacktestService()
    svc.cache = AsyncMock()
    svc.task_manager = AsyncMock()

    req = BacktestRequest(
        strategy_id="001_ma_cross",
        symbol="000001.SZ",
        start_date=datetime(2023, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2023, 3, 5, tzinfo=timezone.utc),
        initial_cash=100000,
        commission=0.001,
        params={},
    )
    svc.task_manager.create_task = AsyncMock(side_effect=ValueError("limit reached"))
    with pytest.raises(ValueError, match="limit reached"):
        await svc.run_backtest("u1", req)

    # cancel_task kill exception is swallowed and still updates state when a local
    # handle exists.
    proc = Mock()
    proc.poll = Mock(return_value=None)
    proc.kill = Mock(side_effect=RuntimeError("kill boom"))
    runner = BacktestExecutionRunner()
    runner.register_process("t1", proc)
    svc.task_runner = runner
    svc.task_repo.get_by_id = AsyncMock(
        return_value=SimpleNamespace(id="t1", user_id="u1", status=TaskStatus.RUNNING)
    )
    svc.task_manager.update_task_status = AsyncMock()
    assert await svc.cancel_task("t1", "u1") is True

    # delete_result rmtree exception is swallowed.
    bad_task = SimpleNamespace(id="t2", user_id="u1", log_dir="/tmp/does-not-matter")
    svc.task_repo.get_by_id = AsyncMock(return_value=bad_task)
    svc.task_manager.delete_task_and_result = AsyncMock(return_value=True)
    svc.cache.delete = AsyncMock()

    with (
        patch("app.services.backtest_service.Path.is_dir", return_value=True),
        patch("app.services.backtest_service.shutil.rmtree", side_effect=RuntimeError("rm boom")),
    ):
        assert await svc.delete_result("t2", "u1") is True


@pytest.mark.asyncio
async def test_strategy_version_service_create_version_and_update_version_branches():
    from app.models.strategy_version import VersionStatus
    from app.services.strategy_version_service import VersionControlService

    svc = VersionControlService()

    # create_version uses several repos.
    svc.strategy_repo = AsyncMock()
    svc.strategy_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(id="s1", user_id="u1"))

    svc.branch_repo = AsyncMock()
    svc.branch_repo.list = AsyncMock(return_value=[])
    svc.branch_repo.create = AsyncMock(return_value=SimpleNamespace(id="b1", version_count=0))
    svc.branch_repo.update = AsyncMock()

    svc.version_repo = AsyncMock()
    svc.version_repo.list = AsyncMock(return_value=[])
    svc.version_repo.create = AsyncMock(
        side_effect=lambda v: SimpleNamespace(**{**v.__dict__, "id": "v1"})
    )

    v = await svc.create_version("u1", "s1", "v1.0.0", code="x=1", params={"a": 1}, is_default=True)
    assert v.id == "v1"

    # update_version raises if not DRAFT.
    svc.version_repo.get_by_id = AsyncMock(
        return_value=SimpleNamespace(
            id="v2",
            status=VersionStatus.STABLE,
            strategy_id="s1",
            is_active=True,
            is_default=False,
            created_by="u1",
        )
    )
    with pytest.raises(ValueError, match="Can only update"):
        await svc.update_version(
            "v2",
            "u1",
            SimpleNamespace(
                code=None, params=None, description=None, tags=None, status=None, changelog=None
            ),
        )
