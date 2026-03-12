"""
Log Parser Service Extended Tests.

Extended test coverage for:
- order.log parsing
- data.log parsing
- position.log parsing
- current_position.json parsing
- run_info.json parsing
- parse_all_logs functionality
- TSV parsing utilities
- Safe float conversion utilities
"""

import json
from pathlib import Path

from app.services.log_parser_service import (
    _parse_tsv,
    _safe_float,
    parse_all_logs,
    parse_current_position,
    parse_data_log,
    parse_order_log,
    parse_position_log,
    parse_run_info,
)


class TestParseTsv:
    """Tests for TSV parsing low-level functionality."""

    def test_nonexistent_file(self, tmp_path: Path):
        """Test parsing nonexistent file returns empty list."""
        result = _parse_tsv(tmp_path / "nope.log")
        assert result == []

    def test_empty_file(self, tmp_path: Path):
        """Test parsing empty file returns empty list."""
        f = tmp_path / "empty.log"
        f.write_text("")
        assert _parse_tsv(f) == []

    def test_header_only(self, tmp_path: Path):
        """Test parsing file with header only returns empty list."""
        f = tmp_path / "header.log"
        f.write_text("col1\tcol2\n")
        assert _parse_tsv(f) == []

    def test_short_row(self, tmp_path: Path):
        """Test parsing row with fewer columns than header."""
        f = tmp_path / "short.log"
        f.write_text("a\tb\tc\n1\t2\n")
        rows = _parse_tsv(f)
        assert len(rows) == 1
        assert rows[0]["c"] == ""


class TestSafeFloat:
    """Tests for safe float conversion utilities."""

    def test_normal(self):
        """Test normal float conversion."""
        assert _safe_float("3.14") == 3.14

    def test_nan(self):
        """Test NaN conversion returns 0.0."""
        assert _safe_float("nan") == 0.0

    def test_inf(self):
        """Test infinity conversion returns 0.0."""
        assert _safe_float("inf") == 0.0

    def test_invalid(self):
        """Test invalid string conversion returns 0.0."""
        assert _safe_float("abc") == 0.0

    def test_none(self):
        """Test None conversion returns 0.0."""
        assert _safe_float(None) == 0.0

    def test_custom_default(self):
        """Test custom default value for invalid input."""
        assert _safe_float("bad", default=-1.0) == -1.0


class TestParseOrderLog:
    """Tests for order.log parsing."""

    def test_parse_orders(self, tmp_path: Path):
        """Test parsing order records from log file."""
        (tmp_path / "order.log").write_text(
            "ref\tordtype\tsize\texecuted_price\tcommission\tdt\tdata_name\tstatus\n"
            "1\tBuy\t100\t10.5\t0.1\t2024-01-01 10:00:00\t000001\tCompleted\n"
            "2\tSell\t50\t11.0\t0.05\t2024-01-02 10:00:00\t000001\tCancelled\n"
        )
        orders = parse_order_log(tmp_path)
        assert len(orders) == 1
        assert orders[0]["ref"] == 1
        assert orders[0]["type"] == "Buy"
        assert orders[0]["dt"] == "2024-01-01"

    def test_empty_dir(self, tmp_path: Path):
        """Test parsing with empty directory."""
        assert parse_order_log(tmp_path) == []


class TestParseDataLog:
    """Tests for data.log parsing."""

    def test_parse_data(self, tmp_path: Path):
        """Test parsing market data from log file."""
        (tmp_path / "data.log").write_text(
            "dt\topen\thigh\tlow\tclose\tvolume\tsma20\n"
            "2024-01-01\t10.0\t11.0\t9.5\t10.5\t1000\t10.2\n"
            "2024-01-02\t10.5\t12.0\t10.0\t11.0\t1500\t10.4\n"
        )
        data = parse_data_log(tmp_path)
        assert len(data["dates"]) == 2
        assert len(data["ohlc"]) == 2
        assert len(data["volumes"]) == 2
        assert "sma20" in data["indicators"]
        assert len(data["indicators"]["sma20"]) == 2

    def test_empty_dir(self, tmp_path: Path):
        """Test parsing with empty directory."""
        data = parse_data_log(tmp_path)
        assert data["dates"] == []


