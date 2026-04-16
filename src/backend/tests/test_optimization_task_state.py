"""Tests for optimization task state management."""

import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.services.optimization_task_state import (
    METRIC_NAMES,
    _runtime_tasks,
    _runtime_tasks_lock,
    build_initial_runtime_task,
    build_progress_response,
    build_results_response,
    build_runtime_task,
    build_runtime_task_from_db_task,
    estimate_remaining_seconds,
    get_runtime_task,
    set_runtime_task,
    update_runtime_task,
)


class _FakeDBTask:
    """Minimal stub for DB task objects."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def _clear_runtime_tasks():
    with _runtime_tasks_lock:
        _runtime_tasks.clear()


class TestRuntimeTaskCRUD:
    def setup_method(self):
        _clear_runtime_tasks()

    def test_get_missing_returns_none(self):
        assert get_runtime_task("nope") is None

    def test_set_and_get(self):
        set_runtime_task("t1", {"status": "running", "total": 10})
        task = get_runtime_task("t1")
        assert task is not None
        assert task["status"] == "running"
        assert task["total"] == 10

    def test_get_returns_copy(self):
        set_runtime_task("t1", {"status": "running"})
        a = get_runtime_task("t1")
        b = get_runtime_task("t1")
        assert a == b
        assert a is not b  # Separate dict instances

    def test_update_existing(self):
        set_runtime_task("t1", {"status": "running", "completed": 0})
        result = update_runtime_task("t1", completed=5, status="running")
        assert result is not None
        assert result["completed"] == 5

    def test_update_missing_returns_none(self):
        assert update_runtime_task("nope", status="done") is None

    def test_thread_safety(self):
        """Concurrent writes should not raise."""
        errors = []

        def writer(i):
            try:
                set_runtime_task(f"task-{i}", {"n": i})
                update_runtime_task(f"task-{i}", n=i * 2)
                get_runtime_task(f"task-{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []


class TestBuildRuntimeTask:
    def test_basic_build(self):
        task = build_runtime_task(
            status="running",
            strategy_id="ma_cross",
            param_ranges={"fast": {"min": 5, "max": 20}},
            total=100,
            completed=10,
            failed=2,
            results=[],
            n_workers=4,
            created_at="2024-01-01T00:00:00",
            error=None,
        )
        assert task["status"] == "running"
        assert task["strategy_id"] == "ma_cross"
        assert task["param_names"] == ["fast"]
        assert task["total"] == 100

    def test_none_param_ranges(self):
        task = build_runtime_task(
            status="pending",
            strategy_id="test",
            param_ranges=None,
            total=0,
            completed=0,
            failed=0,
            results=None,
            n_workers=1,
            created_at="",
            error=None,
        )
        assert task["param_ranges"] == {}
        assert task["param_names"] == []
        assert task["results"] == []


class TestBuildInitialRuntimeTask:
    def test_initializes_counters_to_zero(self):
        task = build_initial_runtime_task(
            strategy_id="test",
            param_ranges={"p1": {"min": 1, "max": 10}},
            total=50,
            n_workers=2,
            created_at="2024-01-01",
            status="pending",
        )
        assert task["completed"] == 0
        assert task["failed"] == 0
        assert task["results"] == []
        assert task["error"] is None

    def test_with_error(self):
        task = build_initial_runtime_task(
            strategy_id="test",
            param_ranges={},
            total=0,
            n_workers=1,
            created_at="",
            status="failed",
            error="Import error",
        )
        assert task["error"] == "Import error"


class TestBuildFromDBTask:
    def test_basic_conversion(self):
        from datetime import datetime, timezone

        db_task = _FakeDBTask(
            status="completed",
            strategy_id="ma_cross",
            param_ranges={"fast": {"min": 5, "max": 20}},
            total=100,
            completed=98,
            failed=2,
            results=[{"params": {"fast": 10}, "metrics": {"sharpe_ratio": 1.5}}],
            n_workers=4,
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            error_message=None,
        )
        task = build_runtime_task_from_db_task(db_task)
        assert task["status"] == "completed"
        assert task["completed"] == 98
        assert "2024-01-01" in task["created_at"]

    def test_handles_none_fields(self):
        db_task = _FakeDBTask(
            status="pending",
            strategy_id="test",
            param_ranges=None,
            total=None,
            completed=None,
            failed=None,
            results=None,
            n_workers=None,
            created_at=None,
            error_message=None,
        )
        task = build_runtime_task_from_db_task(db_task)
        assert task["total"] == 0
        assert task["n_workers"] == 4
        assert task["created_at"] == ""


class TestBuildProgressResponse:
    def test_calculates_progress_percentage(self):
        task = {
            "status": "running",
            "strategy_id": "test",
            "total": 100,
            "completed": 40,
            "failed": 10,
            "n_workers": 4,
            "created_at": "",
        }
        resp = build_progress_response("t1", task)
        assert resp["progress"] == 50.0  # (40+10)/100 * 100

    def test_zero_total(self):
        task = {
            "status": "pending",
            "total": 0,
            "completed": 0,
            "failed": 0,
            "n_workers": 4,
            "created_at": "",
        }
        resp = build_progress_response("t1", task)
        assert resp["progress"] == 0

    def test_handles_none_values(self):
        task = {
            "status": "pending",
            "total": None,
            "completed": None,
            "failed": None,
            "n_workers": None,
            "created_at": None,
        }
        resp = build_progress_response("t1", task)
        assert resp["total"] == 0
        assert resp["n_workers"] == 4

    def test_includes_elapsed_and_remaining_time(self):
        created = datetime(2026, 4, 10, 1, 0, 0, tzinfo=timezone.utc)
        task = {
            "status": "running",
            "total": 10,
            "completed": 2,
            "failed": 1,
            "n_workers": 2,
            "created_at": created.isoformat(),
        }
        with patch("app.services.optimization_task_state.datetime") as mock_datetime:
            mock_datetime.now.return_value = created + timedelta(seconds=15)
            mock_datetime.fromisoformat = datetime.fromisoformat
            resp = build_progress_response("t1", task)

        assert resp["elapsed_time"] == 15.0
        assert resp["remaining_time"] == 35.0

    def test_remaining_time_stays_zero_before_first_worker_batch(self):
        created = datetime(2026, 4, 10, 1, 0, 0, tzinfo=timezone.utc)
        task = {
            "status": "running",
            "total": 10,
            "completed": 0,
            "failed": 0,
            "n_workers": 4,
            "created_at": created.isoformat(),
        }
        with patch("app.services.optimization_task_state.datetime") as mock_datetime:
            mock_datetime.now.return_value = created + timedelta(seconds=20)
            mock_datetime.fromisoformat = datetime.fromisoformat
            resp = build_progress_response("t1", task)

        assert resp["elapsed_time"] == 20.0
        assert resp["remaining_time"] == 0.0

    def test_completed_task_uses_updated_at_for_elapsed_time(self):
        created = datetime(2026, 4, 10, 1, 0, 0, tzinfo=timezone.utc)
        updated = created + timedelta(seconds=6)
        task = {
            "status": "completed",
            "total": 10,
            "completed": 10,
            "failed": 0,
            "n_workers": 2,
            "created_at": created.isoformat(),
            "updated_at": updated.isoformat(),
        }
        with patch("app.services.optimization_task_state.datetime") as mock_datetime:
            mock_datetime.now.return_value = created + timedelta(seconds=30)
            mock_datetime.fromisoformat = datetime.fromisoformat
            resp = build_progress_response("t1", task)

        assert resp["elapsed_time"] == 6.0
        assert resp["remaining_time"] == 0.0

    def test_remaining_time_prefers_recent_completion_speed(self):
        created = datetime(2026, 4, 10, 1, 0, 0, tzinfo=timezone.utc)
        set_runtime_task(
            "t-eta",
            build_initial_runtime_task(
                strategy_id="demo",
                param_ranges={"p": {"min": 1, "max": 10}},
                total=10,
                n_workers=2,
                created_at=created.isoformat(),
                status="running",
            ),
        )
        update_runtime_task(
            "t-eta", completed=1, updated_at=(created + timedelta(seconds=30)).isoformat()
        )
        update_runtime_task(
            "t-eta", completed=2, updated_at=(created + timedelta(seconds=35)).isoformat()
        )
        update_runtime_task(
            "t-eta", completed=3, updated_at=(created + timedelta(seconds=40)).isoformat()
        )
        update_runtime_task(
            "t-eta", completed=4, updated_at=(created + timedelta(seconds=45)).isoformat()
        )
        task = get_runtime_task("t-eta")

        with patch("app.services.optimization_task_state.datetime") as mock_datetime:
            mock_datetime.now.return_value = created + timedelta(seconds=45)
            mock_datetime.fromisoformat = datetime.fromisoformat
            resp = build_progress_response("t-eta", task or {})

        assert resp["elapsed_time"] == 45.0
        assert 30.0 < resp["remaining_time"] < 40.0

    def test_remaining_time_stays_zero_before_first_worker_batch_even_with_progress(self):
        created = datetime(2026, 4, 10, 1, 0, 0, tzinfo=timezone.utc)
        set_runtime_task(
            "t-eta-first",
            build_initial_runtime_task(
                strategy_id="demo",
                param_ranges={"p": {"min": 1, "max": 10}},
                total=12,
                n_workers=4,
                created_at=created.isoformat(),
                status="running",
            ),
        )
        update_runtime_task(
            "t-eta-first",
            completed=3,
            updated_at=(created + timedelta(seconds=18)).isoformat(),
        )
        task = get_runtime_task("t-eta-first")

        with patch("app.services.optimization_task_state.datetime") as mock_datetime:
            mock_datetime.now.return_value = created + timedelta(seconds=18)
            mock_datetime.fromisoformat = datetime.fromisoformat
            resp = build_progress_response("t-eta-first", task or {})

        assert resp["elapsed_time"] == 18.0
        assert resp["remaining_time"] == 0.0

    def test_remaining_time_estimates_after_first_worker_batch(self):
        created = datetime(2026, 4, 10, 1, 0, 0, tzinfo=timezone.utc)
        set_runtime_task(
            "t-eta-first-batch",
            build_initial_runtime_task(
                strategy_id="demo",
                param_ranges={"p": {"min": 1, "max": 10}},
                total=12,
                n_workers=4,
                created_at=created.isoformat(),
                status="running",
            ),
        )
        update_runtime_task(
            "t-eta-first-batch",
            completed=4,
            updated_at=(created + timedelta(seconds=20)).isoformat(),
        )
        task = get_runtime_task("t-eta-first-batch")

        with patch("app.services.optimization_task_state.datetime") as mock_datetime:
            mock_datetime.now.return_value = created + timedelta(seconds=20)
            mock_datetime.fromisoformat = datetime.fromisoformat
            resp = build_progress_response("t-eta-first-batch", task or {})

        assert resp["elapsed_time"] == 20.0
        assert resp["remaining_time"] == 40.0

    def test_remaining_time_counts_down_between_completions(self):
        created = datetime(2026, 4, 10, 1, 0, 0, tzinfo=timezone.utc)
        set_runtime_task(
            "t-eta-countdown",
            build_initial_runtime_task(
                strategy_id="demo",
                param_ranges={"p": {"min": 1, "max": 10}},
                total=10,
                n_workers=2,
                created_at=created.isoformat(),
                status="running",
            ),
        )
        update_runtime_task(
            "t-eta-countdown",
            completed=2,
            updated_at=(created + timedelta(seconds=10)).isoformat(),
        )
        task = get_runtime_task("t-eta-countdown")

        with patch("app.services.optimization_task_state.datetime") as mock_datetime:
            mock_datetime.now.return_value = created + timedelta(seconds=13)
            mock_datetime.fromisoformat = datetime.fromisoformat
            resp = build_progress_response("t-eta-countdown", task or {})

        assert resp["elapsed_time"] == 13.0
        assert resp["remaining_time"] == 37.0

    def test_remaining_time_damps_single_slow_outlier(self):
        created = datetime(2026, 4, 10, 1, 0, 0, tzinfo=timezone.utc)
        set_runtime_task(
            "t-eta-outlier",
            build_initial_runtime_task(
                strategy_id="demo",
                param_ranges={"p": {"min": 1, "max": 10}},
                total=10,
                n_workers=2,
                created_at=created.isoformat(),
                status="running",
            ),
        )
        update_runtime_task(
            "t-eta-outlier",
            completed=1,
            updated_at=(created + timedelta(seconds=5)).isoformat(),
        )
        update_runtime_task(
            "t-eta-outlier",
            completed=2,
            updated_at=(created + timedelta(seconds=10)).isoformat(),
        )
        update_runtime_task(
            "t-eta-outlier",
            completed=3,
            updated_at=(created + timedelta(seconds=50)).isoformat(),
        )
        update_runtime_task(
            "t-eta-outlier",
            completed=4,
            updated_at=(created + timedelta(seconds=55)).isoformat(),
        )
        task = get_runtime_task("t-eta-outlier")

        with patch("app.services.optimization_task_state.datetime") as mock_datetime:
            mock_datetime.now.return_value = created + timedelta(seconds=55)
            mock_datetime.fromisoformat = datetime.fromisoformat
            resp = build_progress_response("t-eta-outlier", task or {})

        assert resp["elapsed_time"] == 55.0
        assert 0.0 < resp["remaining_time"] < 70.0

    def test_estimate_remaining_respects_explicit_worker_count_without_runtime_samples(self):
        assert (
            estimate_remaining_seconds(
                total=12,
                finished=3,
                n_workers=4,
                elapsed_time=18.0,
                status="running",
                task=None,
            )
            == 0.0
        )
        assert (
            estimate_remaining_seconds(
                total=12,
                finished=4,
                n_workers=4,
                elapsed_time=20.0,
                status="running",
                task=None,
            )
            == 40.0
        )


class TestBuildResultsResponse:
    def test_sorts_by_annual_return(self):
        task = {
            "status": "completed",
            "strategy_id": "test",
            "param_names": ["fast"],
            "param_ranges": {"fast": {"min": 5, "max": 20}},
            "total": 2,
            "completed": 2,
            "failed": 0,
            "results": [
                {"params": {"fast": 5}, "metrics": {"annual_return": 0.10}},
                {"params": {"fast": 15}, "metrics": {"annual_return": 0.25}},
            ],
        }
        resp = build_results_response("t1", task)
        assert resp["rows"][0]["annual_return"] == 0.25  # Best first
        assert resp["best"]["annual_return"] == 0.25
        assert resp["rows"][0]["params"] == {"fast": 15}
        assert resp["rows"][0]["result_index"] == 1
        assert resp["rows"][1]["params"] == {"fast": 5}
        assert resp["rows"][1]["result_index"] == 0

    def test_empty_results(self):
        task = {
            "status": "completed",
            "strategy_id": "test",
            "param_names": [],
            "total": 0,
            "completed": 0,
            "failed": 0,
            "results": [],
        }
        resp = build_results_response("t1", task)
        assert resp["rows"] == []
        assert resp["best"] is None

    def test_metric_names_constant(self):
        assert "sharpe_ratio" in METRIC_NAMES
        assert "total_return" in METRIC_NAMES
        assert "max_drawdown" in METRIC_NAMES
