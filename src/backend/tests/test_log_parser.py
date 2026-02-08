"""
日志解析服务测试
"""
import tempfile
from pathlib import Path

from app.services.log_parser_service import (
    parse_value_log,
    parse_trade_log,
    parse_data_log,
    find_latest_log_dir,
)


class TestParseValueLog:
    """value.log 解析测试"""

    def test_parse_valid_log(self, tmp_path: Path):
        log_dir = tmp_path / "log_20240101"
        log_dir.mkdir()
        (log_dir / "value.log").write_text(
            "datetime\tvalue\tcash\n"
            "2024-01-01\t100000.0\t50000.0\n"
            "2024-01-02\t101000.0\t49000.0\n"
        )
        result = parse_value_log(log_dir)
        assert "dates" in result
        assert "equity_curve" in result
        assert len(result["dates"]) == 2

    def test_parse_empty_dir(self, tmp_path: Path):
        result = parse_value_log(tmp_path)
        assert result == {} or result.get("dates") == []

    def test_parse_nonexistent_dir(self, tmp_path: Path):
        result = parse_value_log(tmp_path / "nonexistent")
        assert result == {} or result.get("dates") == []


class TestParseTradeLog:
    """trade.log 解析测试"""

    def test_parse_valid_trade_log(self, tmp_path: Path):
        log_dir = tmp_path / "log_20240101"
        log_dir.mkdir()
        (log_dir / "trade.log").write_text(
            "ref\tdtopen\tdtclose\tlong\tsize\tprice\tpnl\tpnlcomm\tbarlen\tisclosed\n"
            "1\t2024-01-01\t2024-01-05\t1\t100\t10.5\t50.0\t45.0\t5\t1\n"
        )
        trades = parse_trade_log(log_dir)
        assert isinstance(trades, list)
        assert len(trades) == 1
        assert trades[0]["direction"] == "buy"
        assert trades[0]["size"] == 100.0

    def test_parse_empty_dir(self, tmp_path: Path):
        trades = parse_trade_log(tmp_path)
        assert trades == [] or trades is not None


class TestFindLatestLogDir:
    """查找最新日志目录测试"""

    def test_find_latest(self, tmp_path: Path):
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        (logs_dir / "log_20240101").mkdir()
        (logs_dir / "log_20240102").mkdir()
        result = find_latest_log_dir(tmp_path)
        assert result is not None
        assert "20240102" in str(result)

    def test_no_log_dirs(self, tmp_path: Path):
        result = find_latest_log_dir(tmp_path)
        assert result is None

    def test_empty_logs_dir(self, tmp_path: Path):
        (tmp_path / "logs").mkdir()
        result = find_latest_log_dir(tmp_path)
        assert result is None
