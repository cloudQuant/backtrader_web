"""Behavioral contracts for Iteration 195 ownership and routing policy.

The tests intentionally load the repository's source files instead of
re-implementing the policy in test helpers.  Before Task 3 implementation the
load helper fails with a normal assertion, making the expected RED state
observable without masking it as an import-collection error.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[3]
GOVERNANCE_CONTRACT = REPO_ROOT / "scripts" / "ci" / "governance_contract.py"
RISK_MAP = REPO_ROOT / ".github" / "governance" / "risk-paths.json"
MANIFEST_DIR = REPO_ROOT / ".github" / "governance" / "rulesets"
CODEOWNERS = REPO_ROOT / ".github" / "CODEOWNERS"
VALIDATION_NOW = datetime(2026, 8, 24, 0, 30, tzinfo=timezone.utc)


def _load_contract() -> ModuleType:
    assert GOVERNANCE_CONTRACT.is_file(), (
        "Task 3 governance contract is not implemented"
    )
    spec = importlib.util.spec_from_file_location(
        "governance_contract_under_test", GOVERNANCE_CONTRACT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _risk_map() -> dict[str, object]:
    assert RISK_MAP.is_file(), "Task 3 risk map is not implemented"
    return json.loads(RISK_MAP.read_text(encoding="utf-8"))


def _manifests(contract: ModuleType) -> dict[str, dict[str, object]]:
    assert MANIFEST_DIR.is_dir(), "Task 3 ruleset manifests are not implemented"
    return contract.load_manifests(MANIFEST_DIR)


def _evidence(*gates: str) -> dict[str, object]:
    return {
        "gates": list(gates),
        "reference": f"docs/governance/evidence/{'-'.join(gates)}-readback.md",
    }


def _emergency_exception(actor: dict[str, object], *gates: str) -> dict[str, object]:
    return {
        "actor": copy.deepcopy(actor),
        "incident": "INC-195",
        "reason": "documented emergency recovery",
        "issued_at": "2099-01-02T02:04:05Z",
        "expires_at": "2099-01-02T03:04:05Z",
        "readback_evidence": _evidence(*gates),
    }


def _set_verified_tag_actors(
    manifests: dict[str, dict[str, object]], actors: list[dict[str, object]]
) -> None:
    manifests["release-tags"]["bypass"]["actors"] = copy.deepcopy(actors)
    manifests["release-tags"]["bypass"]["emergency_exceptions"] = [
        _emergency_exception(actor, "D3", "D6") for actor in actors
    ]
    manifests["release-tags"]["tag_protection"]["authorized_actors"] = {
        "status": "verified",
        "actors": copy.deepcopy(actors),
        "source": "D3 and D6 approved GitHub API actor readback",
        "evidence": _evidence("D3", "D6"),
    }


class TestRiskClassification:
    def test_highest_matching_risk_wins_across_mixed_paths(self) -> None:
        contract = _load_contract()

        result = contract.classify_paths(
            [
                "docs/guide.md",
                "src/backend/app/db/database.py",
                ".github/workflows/ci.yml",
            ],
            _risk_map(),
        )

        assert result["risk"] == "R3"
        assert result["label_can_lower_risk"] is False
        assert {match["level"] for match in result["matches"]} == {"R0", "R2", "R3"}

    def test_documentation_only_change_is_r0(self) -> None:
        contract = _load_contract()

        result = contract.classify_paths(
            ["docs/architecture/community-pr.md"], _risk_map()
        )

        assert result["risk"] == "R0"

    def test_unmapped_behavior_change_uses_default_r1(self) -> None:
        contract = _load_contract()

        result = contract.classify_paths(
            ["src/backend/app/services/market_data.py"], _risk_map()
        )

        assert result["risk"] == "R1"

    def test_router_change_is_r2_without_an_r3_path(self) -> None:
        contract = _load_contract()

        result = contract.classify_paths(
            ["src/frontend/src/router/index.ts"], _risk_map()
        )

        assert result["risk"] == "R2"

    def test_auth_and_session_boundaries_are_r2_despite_downgrade_labels(self) -> None:
        contract = _load_contract()
        paths = [
            "src/backend/app/services/auth_service.py",
            "src/backend/app/api/_dependencies.py",
            "src/backend/app/api/deps.py",
            "src/backend/app/schemas/auth.py",
            "src/backend/app/utils/security.py",
            "src/frontend/src/api/index.ts",
            "src/frontend/src/api/auth.ts",
            "src/frontend/src/utils/session.ts",
            "src/frontend/src/utils/tokenRef.ts",
        ]

        result = contract.classify_paths(paths, _risk_map(), labels=["risk:R0"])

        assert result["risk"] == "R2"
        assert result["label_can_lower_risk"] is False
        assert {
            path: {
                match["level"] for match in result["matches"] if match["path"] == path
            }
            for path in paths
        } == {path: {"R2"} for path in paths}

    def test_dependency_and_release_operational_inputs_are_r3(self) -> None:
        contract = _load_contract()
        paths = [
            "src/backend/package.json",
            "src/frontend/package.json",
            "src/backend/pyproject.toml",
            "src/backend/.env.example",
            "scripts/ops/docker_deploy.sh",
            "scripts/ops/deploy_server.sh",
            "scripts/ops/generate_lockfiles.sh",
            "scripts/ops/validate_docker_env.py",
        ]

        result = contract.classify_paths(paths, _risk_map(), labels=["risk:R0"])

        assert result["risk"] == "R3"
        assert result["label_can_lower_risk"] is False
        assert {
            path: {
                match["level"] for match in result["matches"] if match["path"] == path
            }
            for path in paths
        } == {path: {"R3"} for path in paths}

    def test_security_guides_are_r3_and_have_governance_owner(self) -> None:
        contract = _load_contract()
        paths = [
            "docs/reference/SECURITY.md",
            "src/backend/docs/SECURITY.md",
        ]

        result = contract.classify_paths(paths, _risk_map(), labels=["risk:R0"])

        assert result["risk"] == "R3"
        levels_by_path = {
            path: {
                match["level"] for match in result["matches"] if match["path"] == path
            }
            for path in paths
        }
        assert all("R3" in levels for levels in levels_by_path.values())
        entries = {
            tuple(line.split()[:2])
            for line in CODEOWNERS.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        assert ("**/SECURITY.md", "@cloudQuant") in entries

    def test_sensitive_paths_cannot_be_downgraded_by_pr_labels(self) -> None:
        contract = _load_contract()

        result = contract.classify_paths(
            [
                ".github/workflows/ci.yml",
                "src/backend/app/api/auth.py",
                "src/backend/app/db/database.py",
                "src/frontend/src/router/index.ts",
                "src/frontend/src/stores/auth.ts",
                "src/bt_api_py/client.py",
            ],
            _risk_map(),
            labels=["risk:R0", "merge-ready"],
        )

        assert result["risk"] == "R3"
        assert result["label_can_lower_risk"] is False
        assert result["ignored_labels"] == ["merge-ready", "risk:R0"]
        levels_by_path = {
            path: {
                match["level"] for match in result["matches"] if match["path"] == path
            }
            for path in {
                ".github/workflows/ci.yml",
                "src/backend/app/api/auth.py",
                "src/backend/app/db/database.py",
                "src/frontend/src/router/index.ts",
                "src/frontend/src/stores/auth.ts",
                "src/bt_api_py/client.py",
            }
        }
        assert levels_by_path == {
            ".github/workflows/ci.yml": {"R3"},
            "src/backend/app/api/auth.py": {"R2"},
            "src/backend/app/db/database.py": {"R2"},
            "src/frontend/src/router/index.ts": {"R2"},
            "src/frontend/src/stores/auth.ts": {"R2"},
            "src/bt_api_py/client.py": {"R2"},
        }


class TestBranchRoutingContract:
    def test_master_rejects_regular_feature_branch(self) -> None:
        contract = _load_contract()

        issues = contract.validate_branch_contract(
            "master", "feature/market-screen", {}
        )

        assert any(
            "master only accepts release/vX.Y.Z or hotfix/master-*" in issue
            for issue in issues
        )

    def test_release_and_hotfix_require_different_evidence(self) -> None:
        contract = _load_contract()

        release_issues = contract.validate_branch_contract(
            "master",
            "release/v2.4.1",
            {"release_checklist": True, "release_validation": "full regression"},
        )
        hotfix_issues = contract.validate_branch_contract(
            "master",
            "hotfix/master-session-expiry",
            {"incident": "INC-195", "forward_port_plan": "PR to dev"},
        )
        wrong_release_evidence = contract.validate_branch_contract(
            "master",
            "release/v2.4.1",
            {"incident": "INC-195", "forward_port_plan": "PR to dev"},
        )
        wrong_hotfix_evidence = contract.validate_branch_contract(
            "master",
            "hotfix/master-session-expiry",
            {"release_checklist": True, "release_validation": "full regression"},
        )

        assert release_issues == []
        assert hotfix_issues == []
        assert any("release checklist" in issue for issue in wrong_release_evidence)
        assert any("incident" in issue for issue in wrong_hotfix_evidence)


class TestRulesetManifestContract:
    def test_repository_manifests_are_valid_desired_state(self) -> None:
        contract = _load_contract()

        assert contract.validate_manifests(_manifests(contract)) == []

    def test_manifest_validation_reports_missing_target_and_wrong_enforcement(
        self,
    ) -> None:
        contract = _load_contract()
        manifests = copy.deepcopy(_manifests(contract))
        del manifests["master"]
        manifests["dev"]["enforcement"] = "evaluate"

        issues = contract.validate_manifests(manifests)

        assert "missing required manifest: master" in issues
        assert any("dev.enforcement" in issue and "active" in issue for issue in issues)

    def test_manifest_validation_rejects_unbound_confirmed_check_and_invalid_bypass_actor(
        self,
    ) -> None:
        contract = _load_contract()
        manifests = copy.deepcopy(_manifests(contract))
        manifests["master"]["required_checks"] = {
            "status": "verified",
            "contexts": [],
            "source": "Task 4 evidence",
            "strict": True,
            "do_not_enforce_on_create": False,
        }
        manifests["dev"]["bypass"]["actors"] = [
            {"actor_type": "Team", "actor_id": "not-a-github-actor-id"}
        ]

        issues = contract.validate_manifests(manifests)

        assert any("master.required_checks.contexts" in issue for issue in issues)
        assert any("dev.bypass.actors[0].actor_id" in issue for issue in issues)

    def test_manifest_validation_rejects_blank_or_duplicate_verified_checks(
        self,
    ) -> None:
        contract = _load_contract()

        for contexts in (
            [
                {"context": "Governance Gate", "integration_id": 195},
                {"context": "", "integration_id": 196},
            ],
            [
                {"context": "Governance Gate", "integration_id": 195},
                {"context": "Governance Gate", "integration_id": 195},
            ],
        ):
            manifests = copy.deepcopy(_manifests(contract))
            manifests["master"]["required_checks"] = {
                "status": "verified",
                "contexts": contexts,
                "source": "D4 approved draft-PR Check Run evidence",
                "strict": True,
                "do_not_enforce_on_create": False,
                "evidence": _evidence("D4"),
            }

            issues = contract.validate_manifests(manifests)

            assert any("master.required_checks.contexts" in issue for issue in issues)

    def test_repository_manifests_record_current_pending_gate_truth(self) -> None:
        contract = _load_contract()
        manifests = _manifests(contract)

        for key in ("dev", "master"):
            assert manifests[key]["activation"]["remote_state"] == "not_applied"
            assert manifests[key]["required_checks"] == {
                "status": "pending_D4",
                "contexts": [],
                "source": manifests[key]["required_checks"]["source"],
                "strict": True,
                "do_not_enforce_on_create": False,
            }
            assert (
                manifests[key]["pull_request"]["code_owner_review"]["enabled"] is False
            )
        assert manifests["release-tags"]["activation"]["remote_state"] == "not_applied"
        assert manifests["release-tags"]["bypass"]["actors"] == []
        assert manifests["release-tags"]["bypass"]["emergency_exceptions"] == []
        assert manifests["release-tags"]["tag_protection"]["authorized_actors"] == {
            "status": "pending_D3_D6",
            "actors": [],
            "source": manifests["release-tags"]["tag_protection"]["authorized_actors"][
                "source"
            ],
        }

    def test_manifest_validation_rejects_future_transitions_without_evidence(
        self,
    ) -> None:
        contract = _load_contract()
        manifests = copy.deepcopy(_manifests(contract))
        manifests["dev"]["activation"]["remote_state"] = "applied"
        manifests["dev"]["bypass"]["actor_source"] = "none"
        manifests["master"]["pull_request"]["code_owner_review"]["enabled"] = True
        manifests["release-tags"]["activation"]["gate"] = "D3"
        manifests["release-tags"]["tag_protection"]["authorized_actors"]["source"] = ""

        issues = contract.validate_manifests(manifests)

        assert any("dev.activation.readback_evidence" in issue for issue in issues)
        assert any("dev.bypass.actor_source" in issue for issue in issues)
        assert any("master.pull_request.code_owner_review" in issue for issue in issues)
        assert any("release-tags.activation.gate" in issue for issue in issues)
        assert any(
            "release-tags.tag_protection.authorized_actors.source" in issue
            for issue in issues
        )

    def test_manifest_validation_allows_evidenced_future_gate_transitions(self) -> None:
        contract = _load_contract()
        manifests = copy.deepcopy(_manifests(contract))
        manifests["dev"]["activation"].update(
            {
                "remote_state": "applied",
                "readback_evidence": _evidence("D3"),
            }
        )
        manifests["master"]["pull_request"]["code_owner_review"].update(
            {
                "enabled": True,
                "evidence": _evidence("D2"),
            }
        )
        manifests["master"]["required_checks"] = {
            "status": "verified",
            "contexts": [{"context": "Governance Gate", "integration_id": 195}],
            "source": "D4 approved draft-PR Check Run evidence",
            "strict": True,
            "do_not_enforce_on_create": False,
            "evidence": _evidence("D4"),
        }
        _set_verified_tag_actors(
            manifests,
            [{"actor_type": "Team", "actor_id": 123, "bypass_mode": "always"}],
        )

        assert contract.validate_manifests(manifests) == []

    def test_manifest_validation_rejects_invalid_verified_tag_actor(self) -> None:
        contract = _load_contract()
        manifests = copy.deepcopy(_manifests(contract))
        manifests["release-tags"]["tag_protection"]["authorized_actors"] = {
            "status": "verified",
            "actors": [
                {
                    "actor_type": "Team",
                    "actor_id": "not-an-api-id",
                    "bypass_mode": "always",
                }
            ],
            "source": "D3 and D6 approved GitHub API actor readback",
            "evidence": _evidence("D3", "D6"),
        }

        issues = contract.validate_manifests(manifests)

        assert any(
            "release-tags.tag_protection.authorized_actors.actors[0].actor_id" in issue
            for issue in issues
        )

    def test_pending_tag_actors_require_an_empty_bypass_pool(self) -> None:
        contract = _load_contract()
        manifests = copy.deepcopy(_manifests(contract))
        manifests["release-tags"]["bypass"]["actors"] = [
            {"actor_type": "Team", "actor_id": 123}
        ]

        issues = contract.validate_manifests(manifests)

        assert any(
            "release-tags.bypass.actors" in issue and "pending" in issue
            for issue in issues
        )

    def test_manifest_validation_allows_future_user_bypass_actor(self) -> None:
        contract = _load_contract()
        manifests = copy.deepcopy(_manifests(contract))
        manifests["dev"]["bypass"]["actors"] = [
            {"actor_type": "User", "actor_id": 123, "bypass_mode": "pull_request"}
        ]
        manifests["dev"]["bypass"]["emergency_exceptions"] = [
            _emergency_exception(
                {
                    "actor_type": "User",
                    "actor_id": 123,
                    "bypass_mode": "pull_request",
                },
                "D3",
            )
        ]

        assert contract.validate_manifests(manifests) == []

    def test_branch_bypass_actor_requires_auditable_emergency_exception(self) -> None:
        contract = _load_contract()
        manifests = copy.deepcopy(_manifests(contract))
        manifests["dev"]["bypass"]["actors"] = [
            {"actor_type": "User", "actor_id": 123, "bypass_mode": "pull_request"}
        ]

        issues = contract.validate_manifests(manifests)

        assert any("dev.bypass.emergency_exceptions" in issue for issue in issues)

    def test_emergency_exception_requires_auditable_fields(self) -> None:
        contract = _load_contract()
        actor = {"actor_type": "User", "actor_id": 123, "bypass_mode": "pull_request"}
        cases = [
            ("incident", ""),
            ("reason", ""),
            ("expires_at", "not-a-timestamp"),
            ("expires_at", "2020-01-02T03:04:05Z"),
            ("readback_evidence", "x"),
        ]

        for field, value in cases:
            manifests = copy.deepcopy(_manifests(contract))
            exception = _emergency_exception(actor, "D3")
            exception[field] = value
            manifests["dev"]["bypass"]["actors"] = [actor]
            manifests["dev"]["bypass"]["emergency_exceptions"] = [exception]

            issues = contract.validate_manifests(manifests)

            assert any(
                f"dev.bypass.emergency_exceptions[0].{field}" in issue
                for issue in issues
            )

    def test_emergency_exception_requires_unexpired_bounded_lifetime(self) -> None:
        contract = _load_contract()
        actor = {"actor_type": "User", "actor_id": 123, "bypass_mode": "pull_request"}
        cases = [
            ("issued_at", "not-a-timestamp", "issued_at"),
            ("expires_at", "2026-08-24T00:00:00Z", "expires_at"),
            ("expires_at", "2026-08-24T00:15:00Z", "expires_at"),
            ("expires_at", "2026-08-25T00:00:01Z", "expires_at"),
        ]

        for field, value, expected_field in cases:
            manifests = copy.deepcopy(_manifests(contract))
            exception = _emergency_exception(actor, "D3")
            exception.update(
                {
                    "issued_at": "2026-08-24T00:00:00Z",
                    field: value,
                }
            )
            manifests["dev"]["bypass"]["actors"] = [actor]
            manifests["dev"]["bypass"]["emergency_exceptions"] = [exception]

            issues = contract.validate_manifests(manifests, now=VALIDATION_NOW)

            assert any(
                f"dev.bypass.emergency_exceptions[0].{expected_field}" in issue
                for issue in issues
            )

    def test_emergency_exception_allows_bounded_unexpired_start_time_alias(
        self,
    ) -> None:
        contract = _load_contract()
        actor = {"actor_type": "User", "actor_id": 123, "bypass_mode": "pull_request"}
        manifests = copy.deepcopy(_manifests(contract))
        exception = _emergency_exception(actor, "D3")
        exception.pop("issued_at")
        exception.update(
            {
                "starts_at": "2026-08-24T00:00:00Z",
                "expires_at": "2026-08-24T01:00:00Z",
            }
        )
        manifests["dev"]["bypass"]["actors"] = [actor]
        manifests["dev"]["bypass"]["emergency_exceptions"] = [exception]

        assert contract.validate_manifests(manifests, now=VALIDATION_NOW) == []

    def test_manifest_validation_rejects_unstructured_future_gate_evidence(
        self,
    ) -> None:
        contract = _load_contract()
        manifests = copy.deepcopy(_manifests(contract))
        manifests["dev"]["activation"].update(
            {"remote_state": "applied", "readback_evidence": "x"}
        )
        manifests["master"]["pull_request"]["code_owner_review"].update(
            {"enabled": True, "evidence": "x"}
        )
        manifests["master"]["required_checks"] = {
            "status": "verified",
            "contexts": [{"context": "Governance Gate", "integration_id": 195}],
            "source": "D4 approved draft-PR Check Run evidence",
            "strict": True,
            "do_not_enforce_on_create": False,
            "evidence": "x",
        }
        _set_verified_tag_actors(
            manifests,
            [{"actor_type": "Team", "actor_id": 123, "bypass_mode": "always"}],
        )
        manifests["release-tags"]["tag_protection"]["authorized_actors"]["evidence"] = (
            "x"
        )

        issues = contract.validate_manifests(manifests)

        assert any("dev.activation.readback_evidence" in issue for issue in issues)
        assert any(
            "master.pull_request.code_owner_review.evidence" in issue
            for issue in issues
        )
        assert any("master.required_checks.evidence" in issue for issue in issues)
        assert any(
            "release-tags.tag_protection.authorized_actors.evidence" in issue
            for issue in issues
        )

    def test_structured_future_evidence_requires_the_corresponding_gate(self) -> None:
        contract = _load_contract()
        manifests = copy.deepcopy(_manifests(contract))
        manifests["dev"]["activation"].update(
            {"remote_state": "applied", "readback_evidence": _evidence("D4")}
        )

        issues = contract.validate_manifests(manifests)

        assert any(
            "dev.activation.readback_evidence.gates" in issue for issue in issues
        )

    def test_required_checks_disallow_enforcement_on_create(self) -> None:
        contract = _load_contract()
        manifests = copy.deepcopy(_manifests(contract))
        manifests["dev"]["required_checks"]["do_not_enforce_on_create"] = True

        issues = contract.validate_manifests(manifests)

        assert any(
            "dev.required_checks.do_not_enforce_on_create" in issue for issue in issues
        )

    def test_bypass_actor_normalization_handles_organization_admin_and_deploy_key(
        self,
    ) -> None:
        contract = _load_contract()
        manifests = copy.deepcopy(_manifests(contract))
        manifests["release-tags"]["bypass"]["actors"] = [
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
        manifests["release-tags"]["bypass"]["emergency_exceptions"] = [
            _emergency_exception(actor, "D3", "D6")
            for actor in manifests["release-tags"]["bypass"]["actors"]
        ]
        manifests["release-tags"]["tag_protection"]["authorized_actors"] = {
            "status": "verified",
            "actors": [
                {
                    "actor_type": "OrganizationAdmin",
                    "actor_id": None,
                    "bypass_mode": "always",
                },
                {
                    "actor_type": "DeployKey",
                    "actor_id": None,
                    "bypass_mode": "always",
                },
            ],
            "source": "D3 and D6 approved GitHub API actor readback",
            "evidence": _evidence("D3", "D6"),
        }

        assert contract.validate_manifests(manifests) == []
        assert contract.normalized_manifest(manifests["release-tags"])[
            "bypass_actors"
        ] == [
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

    def test_manifest_validation_rejects_invalid_bypass_actor_schema(self) -> None:
        contract = _load_contract()
        cases = [
            (
                {"actor_type": "Unknown", "actor_id": 123, "bypass_mode": "always"},
                "actor_type",
            ),
            (
                {"actor_type": "User", "actor_id": None, "bypass_mode": "always"},
                "actor_id",
            ),
            (
                {"actor_type": "DeployKey", "actor_id": 123, "bypass_mode": "always"},
                "actor_id",
            ),
            (
                {"actor_type": "User", "actor_id": 123, "bypass_mode": "exempt"},
                "bypass_mode",
            ),
            (
                {
                    "actor_type": "User",
                    "actor_id": 123,
                    "bypass_mode": "pull_request",
                },
                "bypass_mode",
            ),
            (
                {
                    "actor_type": "DeployKey",
                    "actor_id": None,
                    "bypass_mode": "pull_request",
                },
                "bypass_mode",
            ),
        ]

        for actor, field in cases:
            manifests = copy.deepcopy(_manifests(contract))
            _set_verified_tag_actors(manifests, [actor])

            issues = contract.validate_manifests(manifests)

            assert any(
                f"release-tags.bypass.actors[0].{field}" in issue for issue in issues
            )

    def test_branch_deploy_key_rejects_pull_request_mode(self) -> None:
        contract = _load_contract()
        manifests = copy.deepcopy(_manifests(contract))
        actor = {
            "actor_type": "DeployKey",
            "actor_id": None,
            "bypass_mode": "pull_request",
        }
        manifests["dev"]["bypass"]["actors"] = [actor]
        manifests["dev"]["bypass"]["emergency_exceptions"] = [
            _emergency_exception(actor, "D3")
        ]

        issues = contract.validate_manifests(manifests)

        assert any(
            "dev.bypass.actors[0].bypass_mode" in issue and "DeployKey" in issue
            for issue in issues
        )

    def test_verified_tag_actor_mode_must_match_bypass_actor(self) -> None:
        contract = _load_contract()
        manifests = copy.deepcopy(_manifests(contract))
        manifests["release-tags"]["bypass"]["actors"] = [
            {"actor_type": "Team", "actor_id": 123, "bypass_mode": "always"}
        ]
        manifests["release-tags"]["bypass"]["emergency_exceptions"] = [
            _emergency_exception(
                {"actor_type": "Team", "actor_id": 123, "bypass_mode": "always"},
                "D3",
                "D6",
            )
        ]
        manifests["release-tags"]["tag_protection"]["authorized_actors"] = {
            "status": "verified",
            "actors": [
                {
                    "actor_type": "Team",
                    "actor_id": 123,
                    "bypass_mode": "pull_request",
                }
            ],
            "source": "D3 and D6 approved GitHub API actor readback",
            "evidence": _evidence("D3", "D6"),
        }

        issues = contract.validate_manifests(manifests)

        assert any(
            "release-tags.tag_protection.authorized_actors.actors" in issue
            and "exactly match" in issue
            for issue in issues
        )
