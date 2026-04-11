from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import app.services.param_optimization_service as param_optimization_service
from app.schemas.backtest import TaskStatus
from app.services.optimization_submission import submit_optimization
from app.services.optimization_task_gateway import (
    cancel_optimization_task,
    load_optimization_task_state,
    persist_optimization_task,
)
from app.services.optimization_thread_runner import run_optimization_thread
from app.services.optimization_trial_runner import parse_trial_logs
from app.services.optimization_trial_runner import run_single_trial


class DummyThread:
    def __init__(self, target, args, daemon):
        self.target = target
        self.args = args
        self.daemon = daemon
        self.started = False

    def start(self):
        self.started = True


def test_submission_helper_starts_thread_and_sets_initial_task(tmp_path: Path):
    strategy_dir = tmp_path / "strategy"
    strategy_dir.mkdir()
    (strategy_dir / "run.py").write_text("print('ok')\n", encoding="utf-8")

    tasks: dict[str, dict] = {}
    thread_instances: list[DummyThread] = []

    def _thread_factory(*, target, args, daemon):
        thread = DummyThread(target=target, args=args, daemon=daemon)
        thread_instances.append(thread)
        return thread

    task_id = submit_optimization(
        "demo_strategy",
        {"fast": {"start": 5, "end": 10, "step": 5, "type": "int"}},
        n_workers=2,
        persist_to_db=False,
        artifact_root=str(tmp_path / "artifacts"),
        get_strategy_dir=lambda _strategy_id: strategy_dir,
        set_task_fn=lambda task_id, data: tasks.setdefault(task_id, data),
        build_initial_runtime_task_fn=lambda **kwargs: kwargs,
        created_at_fn=lambda: "2026-03-23T13:34:00",
        running_status=TaskStatus.RUNNING.value,
        thread_cls=_thread_factory,
        run_optimization_thread_fn=Mock(),
        task_id_factory=lambda: "task1234",
    )

    assert task_id == "task1234"
    assert tasks[task_id]["strategy_id"] == "demo_strategy"
    assert tasks[task_id]["total"] == 2
    assert tasks[task_id]["status"] == TaskStatus.RUNNING.value
    assert len(thread_instances) == 1
    assert thread_instances[0].started is True
    assert thread_instances[0].target is not None
    assert thread_instances[0].args[0] == task_id
    assert thread_instances[0].args[3] == 2
    assert thread_instances[0].args[4] is False
    assert thread_instances[0].args[5] == str(tmp_path / "artifacts")


def test_task_gateway_load_uses_runtime_fallback_when_db_errors():
    runtime_task = {"status": "running", "completed": 1}

    result = load_optimization_task_state(
        "task-1",
        user_id="user-1",
        use_db=True,
        get_manager=lambda: SimpleNamespace(get_task=lambda task_id, user_id=None: None),
        run_async=lambda coro: (_ for _ in ()).throw(RuntimeError("db down")),
        get_task=lambda task_id: runtime_task,
        build_runtime_task=lambda db_task: {"status": "completed"},
    )

    assert result == runtime_task


def test_task_gateway_load_prefers_runtime_state_while_db_task_is_active():
    runtime_task = {"status": "running", "completed": 3, "failed": 0}
    db_task = SimpleNamespace(
        status=TaskStatus.RUNNING.value,
        strategy_id="demo",
        param_ranges={},
        total=10,
        completed=1,
        failed=0,
        results=[],
        n_workers=2,
        created_at=None,
        updated_at=None,
        error_message=None,
    )

    result = load_optimization_task_state(
        "task-1",
        user_id="user-1",
        use_db=True,
        get_manager=lambda: SimpleNamespace(get_task=lambda task_id, user_id=None: db_task),
        run_async=lambda payload: payload,
        get_task=lambda task_id: runtime_task,
        build_runtime_task=lambda task: {"status": task.status, "completed": task.completed},
    )

    assert result == runtime_task


def test_task_gateway_load_prefers_db_terminal_state_over_runtime():
    runtime_task = {"status": "running", "completed": 9, "failed": 0}
    db_task = SimpleNamespace(
        status=TaskStatus.COMPLETED.value,
        strategy_id="demo",
        param_ranges={},
        total=10,
        completed=10,
        failed=0,
        results=[],
        n_workers=2,
        created_at=None,
        updated_at=None,
        error_message=None,
    )

    result = load_optimization_task_state(
        "task-1",
        user_id="user-1",
        use_db=True,
        get_manager=lambda: SimpleNamespace(get_task=lambda task_id, user_id=None: db_task),
        run_async=lambda payload: payload,
        get_task=lambda task_id: runtime_task,
        build_runtime_task=lambda task: {"status": task.status, "completed": task.completed},
    )

    assert result == {"status": "completed", "completed": 10}