class TestParsePositionLog:
    """Tests for position.log parsing."""

    def test_parse_positions(self, tmp_path: Path):
        """Test parsing position records from log file."""
        (tmp_path / "position.log").write_text(
            "dt\tdata_name\tsize\tprice\n2024-01-01 10:00:00\t000001\t100\t10.5\n"
        )
        positions = parse_position_log(tmp_path)
        assert len(positions) == 1
        assert positions[0]["dt"] == "2024-01-01"
        assert positions[0]["size"] == 100
        assert positions[0]["market_value"] == 1050.0

    def test_empty_dir(self, tmp_path: Path):
        """Test parsing with empty directory."""
        assert parse_position_log(tmp_path) == []


class TestParseCurrentPosition:
    """Tests for current_position.json parsing."""

    def test_parse(self, tmp_path: Path):
        """Test parsing current position from JSON file."""
        data = [{"data_name": "000001", "size": 100, "price": 10.5}]
        (tmp_path / "current_position.json").write_text(json.dumps(data))
        result = parse_current_position(tmp_path)
        assert len(result) == 1
        assert result[0]["data_name"] == "000001"
        assert result[0]["market_value"] == 1050.0

    def test_no_file(self, tmp_path: Path):
        """Test parsing when file doesn't exist."""
        assert parse_current_position(tmp_path) == []

    def test_invalid_json(self, tmp_path: Path):
        """Test parsing with invalid JSON content."""
        (tmp_path / "current_position.json").write_text("not json")
        assert parse_current_position(tmp_path) == []


class TestParseRunInfo:
    """Tests for run_info.json parsing."""

    def test_parse(self, tmp_path: Path):
        """Test parsing run info from JSON file."""
        info = {"strategy": "ma_cross", "symbol": "000001"}
        (tmp_path / "run_info.json").write_text(json.dumps(info))
        result = parse_run_info(tmp_path)
        assert result["strategy"] == "ma_cross"

    def test_no_file(self, tmp_path: Path):
        """Test parsing when file doesn't exist."""
        assert parse_run_info(tmp_path) == {}

    def test_invalid_json(self, tmp_path: Path):
        """Test parsing with invalid JSON content."""
        (tmp_path / "run_info.json").write_text("broken")
        assert parse_run_info(tmp_path) == {}


class TestParseAllLogs:
    """Tests for complete log parsing functionality."""

    def test_no_logs_dir(self, tmp_path: Path):
        """Test parsing when logs directory doesn't exist."""
        result = parse_all_logs(tmp_path)
        assert result is None

    def test_full_parse(self, tmp_path: Path):
        """Test complete parsing of all log files."""
        logs_dir = tmp_path / "logs" / "run_20240101"
        logs_dir.mkdir(parents=True)

        (logs_dir / "value.log").write_text(
            "dt\tvalue\tcash\n"
            "2024-01-01\t100000.0\t50000.0\n"
            "2024-01-02\t105000.0\t55000.0\n"
            "2024-01-03\t103000.0\t53000.0\n"
        )
        (logs_dir / "trade.log").write_text(
            "ref\tdtopen\tdtclose\tdata_name\tlong\tsize\tprice\tvalue\tcommission\tpnl\tpnlcomm\tbarlen\tisclosed\n"
            "1\t2024-01-01\t2024-01-02\t000001\t1\t100\t10.5\t1050\t1.0\t50.0\t49.0\t1\t1\n"
        )
        (logs_dir / "order.log").write_text(
            "ref\tordtype\tsize\texecuted_price\tcommission\tdt\tdata_name\tstatus\n"
        )
        (logs_dir / "data.log").write_text("dt\topen\thigh\tlow\tclose\tvolume\n")
        (logs_dir / "run_info.json").write_text(json.dumps({"strategy": "test"}))

        result = parse_all_logs(tmp_path)
        assert result is not None
        assert result["total_return"] > 0
        assert result["total_trades"] == 1
        assert result["win_rate"] > 0
        assert len(result["equity_curve"]) == 3
