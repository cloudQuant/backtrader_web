"""Offline contracts for the read-only GitHub-to-Gitee ref comparison."""

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
CHECKED_AT = datetime(2026, 8, 24, tzinfo=timezone.utc)


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


def _fake_runner(
    outputs: dict[str, str], *, returncode: int = 0, stderr: str = ""
) -> tuple[object, list[list[str]]]:
    calls: list[list[str]] = []

    def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(
            command, returncode, stdout=outputs.get(command[-1], ""), stderr=stderr
        )

    return run, calls


def _exception(**changes: str) -> dict[str, object]:
    entry: dict[str, object] = {
        "branch": "master",
        "source_sha": SOURCE_MASTER,
        "mirror_sha": MIRROR_MASTER,
        "issue": ".github/governance/decisions/remote-sync-incident.md",
        "owner": "@cloudQuant",
        "reason": "D1-approved temporary master mirror divergence",
        "created_at": "2026-08-23T00:00:00Z",
        "expires_at": "2026-09-30T00:00:00Z",
    }
    entry.update(changes)
    return entry


def _exceptions_file(tmp_path: Path, entry: dict[str, object]) -> Path:
    path = tmp_path / "exceptions.json"
    path.write_text(json.dumps({"version": 1, "exceptions": [entry]}), encoding="utf-8")
    return path


def test_equal_heads_pass_and_only_execute_ls_remote_heads() -> None:
    checker = _load_checker()
    runner, calls = _fake_runner({"source": _heads(DEV_SHA), "mirror": _heads(DEV_SHA)})

    result = checker.check_remote_sync(
        source="source", mirror="mirror", branches=("master", "dev"), now=CHECKED_AT, run=runner
    )

    assert result["ok"] is True
    assert result["warnings"] == []
    assert calls == [
        ["git", "ls-remote", "--heads", "source"],
        ["git", "ls-remote", "--heads", "mirror"],
    ]


def test_unexcepted_mismatch_and_changed_sha_with_old_exception_fail(tmp_path: Path) -> None:
    checker = _load_checker()
    changed_source = "a" * 40
    runner, _ = _fake_runner({"source": _heads(changed_source), "mirror": _heads(MIRROR_MASTER)})

    result = checker.check_remote_sync(
        source="source",
        mirror="mirror",
        branches=("master", "dev"),
        exceptions_path=_exceptions_file(tmp_path, _exception()),
        now=CHECKED_AT,
        run=runner,
    )

    assert result["ok"] is False
    assert result["warnings"] == []
    assert result["mismatches"][0]["status"] == "failed"


def test_unexpired_exact_exception_warns_but_allows_known_divergence(tmp_path: Path) -> None:
    checker = _load_checker()
    runner, _ = _fake_runner({"source": _heads(SOURCE_MASTER), "mirror": _heads(MIRROR_MASTER)})

    result = checker.check_remote_sync(
        source="source",
        mirror="mirror",
        branches=("master", "dev"),
        exceptions_path=_exceptions_file(tmp_path, _exception()),
        now=CHECKED_AT,
        run=runner,
    )

    assert result["ok"] is True
    assert result["mismatches"] == []
    assert result["warnings"] == [
        "approved temporary divergence "
        "branch=master issue=.github/governance/decisions/remote-sync-incident.md "
        "owner=@cloudQuant expires_at=2026-09-30T00:00:00Z"
    ]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"branch": "dev"}, "master"),
        ({"source_sha": "a" * 40}, "approved source"),
        ({"mirror_sha": "b" * 40}, "approved mirror"),
        ({"owner": "release/platform owner"}, "owner"),
        ({"created_at": "2026-08-25T00:00:00Z"}, "future"),
        ({"expires_at": "2026-10-01T00:00:00Z"}, "2026-09-30"),
    ],
)
def test_exception_policy_rejects_any_scope_widening(
    tmp_path: Path, changes: dict[str, str], message: str
) -> None:
    checker = _load_checker()

    with pytest.raises(checker.RemoteSyncError, match=message):
        checker.load_exceptions(_exceptions_file(tmp_path, _exception(**changes)), now=CHECKED_AT)


def test_exception_is_inactive_at_its_exact_expiry(tmp_path: Path) -> None:
    checker = _load_checker()
    runner, _ = _fake_runner({"source": _heads(SOURCE_MASTER), "mirror": _heads(MIRROR_MASTER)})

    result = checker.check_remote_sync(
        source="source",
        mirror="mirror",
        branches=("master", "dev"),
        exceptions_path=_exceptions_file(tmp_path, _exception()),
        now=datetime(2026, 9, 30, tzinfo=timezone.utc),
        run=runner,
    )

    assert result["ok"] is False
    assert result["mismatches"][0]["status"] == "expired_exception"


def test_nonzero_git_command_is_reported_without_generic_exception() -> None:
    checker = _load_checker()
    runner, calls = _fake_runner({}, returncode=128, stderr="remote unavailable")

    with pytest.raises(checker.RemoteSyncError, match="remote unavailable"):
        checker.check_remote_sync(
            source="source", mirror="mirror", branches=("master",), now=CHECKED_AT, run=runner
        )
    assert calls == [["git", "ls-remote", "--heads", "source"]]


def test_main_returns_machine_readable_error_status(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    checker = _load_checker()

    def fail(**_: object) -> dict[str, object]:
        raise checker.RemoteSyncError("fake command failure")

    monkeypatch.setattr(checker, "check_remote_sync", fail)

    status = checker.main(["--source", "source", "--mirror", "mirror", "--branches", "master"])

    assert status == 2
    assert "REMOTE_SYNC_ERROR: fake command failure" in capsys.readouterr().out


def test_malformed_remote_output_is_a_specific_error() -> None:
    checker = _load_checker()

    with pytest.raises(checker.RemoteSyncError, match="malformed"):
        checker.parse_ls_remote_heads("not-a-git-ls-remote-line\n")