def test_task_gateway_cancel_does_not_fallback_when_db_rejects_user_scoped_request():
    updated = Mock()

    result = cancel_optimization_task(
        "task-2",
        user_id="user-1",
        use_db=True,
        get_manager=lambda: SimpleNamespace(set_cancelled=lambda task_id, user_id=None: None),
        run_async=lambda coro: False,
        get_task=lambda task_id: {"status": TaskStatus.RUNNING.value},
        update_task=updated,
    )

    assert result is False
    updated.assert_not_called()


def test_trial_runner_uses_injected_subprocess_module(tmp_path: Path):
    strategy_dir = tmp_path / "strategies" / "s1"
    strategy_dir.mkdir(parents=True)
    (strategy_dir / "run.py").write_text("print('ok')\n", encoding="utf-8")
    (strategy_dir / "config.yaml").write_text("params: {}\n", encoding="utf-8")

    subprocess_module = SimpleNamespace(run=Mock(return_value=SimpleNamespace(returncode=0, stderr="")))

    result = run_single_trial(
        str(strategy_dir),
        {"period": 20},
        0,
        str(tmp_path / "tmp_base"),
        parse_trial_logs_fn=lambda trial_dir: {"total_return": 1.23},
        subprocess_module=subprocess_module,
    )

    assert result["success"] is True
    assert result["metrics"] == {"total_return": 1.23}
    subprocess_module.run.assert_called_once()


def test_service_trial_wrapper_accepts_artifact_root_and_forwards_it():
    captured: dict[str, object] = {}
    original = param_optimization_service._trial_runner_run_single_trial

    def _fake_trial_runner(
        strategy_dir,
        params,
        trial_index,
        tmp_base,
        artifact_root,
        *,
        parse_trial_logs_fn,
        subprocess_module,
    ):
        captured.update(
            strategy_dir=strategy_dir,
            params=params,
            trial_index=trial_index,
            tmp_base=tmp_base,
            artifact_root=artifact_root,
            parse_trial_logs_fn=parse_trial_logs_fn,
            subprocess_module=subprocess_module,
        )
        return {"success": True}

    param_optimization_service._trial_runner_run_single_trial = _fake_trial_runner
    try:
        result = param_optimization_service._run_single_trial(
            "strategy-dir",
            {"fast": 5},
            2,
            "/tmp/opt",
            "/tmp/artifacts",
        )
    finally:
        param_optimization_service._trial_runner_run_single_trial = original

    assert result == {"success": True}
    assert captured["artifact_root"] == "/tmp/artifacts"
    assert captured["trial_index"] == 2


def test_trial_runner_persists_artifacts_when_root_provided(tmp_path: Path):
    strategy_dir = tmp_path / "strategies" / "s2"
    strategy_dir.mkdir(parents=True)
    (strategy_dir / "run.py").write_text("print('ok')\n", encoding="utf-8")
    (strategy_dir / "config.yaml").write_text("params: {}\n", encoding="utf-8")

    def _run(*args, **kwargs):
        trial_dir = Path(kwargs["cwd"])
        logs_dir = trial_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / "value.log").write_text("ok\n", encoding="utf-8")
        return SimpleNamespace(returncode=0, stderr="")

    subprocess_module = SimpleNamespace(run=_run)
    artifact_root = tmp_path / "artifacts"

    result = run_single_trial(
        str(strategy_dir),
        {"period": 42},
        0,
        str(tmp_path / "tmp_base"),
        str(artifact_root),
        parse_trial_logs_fn=lambda trial_dir: {"total_return": 1.23, "sharpe_ratio": 0.88},
        subprocess_module=subprocess_module,
    )

    assert result["success"] is True
    assert result["artifact_path"] == str(artifact_root / "trial_0001")
    assert (artifact_root / "trial_0001" / "params.json").is_file()
    assert (artifact_root / "trial_0001" / "metrics.json").is_file()
    assert (artifact_root / "trial_0001" / "config.yaml").is_file()
    assert (artifact_root / "trial_0001" / "result.json").is_file()
    assert (artifact_root / "trial_0001" / "summary.json").is_file()


