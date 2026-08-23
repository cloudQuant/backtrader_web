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
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[3]
GOVERNANCE_CONTRACT = REPO_ROOT / "scripts" / "ci" / "governance_contract.py"
RISK_MAP = REPO_ROOT / ".github" / "governance" / "risk-paths.json"
MANIFEST_DIR = REPO_ROOT / ".github" / "governance" / "rulesets"
CODEOWNERS = REPO_ROOT / ".github" / "CODEOWNERS"


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
            "src/backend/app/schemas/auth.py",
            "src/backend/app/utils/security.py",
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
            ["Governance Gate", ""],
            ["Governance Gate", "Governance Gate"],
        ):
            manifests = copy.deepcopy(_manifests(contract))
            manifests["master"]["required_checks"] = {
                "status": "verified",
                "contexts": contexts,
                "source": "D4 approved draft-PR Check Run evidence",
                "strict": True,
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
            }
            assert (
                manifests[key]["pull_request"]["code_owner_review"]["enabled"] is False
            )
        assert manifests["release-tags"]["activation"]["remote_state"] == "not_applied"
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
                "readback_evidence": "D3 approved Rulesets API readback",
            }
        )
        manifests["master"]["pull_request"]["code_owner_review"].update(
            {
                "enabled": True,
                "evidence": "D2 approved independent owner matrix",
            }
        )
        manifests["master"]["required_checks"] = {
            "status": "verified",
            "contexts": ["Governance Gate"],
            "source": "D4 approved draft-PR Check Run evidence",
            "strict": True,
        }
        manifests["release-tags"]["tag_protection"]["authorized_actors"] = {
            "status": "verified",
            "actors": [{"actor_type": "Team", "actor_id": 123}],
            "source": "D3 and D6 approved GitHub API actor readback",
        }
        manifests["release-tags"]["bypass"]["actors"] = [
            {"actor_type": "Team", "actor_id": 123}
        ]

        assert contract.validate_manifests(manifests) == []

    def test_manifest_validation_rejects_invalid_verified_tag_actor(self) -> None:
        contract = _load_contract()
        manifests = copy.deepcopy(_manifests(contract))
        manifests["release-tags"]["tag_protection"]["authorized_actors"] = {
            "status": "verified",
            "actors": [{"actor_type": "Team", "actor_id": "not-an-api-id"}],
            "source": "D3 and D6 approved GitHub API actor readback",
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
