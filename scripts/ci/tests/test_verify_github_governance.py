"""Verifier-level contracts for normalized GitHub Ruleset readback."""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
VERIFIER = REPO_ROOT / "scripts" / "ci" / "verify_github_governance.py"
MANIFEST_DIR = REPO_ROOT / ".github" / "governance" / "rulesets"
FIXTURE = Path(__file__).parent / "fixtures" / "github-rulesets.json"


def _load_verifier() -> ModuleType:
    assert VERIFIER.is_file(), "Task 3 GitHub governance verifier is not implemented"
    if str(VERIFIER.parent) not in sys.path:
        sys.path.insert(0, str(VERIFIER.parent))
    spec = importlib.util.spec_from_file_location("verify_github_governance_under_test", VERIFIER)
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
    issued_at = datetime.now(timezone.utc).replace(microsecond=0)
    expires_at = issued_at + timedelta(hours=1)
    for name in ("dev", "master", "release-tags"):
        source = MANIFEST_DIR / f"{name}.json"
        manifest = json.loads(source.read_text(encoding="utf-8"))
        if name == "release-tags":
            manifest["bypass"]["actors"] = [bypass_actor]
            manifest["bypass"]["emergency_exceptions"] = [
                {
                    "actor": copy.deepcopy(bypass_actor),
                    "incident": "INC-195",
                    "reason": "documented emergency recovery",
                    "issued_at": issued_at.isoformat().replace("+00:00", "Z"),
                    "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
                    "readback_evidence": {
                        "gates": ["D3", "D6"],
                        "reference": "docs/governance/evidence/D3-D6-readback.md",
                    },
                }
            ]
            manifest["tag_protection"]["authorized_actors"] = {
                "status": "verified",
                "actors": [authorized_actor],
                "source": "D3 and D6 approved GitHub API actor readback",
                "evidence": {
                    "gates": ["D3", "D6"],
                    "reference": "docs/governance/evidence/D3-D6-readback.md",
                },
            }
        (tmp_path / f"{name}.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path


def _future_branch_manifest_dir(tmp_path: Path, *, integration_id: int) -> Path:
    """Write a D4-evidenced branch transition with a pinned Check Run source."""
    for name in ("dev", "master", "release-tags"):
        source = MANIFEST_DIR / f"{name}.json"
        manifest = json.loads(source.read_text(encoding="utf-8"))
        if name == "dev":
            manifest["required_checks"] = {
                "status": "verified",
                "contexts": [{"context": "Governance Gate", "integration_id": integration_id}],
                "source": "D4 approved draft-PR Check Run evidence",
                "strict": True,
                "do_not_enforce_on_create": False,
                "evidence": {
                    "gates": ["D4"],
                    "reference": "docs/governance/evidence/D4-readback.md",
                },
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
        pull_request = next(rule for rule in dev_rule["rules"] if rule["type"] == "pull_request")
        pull_request["parameters"]["required_approving_review_count"] = 0

        report = verifier.verify_rulesets(MANIFEST_DIR, actual)

        assert report["ok"] is False
        assert any("dev.pull_request.required_approvals" in diff for diff in report["differences"])

    def test_review_reset_and_last_push_requirements_are_compared(self) -> None:
        verifier = _load_verifier()
        actual = copy.deepcopy(_fixture()["rulesets"])
        dev_rule = next(rule for rule in actual if rule["name"] == "Iteration 195: dev")
        pull_request = next(rule for rule in dev_rule["rules"] if rule["type"] == "pull_request")
        pull_request["parameters"]["dismiss_stale_reviews_on_push"] = False
        pull_request["parameters"].pop("require_last_push_approval", None)

        report = verifier.verify_rulesets(MANIFEST_DIR, actual, source="fixture")

        assert report["ok"] is False
        assert any(
            "dev.pull_request.dismiss_stale_reviews_on_push" in diff
            for diff in report["differences"]
        )
        assert any(
            "dev.pull_request.require_last_push_approval" in diff for diff in report["differences"]
        )

    def test_unmodeled_actual_rule_type_fails_closed(self) -> None:
        verifier = _load_verifier()
        actual = copy.deepcopy(_fixture()["rulesets"])
        dev_rule = next(rule for rule in actual if rule["name"] == "Iteration 195: dev")
        dev_rule["rules"].append({"type": "required_workflows", "parameters": {}})

        report = verifier.verify_rulesets(MANIFEST_DIR, actual, source="fixture")

        assert report["ok"] is False
        assert any(
            "dev.readback_errors" in difference and "unmodeled rule type" in difference
            for difference in report["differences"]
        )

    def test_fixture_mode_compares_desired_shape_without_claiming_remote_activation(
        self,
    ) -> None:
        verifier = _load_verifier()

        report = verifier.verify_rulesets(
            MANIFEST_DIR,
            copy.deepcopy(_fixture()["rulesets"]),
            source="fixture",
        )

        assert report == {"ok": True, "differences": []}

    def test_live_mode_rejects_present_rulesets_declared_not_applied(self) -> None:
        verifier = _load_verifier()

        report = verifier.verify_rulesets(
            MANIFEST_DIR,
            copy.deepcopy(_fixture()["rulesets"]),
            source="live",
        )

        assert report["ok"] is False
        assert any(
            "dev.activation.remote_state" in difference for difference in report["differences"]
        )

    def test_live_mode_accepts_the_absence_of_rulesets_declared_not_applied(
        self,
    ) -> None:
        verifier = _load_verifier()

        report = verifier.verify_rulesets(MANIFEST_DIR, [], source="live")

        assert report == {"ok": True, "differences": []}

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
        dev_rule = next(rule for rule in original if rule["name"] == "Iteration 195: dev")

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
        actor = {"actor_type": "Team", "actor_id": 123, "bypass_mode": "always"}
        manifest_dir = _future_tag_manifest_dir(
            tmp_path, bypass_actor=actor, authorized_actor=actor
        )
        actual = copy.deepcopy(_fixture()["rulesets"])
        tag_rule = next(rule for rule in actual if rule["name"] == "Iteration 195: release tags")
        tag_rule["bypass_actors"] = [actor]

        report = verifier.verify_rulesets(manifest_dir, actual)

        assert report == {"ok": True, "differences": []}

    def test_verified_tag_actor_must_match_bypass_actor(self, tmp_path: Path) -> None:
        verifier = _load_verifier()
        manifest_dir = _future_tag_manifest_dir(
            tmp_path,
            bypass_actor={
                "actor_type": "Team",
                "actor_id": 123,
                "bypass_mode": "always",
            },
            authorized_actor={
                "actor_type": "Team",
                "actor_id": 456,
                "bypass_mode": "always",
            },
        )
        actual = copy.deepcopy(_fixture()["rulesets"])
        tag_rule = next(rule for rule in actual if rule["name"] == "Iteration 195: release tags")
        tag_rule["bypass_actors"] = [
            {"actor_type": "Team", "actor_id": 123, "bypass_mode": "always"}
        ]

        report = verifier.verify_rulesets(manifest_dir, actual)

        assert report["ok"] is False
        assert any(
            "release-tags.tag_protection.authorized_actors.actors" in difference
            for difference in report["differences"]
        )

    def test_bypass_mode_drift_is_not_ignored(self, tmp_path: Path) -> None:
        verifier = _load_verifier()
        expected_actor = {
            "actor_type": "Team",
            "actor_id": 123,
            "bypass_mode": "always",
        }
        manifest_dir = _future_tag_manifest_dir(
            tmp_path,
            bypass_actor=expected_actor,
            authorized_actor=expected_actor,
        )
        actual = copy.deepcopy(_fixture()["rulesets"])
        tag_rule = next(rule for rule in actual if rule["name"] == "Iteration 195: release tags")
        tag_rule["bypass_actors"] = [
            {"actor_type": "Team", "actor_id": 123, "bypass_mode": "exempt"}
        ]

        report = verifier.verify_rulesets(manifest_dir, actual)

        assert report["ok"] is False
        assert any(
            "release-tags.bypass_actors[0].bypass_mode" in difference
            for difference in report["differences"]
        )

    def test_missing_api_bypass_actor_readback_fails_closed(self) -> None:
        verifier = _load_verifier()
        actual = copy.deepcopy(_fixture()["rulesets"])
        for ruleset in actual:
            del ruleset["bypass_actors"]

        report = verifier.verify_rulesets(MANIFEST_DIR, actual)

        assert report["ok"] is False
        assert all(
            verifier.normalize_github_ruleset(ruleset)["bypass_actors"] is None
            for ruleset in actual
        )
        assert any(
            ".bypass_actors: unavailable in API readback" in difference
            for difference in report["differences"]
        )

    def test_explicit_empty_api_bypass_actor_readback_matches_empty_manifest(
        self,
    ) -> None:
        verifier = _load_verifier()
        actual = copy.deepcopy(_fixture()["rulesets"])
        for ruleset in actual:
            ruleset["bypass_actors"] = []

        report = verifier.verify_rulesets(MANIFEST_DIR, actual)

        assert report == {"ok": True, "differences": []}

    def test_malformed_api_bypass_actor_readback_fails_closed(self) -> None:
        verifier = _load_verifier()
        for malformed_entry in (None, "unexpected-non-object", 7):
            actual = copy.deepcopy(_fixture()["rulesets"])
            dev_rule = next(rule for rule in actual if rule["name"] == "Iteration 195: dev")
            dev_rule["bypass_actors"] = [malformed_entry]

            report = verifier.verify_rulesets(MANIFEST_DIR, actual)

            assert report["ok"] is False
            assert any("dev.bypass_actors[0]" in difference for difference in report["differences"])

    def test_malformed_empty_critical_readback_fields_fail_closed(self) -> None:
        verifier = _load_verifier()

        for field_path, malformed_value in (
            ("target.exclude", "not-a-list"),
            ("required_checks.contexts", "not-a-list"),
            ("required_checks.contexts", [None]),
        ):
            actual = copy.deepcopy(_fixture()["rulesets"])
            dev_rule = next(rule for rule in actual if rule["name"] == "Iteration 195: dev")
            if field_path == "target.exclude":
                dev_rule["conditions"]["ref_name"]["exclude"] = malformed_value
            else:
                status_checks = next(
                    rule for rule in dev_rule["rules"] if rule["type"] == "required_status_checks"
                )
                status_checks["parameters"]["required_status_checks"] = malformed_value

            report = verifier.verify_rulesets(MANIFEST_DIR, actual)

            assert report["ok"] is False
            assert any(f"dev.{field_path}" in difference for difference in report["differences"])

    def test_duplicate_required_status_check_rules_fail_closed(self) -> None:
        verifier = _load_verifier()
        actual = copy.deepcopy(_fixture()["rulesets"])
        dev_rule = next(rule for rule in actual if rule["name"] == "Iteration 195: dev")
        status_checks = next(
            rule for rule in dev_rule["rules"] if rule["type"] == "required_status_checks"
        )
        dev_rule["rules"].append(copy.deepcopy(status_checks))

        report = verifier.verify_rulesets(MANIFEST_DIR, actual)

        assert report["ok"] is False
        assert any(
            "dev.readback_errors" in difference and "duplicate required_status_checks" in difference
            for difference in report["differences"]
        )

    @pytest.mark.parametrize(
        ("ruleset_name", "rule_type"),
        (
            ("Iteration 195: dev", "pull_request"),
            ("Iteration 195: dev", "required_status_checks"),
            ("Iteration 195: dev", "non_fast_forward"),
            ("Iteration 195: dev", "deletion"),
            ("Iteration 195: release tags", "creation"),
            ("Iteration 195: release tags", "update"),
            ("Iteration 195: release tags", "deletion"),
        ),
    )
    @pytest.mark.parametrize("duplicate_first", (True, False))
    @pytest.mark.parametrize("conflicting_parameters", (False, True))
    def test_duplicate_security_critical_rules_fail_closed_regardless_of_order_or_content(
        self,
        ruleset_name: str,
        rule_type: str,
        duplicate_first: bool,
        conflicting_parameters: bool,
    ) -> None:
        verifier = _load_verifier()
        actual = copy.deepcopy(_fixture()["rulesets"])
        ruleset = next(rule for rule in actual if rule["name"] == ruleset_name)
        source_rule = next(rule for rule in ruleset["rules"] if rule["type"] == rule_type)
        duplicate_rule = copy.deepcopy(source_rule)
        if conflicting_parameters:
            duplicate_rule["parameters"] = {"unexpected_duplicate_parameter": True}
        if duplicate_first:
            ruleset["rules"].insert(0, duplicate_rule)
        else:
            ruleset["rules"].append(duplicate_rule)

        report = verifier.verify_rulesets(MANIFEST_DIR, actual)
        manifest_key = "dev" if ruleset_name.endswith("dev") else "release-tags"

        assert report["ok"] is False
        assert any(
            f"{manifest_key}.readback_errors" in difference
            and f"duplicate {rule_type} rules" in difference
            for difference in report["differences"]
        )

    @pytest.mark.parametrize("ruleset_name", ("Iteration 195: dev", "Iteration 195: release tags"))
    def test_unique_security_critical_rule_order_remains_non_semantic(
        self,
        ruleset_name: str,
    ) -> None:
        verifier = _load_verifier()
        actual = copy.deepcopy(_fixture()["rulesets"])
        ruleset = next(rule for rule in actual if rule["name"] == ruleset_name)
        ruleset["rules"].reverse()

        report = verifier.verify_rulesets(MANIFEST_DIR, actual)

        assert report == {"ok": True, "differences": []}

    def test_required_check_integration_id_is_preserved_for_identity_matching(
        self,
    ) -> None:
        verifier = _load_verifier()
        actual = copy.deepcopy(_fixture()["rulesets"])
        dev_rule = next(rule for rule in actual if rule["name"] == "Iteration 195: dev")
        status_checks = next(
            rule for rule in dev_rule["rules"] if rule["type"] == "required_status_checks"
        )
        status_checks["parameters"]["required_status_checks"] = [
            {"context": "Governance Gate", "integration_id": 195}
        ]

        normalized = verifier.normalize_github_ruleset(dev_rule)

        assert normalized["required_checks"]["contexts"] == [
            {"context": "Governance Gate", "integration_id": 195}
        ]

        differences = verifier._diff(
            {"contexts": [{"context": "Governance Gate", "integration_id": 196}]},
            {"contexts": normalized["required_checks"]["contexts"]},
            "dev.required_checks",
        )

        assert any(
            "dev.required_checks.contexts[0].integration_id" in difference
            for difference in differences
        )

    def test_do_not_enforce_on_create_drift_is_not_ignored(self) -> None:
        verifier = _load_verifier()
        actual = copy.deepcopy(_fixture()["rulesets"])
        dev_rule = next(rule for rule in actual if rule["name"] == "Iteration 195: dev")
        status_checks = next(
            rule for rule in dev_rule["rules"] if rule["type"] == "required_status_checks"
        )
        status_checks["parameters"]["do_not_enforce_on_create"] = True

        report = verifier.verify_rulesets(MANIFEST_DIR, actual)

        assert report["ok"] is False
        assert any(
            "dev.required_checks.do_not_enforce_on_create" in difference
            for difference in report["differences"]
        )

    def test_required_check_integration_id_drift_is_reported(self, tmp_path: Path) -> None:
        verifier = _load_verifier()
        manifest_dir = _future_branch_manifest_dir(tmp_path, integration_id=195)
        actual = copy.deepcopy(_fixture()["rulesets"])
        dev_rule = next(rule for rule in actual if rule["name"] == "Iteration 195: dev")
        status_checks = next(
            rule for rule in dev_rule["rules"] if rule["type"] == "required_status_checks"
        )
        status_checks["parameters"]["required_status_checks"] = [
            {"context": "Governance Gate", "integration_id": 196}
        ]

        report = verifier.verify_rulesets(manifest_dir, actual)

        assert report["ok"] is False
        assert any(
            "dev.required_checks.contexts[0].integration_id" in difference
            for difference in report["differences"]
        )

    def test_api_actor_normalization_preserves_mode_and_ignores_org_admin_id(
        self,
    ) -> None:
        verifier = _load_verifier()
        actual = copy.deepcopy(_fixture()["rulesets"])
        tag_rule = next(rule for rule in actual if rule["name"] == "Iteration 195: release tags")
        tag_rule["bypass_actors"] = [
            {
                "actor_type": "OrganizationAdmin",
                "actor_id": 321,
                "bypass_mode": "always",
            },
            {
                "actor_type": "DeployKey",
                "actor_id": None,
                "bypass_mode": "always",
            },
        ]

        normalized = verifier.normalize_github_ruleset(tag_rule)

        assert normalized["bypass_actors"] == [
            {
                "actor_type": "DeployKey",
                "actor_id": None,
                "bypass_mode": "always",
            },
            {
                "actor_type": "OrganizationAdmin",
                "actor_id": None,
                "bypass_mode": "always",
            },
        ]


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
            return json.dumps(next(item for item in raw_rulesets if item["id"] == ruleset_id))

        loaded = verifier.load_live_rulesets("cloudQuant/backtrader_web", runner=runner)

        assert [item["name"] for item in loaded] == [item["name"] for item in raw_rulesets]
        assert commands[0] == [
            "gh",
            "api",
            "--method",
            "GET",
            "--paginate",
            "--slurp",
            "repos/cloudQuant/backtrader_web/rulesets",
        ]
        assert all(command[:4] == ["gh", "api", "--method", "GET"] for command in commands)
        payload_flags = {
            "-d",
            "-f",
            "-F",
            "--body",
            "--data",
            "--data-binary",
            "--field",
            "--input",
            "--raw-field",
        }
        assert all(not payload_flags.intersection(command) for command in commands)
        assert all(
            not {"POST", "PATCH", "PUT", "DELETE"}.intersection(command) for command in commands
        )

    @pytest.mark.parametrize(
        "listing",
        (
            [{"id": 1}, "unexpected-non-object"],
            [[{"id": 1}, "unexpected-non-object"]],
        ),
    )
    def test_live_loader_rejects_non_object_pager_entries(self, listing: object) -> None:
        verifier = _load_verifier()

        def runner(command: list[str]) -> str:
            if command[-1].endswith("/rulesets"):
                return json.dumps(listing)
            return json.dumps(_fixture()["rulesets"][0])

        with pytest.raises(ValueError, match="non-object entry"):
            verifier.load_live_rulesets("cloudQuant/backtrader_web", runner=runner)