def test_trial_runner_persists_failed_artifacts_when_root_provided(tmp_path: Path):
    strategy_dir = tmp_path / "strategies" / "s3"
    strategy_dir.mkdir(parents=True)
    (strategy_dir / "run.py").write_text("print('boom')\n", encoding="utf-8")
    (strategy_dir / "config.yaml").write_text("params: {}\n", encoding="utf-8")

    def _run(*args, **kwargs):
        trial_dir = Path(kwargs["cwd"])
        logs_dir = trial_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / "monitor.log").write_text("failed\n", encoding="utf-8")
        return SimpleNamespace(returncode=2, stdout="hello", stderr="Traceback\nValueError: bad")

    artifact_root = tmp_path / "artifacts_failed"
    result = run_single_trial(
        str(strategy_dir),
        {"period": 7},
        1,
        str(tmp_path / "tmp_failed"),
        str(artifact_root),
        subprocess_module=SimpleNamespace(run=_run),
    )

    assert result["success"] is False
    assert result["artifact_path"] == str(artifact_root / "trial_0002")
    assert (artifact_root / "trial_0002" / "result.json").is_file()
    assert (artifact_root / "trial_0002" / "summary.json").is_file()
    assert (artifact_root / "trial_0002" / "stdout.txt").read_text(encoding="utf-8") == "hello"
    assert "ValueError: bad" in (artifact_root / "trial_0002" / "stderr.txt").read_text(encoding="utf-8")


def test_parse_trial_logs_supports_flat_logs_layout(tmp_path: Path):
    trial_dir = tmp_path / "trial_0"
    logs_dir = trial_dir / "logs"
    logs_dir.mkdir(parents=True)
    (logs_dir / "value.log").write_text(
        "dt\tvalue\tcash\n2024-01-01\t100000\t100000\n2024-01-02\t101000\t101000\n",
        encoding="utf-8",
    )
    (logs_dir / "trade.log").write_text(
        "isclosed\tpnl\tpnlcomm\tcommission\n1\t120\t100\t20\n",
        encoding="utf-8",
    )
    (logs_dir / "monitor.log").write_text("ok\n", encoding="utf-8")

    metrics = parse_trial_logs(trial_dir)

    assert metrics is not None
    assert metrics["final_value"] == 101000.0
    assert metrics["total_trades"] == 1
    assert metrics["trading_cost"] == 20.0


def test_parse_trial_logs_supports_pipe_key_value_logs(tmp_path: Path):
    trial_dir = tmp_path / "trial_pipe"
    logs_dir = trial_dir / "logs"
    logs_dir.mkdir(parents=True)
    (logs_dir / "value.log").write_text(
        "2026-04-10T07:57:30.133+08:00 | datetime=2024-01-01 00:00:00 | value=100000.00 | cash=100000.00\n"
        "2026-04-10T07:57:30.134+08:00 | datetime=2024-01-02 00:00:00 | value=101500.00 | cash=101200.00\n",
        encoding="utf-8",
    )
    (logs_dir / "trade.log").write_text(
        "2026-04-10T07:22:28.008+08:00 | OPEN | ref=1 | data=AAPL | size=10 | pnl=0.00 | pnlcomm=-0.17\n"
        "2026-04-10T07:22:28.009+08:00 | CLOSED | ref=1 | data=AAPL | size=0 | pnl=53.30 | pnlcomm=52.96\n",
        encoding="utf-8",
    )
    (logs_dir / "monitor.log").write_text("ok\n", encoding="utf-8")

    metrics = parse_trial_logs(trial_dir)

    assert metrics is not None
    assert metrics["final_value"] == 101500.0
    assert metrics["total_return"] == 1.5
    assert metrics["total_trades"] == 1
    assert metrics["win_rate"] == 100.0
    assert metrics["avg_profit"] == 52.96


def test_task_gateway_persist_uses_runtime_defaults_when_fields_omitted():
    captured: dict[str, object] = {}
    runtime_task = {"completed": 3, "failed": 1, "results": [{"p": 1}]}

    result = persist_optimization_task(
        "task-3",
        status=TaskStatus.RUNNING.value,
        error_message="warn",
        get_manager=lambda: SimpleNamespace(
            update_progress=lambda task_id, **kwargs: {"task_id": task_id, **kwargs}
        ),
        run_async=lambda payload: captured.update(payload) or True,
        get_task=lambda task_id: runtime_task,
    )

    assert result is True
    assert captured["task_id"] == "task-3"
    assert captured["completed"] == 3
    assert captured["failed"] == 1
    assert captured["results"] == [{"p": 1}]
    assert captured["status"] == TaskStatus.RUNNING.value
    assert captured["error_message"] == "warn"


