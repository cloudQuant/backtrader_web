"""Unit tests for the extracted ``app.services.sync.progress`` module."""

import json

from app.services.sync import progress as sp


class TestNowIso:
    def test_now_iso_is_parseable_utc(self):
        value = sp.now_iso()
        # ISO string ending in +00:00 for UTC
        assert value.endswith("+00:00")
        # round-trips through fromisoformat
        from datetime import datetime

        parsed = datetime.fromisoformat(value)
        assert parsed.tzinfo is not None


class TestNormalizeHost:
    def test_blank(self):
        assert sp.normalize_host("   ") == ""

    def test_plain_host_kept(self):
        assert sp.normalize_host(" db.example.com ") == "db.example.com"

    def test_http_url_reduced_to_hostname(self):
        assert sp.normalize_host("http://db.example.com:3306") == "db.example.com"

    def test_https_url_reduced_to_hostname(self):
        assert sp.normalize_host("https://db.example.com/path") == "db.example.com"


class TestFormatBytes:
    def test_bytes_no_decimals(self):
        assert sp.format_bytes(512) == "512 B"

    def test_kb_one_decimal(self):
        assert sp.format_bytes(1536) == "1.5 KB"

    def test_mb(self):
        assert sp.format_bytes(5 * 1024 * 1024) == "5.0 MB"

    def test_negative_clamped_to_zero(self):
        assert sp.format_bytes(-1) == "0 B"

    def test_terabyte_is_top_unit(self):
        out = sp.format_bytes(3 * 1024**4)
        assert out.endswith("TB")


class TestHistoryPersistence:
    def test_load_missing_returns_empty(self, tmp_path):
        assert sp.load_history(tmp_path / "nope.json") == []

    def test_load_corrupt_returns_empty(self, tmp_path):
        f = tmp_path / "hist.json"
        f.write_text("{not json", encoding="utf-8")
        assert sp.load_history(f) == []

    def test_load_non_list_returns_empty(self, tmp_path):
        f = tmp_path / "hist.json"
        f.write_text(json.dumps({"a": 1}), encoding="utf-8")
        assert sp.load_history(f) == []

    def test_load_filters_non_dict_items(self, tmp_path):
        f = tmp_path / "hist.json"
        f.write_text(json.dumps([{"ok": 1}, "bad", 5]), encoding="utf-8")
        assert sp.load_history(f) == [{"ok": 1}]

    def test_write_then_load_roundtrip(self, tmp_path):
        f = tmp_path / "sub" / "hist.json"  # parent created on write
        items = [{"task_id": "1"}, {"task_id": "2"}]
        sp.write_history(f, items)
        assert sp.load_history(f) == items

    def test_write_caps_at_max_entries(self, tmp_path):
        f = tmp_path / "hist.json"
        items = [{"i": i} for i in range(sp.HISTORY_MAX_ENTRIES + 50)]
        sp.write_history(f, items)
        loaded = sp.load_history(f)
        assert len(loaded) == sp.HISTORY_MAX_ENTRIES
        assert loaded[0] == {"i": 0}


class TestServiceFacadeDelegation:
    def test_facade_matches_module(self):
        from app.services.sync_service import get_sync_service

        svc = get_sync_service()
        assert svc._format_bytes(1536) == sp.format_bytes(1536)
        assert svc._normalize_host("https://h:3306") == sp.normalize_host("https://h:3306")
