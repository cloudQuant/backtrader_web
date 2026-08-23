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


def _future_tag_manifest_dir(
    tmp_path: Path,
    *,
    bypass_actor: dict[str, object],
    authorized_actor: dict[str, object],
) -> Path:
    """Write an evidenced D3/D6 tag transition without changing repo fixtures."""
    for name in ("dev", "master", "release-tags"):
        source = MANIFEST_DIR / f"{name}.json"
        manifest = json.loads(source.read_text(encoding="utf-8"))
        if name == "release-tags":
            manifest["bypass"]["actors"] = [bypass_actor]
            manifest["tag_protection"]["authorized_actors"] = {
                "status": "verified",
                "actors": [authorized_actor],
                "source": "D3 and D6 approved GitHub API actor readback",
            }
        (tmp_path / f"{name}.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path


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

    def test_ref_name_exclude_drift_is_not_ignored(self) -> None:
        verifier = _load_verifier()
        actual = copy.deepcopy(_fixture()["rulesets"])
        dev_rule = next(rule for rule in actual if rule["name"] == "Iteration 195: dev")
        dev_rule["conditions"]["ref_name"]["exclude"] = ["refs/heads/dev"]

        report = verifier.verify_rulesets(MANIFEST_DIR, actual)

        assert report["ok"] is False
        assert any("dev.target.exclude" in diff for diff in report["differences"])

    def test_duplicate_named_actual_rulesets_fail_regardless_of_order(self) -> None:
        verifier = _load_verifier()
        original = _fixture()["rulesets"]
        dev_rule = next(
            rule for rule in original if rule["name"] == "Iteration 195: dev"
        )

        for duplicate_first in (True, False):
            actual = copy.deepcopy(original)
            duplicate = copy.deepcopy(dev_rule)
            duplicate["id"] = 999 if duplicate_first else 998
            if duplicate_first:
                actual.insert(0, duplicate)
            else:
                actual.append(duplicate)

            report = verifier.verify_rulesets(MANIFEST_DIR, actual)

            assert report["ok"] is False
            assert any(
                "duplicate actual Ruleset named 'Iteration 195: dev'" in difference
                for difference in report["differences"]
            )

    def test_verified_tag_actor_matches_api_bypass_actor(self, tmp_path: Path) -> None:
        verifier = _load_verifier()
        actor = {"actor_type": "Team", "actor_id": 123}
        manifest_dir = _future_tag_manifest_dir(
            tmp_path, bypass_actor=actor, authorized_actor=actor
        )
        actual = copy.deepcopy(_fixture()["rulesets"])
        tag_rule = next(
            rule for rule in actual if rule["name"] == "Iteration 195: release tags"
        )
        tag_rule["bypass_actors"] = [actor]

        report = verifier.verify_rulesets(manifest_dir, actual)

        assert report == {"ok": True, "differences": []}

    def test_verified_tag_actor_must_match_bypass_actor(self, tmp_path: Path) -> None:
        verifier = _load_verifier()
        manifest_dir = _future_tag_manifest_dir(
            tmp_path,
            bypass_actor={"actor_type": "Team", "actor_id": 123},
            authorized_actor={"actor_type": "Team", "actor_id": 456},
        )
        actual = copy.deepcopy(_fixture()["rulesets"])
        tag_rule = next(
            rule for rule in actual if rule["name"] == "Iteration 195: release tags"
        )
        tag_rule["bypass_actors"] = [{"actor_type": "Team", "actor_id": 123}]

        report = verifier.verify_rulesets(manifest_dir, actual)

        assert report["ok"] is False
        assert any(
            "release-tags.tag_protection.authorized_actors.actors" in difference
            for difference in report["differences"]
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
