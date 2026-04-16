"""Log parser service tests."""

from pathlib import Path

from app.services.log_parser_service import (
    find_latest_log_dir,
    parse_data_log,
    parse_trade_log,
    parse_value_log,
)


class TestParseValueLog:
    """Tests for value.log parsing."""

    def test_parse_valid_log(self, tmp_path: Path):
        """Test parsing a valid value log file.

        Args:
            tmp_path: Temporary path fixture.

        Returns:
            None
        """
        log_dir = tmp_path / "log_20240101"
        log_dir.mkdir()
        (log_dir / "value.log").write_text(
            "datetime\tvalue\tcash\n2024-01-01\t100000.0\t50000.0\n2024-01-02\t101000.0\t49000.0\n"
        )
        result = parse_value_log(log_dir)
        assert "dates" in result
        assert "equity_curve" in result
        assert len(result["dates"]) == 2

    def test_parse_empty_dir(self, tmp_path: Path):
        """Test parsing an empty directory.

        Args:
            tmp_path: Temporary path fixture.

        Returns:
            None
        """
        result = parse_value_log(tmp_path)
        assert result == {} or result.get("dates") == []

    def test_parse_json_value_log(self, tmp_path: Path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (log_dir / "value.log").write_text(
            "\n".join(
                [
                    '{"datetime":"2024-01-01 00:00:00","broker_value":100000.0,'
                    '"broker_cash":50000.0}',
                    '{"datetime":"2024-01-02 00:00:00","broker_value":101000.0,'
                    '"broker_cash":51000.0}',
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        result = parse_value_log(log_dir)

        assert result["dates"] == ["2024-01-01", "2024-01-02"]
        assert result["equity_curve"] == [100000.0, 101000.0]
        assert result["cash_curve"] == [50000.0, 51000.0]

    def test_parse_nonexistent_dir(self, tmp_path: Path):
        """Test parsing a non-existent directory.

        Args:
            tmp_path: Temporary path fixture.

        Returns:
            None
        """
        result = parse_value_log(tmp_path / "nonexistent")
        assert result == {} or result.get("dates") == []


class TestParseTradeLog:
    """Tests for trade.log parsing."""

    def test_parse_valid_trade_log(self, tmp_path: Path):
        """Test parsing a valid trade log file.

        Args:
            tmp_path: Temporary path fixture.

        Returns:
            None
        """
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
        """Test parsing trade log from empty directory.

        Args:
            tmp_path: Temporary path fixture.

        Returns:
            None
        """
        trades = parse_trade_log(tmp_path)
        assert trades == [] or trades is not None


class TestFindLatestLogDir:
    """Tests for finding latest log directory."""

    def test_find_latest(self, tmp_path: Path):
        """Test finding the latest log directory.

        Args:
            tmp_path: Temporary path fixture.

        Returns:
            None
        """
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        (logs_dir / "log_20240101").mkdir()
        (logs_dir / "log_20240102").mkdir()
        (logs_dir / "log_20240101" / "trade.log").write_text("ok")
        (logs_dir / "log_20240102" / "trade.log").write_text("ok")
        result = find_latest_log_dir(tmp_path)
        assert result is not None
        assert "20240102" in str(result)

    def test_no_log_dirs(self, tmp_path: Path):
        """Test when no log directories exist.

        Args:
            tmp_path: Temporary path fixture.

        Returns:
            None
        """
        result = find_latest_log_dir(tmp_path)
        assert result is None

    def test_empty_logs_dir(self, tmp_path: Path):
        """Test with an empty logs directory.

        Args:
            tmp_path: Temporary path fixture.

        Returns:
            None
        """
        (tmp_path / "logs").mkdir()
        result = find_latest_log_dir(tmp_path)
        assert result is None

    def test_flat_logs_dir(self, tmp_path: Path):
        """Test flat logs/ with no subdirs (simulate strategy layout).

        Args:
            tmp_path: Temporary path fixture.

        Returns:
            None
        """
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        (logs_dir / "trade.log").touch()
        result = find_latest_log_dir(tmp_path)
        assert result is not None
        assert result == logs_dir

    def test_flat_logs_dir_with_json_simulate_logs(self, tmp_path: Path):
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        (logs_dir / "bar.log").touch()
        result = find_latest_log_dir(tmp_path)
        assert result is not None
        assert result == logs_dir


class TestParseJsonSimulateLogs:
    def test_parse_trade_log_from_json_lines(self, tmp_path: Path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (log_dir / "trade.log").write_text(
            "\n".join(
                [
                    '{"datetime":"2026-03-13 09:00:00","ref":1,"data_name":"EURUSD","size":0.01,"price":1.1,"value":0.011,"commission":0.001,"pnl":0.0,"pnlcomm":-0.001,"isopen":true,"isclosed":false,"barlen":0}',
                    '{"datetime":"2026-03-13 10:00:00","ref":1,"data_name":"EURUSD","size":0.0,"price":1.11,"value":0.0,"commission":0.001,"pnl":10.0,"pnlcomm":9.998,"isopen":false,"isclosed":true,"barlen":4}',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        trades = parse_trade_log(log_dir)
        assert len(trades) == 1
        assert trades[0]["dtopen"] == "2026-03-13 09:00:00"
        assert trades[0]["dtclose"] == "2026-03-13 10:00:00"
        assert trades[0]["pnlcomm"] == 10.0

    def test_parse_data_log_from_bar_and_indicator_json_lines(self, tmp_path: Path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (log_dir / "bar.log").write_text(
            "\n".join(
                [
                    '{"datetime":"2026-03-13 09:00:00","open":1.1,"high":1.2,"low":1.0,"close":1.15,"volume":10}',
                    '{"datetime":"2026-03-13 09:15:00","open":1.15,"high":1.25,"low":1.1,"close":1.2,"volume":12}',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (log_dir / "indicator.log").write_text(
            "\n".join(
                [
                    '{"datetime":"2026-03-13 09:00:00","fast_ma":1.11}',
                    '{"datetime":"2026-03-13 09:15:00","fast_ma":1.16}',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        result = parse_data_log(log_dir)
        assert result["dates"] == ["2026-03-13 09:00:00", "2026-03-13 09:15:00"]
        assert result["ohlc"][0] == [1.1, 1.15, 1.0, 1.2]
        assert result["indicators"]["fast_ma"] == [1.11, 1.16]
