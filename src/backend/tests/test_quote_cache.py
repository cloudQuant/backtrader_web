from pathlib import Path

from app.services.quote.cache import (
    get_cached_tick_metrics,
    load_custom_symbols,
    match_cached_tick,
    save_custom_symbols,
    wait_for_initial_ticks,
)


class _Receiver:
    def __init__(self, payloads: list[dict[str, dict]], *, is_alive: bool = True) -> None:
        self._payloads = payloads
        self._index = 0
        self.is_alive = is_alive

    def get_all_ticks(self) -> dict[str, dict]:
        payload = self._payloads[min(self._index, len(self._payloads) - 1)]
        if self._index < len(self._payloads) - 1:
            self._index += 1
        return payload


def test_load_custom_symbols_returns_data_from_disk(tmp_path):
    file_path = tmp_path / "quote_custom_symbols.json"
    file_path.write_text('{"user-1": {"MT5": ["EURUSD"]}}', encoding="utf-8")

    result = load_custom_symbols(file_path)

    assert result == {"user-1": {"MT5": ["EURUSD"]}}


def test_load_custom_symbols_returns_empty_dict_when_missing_or_invalid(tmp_path):
    missing = tmp_path / "missing.json"
    invalid = tmp_path / "invalid.json"
    invalid.write_text("[]", encoding="utf-8")

    assert load_custom_symbols(missing) == {}
    assert load_custom_symbols(invalid) == {}


def test_load_custom_symbols_returns_empty_dict_on_read_error(tmp_path, monkeypatch):
    file_path = tmp_path / "quote_custom_symbols.json"
    file_path.write_text("{}", encoding="utf-8")

    def _raise_read_error(self: Path, encoding: str) -> str:
        raise OSError("boom")

    monkeypatch.setattr(Path, "read_text", _raise_read_error)

    assert load_custom_symbols(file_path) == {}


def test_save_custom_symbols_writes_json_payload(tmp_path):
    file_path = tmp_path / "nested" / "quote_custom_symbols.json"

    save_custom_symbols({"user-1": {"BINANCE": ["BTCUSDT"]}}, file_path)

    assert file_path.exists()
    assert load_custom_symbols(file_path) == {"user-1": {"BINANCE": ["BTCUSDT"]}}


def test_save_custom_symbols_swallows_write_errors(tmp_path, monkeypatch):
    file_path = tmp_path / "quote_custom_symbols.json"

    def _raise_write_error(self: Path, data: str, encoding: str) -> int:
        raise OSError("boom")

    monkeypatch.setattr(Path, "write_text", _raise_write_error)

    save_custom_symbols({"user-1": {"OKX": ["ETH-USDT-SWAP"]}}, file_path)


def test_get_cached_tick_metrics_returns_zero_for_missing_receiver():
    assert get_cached_tick_metrics({}, "") == {"tick_count": 0, "last_tick_time": None}
    assert get_cached_tick_metrics({}, "CTP") == {"tick_count": 0, "last_tick_time": None}


def test_get_cached_tick_metrics_normalizes_latest_valid_timestamp():
    receiver = _Receiver(
        [
            {
                "A": {"timestamp": 1712678400000},
                "B": {"timestamp": "1712678405"},
                "C": {"timestamp": ""},
                "D": {"timestamp": "nan"},
                "E": "bad-payload",
            }
        ]
    )

    result = get_cached_tick_metrics({"MT5": receiver}, "mt5")

    assert result == {"tick_count": 5, "last_tick_time": 1712678405}


def test_wait_for_initial_ticks_handles_missing_receiver_and_immediate_cache():
    assert wait_for_initial_ticks(None, ["EURUSD"]) == {}
    assert wait_for_initial_ticks(_Receiver([{}], is_alive=False), ["EURUSD"]) == {}

    receiver = _Receiver([{"EURUSD": {"bid_price": 1.2}}])

    assert wait_for_initial_ticks(receiver, ["EURUSD"]) == {"EURUSD": {"bid_price": 1.2}}


def test_wait_for_initial_ticks_polls_until_symbol_appears():
    receiver = _Receiver([{}, {"BTCUSDT": {"last_price": 68000.0}}])

    result = wait_for_initial_ticks(receiver, ["BTCUSDT"], timeout_sec=0.3)

    assert result == {"BTCUSDT": {"last_price": 68000.0}}


def test_match_cached_tick_supports_exact_alias_prefix_and_missing_cases():
    exact_payload = {"symbol": "EURUSD", "bid_price": 1.1}
    alias_payload = {"symbol": "BTCUSDT", "instrument_id": "BTCUSDT-SWAP", "last_price": 1}

    assert match_cached_tick({"EURUSD": exact_payload}, "EURUSD") == exact_payload
    assert match_cached_tick({"alias": alias_payload}, "BTCUSDT") == alias_payload
    assert match_cached_tick({"ETHUSDTm": {"instrument_id": "ETHUSDTm"}}, "ETHUSDT") == {
        "instrument_id": "ETHUSDTm"
    }
    assert match_cached_tick({}, "XAUUSD") is None
