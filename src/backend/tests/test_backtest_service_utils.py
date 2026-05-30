"""
Tests for BacktestService static utility methods.

These methods are pure functions that don't require database or external services.
"""

from app.services.backtest_service import BacktestService


class TestNormalizeTradeDateMethod:
    """Test _normalize_trade_date static method."""

    def test_iso_format(self):
        result = BacktestService._normalize_trade_date("2024-01-15T10:30:00")
        assert "2024-01-15" in result

    def test_date_only(self):
        result = BacktestService._normalize_trade_date("2024-01-15")
        assert "2024-01-15" in result

    def test_datetime_with_space(self):
        result = BacktestService._normalize_trade_date("2024-01-15 10:30:00")
        assert "2024-01-15" in result

    def test_slash_format(self):
        result = BacktestService._normalize_trade_date("2024/01/15")
        assert "2024-01-15" in result

    def test_slash_datetime(self):
        result = BacktestService._normalize_trade_date("2024/01/15 10:30:00")
        assert "2024-01-15" in result

    def test_with_z_suffix(self):
        result = BacktestService._normalize_trade_date("2024-01-15T10:30:00Z")
        assert "2024-01-15" in result

    def test_empty_string(self):
        assert BacktestService._normalize_trade_date("") is None

    def test_none(self):
        assert BacktestService._normalize_trade_date(None) is None

    def test_non_string(self):
        assert BacktestService._normalize_trade_date(12345) is None

    def test_whitespace_only(self):
        assert BacktestService._normalize_trade_date("   ") is None


class TestNormalizeTradeType:
    """Test _normalize_trade_type static method."""

    def test_buy_variants(self):
        for v in ["buy", "Buy", "BUY", "b", "long", "open", "open_long", "buy_long"]:
            assert BacktestService._normalize_trade_type(v) == "buy", f"Failed for {v}"

    def test_sell_variants(self):
        for v in ["sell", "Sell", "SELL", "s", "short", "close", "close_long", "sell_short"]:
            assert BacktestService._normalize_trade_type(v) == "sell", f"Failed for {v}"

    def test_unknown_type(self):
        assert BacktestService._normalize_trade_type("unknown") is None

    def test_empty(self):
        assert BacktestService._normalize_trade_type("") is None

    def test_none(self):
        assert BacktestService._normalize_trade_type(None) is None


class TestCoerceFloat:
    """Test _coerce_float static method."""

    def test_float_value(self):
        assert BacktestService._coerce_float(3.14) == 3.14

    def test_int_value(self):
        assert BacktestService._coerce_float(42) == 42.0

    def test_string_number(self):
        assert BacktestService._coerce_float("3.14") == 3.14

    def test_none_returns_default(self):
        assert BacktestService._coerce_float(None) == 0.0
        assert BacktestService._coerce_float(None, 99.9) == 99.9

    def test_invalid_string(self):
        assert BacktestService._coerce_float("abc") == 0.0

    def test_empty_string(self):
        assert BacktestService._coerce_float("") == 0.0


class TestCoerceInt:
    """Test _coerce_int static method."""

    def test_int_value(self):
        assert BacktestService._coerce_int(42) == 42

    def test_float_value(self):
        assert BacktestService._coerce_int(3.7) == 3

    def test_string_number(self):
        assert BacktestService._coerce_int("42") == 42

    def test_none_returns_default(self):
        assert BacktestService._coerce_int(None) == 0
        assert BacktestService._coerce_int(None, 99) == 99

    def test_invalid_string(self):
        assert BacktestService._coerce_int("abc") == 0


