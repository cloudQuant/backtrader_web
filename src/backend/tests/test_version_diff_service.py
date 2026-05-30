"""Tests for version_diff_service - code/params/performance diff utilities."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.version_diff_service import (
    generate_code_diff,
    generate_params_diff,
    generate_performance_diff,
)


class TestGenerateCodeDiff:
    """Test code diff generation."""

    def test_identical_code_produces_empty_diff(self):
        code = "def foo():\n    return 1\n"
        result = generate_code_diff(code, code, "v1", "v2")
        assert result == ""

    def test_single_line_change(self):
        code1 = "def foo():\n    return 1\n"
        code2 = "def foo():\n    return 2\n"
        result = generate_code_diff(code1, code2, "v1.py", "v2.py")
        assert "--- v1.py" in result
        assert "+++ v2.py" in result
        assert "-    return 1" in result
        assert "+    return 2" in result

    def test_added_lines(self):
        code1 = "line1\n"
        code2 = "line1\nline2\nline3\n"
        result = generate_code_diff(code1, code2, "old", "new")
        assert "+line2" in result
        assert "+line3" in result

    def test_removed_lines(self):
        code1 = "line1\nline2\nline3\n"
        code2 = "line1\n"
        result = generate_code_diff(code1, code2, "old", "new")
        assert "-line2" in result
        assert "-line3" in result

    def test_empty_to_content(self):
        result = generate_code_diff("", "hello\nworld\n", "empty", "filled")
        assert "+hello" in result
        assert "+world" in result

    def test_content_to_empty(self):
        result = generate_code_diff("hello\nworld\n", "", "filled", "empty")
        assert "-hello" in result
        assert "-world" in result

    def test_multiline_complex_diff(self):
        code1 = """import numpy as np

class MyStrategy:
    def __init__(self):
        self.period = 20

    def next(self):
        pass
"""
        code2 = """import numpy as np
import pandas as pd

class MyStrategy:
    def __init__(self):
        self.period = 30
        self.threshold = 0.5

    def next(self):
        self.execute()
