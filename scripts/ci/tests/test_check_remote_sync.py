"""Contract tests for the read-only GitHub-to-Gitee ref comparison."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECKER_PATH = REPO_ROOT / "scripts" / "ci" / "check_remote_sync.py"

SOURCE_MASTER = "605d4d0e1cf1ad6627483aab6c4cef2a742b3d0f"
MIRROR_MASTER = "3d05130635f50c45adeaa4514af246380ff00451"
DEV_SHA = "ebec2a0adf0f239784edbe4d2f3221ac581bd65e"


def _load_checker() -> ModuleType:
    assert CHECKER_PATH.is_file(), "Task 5 remote-sync checker is not implemented"
    spec = importlib.util.spec_from_file_location("check_remote_sync_under_test", CHECKER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def _heads(master: str, dev: str = DEV_SHA) -> str:
    return f"{master}\trefs/heads/master\n{dev}\trefs/heads/dev\n"


def _fake_runner(outputs: dict[str, str]):
    calls: list[list[str]] = []

    def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=outputs[command[-1]], stderr="")

    return run, calls


def _exception(expires_at: str = "2026-09-30T00:00:00Z") -> dict[str, object]:
    return {
        "branch": "master",
        "source_sha": SOURCE_MASTER,
        "mirror_sha": MIRROR_MASTER,
        "issue": ".github/governance/decisions/remote-sync-incident.md",
        "owner": "release/platform owner",
        "reason": "D1-approved temporary master mirror divergence",
        "created_at": "2026-08-24T00:00:00Z",
        "expires_at": expires_at,
    }


def _exceptions_file(tmp_path: Path, entry: dict[str, object]) -> Path:
    path = tmp_path / "exceptions.json"
    path.write_text(json.dumps({"version": 1, "exceptions": [entry]}), encoding="utf-8")
    return path


def test_equal_heads_pass_without_warnings_or_network_access() -> None:
    checker = _load_checker()
    runner, calls = _fake_runner({"source": _heads(DEV_SHA), "mirror": _heads(DEV_SHA)})

    result = checker.check_remote_sync(
        source="source", mirror="mirror", branches=("master", "dev"), run=runner
    )

    assert result["ok"] is True
    assert result["warnings"] == []
    assert calls == [
        ["git", "ls-remote", "--heads", "source"],
        ["git", "ls-remote", "--heads", "mirror"],
    ]


def test_unexcepted_mismatch_fails() -> None:
    checker = _load_checker()
    runner, _ = _fake_runner({"source": _heads(SOURCE_MASTER), "mirror": _heads(MIRROR_MASTER)})

    result = checker.check_remote_sync(
        source="source", mirror="mirror", branches=("master", "dev"), run=runner
    )

    assert result["ok"] is False
    assert result["warnings"] == []
    assert result["mismatches"] == [
        {
            "branch": "master",
            "source_sha": SOURCE_MASTER,
            "mirror_sha": MIRROR_MASTER,
            "status": "failed",
        }
    ]


def test_unexpired_exact_exception_warns_but_allows_known_divergence(tmp_path: Path) -> None:
    checker = _load_checker()
    runner, _ = _fake_runner({"source": _heads(SOURCE_MASTER), "mirror": _heads(MIRROR_MASTER)})

    result = checker.check_remote_sync(
        source="source",
        mirror="mirror",
        branches=("master", "dev"),
        exceptions_path=_exceptions_file(tmp_path, _exception()),
        now=datetime(2026, 8, 24, tzinfo=timezone.utc),
        run=runner,
    )

    assert result["ok"] is True
    assert result["mismatches"] == []
    assert len(result["warnings"]) == 1
    assert "expires_at=2026-09-30T00:00:00Z" in result["warnings"][0]


def test_expired_exception_fails(tmp_path: Path) -> None:
    checker = _load_checker()
    runner, _ = _fake_runner({"source": _heads(SOURCE_MASTER), "mirror": _heads(MIRROR_MASTER)})

    result = checker.check_remote_sync(
        source="source",
        mirror="mirror",
        branches=("master", "dev"),
        exceptions_path=_exceptions_file(tmp_path, _exception("2026-08-24T00:00:01Z")),
        now=datetime(2026, 8, 25, tzinfo=timezone.utc),
        run=runner,
    )

    assert result["ok"] is False
    assert result["warnings"] == []
    assert result["mismatches"][0]["status"] == "expired_exception"


def test_malformed_remote_output_is_a_specific_error() -> None:
    checker = _load_checker()

    with pytest.raises(checker.RemoteSyncError, match="malformed"):
        checker.parse_ls_remote_heads("not-a-git-ls-remote-line\n")
