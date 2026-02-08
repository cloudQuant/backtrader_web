"""
日志解析服务扩展测试 - 覆盖 order, data, position, current_position, run_info, parse_all_logs
"""
import json
from pathlib import Path

from app.services.log_parser_service import (
    parse_order_log,
    parse_data_log,
    parse_position_log,
    parse_current_position,
    parse_run_info,
    parse_all_logs,
    _parse_tsv,
    _safe_float,
)


class TestParseTsv:
    """TSV 解析底层测试"""

    def test_nonexistent_file(self, tmp_path: Path):
        result = _parse_tsv(tmp_path / "nope.log")
        assert result == []

    def test_empty_file(self, tmp_path: Path):
        f = tmp_path / "empty.log"
        f.write_text("")
        assert _parse_tsv(f) == []

    def test_header_only(self, tmp_path: Path):
        f = tmp_path / "header.log"
        f.write_text("col1\tcol2\n")
        assert _parse_tsv(f) == []

    def test_short_row(self, tmp_path: Path):
        f = tmp_path / "short.log"
        f.write_text("a\tb\tc\n1\t2\n")
        rows = _parse_tsv(f)
        assert len(rows) == 1
        assert rows[0]["c"] == ""


class TestSafeFloat:
    """安全浮点转换测试"""

    def test_normal(self):
        assert _safe_float("3.14") == 3.14

    def test_nan(self):
        assert _safe_float("nan") == 0.0

    def test_inf(self):
        assert _safe_float("inf") == 0.0

    def test_invalid(self):
        assert _safe_float("abc") == 0.0

    def test_none(self):
        assert _safe_float(None) == 0.0

    def test_custom_default(self):
        assert _safe_float("bad", default=-1.0) == -1.0


class TestParseOrderLog:
    """order.log 解析测试"""

    def test_parse_orders(self, tmp_path: Path):
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
        assert parse_order_log(tmp_path) == []


class TestParseDataLog:
    """data.log 解析测试"""

    def test_parse_data(self, tmp_path: Path):
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
        data = parse_data_log(tmp_path)
        assert data["dates"] == []


class TestParsePositionLog:
    """position.log 解析测试"""

    def test_parse_positions(self, tmp_path: Path):
        (tmp_path / "position.log").write_text(
            "dt\tdata_name\tsize\tprice\n"
            "2024-01-01 10:00:00\t000001\t100\t10.5\n"
        )
        positions = parse_position_log(tmp_path)
        assert len(positions) == 1
        assert positions[0]["dt"] == "2024-01-01"
        assert positions[0]["size"] == 100
        assert positions[0]["market_value"] == 1050.0

    def test_empty_dir(self, tmp_path: Path):
        assert parse_position_log(tmp_path) == []


class TestParseCurrentPosition:
    """current_position.json 解析测试"""

    def test_parse(self, tmp_path: Path):
        data = [{"data_name": "000001", "size": 100, "price": 10.5}]
        (tmp_path / "current_position.json").write_text(json.dumps(data))
        result = parse_current_position(tmp_path)
        assert len(result) == 1
        assert result[0]["data_name"] == "000001"
        assert result[0]["market_value"] == 1050.0

    def test_no_file(self, tmp_path: Path):
        assert parse_current_position(tmp_path) == []

    def test_invalid_json(self, tmp_path: Path):
        (tmp_path / "current_position.json").write_text("not json")
        assert parse_current_position(tmp_path) == []


class TestParseRunInfo:
    """run_info.json 解析测试"""

    def test_parse(self, tmp_path: Path):
        info = {"strategy": "ma_cross", "symbol": "000001"}
        (tmp_path / "run_info.json").write_text(json.dumps(info))
        result = parse_run_info(tmp_path)
        assert result["strategy"] == "ma_cross"

    def test_no_file(self, tmp_path: Path):
        assert parse_run_info(tmp_path) == {}

    def test_invalid_json(self, tmp_path: Path):
        (tmp_path / "run_info.json").write_text("broken")
        assert parse_run_info(tmp_path) == {}


class TestParseAllLogs:
    """完整日志解析测试"""

    def test_no_logs_dir(self, tmp_path: Path):
        result = parse_all_logs(tmp_path)
        assert result is None

    def test_full_parse(self, tmp_path: Path):
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
        (logs_dir / "order.log").write_text("ref\tordtype\tsize\texecuted_price\tcommission\tdt\tdata_name\tstatus\n")
        (logs_dir / "data.log").write_text("dt\topen\thigh\tlow\tclose\tvolume\n")
        (logs_dir / "run_info.json").write_text(json.dumps({"strategy": "test"}))

        result = parse_all_logs(tmp_path)
        assert result is not None
        assert result["total_return"] > 0
        assert result["total_trades"] == 1
        assert result["win_rate"] > 0
        assert len(result["equity_curve"]) == 3
