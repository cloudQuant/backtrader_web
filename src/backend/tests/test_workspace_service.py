from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.workspace_service import WorkspaceService


@pytest.mark.asyncio
async def test_resolve_unit_bar_count_uses_resolved_log_dir_parent_fallback():
    backtest_service = SimpleNamespace(
        task_manager=SimpleNamespace(
            get_task=AsyncMock(
                return_value=SimpleNamespace(
                    log_dir="/tmp/test_logs/task-123",
                    strategy_id="demo_strategy",
                )
            )
        )
    )

    with patch("app.api.analytics._resolve_log_dir", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.return_value = Path("/tmp/test_logs")
        with patch("pathlib.Path.is_dir", return_value=True):
            with patch("app.services.log_parser_service.parse_log_dir") as mock_parse_log_dir:
                mock_parse_log_dir.return_value = {
                    "kline": {"dates": ["2024-01-01", "2024-01-02", "2024-01-03"]}
                }
                result = await WorkspaceService._resolve_unit_bar_count(
                    backtest_service,
                    "task-123",
                    "user-1",
                )

    assert result == 3
    mock_resolve.assert_awaited_once_with("task-123", "demo_strategy")
    mock_parse_log_dir.assert_called_once_with(Path("/tmp/test_logs"))


def test_task_elapsed_seconds_uses_persisted_task_timestamps():
    task = SimpleNamespace(
        created_at=datetime(2026, 4, 10, 1, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 10, 1, 0, 5, tzinfo=timezone.utc)
        + timedelta(milliseconds=250),
        status="completed",
    )

    assert WorkspaceService._task_elapsed_seconds(task) == 5.25


def test_db_task_elapsed_seconds_uses_now_for_running_tasks():
    task = SimpleNamespace(
        created_at=datetime(2026, 4, 10, 1, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 10, 1, 0, 2, tzinfo=timezone.utc),
        status="running",
    )

    with patch("app.services.workspace_service.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime(2026, 4, 10, 1, 0, 9, tzinfo=timezone.utc)
        assert WorkspaceService._db_task_elapsed_seconds(task) == 9.0


def test_runtime_optimization_elapsed_seconds_with_utc_iso_string():
    """created_at stored as tz-aware UTC ISO-8601 string should yield positive elapsed.

    Bug8 regression: a previous implementation used datetime.now().isoformat() to
    populate the runtime task's created_at, which returned a naive local-time string.
    The elapsed helper then treated it as UTC, producing a negative delta on any
    non-UTC host and returning None.  The fix is to persist tz-aware timestamps and
    this test pins that behaviour.
    """
    created = datetime(2026, 4, 10, 1, 0, 0, tzinfo=timezone.utc)
    task = {"created_at": created.isoformat()}

    with patch("app.services.workspace_service.datetime") as mock_datetime:
        mock_datetime.now.return_value = created + timedelta(seconds=12)
        mock_datetime.fromisoformat = datetime.fromisoformat
        result = WorkspaceService._runtime_optimization_elapsed_seconds(task)

    assert result == 12.0


def test_runtime_optimization_elapsed_seconds_naive_iso_string_treated_as_utc():
    """Legacy naive ISO strings still parse (treated as UTC) rather than failing."""
    created = datetime(2026, 4, 10, 1, 0, 0)  # naive
    task = {"created_at": created.isoformat()}

    with patch("app.services.workspace_service.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime(2026, 4, 10, 1, 0, 5, tzinfo=timezone.utc)
        mock_datetime.fromisoformat = datetime.fromisoformat
        result = WorkspaceService._runtime_optimization_elapsed_seconds(task)

    assert result == 5.0


def test_runtime_optimization_elapsed_seconds_uses_updated_at_for_terminal_status():
    created = datetime(2026, 4, 10, 1, 0, 0, tzinfo=timezone.utc)
    updated = created + timedelta(seconds=6)
    task = {
        "status": "completed",
        "created_at": created.isoformat(),
        "updated_at": updated.isoformat(),
    }

    with patch("app.services.workspace_service.datetime") as mock_datetime:
        mock_datetime.now.return_value = created + timedelta(seconds=30)
        mock_datetime.fromisoformat = datetime.fromisoformat
        result = WorkspaceService._runtime_optimization_elapsed_seconds(task)

    assert result == 6.0


def test_runtime_optimization_elapsed_seconds_returns_none_when_missing():
    assert WorkspaceService._runtime_optimization_elapsed_seconds(None) is None
    assert WorkspaceService._runtime_optimization_elapsed_seconds({}) is None
    assert (
        WorkspaceService._runtime_optimization_elapsed_seconds({"created_at": "not-a-date"}) is None
    )


def test_resolve_optimization_progress_prefers_db_terminal_task():
    created = datetime(2026, 4, 10, 1, 0, 0, tzinfo=timezone.utc)
    runtime_task = {
        "status": "running",
        "total": 10,
        "completed": 5,
        "failed": 0,
        "n_workers": 2,
        "created_at": created.isoformat(),
        "updated_at": (created + timedelta(seconds=20)).isoformat(),
    }
    db_task = SimpleNamespace(
        status="completed",
        total=10,
        completed=10,
        failed=0,
        n_workers=2,
        created_at=created,
        updated_at=created + timedelta(seconds=24),
    )

    progress = WorkspaceService._resolve_optimization_progress(runtime_task, db_task)

    assert progress == {
        "opt_status": "completed",
        "opt_total": 10,
        "opt_completed": 10,
        "opt_progress": 100.0,
        "opt_elapsed_time": 24.0,
        "opt_remaining_time": 0.0,
    }


def test_db_task_elapsed_seconds_zero_remaining_for_terminal_task():
    task = SimpleNamespace(
        created_at=datetime(2026, 4, 10, 1, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 10, 1, 0, 9, tzinfo=timezone.utc),
        status="completed",
        total=12,
        completed=12,
        failed=0,
        n_workers=4,
    )

    elapsed = WorkspaceService._db_task_elapsed_seconds(task)

    assert elapsed == 9.0
