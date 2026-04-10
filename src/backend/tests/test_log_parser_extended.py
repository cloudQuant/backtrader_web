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
    parse_trade_log,
    parse_value_log,
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

    def test_parse_pipe_orders(self, tmp_path: Path):
        (tmp_path / "order.log").write_text(
            "2026-04-08T15:42:14.393+08:00 | SELL | ref=1 | status=Completed | size=-952244.9173927535 | price=None\n",
            encoding="utf-8",
        )
        orders = parse_order_log(tmp_path)
        assert len(orders) == 1
        assert orders[0]["ref"] == 1
        assert orders[0]["type"] == "SELL"
        assert orders[0]["dt"] == "2026-04-08"


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

    def test_parse_yaml(self, tmp_path: Path):
        (tmp_path / "current_position.yaml").write_text(
            "datetime: '2026-04-07 00:00:00'\n"
            "positions:\n"
            "  EURUSD:\n"
            "    size: -10\n"
            "    price: 1.1427\n"
            "    value: -11.55\n",
            encoding="utf-8",
        )
        result = parse_current_position(tmp_path)
        assert len(result) == 1
        assert result[0]["data_name"] == "EURUSD"
        assert result[0]["dt"] == "2026-04-07"
        assert result[0]["value"] == -11.55


class TestParsePipeTradeLog:
    def test_parse_pipe_trade_log(self, tmp_path: Path):
        (tmp_path / "trade.log").write_text(
            "2026-04-08T15:42:14.393+08:00 | OPEN | ref=1 | data=EURUSD | size=-952244.9173927535 | pnl=0.00 | pnlcomm=-99.99\n"
            "2026-04-08T15:42:14.398+08:00 | CLOSED | ref=1 | data=EURUSD | size=0.0 | pnl=-35947.25 | pnlcomm=-36150.83\n",
            encoding="utf-8",
        )
        trades = parse_trade_log(tmp_path)
        assert len(trades) == 1
        assert trades[0]["data_name"] == "EURUSD"
        assert trades[0]["direction"] == "sell"
        assert trades[0]["pnlcomm"] == -36150.83


