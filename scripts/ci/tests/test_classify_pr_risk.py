"""Tests for the local-only Iteration 195 PR path-risk classifier."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_CI = REPO_ROOT / "scripts" / "ci"
CLASSIFIER_PATH = SCRIPTS_CI / "classify_pr_risk.py"
RISK_MAP_PATH = REPO_ROOT / ".github" / "governance" / "risk-paths.json"


def _load_classifier() -> ModuleType:
    assert CLASSIFIER_PATH.is_file(), "Task 4 risk classifier is not implemented"
    sys.path.insert(0, str(SCRIPTS_CI))
    try:
        spec = importlib.util.spec_from_file_location(
            "classify_pr_risk_under_test", CLASSIFIER_PATH
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


def _risk_map() -> dict[str, object]:
    return json.loads(RISK_MAP_PATH.read_text(encoding="utf-8"))


def test_unmapped_behavior_change_is_r1_and_has_no_label_downgrade_path() -> None:
    classifier = _load_classifier()

    result = classifier.classify_changed_files(
        ["src/backend/app/services/market_data.py"], _risk_map()
    )

    assert result["risk"] == "R1"
    assert result["matches"] == []
    assert result["labels_can_lower_risk"] is False
    assert "label" in result["downgrade_policy"].casefold()


def test_auth_router_and_store_changes_raise_risk_to_r2() -> None:
    classifier = _load_classifier()

    result = classifier.classify_changed_files(
        [
            "src/backend/app/api/auth.py",
            "src/frontend/src/router/index.ts",
            "src/frontend/src/stores/auth.ts",
        ],
        _risk_map(),
    )

    assert result["risk"] == "R2"
    assert {match["level"] for match in result["matches"]} == {"R2"}
    assert result["labels_can_lower_risk"] is False


def test_workflow_lock_and_release_changes_raise_risk_to_r3() -> None:
    classifier = _load_classifier()

    result = classifier.classify_changed_files(
        [
            ".github/workflows/ci.yml",
            "config/requirements-dev.lock",
            "scripts/ops/release.sh",
        ],
        _risk_map(),
    )

    assert result["risk"] == "R3"
    assert {match["level"] for match in result["matches"]} == {"R3"}
    assert result["labels_can_lower_risk"] is False


def test_cli_reads_only_a_local_changed_files_payload_and_risk_map(tmp_path: Path) -> None:
    payload = tmp_path / "changed-files.json"
    payload.write_text(json.dumps([{"filename": "src/backend/app/api/auth.py"}]), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(CLASSIFIER_PATH),
            "--changed-files",
            str(payload),
            "--risk-map",
            str(RISK_MAP_PATH),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    assert result["risk"] == "R2"
    assert result["labels_can_lower_risk"] is False
