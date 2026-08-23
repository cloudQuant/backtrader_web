"""Verifier-level contracts for normalized GitHub Ruleset readback."""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[3]
VERIFIER = REPO_ROOT / "scripts" / "ci" / "verify_github_governance.py"
MANIFEST_DIR = REPO_ROOT / ".github" / "governance" / "rulesets"
FIXTURE = Path(__file__).parent / "fixtures" / "github-rulesets.json"


def _load_verifier() -> ModuleType:
    assert VERIFIER.is_file(), "Task 3 GitHub governance verifier is not implemented"
    if str(VERIFIER.parent) not in sys.path:
        sys.path.insert(0, str(VERIFIER.parent))
    spec = importlib.util.spec_from_file_location(
        "verify_github_governance_under_test", VERIFIER
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fixture() -> dict[str, object]:
    assert FIXTURE.is_file(), "Task 3 GitHub rulesets fixture is not implemented"
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class TestRulesetNormalization:
    def test_api_ids_timestamps_and_rule_order_do_not_create_drift(self) -> None:
        verifier = _load_verifier()
        actual = _fixture()["rulesets"]
        changed_metadata = copy.deepcopy(actual)
        changed_metadata.reverse()
        for index, ruleset in enumerate(changed_metadata, start=900):
            ruleset["id"] = index
            ruleset["node_id"] = f"RRS_changed_{index}"
            ruleset["created_at"] = "2036-02-03T04:05:06Z"
            ruleset["updated_at"] = "2036-02-04T05:06:07Z"
            ruleset["rules"].reverse()

        report = verifier.verify_rulesets(MANIFEST_DIR, changed_metadata)

        assert report["ok"] is True
        assert report["differences"] == []

    def test_real_rule_drift_has_a_human_readable_path(self) -> None:
        verifier = _load_verifier()
        actual = copy.deepcopy(_fixture()["rulesets"])
        dev_rule = next(rule for rule in actual if rule["name"] == "Iteration 195: dev")
        pull_request = next(
            rule for rule in dev_rule["rules"] if rule["type"] == "pull_request"
        )
        pull_request["parameters"]["required_approving_review_count"] = 0

        report = verifier.verify_rulesets(MANIFEST_DIR, actual)

        assert report["ok"] is False
        assert any(
            "dev.pull_request.required_approvals" in diff
            for diff in report["differences"]
        )


class TestVerifierCli:
    def test_fixture_cli_emits_machine_readable_success(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(VERIFIER),
                "--fixture",
                str(FIXTURE),
                "--manifest-dir",
                str(MANIFEST_DIR),
                "--json",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == {"differences": [], "ok": True}

    def test_live_loader_uses_only_read_only_get_endpoints(self) -> None:
        verifier = _load_verifier()
        commands: list[list[str]] = []
        raw_rulesets = _fixture()["rulesets"]

        def runner(command: list[str]) -> str:
            commands.append(command)
            if command[-1].endswith("/rulesets"):
                return json.dumps([[{"id": item["id"]} for item in raw_rulesets]])
            ruleset_id = int(command[-1].rsplit("/", maxsplit=1)[-1])
            return json.dumps(
                next(item for item in raw_rulesets if item["id"] == ruleset_id)
            )

        loaded = verifier.load_live_rulesets("cloudQuant/backtrader_web", runner=runner)

        assert [item["name"] for item in loaded] == [
            item["name"] for item in raw_rulesets
        ]
        assert commands[0] == [
            "gh",
            "api",
            "--paginate",
            "--slurp",
            "repos/cloudQuant/backtrader_web/rulesets",
        ]
        assert all(
            "POST" not in command and "PATCH" not in command for command in commands
        )
