"""Tests for optimization_submission module."""

import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services.optimization_submission import generate_param_grid, submit_optimization


class TestGenerateParamGrid:
    def test_single_param(self):
        grid = generate_param_grid({"fast": {"start": 5, "end": 15, "step": 5}})
        assert grid == [{"fast": 5.0}, {"fast": 10.0}, {"fast": 15.0}]

    def test_int_type(self):
        grid = generate_param_grid(
            {"period": {"start": 10, "end": 30, "step": 10, "type": "int"}}
        )
        assert grid == [{"period": 10}, {"period": 20}, {"period": 30}]

    def test_two_params_cartesian_product(self):
        grid = generate_param_grid(
            {
                "a": {"start": 1, "end": 2, "step": 1},
                "b": {"start": 10, "end": 20, "step": 10},
            }
        )
        assert len(grid) == 4
        assert {"a": 1.0, "b": 10.0} in grid
        assert {"a": 2.0, "b": 20.0} in grid

    def test_single_value_range(self):
        grid = generate_param_grid({"x": {"start": 5, "end": 5, "step": 1}})
        assert grid == [{"x": 5.0}]

    def test_float_step(self):
        grid = generate_param_grid({"x": {"start": 0.1, "end": 0.3, "step": 0.1}})
        assert len(grid) == 3
        assert all(isinstance(combo["x"], float) for combo in grid)

    def test_empty_params(self):
        grid = generate_param_grid({})
        assert grid == [{}]


