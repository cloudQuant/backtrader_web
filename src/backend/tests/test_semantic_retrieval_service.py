"""Unit tests for SemanticRetrievalService offline-cache handling.

Regression context: even when the embedding model is fully cached locally,
``huggingface_hub`` performs online HEAD requests against huggingface.co.
On networks where that host is slow or unreachable, the retry/backoff chain
blocks application startup for minutes and the ops health check times out.
The service must therefore prefer offline loading whenever a cached
snapshot exists.

The cache probe is a deliberate filesystem check (not a ``huggingface_hub``
call): ``huggingface_hub.constants.HF_HUB_OFFLINE`` is frozen at import
time, so the offline preference must be decided before any Hugging Face
import happens.
"""

from __future__ import annotations

import os
from pathlib import Path

from app.services.semantic_retrieval_service import SemanticRetrievalService

MODEL_NAME = "BAAI/bge-small-zh-v1.5"
REPO_DIR = "models--BAAI--bge-small-zh-v1.5"


def _make_service(tmp_path) -> SemanticRetrievalService:
    return SemanticRetrievalService(
        enabled=True,
        persistence_path=tmp_path,
        model_name=MODEL_NAME,
    )


def _isolate_default_cache(tmp_path, monkeypatch) -> None:
    """Point every cache-location source at empty directories.

    Without this, the ``~/.cache/huggingface/hub`` fallback resolves to the
    developer's real cache, where the embedding model is usually present.
    """
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir(exist_ok=True)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "empty-hub"))
    monkeypatch.delenv("HF_HOME", raising=False)


def _build_cached_snapshot(cache_root: Path) -> Path:
    snapshot = cache_root / REPO_DIR / "snapshots" / "abc123"
    snapshot.mkdir(parents=True)
    (snapshot / "config.json").write_text("{}")
    return snapshot


class TestModelIsCached:
    def test_true_when_snapshot_file_present(self, tmp_path, monkeypatch):
        cache_root = tmp_path / "hub"
        _build_cached_snapshot(cache_root)
        monkeypatch.setenv("HF_HUB_CACHE", str(cache_root))

        assert _make_service(tmp_path)._model_is_cached() is True

    def test_true_via_hf_home_when_hub_cache_unset(self, tmp_path, monkeypatch):
        cache_root = tmp_path / "hub"
        _build_cached_snapshot(cache_root)
        monkeypatch.delenv("HF_HUB_CACHE", raising=False)
        monkeypatch.setenv("HF_HOME", str(tmp_path))

        assert _make_service(tmp_path)._model_is_cached() is True

    def test_false_when_repo_dir_missing(self, tmp_path, monkeypatch):
        _isolate_default_cache(tmp_path, monkeypatch)

        assert _make_service(tmp_path)._model_is_cached() is False

    def test_false_when_snapshot_lacks_config(self, tmp_path, monkeypatch):
        cache_root = tmp_path / "hub"
        snapshot = cache_root / REPO_DIR / "snapshots" / "abc123"
        snapshot.mkdir(parents=True)
        (snapshot / "README.md").write_text("no model files")
        monkeypatch.setenv("HF_HUB_CACHE", str(cache_root))
        fake_home = tmp_path / "fake-home"
        fake_home.mkdir(exist_ok=True)
        monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
        monkeypatch.delenv("HF_HOME", raising=False)

        assert _make_service(tmp_path)._model_is_cached() is False


class TestPreferOfflineCache:
    def test_sets_offline_env_when_cached(self, tmp_path, monkeypatch):
        cache_root = tmp_path / "hub"
        _build_cached_snapshot(cache_root)
        monkeypatch.setenv("HF_HUB_CACHE", str(cache_root))
        monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
        monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)

        _make_service(tmp_path)._prefer_offline_cache()

        assert os.environ.get("HF_HUB_OFFLINE") == "1"
        assert os.environ.get("TRANSFORMERS_OFFLINE") == "1"

    def test_leaves_env_untouched_when_not_cached(self, tmp_path, monkeypatch):
        _isolate_default_cache(tmp_path, monkeypatch)
        monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
        monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)

        _make_service(tmp_path)._prefer_offline_cache()

        assert "HF_HUB_OFFLINE" not in os.environ
        assert "TRANSFORMERS_OFFLINE" not in os.environ

    def test_fixes_frozen_hub_constant_from_earlier_import(self, tmp_path, monkeypatch):
        """Regression: ``huggingface_hub.constants.HF_HUB_OFFLINE`` is frozen
        at import time.  When an unrelated dependency (e.g. ``datasets``)
        imports ``huggingface_hub`` before warm-up runs, setting the env var
        alone is not enough — the cached constant must be corrected too.
        """
        import huggingface_hub.constants as hf_constants

        cache_root = tmp_path / "hub"
        _build_cached_snapshot(cache_root)
        monkeypatch.setenv("HF_HUB_CACHE", str(cache_root))
        monkeypatch.setattr(hf_constants, "HF_HUB_OFFLINE", False)

        _make_service(tmp_path)._prefer_offline_cache()

        assert hf_constants.HF_HUB_OFFLINE is True
