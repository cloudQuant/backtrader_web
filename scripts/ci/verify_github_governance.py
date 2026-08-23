#!/usr/bin/env python3
"""Read-only verifier for Iteration 195 GitHub Ruleset desired state.

The script only calls ``gh api`` GET endpoints when ``--live`` is selected.
It never creates, updates, deletes, or applies a GitHub Ruleset.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from governance_contract import (
    load_manifests,
    normalize_bypass_actors,
    normalize_required_check_contexts,
    normalized_manifest,
    validate_manifests,
)


Runner = Callable[[list[str]], str]


def _rule_by_type(rules: Any, rule_type: str) -> Mapping[str, Any]:
    if not isinstance(rules, list):
        return {}
    for rule in rules:
        if isinstance(rule, Mapping) and rule.get("type") == rule_type:
            return rule
    return {}


def _rule_parameters(rules: Any, rule_type: str) -> Mapping[str, Any]:
    rule = _rule_by_type(rules, rule_type)
    parameters = rule.get("parameters", {})
    return parameters if isinstance(parameters, Mapping) else {}


def _has_rule(rules: Any, rule_type: str) -> bool:
    return bool(_rule_by_type(rules, rule_type))


def normalize_github_ruleset(raw_ruleset: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize API readback, intentionally ignoring IDs, timestamps, and order."""
    conditions = raw_ruleset.get("conditions", {})
    ref_name = conditions.get("ref_name", {}) if isinstance(conditions, Mapping) else {}
    include = ref_name.get("include", []) if isinstance(ref_name, Mapping) else []
    exclude = ref_name.get("exclude", []) if isinstance(ref_name, Mapping) else []
    rules = raw_ruleset.get("rules", [])
    target = raw_ruleset.get("target")
    raw_bypass_actors = raw_ruleset.get("bypass_actors")
    canonical: dict[str, Any] = {
        "name": raw_ruleset.get("name"),
        "target": {
            "kind": target,
            "include": sorted(include) if isinstance(include, list) else [],
            "exclude": sorted(exclude) if isinstance(exclude, list) else [],
        },
        "enforcement": raw_ruleset.get("enforcement"),
        "bypass_actors": (
            normalize_bypass_actors(raw_bypass_actors)
            if isinstance(raw_bypass_actors, list)
            else None
        ),
    }
    if target == "branch":
        pull_request = _rule_parameters(rules, "pull_request")
        status_checks = _rule_parameters(rules, "required_status_checks")
        raw_contexts = status_checks.get("required_status_checks", [])
        contexts = normalize_required_check_contexts(raw_contexts)
        canonical.update(
            {
                "pull_request": {
                    "required": _has_rule(rules, "pull_request"),
                    "required_approvals": pull_request.get(
                        "required_approving_review_count"
                    ),
                    "code_owner_review_enabled": pull_request.get(
                        "require_code_owner_review"
                    ),
                    "conversation_resolution": pull_request.get(
                        "required_review_thread_resolution"
                    ),
                },
                "protection": {
                    "block_force_push": _has_rule(rules, "non_fast_forward"),
                    "block_deletion": _has_rule(rules, "deletion"),
                },
                "required_checks": {
                    "contexts": contexts,
                    "strict": status_checks.get("strict_required_status_checks_policy"),
                    "do_not_enforce_on_create": status_checks.get(
                        "do_not_enforce_on_create"
                    ),
                },
            }
        )
    elif target == "tag":
        canonical["tag_protection"] = {
            "block_creation": _has_rule(rules, "creation"),
            "block_update": _has_rule(rules, "update"),
            "block_deletion": _has_rule(rules, "deletion"),
        }
    return canonical


def _diff(expected: Any, actual: Any, path: str) -> list[str]:
    if isinstance(expected, Mapping) and isinstance(actual, Mapping):
        differences: list[str] = []
        for key in sorted(set(expected) | set(actual)):
            child_path = f"{path}.{key}" if path else str(key)
            if key not in expected:
                differences.append(
                    f"{child_path}: unexpected actual value {actual[key]!r}"
                )
            elif key not in actual:
                differences.append(
                    f"{child_path}: missing actual value; expected {expected[key]!r}"
                )
            else:
                differences.extend(_diff(expected[key], actual[key], child_path))
        return differences
    if isinstance(expected, list) and isinstance(actual, list):
        differences = []
        for index in range(max(len(expected), len(actual))):
            child_path = f"{path}[{index}]"
            if index >= len(expected):
                differences.append(
                    f"{child_path}: unexpected actual value {actual[index]!r}"
                )
            elif index >= len(actual):
                differences.append(
                    f"{child_path}: missing actual value; expected {expected[index]!r}"
                )
            else:
                differences.extend(_diff(expected[index], actual[index], child_path))
        return differences
    if expected != actual:
        return [f"{path}: expected {expected!r}, actual {actual!r}"]
    return []


