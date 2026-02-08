"""
回测服务单元测试
"""
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

from app.services.backtest_service import BacktestService
from app.schemas.backtest import BacktestRequest


class TestBacktestServiceHelpers:
    """回测服务辅助方法测试"""

    def test_has_custom_params_default(self):
        svc = BacktestService()
        req = BacktestRequest(
            strategy_id="test", symbol="000001.SZ",
            start_date="2024-01-01T00:00:00", end_date="2024-06-30T00:00:00",
            initial_cash=100000, commission=0.001, params={},
        )
        assert svc._has_custom_params(req) is False

    def test_has_custom_params_custom_cash(self):
        svc = BacktestService()
        req = BacktestRequest(
            strategy_id="test", symbol="000001.SZ",
            start_date="2024-01-01T00:00:00", end_date="2024-06-30T00:00:00",
            initial_cash=200000, commission=0.001, params={},
        )
        assert svc._has_custom_params(req) is True

    def test_has_custom_params_with_params(self):
        svc = BacktestService()
        req = BacktestRequest(
            strategy_id="test", symbol="000001.SZ",
            start_date="2024-01-01T00:00:00", end_date="2024-06-30T00:00:00",
            initial_cash=100000, commission=0.001, params={"period": 20},
        )
        assert svc._has_custom_params(req) is True

    def test_strip_asserts(self, tmp_path: Path):
        run_py = tmp_path / "run.py"
        run_py.write_text("x = 1\nassert x == 1\nassert(x > 0)\ny = 2\n")
        BacktestService._strip_asserts(run_py)
        content = run_py.read_text()
        assert "assert x == 1" not in content
        assert "assert(x > 0)" not in content
        assert "x = 1" in content
        assert "y = 2" in content

    def test_strip_asserts_no_file(self, tmp_path: Path):
        BacktestService._strip_asserts(tmp_path / "nonexistent.py")  # should not raise

    def test_write_temp_config(self, tmp_path: Path):
        svc = BacktestService()
        config_path = tmp_path / "config.yaml"
        req = BacktestRequest(
            strategy_id="test", symbol="600519.SH",
            start_date="2024-01-01T00:00:00", end_date="2024-06-30T00:00:00",
            initial_cash=200000, commission=0.002, params={"period": 30},
        )
        svc._write_temp_config(config_path, req, None)
        content = config_path.read_text()
        assert "200000" in content
        assert "0.002" in content
        assert "period" in content
        assert "600519.SH" in content

    def test_write_temp_config_with_existing(self, tmp_path: Path):
        svc = BacktestService()
        config_path = tmp_path / "config.yaml"
        original = "strategy:\n  name: test\nparams:\n  old_param: 10\n"
        svc._write_temp_config(config_path, BacktestRequest(
            strategy_id="test", symbol="000001.SZ",
            start_date="2024-01-01T00:00:00", end_date="2024-06-30T00:00:00",
            initial_cash=100000, commission=0.001, params={"new_param": 5},
        ), original)
        content = config_path.read_text()
        assert "new_param" in content