class TestSanitizeTrades:
    """Test _sanitize_trades class method."""

    def test_valid_trade(self):
        trades = [
            {
                "date": "2024-01-15",
                "type": "buy",
                "price": 100.0,
                "size": 10,
                "pnl": 50.0,
                "pnlcomm": 48.0,
                "commission": 2.0,
                "barlen": 5,
            }
        ]
        result = BacktestService._sanitize_trades(trades)
        assert len(result) == 1
        assert result[0]["type"] == "buy"
        assert result[0]["price"] == 100.0
        assert result[0]["size"] == 10

    def test_trade_with_datetime_field(self):
        trades = [{"datetime": "2024-01-15 10:00:00", "type": "sell", "price": 50.0, "size": 5}]
        result = BacktestService._sanitize_trades(trades)
        assert len(result) == 1

    def test_trade_missing_date_skipped(self):
        trades = [{"type": "buy", "price": 100.0, "size": 10}]
        result = BacktestService._sanitize_trades(trades)
        assert len(result) == 0

    def test_trade_missing_type_skipped(self):
        trades = [{"date": "2024-01-15", "price": 100.0, "size": 10}]
        result = BacktestService._sanitize_trades(trades)
        assert len(result) == 0

    def test_trade_zero_price_skipped(self):
        trades = [{"date": "2024-01-15", "type": "buy", "price": 0, "size": 10}]
        result = BacktestService._sanitize_trades(trades)
        assert len(result) == 0

    def test_trade_zero_size_skipped(self):
        trades = [{"date": "2024-01-15", "type": "buy", "price": 100.0, "size": 0}]
        result = BacktestService._sanitize_trades(trades)
        assert len(result) == 0

    def test_non_list_input(self):
        assert BacktestService._sanitize_trades(None) == []
        assert BacktestService._sanitize_trades("not a list") == []
        assert BacktestService._sanitize_trades(123) == []

    def test_non_dict_items_skipped(self):
        trades = ["not a dict", 123, None]
        result = BacktestService._sanitize_trades(trades)
        assert len(result) == 0

    def test_trade_with_qty_field(self):
        """Should accept 'qty' as alternative to 'size'."""
        trades = [{"date": "2024-01-15", "type": "buy", "price": 100.0, "qty": 10}]
        result = BacktestService._sanitize_trades(trades)
        assert len(result) == 1
        assert result[0]["size"] == 10

    def test_trade_with_volume_field(self):
        """Should accept 'volume' as alternative to 'size'."""
        trades = [{"date": "2024-01-15", "type": "buy", "price": 100.0, "volume": 10}]
        result = BacktestService._sanitize_trades(trades)
        assert len(result) == 1

    def test_trade_value_calculated(self):
        """Value should be price * size if not provided."""
        trades = [{"date": "2024-01-15", "type": "buy", "price": 100.0, "size": 10}]
        result = BacktestService._sanitize_trades(trades)
        assert result[0]["value"] == 1000.0

    def test_trade_direction_field(self):
        """Should accept 'direction' as alternative to 'type'."""
        trades = [{"date": "2024-01-15", "direction": "buy", "price": 100.0, "size": 10}]
        result = BacktestService._sanitize_trades(trades)
        assert len(result) == 1
        assert result[0]["type"] == "buy"


class TestSanitizeCachedResultPayload:
    """Test _sanitize_cached_result_payload class method."""

    def test_normalizes_numeric_fields(self):
        payload = {
            "total_return": "0.15",
            "annual_return": None,
            "sharpe_ratio": 1.5,
            "max_drawdown": "-0.1",
            "win_rate": "0.6",
            "total_trades": "10",
            "profitable_trades": 6,
            "losing_trades": None,
            "trades": [],
        }
        result = BacktestService._sanitize_cached_result_payload(payload)
        assert result["total_return"] == 0.15
        assert result["annual_return"] == 0.0
        assert result["sharpe_ratio"] == 1.5
        assert result["max_drawdown"] == -0.1
        assert result["total_trades"] == 10
        assert result["losing_trades"] == 0

    def test_sanitizes_trades(self):
        payload = {
            "total_return": 0.1,
            "annual_return": 0.1,
            "sharpe_ratio": 1.0,
            "max_drawdown": -0.05,
            "win_rate": 0.5,
            "total_trades": 1,
            "profitable_trades": 1,
            "losing_trades": 0,
            "trades": [{"date": "2024-01-15", "type": "buy", "price": 100.0, "size": 10}],
        }
        result = BacktestService._sanitize_cached_result_payload(payload)
        assert len(result["trades"]) == 1


class TestGetRequestData:
    """Test _get_request_data static method."""

    def test_dict_input(self):
        from unittest.mock import MagicMock

        task = MagicMock()
        task.request_data = {"symbol": "000001.SZ", "start_date": "2024-01-01"}
        result = BacktestService._get_request_data(task)
        assert result["symbol"] == "000001.SZ"

    def test_json_string_input(self):
        import json
        from unittest.mock import MagicMock

        task = MagicMock()
        task.request_data = json.dumps({"symbol": "000001.SZ"})
        result = BacktestService._get_request_data(task)
        assert result["symbol"] == "000001.SZ"

    def test_invalid_json_string(self):
        from unittest.mock import MagicMock

        task = MagicMock()
        task.request_data = "not json"
        result = BacktestService._get_request_data(task)
        assert result == {}

    def test_none_input(self):
        from unittest.mock import MagicMock

        task = MagicMock()
        task.request_data = None
        result = BacktestService._get_request_data(task)
        assert result == {}