class TestSubmitOptimization:
    def _make_deps(self, *, strategy_dir_exists=True, run_py_exists=True):
        """Build a dependency dict for submit_optimization."""
        strategy_dir = Path("/fake/strategies/ma_cross")
        mock_thread = MagicMock()

        deps = {
            "get_strategy_dir": MagicMock(return_value=strategy_dir),
            "generate_param_grid_fn": MagicMock(
                return_value=[{"fast": 5}, {"fast": 10}]
            ),
            "set_task_fn": MagicMock(),
            "build_initial_runtime_task_fn": MagicMock(return_value={"status": "running"}),
            "created_at_fn": MagicMock(return_value="2024-01-01T00:00:00"),
            "running_status": "running",
            "thread_cls": MagicMock(return_value=mock_thread),
            "run_optimization_thread_fn": MagicMock(),
            "task_id_factory": MagicMock(return_value="auto-task-id"),
        }

        # Patch Path.is_file via the get_strategy_dir result
        if not run_py_exists:
            # Make run.py not exist
            deps["get_strategy_dir"] = MagicMock(
                return_value=MagicMock(
                    __truediv__=MagicMock(
                        return_value=MagicMock(is_file=MagicMock(return_value=False))
                    )
                )
            )

        return deps, mock_thread

    def test_returns_task_id(self, tmp_path):
        strategy_dir = tmp_path / "ma_cross"
        strategy_dir.mkdir()
        (strategy_dir / "run.py").write_text("# strategy")

        deps = {
            "get_strategy_dir": MagicMock(return_value=strategy_dir),
            "generate_param_grid_fn": MagicMock(return_value=[{"fast": 5}]),
            "set_task_fn": MagicMock(),
            "build_initial_runtime_task_fn": MagicMock(return_value={}),
            "created_at_fn": MagicMock(return_value="now"),
            "running_status": "running",
            "thread_cls": MagicMock(return_value=MagicMock()),
            "run_optimization_thread_fn": MagicMock(),
            "task_id_factory": MagicMock(return_value="gen-id"),
        }

        result = submit_optimization(
            strategy_id="ma_cross",
            param_ranges={"fast": {"start": 5, "end": 5, "step": 1}},
            **deps,
        )
        assert result == "gen-id"

    def test_uses_provided_task_id(self, tmp_path):
        strategy_dir = tmp_path / "test_strat"
        strategy_dir.mkdir()
        (strategy_dir / "run.py").write_text("# strategy")

        deps = {
            "get_strategy_dir": MagicMock(return_value=strategy_dir),
            "generate_param_grid_fn": MagicMock(return_value=[{"a": 1}]),
            "set_task_fn": MagicMock(),
            "build_initial_runtime_task_fn": MagicMock(return_value={}),
            "created_at_fn": MagicMock(return_value="now"),
            "running_status": "running",
            "thread_cls": MagicMock(return_value=MagicMock()),
            "run_optimization_thread_fn": MagicMock(),
            "task_id_factory": MagicMock(return_value="should-not-use"),
        }

        result = submit_optimization(
            strategy_id="test_strat",
            param_ranges={"a": {"start": 1, "end": 1, "step": 1}},
            task_id="my-custom-id",
            **deps,
        )
        assert result == "my-custom-id"
        deps["task_id_factory"].assert_not_called()

    def test_raises_if_run_py_missing(self, tmp_path):
        strategy_dir = tmp_path / "no_run"
        strategy_dir.mkdir()
        # No run.py

        deps = {
            "get_strategy_dir": MagicMock(return_value=strategy_dir),
            "generate_param_grid_fn": MagicMock(),
            "set_task_fn": MagicMock(),
            "build_initial_runtime_task_fn": MagicMock(),
            "created_at_fn": MagicMock(),
            "running_status": "running",
            "thread_cls": MagicMock(),
            "run_optimization_thread_fn": MagicMock(),
            "task_id_factory": MagicMock(),
        }

        with pytest.raises(ValueError, match="not found or missing run.py"):
            submit_optimization(
                strategy_id="no_run",
                param_ranges={"a": {"start": 1, "end": 1, "step": 1}},
                **deps,
            )

    def test_raises_if_grid_empty(self, tmp_path):
        strategy_dir = tmp_path / "strat"
        strategy_dir.mkdir()
        (strategy_dir / "run.py").write_text("# strategy")

        deps = {
            "get_strategy_dir": MagicMock(return_value=strategy_dir),
            "generate_param_grid_fn": MagicMock(return_value=[]),
            "set_task_fn": MagicMock(),
            "build_initial_runtime_task_fn": MagicMock(),
            "created_at_fn": MagicMock(),
            "running_status": "running",
            "thread_cls": MagicMock(),
            "run_optimization_thread_fn": MagicMock(),
            "task_id_factory": MagicMock(),
        }

        with pytest.raises(ValueError, match="grid is empty"):
            submit_optimization(
                strategy_id="strat",
                param_ranges={},
                **deps,
            )

    def test_starts_daemon_thread(self, tmp_path):
        strategy_dir = tmp_path / "strat"
        strategy_dir.mkdir()
        (strategy_dir / "run.py").write_text("# strategy")

        mock_thread = MagicMock()
        deps = {
            "get_strategy_dir": MagicMock(return_value=strategy_dir),
            "generate_param_grid_fn": MagicMock(return_value=[{"x": 1}]),
            "set_task_fn": MagicMock(),
            "build_initial_runtime_task_fn": MagicMock(return_value={}),
            "created_at_fn": MagicMock(return_value="now"),
            "running_status": "running",
            "thread_cls": MagicMock(return_value=mock_thread),
            "run_optimization_thread_fn": MagicMock(),
            "task_id_factory": MagicMock(return_value="tid"),
        }

        submit_optimization(
            strategy_id="strat",
            param_ranges={"x": {"start": 1, "end": 1, "step": 1}},
            **deps,
        )

        deps["thread_cls"].assert_called_once()
        call_kwargs = deps["thread_cls"].call_args
        assert call_kwargs[1]["daemon"] is True
        mock_thread.start.assert_called_once()

    def test_set_task_called_with_build_result(self, tmp_path):
        strategy_dir = tmp_path / "strat"
        strategy_dir.mkdir()
        (strategy_dir / "run.py").write_text("# strategy")

        build_result = {"status": "running", "total": 5}
        deps = {
            "get_strategy_dir": MagicMock(return_value=strategy_dir),
            "generate_param_grid_fn": MagicMock(return_value=[{"x": i} for i in range(5)]),
            "set_task_fn": MagicMock(),
            "build_initial_runtime_task_fn": MagicMock(return_value=build_result),
            "created_at_fn": MagicMock(return_value="now"),
            "running_status": "running",
            "thread_cls": MagicMock(return_value=MagicMock()),
            "run_optimization_thread_fn": MagicMock(),
            "task_id_factory": MagicMock(return_value="tid"),
        }

        submit_optimization(
            strategy_id="strat",
            param_ranges={"x": {"start": 1, "end": 5, "step": 1}},
            **deps,
        )

        deps["set_task_fn"].assert_called_once_with("tid", build_result)