def verify_rulesets(
    manifest_dir: Path | str, actual_rulesets: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Compare manifest desired state to a Rulesets API readback or fixture."""
    manifests = load_manifests(manifest_dir)
    differences = validate_manifests(manifests)
    expected_by_name = {
        manifest["name"]: (key, normalized_manifest(manifest))
        for key, manifest in manifests.items()
    }
    actual_by_name: dict[str, list[dict[str, Any]]] = {}
    for ruleset in actual_rulesets:
        if not isinstance(ruleset, Mapping):
            continue
        name = str(ruleset.get("name"))
        actual_by_name.setdefault(name, []).append(normalize_github_ruleset(ruleset))

    for name, matching_rulesets in sorted(actual_by_name.items()):
        if len(matching_rulesets) > 1:
            differences.append(
                f"duplicate actual Ruleset named {name!r}: found {len(matching_rulesets)}"
            )
    for name, (key, expected) in sorted(expected_by_name.items()):
        matching_rulesets = actual_by_name.get(name)
        if matching_rulesets is None:
            differences.append(f"{key}: missing actual Ruleset named {name!r}")
            continue
        actual = matching_rulesets[0]
        if actual.get("bypass_actors") is None:
            differences.append(
                f"{key}.bypass_actors: unavailable in API readback; cannot verify an explicit empty bypass pool"
            )
            expected = {
                name: value
                for name, value in expected.items()
                if name != "bypass_actors"
            }
            actual = {
                name: value for name, value in actual.items() if name != "bypass_actors"
            }
        differences.extend(_diff(expected, actual, key))
    managed_names = set(expected_by_name)
    for name in sorted(set(actual_by_name) - managed_names):
        differences.append(f"unexpected actual Ruleset: {name!r}")
    return {"ok": not differences, "differences": differences}


def load_fixture(path: Path | str) -> list[dict[str, Any]]:
    """Load a saved, sanitized Rulesets API response."""
    with Path(path).open(encoding="utf-8") as handle:
        payload = json.load(handle)
    rulesets = payload.get("rulesets") if isinstance(payload, Mapping) else payload
    if not isinstance(rulesets, list) or not all(
        isinstance(item, dict) for item in rulesets
    ):
        raise ValueError("fixture must contain a rulesets array")
    return rulesets


def _run_gh(command: list[str]) -> str:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "gh api read failed")
    return completed.stdout


def _flatten_pages(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise ValueError("GitHub Rulesets API list response must be an array")
    if payload and all(isinstance(page, list) for page in payload):
        return [item for page in payload for item in page if isinstance(item, dict)]
    return [item for item in payload if isinstance(item, dict)]


def load_live_rulesets(
    repo: str, *, runner: Runner | None = None
) -> list[dict[str, Any]]:
    """Read each Ruleset detail with GitHub CLI GET requests only."""
    execute = runner or _run_gh
    listing = json.loads(
        execute(
            [
                "gh",
                "api",
                "--method",
                "GET",
                "--paginate",
                "--slurp",
                f"repos/{repo}/rulesets",
            ]
        )
    )
    summaries = _flatten_pages(listing)
    details: list[dict[str, Any]] = []
    for summary in summaries:
        ruleset_id = summary.get("id")
        if not isinstance(ruleset_id, int):
            raise ValueError("GitHub Rulesets API list response contains an invalid id")
        detail = json.loads(
            execute(
                ["gh", "api", "--method", "GET", f"repos/{repo}/rulesets/{ruleset_id}"]
            )
        )
        if not isinstance(detail, dict):
            raise ValueError(
                f"GitHub Ruleset {ruleset_id} detail response must be an object"
            )
        details.append(detail)
    return details


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--fixture", type=Path, help="sanitized local Rulesets API fixture"
    )
    source.add_argument(
        "--live", action="store_true", help="read Rulesets with gh api GET requests"
    )
    parser.add_argument(
        "--repo",
        default="cloudQuant/backtrader_web",
        help="owner/repository for --live",
    )
    parser.add_argument(
        "--manifest-dir",
        type=Path,
        required=True,
        help="normalized desired-state manifests",
    )
    parser.add_argument(
        "--json", action="store_true", help="print only the machine-readable report"
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        rulesets = (
            load_fixture(args.fixture)
            if args.fixture
            else load_live_rulesets(args.repo)
        )
        report = verify_rulesets(args.manifest_dir, rulesets)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        report = {"ok": False, "differences": [f"verifier error: {error}"]}

    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        status = "OK" if report["ok"] else "DRIFT"
        print(f"GitHub Ruleset desired-state verification: {status}")
        for difference in report["differences"]:
            print(f"  - {difference}")
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