def test_thread_runner_success_path_updates_runtime_and_persists_final_state():
    class DummyFuture:
        def __init__(self, payload):
            self.payload = payload
            self.cancelled = False

        def result(self, timeout=None):
            return self.payload

        def cancel(self):
            self.cancelled = True

    class DummyExecutor:
        def __init__(self, max_workers):
            self.max_workers = max_workers
            self.futures = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, *args):
            future = DummyFuture(fn(*args))
            self.futures.append(future)
            return future

    runtime_task = {"status": TaskStatus.RUNNING.value, "failed": 0, "results": []}
    persist_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    removed_paths: list[tuple[str, bool]] = []

    def _update_task(_task_id, **kwargs):
        runtime_task.update(kwargs)
        return runtime_task

    def _persist(*args, **kwargs):
        persist_calls.append((args, kwargs))
        return True

    run_optimization_thread(
        "task-4",
        "strategy-dir",
        [{"fast": 5}],
        1,
        persist_to_db=True,
        run_single_trial_fn=lambda strategy_dir, params, trial_index, tmp_base, artifact_root: {
            "success": True,
            "params": params,
            "trial_index": trial_index,
            "metrics": {"total_return": 2.5},
        },
        is_cancelled_fn=lambda task_id, persist_to_db: False,
        persist_runtime_task_fn=_persist,
        get_task_fn=lambda task_id: runtime_task,
        update_task_fn=_update_task,
        process_pool_executor_cls=DummyExecutor,
        as_completed_fn=lambda futures: list(futures.keys()),
        mkdtemp_fn=lambda prefix: "/tmp/thread-runner-test",
        rmtree_fn=lambda path, ignore_errors=True: removed_paths.append((path, ignore_errors)),
    )

    assert runtime_task["status"] == TaskStatus.COMPLETED.value
    assert runtime_task["results"][0]["metrics"]["total_return"] == 2.5
    assert any(args == ("task-4",) and kwargs == {} for args, kwargs in persist_calls)
    assert any(
        kwargs.get("status") == TaskStatus.COMPLETED.value and kwargs.get("completed") == 1
        for _, kwargs in persist_calls
    )
    assert removed_paths == [("/tmp/thread-runner-test", True)]


def test_thread_runner_updates_manifest_and_summary(tmp_path: Path):
    class DummyFuture:
        def __init__(self, payload):
            self.payload = payload

        def result(self, timeout=None):
            return self.payload

        def cancel(self):
            return None

    class DummyExecutor:
        def __init__(self, max_workers):
            self.max_workers = max_workers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, *args):
            return DummyFuture(fn(*args))

    artifact_root = tmp_path / "optimization_runs" / "task-5"
    artifact_root.mkdir(parents=True)
    (artifact_root / "manifest.json").write_text('{"workspace_id":"w1"}', encoding="utf-8")
    runtime_task = {"status": TaskStatus.RUNNING.value, "failed": 0, "results": []}

    def _update_task(_task_id, **kwargs):
        runtime_task.update(kwargs)
        return runtime_task

    run_optimization_thread(
        "task-5",
        "strategy-dir",
        [{"fast": 5}, {"fast": 10}],
        1,
        persist_to_db=False,
        artifact_root=str(artifact_root),
        run_single_trial_fn=lambda strategy_dir, params, trial_index, tmp_base, root: {
            "success": trial_index == 0,
            "params": params,
            "trial_index": trial_index,
            "metrics": {"total_return": 2.5} if trial_index == 0 else {},
            "error": None if trial_index == 0 else "bad run",
            "artifact_path": str(Path(root or "") / f"trial_{trial_index + 1:04d}"),
        },
        is_cancelled_fn=lambda task_id, persist_to_db: False,
        persist_runtime_task_fn=lambda *args, **kwargs: True,
        get_task_fn=lambda task_id: runtime_task,
        update_task_fn=_update_task,
        process_pool_executor_cls=DummyExecutor,
        as_completed_fn=lambda futures: list(futures.keys()),
        mkdtemp_fn=lambda prefix: str(tmp_path / "tmp_runner"),
        rmtree_fn=lambda path, ignore_errors=True: None,
    )

    manifest = (artifact_root / "manifest.json").read_text(encoding="utf-8")
    summary = (artifact_root / "summary.json").read_text(encoding="utf-8")

    assert '"workspace_id": "w1"' in manifest
    assert '"successful_trials": 1' in manifest
    assert '"failed_trials": 1' in manifest
    assert '"trial_artifacts"' in manifest
    assert '"success_rate": 0.5' in summary
    assert '"status": "completed"' in summary
