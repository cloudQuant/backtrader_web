"""Safety and summary contracts for the Iteration 191 MySQL capacity runner."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_capacity_script() -> ModuleType:
    path = REPO_ROOT / "scripts" / "ci" / "run_asset_research_capacity.py"
    spec = importlib.util.spec_from_file_location("test_asset_research_capacity", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_capacity_runner_rejects_non_disposable_or_non_mysql_targets() -> None:
    module = _load_capacity_script()

    assert (
        module.validate_disposable_mysql_url(
            "mysql+aiomysql://root@127.0.0.1:33361/codex_iter191_capacity_acceptance"
        )
        == "codex_iter191_capacity_acceptance"
    )
    with pytest.raises(ValueError, match="disposable"):
        module.validate_disposable_mysql_url(
            "mysql+aiomysql://root@127.0.0.1:33361/ai_investor"
        )
    with pytest.raises(ValueError, match="MySQL"):
        module.validate_disposable_mysql_url("sqlite+aiosqlite:////tmp/capacity.db")


def test_capacity_runner_uses_nearest_rank_latency_percentiles() -> None:
    module = _load_capacity_script()

    assert module.nearest_rank_percentile([0.1, 0.2, 0.3, 0.4], 0.50) == 0.2
    assert module.nearest_rank_percentile([0.1, 0.2, 0.3, 0.4], 0.95) == 0.4
    with pytest.raises(ValueError, match="values"):
        module.nearest_rank_percentile([], 0.95)


def test_capacity_runner_hashes_the_exact_source_file(tmp_path) -> None:
    module = _load_capacity_script()
    source = tmp_path / "capacity-source.txt"
    source.write_text("capacity fixture", encoding="utf-8")

    assert module.file_sha256(source) == hashlib.sha256(b"capacity fixture").hexdigest()


def test_capacity_runner_uses_only_a_valid_explicit_commit_sha(monkeypatch) -> None:
    module = _load_capacity_script()

    monkeypatch.setenv("GIT_COMMIT_SHA", "A" * 40)
    assert module._commit_sha() == "a" * 40
    monkeypatch.setenv("GIT_COMMIT_SHA", "not-a-commit")
    assert module._commit_sha() is None
