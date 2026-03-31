from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from app.schemas.backtest import TaskStatus
from app.services.optimization_submission import submit_optimization
from app.services.optimization_task_gateway import (
    cancel_optimization_task,
    load_optimization_task_state,
    persist_optimization_task,
)
from app.services.optimization_thread_runner import run_optimization_thread
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
        run_single_trial_fn=lambda strategy_dir, params, trial_index, tmp_base: {
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