"""
        result = generate_code_diff(code1, code2, "v1.py", "v2.py")
        assert "+import pandas as pd" in result
        assert "-        self.period = 20" in result
        assert "+        self.period = 30" in result
        assert "+        self.threshold = 0.5" in result


class TestGenerateParamsDiff:
    """Test parameter diff generation."""

    def test_identical_params(self):
        params = {"period": 20, "threshold": 0.5}
        result = generate_params_diff(params, params)
        assert result["added"] == {}
        assert result["removed"] == {}
        assert result["modified"] == {}
        assert result["unchanged"] == {"period": 20, "threshold": 0.5}

    def test_added_params(self):
        params1 = {"period": 20}
        params2 = {"period": 20, "threshold": 0.5}
        result = generate_params_diff(params1, params2)
        assert result["added"] == {"threshold": 0.5}
        assert result["removed"] == {}
        assert result["modified"] == {}
        assert result["unchanged"] == {"period": 20}

    def test_removed_params(self):
        params1 = {"period": 20, "threshold": 0.5}
        params2 = {"period": 20}
        result = generate_params_diff(params1, params2)
        assert result["added"] == {}
        assert result["removed"] == {"threshold": 0.5}
        assert result["modified"] == {}
        assert result["unchanged"] == {"period": 20}

    def test_modified_params(self):
        params1 = {"period": 20, "threshold": 0.5}
        params2 = {"period": 30, "threshold": 0.5}
        result = generate_params_diff(params1, params2)
        assert result["modified"] == {"period": {"from": 20, "to": 30}}
        assert result["unchanged"] == {"threshold": 0.5}

    def test_empty_params(self):
        result = generate_params_diff({}, {})
        assert result["added"] == {}
        assert result["removed"] == {}
        assert result["modified"] == {}
        assert result["unchanged"] == {}

    def test_all_new_params(self):
        result = generate_params_diff({}, {"a": 1, "b": 2})
        assert result["added"] == {"a": 1, "b": 2}
        assert result["removed"] == {}

    def test_all_removed_params(self):
        result = generate_params_diff({"a": 1, "b": 2}, {})
        assert result["removed"] == {"a": 1, "b": 2}
        assert result["added"] == {}

    def test_complex_param_values(self):
        params1 = {"nested": {"a": 1}, "list_param": [1, 2, 3]}
        params2 = {"nested": {"a": 2}, "list_param": [1, 2, 3]}
        result = generate_params_diff(params1, params2)
        assert result["modified"] == {"nested": {"from": {"a": 1}, "to": {"a": 2}}}
        assert result["unchanged"] == {"list_param": [1, 2, 3]}


class TestGeneratePerformanceDiff:
    """Test performance diff generation."""

    @pytest.mark.asyncio
    async def test_no_results_available(self):
        """When no backtest results exist for either version."""
        with patch("app.services.version_diff_service.db") as mock_db:
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.first.return_value = None
            mock_session.execute.return_value = mock_result
            mock_db.async_session_maker.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_db.async_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await generate_performance_diff("v1", "v2")
            assert result["available"] is False

    @pytest.mark.asyncio
    async def test_only_from_version_has_results(self):
        """When only the source version has backtest results."""
        call_count = [0]

        async def mock_session_context():
            session = AsyncMock()
            mock_result = MagicMock()

            nonlocal call_count
            if call_count[0] == 0:
                # First call - from_version has results
                mock_task = MagicMock()
                mock_task.id = "task1"
                mock_task.created_at = MagicMock()
                mock_task.created_at.isoformat.return_value = "2024-01-01T00:00:00"
                mock_res = MagicMock()
                mock_res.total_return = 0.15
                mock_res.annual_return = 0.12
                mock_res.sharpe_ratio = 1.5
                mock_res.max_drawdown = 0.1
                mock_res.win_rate = 0.6
                mock_res.total_trades = 100
                mock_res.profitable_trades = 60
                mock_res.losing_trades = 40
                mock_result.first.return_value = (mock_task, mock_res)
            else:
                # Second call - to_version has no results
                mock_result.first.return_value = None

            call_count[0] += 1
            session.execute.return_value = mock_result
            return session

        with patch("app.services.version_diff_service.db") as mock_db:
            mock_db.async_session_maker.return_value.__aenter__ = AsyncMock(
                side_effect=mock_session_context
            )
            mock_db.async_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await generate_performance_diff("v1", "v2")
            assert result["available"] is False

    @pytest.mark.asyncio
    async def test_both_versions_have_results(self):
        """When both versions have backtest results, diff is computed."""

        def make_mock_row(total_return, sharpe, max_dd, trades):
            task = MagicMock()
            task.id = f"task_{total_return}"
            task.created_at = MagicMock()
            task.created_at.isoformat.return_value = "2024-01-01T00:00:00"
            res = MagicMock()
            res.total_return = total_return
            res.annual_return = total_return * 0.8
            res.sharpe_ratio = sharpe
            res.max_drawdown = max_dd
            res.win_rate = 0.6
            res.total_trades = trades
            res.profitable_trades = int(trades * 0.6)
            res.losing_trades = trades - int(trades * 0.6)
            return (task, res)

        rows = [
            make_mock_row(0.10, 1.2, 0.08, 80),
            make_mock_row(0.20, 1.8, 0.05, 120),
        ]
        call_idx = [0]

        async def mock_session_context():
            session = AsyncMock()
            mock_result = MagicMock()
            mock_result.first.return_value = rows[call_idx[0]]
            call_idx[0] += 1
            session.execute.return_value = mock_result
            return session

        with patch("app.services.version_diff_service.db") as mock_db:
            mock_db.async_session_maker.return_value.__aenter__ = AsyncMock(
                side_effect=mock_session_context
            )
            mock_db.async_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await generate_performance_diff("v1", "v2")
            assert result["available"] is True
            assert "diff" in result
            # to - from: 0.20 - 0.10 = 0.10
            assert abs(result["diff"]["total_return"] - 0.10) < 0.001
            assert abs(result["diff"]["sharpe_ratio"] - 0.6) < 0.001
