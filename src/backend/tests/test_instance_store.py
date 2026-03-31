"""Tests for instance_store module."""

import json

import pytest

from app.services.instance_store import InstanceStore


@pytest.fixture()
def store(tmp_path):
    """Provide an InstanceStore backed by a temporary file."""
    return InstanceStore(instances_file=tmp_path / "instances.json")


class TestLoadAll:
    def test_empty_when_file_missing(self, store):
        assert store.load_all() == {}

    def test_loads_valid_json(self, store):
        data = {"inst-1": {"status": "running"}}
        store._file.write_text(json.dumps(data), "utf-8")
        assert store.load_all() == data

    def test_returns_empty_on_invalid_json(self, store):
        store._file.write_text("not json", "utf-8")
        assert store.load_all() == {}

    def test_returns_empty_on_empty_file(self, store):
        store._file.write_text("", "utf-8")
        assert store.load_all() == {}


class TestSaveAll:
    def test_creates_parent_dirs(self, tmp_path):
        deep_path = tmp_path / "a" / "b" / "instances.json"
        store = InstanceStore(instances_file=deep_path)
        store.save_all({"x": {"v": 1}})
        assert deep_path.is_file()
        assert json.loads(deep_path.read_text("utf-8")) == {"x": {"v": 1}}

    def test_overwrites_existing(self, store):
        store.save_all({"a": {"v": 1}})
        store.save_all({"b": {"v": 2}})
        assert store.load_all() == {"b": {"v": 2}}


class TestGet:
    def test_returns_none_when_missing(self, store):
        assert store.get("nonexistent") is None

    def test_returns_instance(self, store):
        store.save_all({"inst-1": {"status": "stopped"}})
        assert store.get("inst-1") == {"status": "stopped"}


class TestPut:
    def test_creates_new_instance(self, store):
        store.put("inst-1", {"status": "running"})
        assert store.get("inst-1") == {"status": "running"}

    def test_updates_existing_instance(self, store):
        store.put("inst-1", {"status": "running"})
        store.put("inst-1", {"status": "stopped"})
        assert store.get("inst-1") == {"status": "stopped"}

    def test_preserves_other_instances(self, store):
        store.put("inst-1", {"a": 1})
        store.put("inst-2", {"b": 2})
        assert store.get("inst-1") == {"a": 1}
        assert store.get("inst-2") == {"b": 2}


class TestDelete:
    def test_returns_false_when_not_found(self, store):
        assert store.delete("nonexistent") is False

    def test_removes_instance(self, store):
        store.put("inst-1", {"status": "running"})
        result = store.delete("inst-1")
        assert result is True
        assert store.get("inst-1") is None

    def test_preserves_other_instances_after_delete(self, store):
        store.put("inst-1", {"a": 1})
        store.put("inst-2", {"b": 2})
        store.delete("inst-1")
        assert store.get("inst-2") == {"b": 2}


class TestUpdateFields:
    def test_returns_none_when_not_found(self, store):
        assert store.update_fields("nonexistent", status="stopped") is None

    def test_updates_specific_fields(self, store):
        store.put("inst-1", {"status": "running", "pid": 123})
        result = store.update_fields("inst-1", status="stopped", pid=None)
        assert result == {"status": "stopped", "pid": None}
        assert store.get("inst-1") == {"status": "stopped", "pid": None}

    def test_adds_new_fields(self, store):
        store.put("inst-1", {"status": "running"})
        result = store.update_fields("inst-1", error="timeout")
        assert result["error"] == "timeout"
        assert result["status"] == "running"
