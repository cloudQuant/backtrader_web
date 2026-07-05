from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.workspace import StrategyUnitCreate, StrategyUnitUpdate
from app.services import workspace_unit_runtime
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


@pytest.mark.asyncio
async def test_strategy_unit_create_update_serializes_python_json_values(
    client,
    auth_headers: dict[str, str],
):
    service = WorkspaceService()
    workspace_response = await client.post(
        "/api/v1/workspace/",
        headers=auth_headers,
        json={"name": "JSON 清洗", "workspace_type": "research"},
    )
    assert workspace_response.status_code == 201
    workspace = workspace_response.json()

    unit = await service.create_unit(
        workspace["id"],
        workspace["user_id"],
        StrategyUnitCreate(
            strategy_id="simulate/gateway_dual_ma",
            strategy_name="Date Strategy",
            symbol="000001.SZ",
            timeframe="1d",
            data_config={
                "start_date": date(2024, 1, 1),
                "end_date": date(2024, 2, 1),
                "windows": [date(2024, 1, 15)],
            },
            unit_settings={
                "commission": Decimal("0.0003"),
                "generated_at": datetime(2024, 1, 1, 9, 30, tzinfo=timezone.utc),
            },
            params={"lookback": Decimal("20")},
            optimization_config={"fast_range": (5, 10)},
        ),
    )

    assert unit is not None
    assert unit["data_config"]["start_date"] == "2024-01-01"
    assert unit["data_config"]["end_date"] == "2024-02-01"
    assert unit["data_config"]["windows"] == ["2024-01-15"]
    assert unit["unit_settings"]["commission"] == pytest.approx(0.0003)
    assert unit["unit_settings"]["generated_at"] == "2024-01-01T09:30:00+00:00"
    assert unit["params"]["lookback"] == pytest.approx(20.0)
    assert unit["optimization_config"]["fast_range"] == [5, 10]

    updated = await service.update_unit(
        workspace["id"],
        unit["id"],
        workspace["user_id"],
        StrategyUnitUpdate(
            data_config={"start_date": date(2024, 3, 1), "end_date": date(2024, 3, 31)},
            unit_settings={"reviewed_at": datetime(2024, 3, 2, tzinfo=timezone.utc)},
        ),
    )

    assert updated is not None
    assert updated["data_config"]["start_date"] == "2024-03-01"
    assert updated["data_config"]["end_date"] == "2024-03-31"
    assert updated["unit_settings"]["reviewed_at"] == "2024-03-02T00:00:00+00:00"


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

    with patch("app.services.workspace._helpers.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime(2026, 4, 10, 1, 0, 9, tzinfo=timezone.utc)
        assert WorkspaceService._db_task_elapsed_seconds(task) == 9.0


def test_db_task_elapsed_seconds_treats_naive_db_datetimes_as_utc():
    task = SimpleNamespace(
        created_at=datetime(2026, 4, 10, 1, 0, 0),
        updated_at=datetime(2026, 4, 10, 1, 0, 2),
        status="running",
    )

    with patch("app.services.workspace._helpers.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime(2026, 4, 10, 1, 0, 9, tzinfo=timezone.utc)
        assert WorkspaceService._db_task_elapsed_seconds(task) == 9.0


def test_unit_runtime_template_defines_signed_rate_helper():
    assert "def _normalise_signed_rate" in workspace_unit_runtime._UNIT_RUN_PY


def test_unit_runtime_template_resolves_pandas_data_class_compatibly():
    assert "_PANDAS_DATA_CLASS = getattr(bt.feeds, 'PandasData', None)" in (
        workspace_unit_runtime._UNIT_RUN_PY
    )
    assert "from backtrader.feeds.pandafeed import PandasData" in (
        workspace_unit_runtime._UNIT_RUN_PY
    )


def test_unit_runtime_template_does_not_force_default_observers():
    assert "stdstats=True" not in workspace_unit_runtime._UNIT_RUN_PY
    assert "stdstats=_safe_bool" in workspace_unit_runtime._UNIT_RUN_PY


def test_unit_runtime_asset_type_prefers_explicit_unit_setting_over_strategy_style():
    asset_type = workspace_unit_runtime._asset_type_for_unit_config(
        category="trend",
        symbol="SA505",
        data_config={"range_type": "date"},
        unit_settings={"asset_type": "future"},
    )

    assert asset_type == "future"


def test_unit_runtime_asset_type_infers_future_symbol_for_strategy_style_category():
    asset_type = workspace_unit_runtime._asset_type_for_unit_config(
        category="trend",
        symbol="SA505",
        data_config={"range_type": "date"},
        unit_settings={},
    )

    assert asset_type == "future"


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

    with patch("app.services.workspace._helpers.datetime") as mock_datetime:
        mock_datetime.now.return_value = created + timedelta(seconds=12)
        mock_datetime.fromisoformat = datetime.fromisoformat
        result = WorkspaceService._runtime_optimization_elapsed_seconds(task)

    assert result == 12.0


def test_runtime_optimization_elapsed_seconds_naive_iso_string_treated_as_utc():
    """Legacy naive ISO strings still parse (treated as UTC) rather than failing."""
    created = datetime(2026, 4, 10, 1, 0, 0)  # naive
    task = {"created_at": created.isoformat()}

    with patch("app.services.workspace._helpers.datetime") as mock_datetime:
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

    with patch("app.services.workspace._helpers.datetime") as mock_datetime:
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