class TestParseTextTradeLoggerLogs:
    def test_parse_text_value_log(self, tmp_path: Path):
        (tmp_path / "value.log").write_text(
            "2026-04-10T07:57:30.133+08:00 | datetime=2020-01-02 00:00:00 | value=100000.00 | cash=100000.00\n"
            "2026-04-10T07:57:30.134+08:00 | datetime=2020-01-03 00:00:00 | value=100100.00 | cash=99900.00\n",
            encoding="utf-8",
        )

        result = parse_value_log(tmp_path)

        assert result["dates"] == ["2020-01-02", "2020-01-03"]
        assert result["equity_curve"] == [100000.0, 100100.0]
        assert result["cash_curve"] == [100000.0, 99900.0]

    def test_parse_text_bar_and_indicator_logs(self, tmp_path: Path):
        (tmp_path / "value.log").write_text(
            "2026-04-10T07:57:30.133+08:00 | datetime=2020-01-02 00:00:00 | value=100000.00 | cash=100000.00\n"
            "2026-04-10T07:57:30.134+08:00 | datetime=2020-01-03 00:00:00 | value=100100.00 | cash=99900.00\n",
            encoding="utf-8",
        )
        (tmp_path / "bar.log").write_text(
            "2026-04-10T07:57:30.133+08:00 | BAR | data_name=AAPL | open=74.0600 | high=75.1500 | low=73.8000 | close=75.1500 | volume=88333.00 | broker_value=100000.00 | broker_cash=100000.00\n"
            "2026-04-10T07:57:30.134+08:00 | BAR | data_name=AAPL | open=74.2800 | high=75.1500 | low=74.1300 | close=74.3500 | volume=86262.00 | broker_value=100100.00 | broker_cash=99900.00\n",
            encoding="utf-8",
        )
        (tmp_path / "indicator.log").write_text(
            "2026-04-10T07:57:30.133+08:00 | INDICATOR | datetime=2020-01-02 00:00:00 | CrossOver=0.0000 | dema_fast_DoubleExponentialMovingAverage_dema=78.8130\n"
            "2026-04-10T07:57:30.134+08:00 | INDICATOR | datetime=2020-01-03 00:00:00 | CrossOver=1.0000 | dema_fast_DoubleExponentialMovingAverage_dema=79.1200\n",
            encoding="utf-8",
        )

        result = parse_data_log(tmp_path)

        assert result["dates"] == ["2020-01-02 00:00:00", "2020-01-03 00:00:00"]
        assert result["ohlc"][0] == [74.06, 75.15, 73.8, 75.15]
        assert result["volumes"] == [88333.0, 86262.0]
        assert result["indicators"]["CrossOver"] == [0.0, 1.0]

    def test_parse_text_position_log(self, tmp_path: Path):
        (tmp_path / "value.log").write_text(
            "2026-04-10T07:57:30.133+08:00 | datetime=2020-01-02 00:00:00 | value=100000.00 | cash=100000.00\n",
            encoding="utf-8",
        )
        (tmp_path / "position.log").write_text(
            "2026-04-10T07:57:30.133+08:00 | AAPL | size=10 | price=254.3000 | value=2543.00 | broker_value=100000.00 | broker_cash=97457.00\n",
            encoding="utf-8",
        )

        result = parse_position_log(tmp_path)

        assert len(result) == 1
        assert result[0]["dt"] == "2020-01-02"
        assert result[0]["data_name"] == "AAPL"
        assert result[0]["value"] == 2543.0

    def test_parse_pipe_trade_log_with_explicit_datetime_and_price(self, tmp_path: Path):
        (tmp_path / "trade.log").write_text(
            "2026-04-10T08:00:00.000+08:00 | OPEN | datetime=2020-01-02 00:00:00 | ref=1 | data=AAPL | size=10 | price=83.3800 | value=833.80 | commission=0.17 | pnl=0.00 | pnlcomm=-0.17\n"
            "2026-04-10T08:01:00.000+08:00 | CLOSED | datetime=2020-01-09 00:00:00 | ref=1 | data=AAPL | size=0 | price=88.4500 | value=0.00 | commission=0.17 | pnl=53.30 | pnlcomm=52.96\n",
            encoding="utf-8",
        )

        trades = parse_trade_log(tmp_path)

        assert len(trades) == 1
        assert trades[0]["dtopen"] == "2020-01-02 00:00:00"
        assert trades[0]["dtclose"] == "2020-01-09 00:00:00"
        assert trades[0]["price"] == 83.38
        assert trades[0]["value"] == 833.8


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

    def test_parse_all_logs_synthesizes_equity_for_json_simulate_logs(self, tmp_path: Path):
        strategy_dir = tmp_path / "strategy"
        logs_dir = strategy_dir / "logs"
        logs_dir.mkdir(parents=True)
        (strategy_dir / "config.yaml").write_text("simulate:\n  initial_cash: 100000\n", encoding="utf-8")
        (logs_dir / "bar.log").write_text(
            '\n'.join(
                [
                    '{"datetime":"2026-03-13 09:00:00","open":100,"high":101,"low":99,"close":100.5,"volume":10}',
                    '{"datetime":"2026-03-13 09:15:00","open":100.5,"high":102,"low":100,"close":101.5,"volume":12}',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (logs_dir / "position.log").write_text(
            '\n'.join(
                [
                    '{"datetime":"2026-03-13 09:00:00","data_name":"CF609","size":0,"price":0,"value":0}',
                    '{"datetime":"2026-03-13 09:15:00","data_name":"CF609","size":1,"price":100.5,"value":101.5}',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (logs_dir / "trade.log").write_text(
            '\n'.join(
                [
                    '{"datetime":"2026-03-13 09:00:00","ref":1,"data_name":"CF609","size":1,"price":100.5,"value":100.5,"commission":0.1,"pnl":0.0,"pnlcomm":-0.1,"isopen":true,"isclosed":false,"barlen":0}',
                    '{"datetime":"2026-03-13 09:15:00","ref":1,"data_name":"CF609","size":0,"price":101.5,"value":0.0,"commission":0.1,"pnl":1.0,"pnlcomm":0.8,"isopen":false,"isclosed":true,"barlen":1}',
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        result = parse_all_logs(strategy_dir)
        assert result is not None
        assert result["equity_dates"] == ["2026-03-13 09:00:00", "2026-03-13 09:15:00"]
        assert len(result["equity_curve"]) == 2
        assert result["total_trades"] == 1

    def test_parse_all_logs_synthesizes_equity_for_pipe_workspace_logs(self, tmp_path: Path):
        strategy_dir = tmp_path / "strategy"
        logs_dir = strategy_dir / "logs" / "task_1"
        logs_dir.mkdir(parents=True)
        (strategy_dir / "config.yaml").write_text("backtest:\n  initial_cash: 100000\n", encoding="utf-8")
        (logs_dir / "trade.log").write_text(
            "2026-04-08T15:42:14.393+08:00 | OPEN | ref=1 | data=EURUSD | size=-952244.9173927535 | pnl=0.00 | pnlcomm=-99.99\n"
            "2026-04-08T15:42:14.398+08:00 | CLOSED | ref=1 | data=EURUSD | size=0.0 | pnl=-35947.25 | pnlcomm=-36150.83\n",
            encoding="utf-8",
        )
        (logs_dir / "order.log").write_text(
            "2026-04-08T15:42:14.393+08:00 | SELL | ref=1 | status=Completed | size=-952244.9173927535 | price=None\n",
            encoding="utf-8",
        )
        (logs_dir / "current_position.yaml").write_text(
            "datetime: '2026-04-07 00:00:00'\n"
            "positions:\n"
            "  EURUSD:\n"
            "    size: -826123.8794732849\n"
            "    price: 1.1427\n"
            "    value: -954082.21\n",
            encoding="utf-8",
        )

        result = parse_all_logs(strategy_dir)
        assert result is not None
        assert result["total_trades"] == 1
        assert len(result["trades"]) == 1
        assert len(result["orders"]) == 1
        assert len(result["equity_curve"]) >= 1
