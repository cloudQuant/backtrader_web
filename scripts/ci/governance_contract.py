#!/usr/bin/env python3
"""Pure policy helpers for the Iteration 195 PR governance contract.

This module deliberately contains no GitHub write operation.  It is shared by
the read-only Ruleset verifier and the later PR Governance gate.
"""

from __future__ import annotations

import fnmatch
import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


RISK_ORDER = {"R0": 0, "R1": 1, "R2": 2, "R3": 3}
REQUIRED_MANIFESTS = {
    "dev": {
        "name": "Iteration 195: dev",
        "target_kind": "branch",
        "target_include": ["refs/heads/dev"],
        "target_exclude": [],
        "required_approvals": 1,
        "activation_gate": "D3",
        "actor_source_tokens": ("GitHub API readback", "D3"),
    },
    "master": {
        "name": "Iteration 195: master",
        "target_kind": "branch",
        "target_include": ["refs/heads/master"],
        "target_exclude": [],
        "required_approvals": 2,
        "activation_gate": "D3",
        "actor_source_tokens": ("GitHub API readback", "D3"),
    },
    "release-tags": {
        "name": "Iteration 195: release tags",
        "target_kind": "tag",
        "target_include": ["refs/tags/v*"],
        "target_exclude": [],
        "activation_gate": "D3_D6",
        "actor_source_tokens": ("GitHub API readback", "D3", "D6"),
    },
}
VALID_BYPASS_ACTOR_TYPES = {
    "Integration",
    "OrganizationAdmin",
    "RepositoryRole",
    "Team",
    "DeployKey",
    "User",
}
POSITIVE_ID_BYPASS_ACTOR_TYPES = {
    "Integration",
    "RepositoryRole",
    "Team",
    "User",
}
GITHUB_BYPASS_MODES = {"always", "pull_request", "exempt"}
ALLOWED_BYPASS_MODES = {"always", "pull_request"}
EVIDENCE_PATH_PREFIXES = ("docs/", ".github/", "artifacts/")
RELEASE_BRANCH = re.compile(r"^release/v\d+\.\d+\.\d+(?:-rc\d+)?$")
HOTFIX_BRANCH = re.compile(r"^hotfix/master-[A-Za-z0-9][A-Za-z0-9._-]*$")
DEV_BRANCH_PREFIXES = ("feature/", "fix/", "docs/", "refactor/", "test/")


def load_risk_map(path: Path | str) -> dict[str, Any]:
    """Load the single source of truth for path risk classification."""
    with Path(path).open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("risk map must be a JSON object")
    return value


def _glob_matches(path: str, pattern: str) -> bool:
    """Match repository-relative paths using CODEOWNERS-style glob intent."""
    normalized_path = path.lstrip("/")
    normalized_pattern = pattern.lstrip("/")
    return fnmatch.fnmatchcase(normalized_path, normalized_pattern)


def _risk_rank(level: str) -> int:
    if level not in RISK_ORDER:
        raise ValueError(f"unknown risk level: {level!r}")
    return RISK_ORDER[level]


def classify_paths(
    changed_files: Sequence[str],
    risk_map: Mapping[str, Any],
    *,
    labels: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Classify paths and always retain the highest matched risk level.

    Labels are included in the result only as ignored metadata. They can
    request more review in a human process, but cannot lower path-derived risk.
    """
    default = risk_map.get("default", {})
    default_level = default.get("level", "R1") if isinstance(default, Mapping) else "R1"
    _risk_rank(str(default_level))

    rules = risk_map.get("rules", [])
    if not isinstance(rules, list):
        raise ValueError("risk map rules must be a list")

    matches: list[dict[str, str]] = []
    highest: str | None = None
    for path in changed_files:
        if not isinstance(path, str) or not path:
            raise ValueError("changed files must be non-empty strings")
        for rule in rules:
            if not isinstance(rule, Mapping):
                raise ValueError("risk map rule must be an object")
            level = str(rule.get("level", ""))
            patterns = rule.get("globs", [])
            if not isinstance(patterns, list):
                rule_id = rule.get("id", "<unknown>")
                raise ValueError(f"risk map rule {rule_id} globs must be a list")
            for pattern in patterns:
                if isinstance(pattern, str) and _glob_matches(path, pattern):
                    matches.append(
                        {
                            "path": path,
                            "rule_id": str(rule.get("id", "<unnamed>")),
                            "level": level,
                            "glob": pattern,
                        }
                    )
                    if highest is None or _risk_rank(level) > _risk_rank(highest):
                        highest = level

    selection = risk_map.get("selection", {})
    can_lower = (
        bool(selection.get("labels_can_lower_risk", False))
        if isinstance(selection, Mapping)
        else False
    )
    return {
        "risk": highest or str(default_level),
        "matches": matches,
        "label_can_lower_risk": can_lower,
        "ignored_labels": sorted(set(labels or [])),
    }


def _has_value(evidence: Mapping[str, Any], key: str) -> bool:
    value = evidence.get(key)
    return value is True or (isinstance(value, str) and bool(value.strip()))


def validate_branch_contract(
    base_branch: str, head_branch: str, evidence: Mapping[str, Any]
) -> list[str]:
    """Return contributor-actionable routing and evidence issues for a PR."""
    issues: list[str] = []
    if base_branch == "master":
        if RELEASE_BRANCH.fullmatch(head_branch):
            if not _has_value(evidence, "release_checklist"):
                issues.append(
                    "release/vX.Y.Z -> master requires a completed release checklist"
                )
            if not _has_value(evidence, "release_validation"):
                issues.append(
                    "release/vX.Y.Z -> master requires release validation evidence"
                )
        elif HOTFIX_BRANCH.fullmatch(head_branch):
            if not _has_value(evidence, "incident"):
                issues.append(
                    "hotfix/master-* -> master requires an incident or private disclosure record"
                )
            if not _has_value(evidence, "forward_port_plan"):
                issues.append(
                    "hotfix/master-* -> master requires a forward-port plan for dev"
                )
        else:
            issues.append(
                "master only accepts release/vX.Y.Z or hotfix/master-* branches"
            )
    elif base_branch == "dev":
        if not head_branch.startswith(DEV_BRANCH_PREFIXES):
            issues.append(
                "dev accepts feature/*, fix/*, docs/*, refactor/*, or test/* branches"
            )
    else:
        issues.append(f"unsupported target branch: {base_branch}")
    return issues


def load_manifests(manifest_dir: Path | str) -> dict[str, dict[str, Any]]:
    """Load the three normalized Ruleset desired-state files."""
    directory = Path(manifest_dir)
    manifests: dict[str, dict[str, Any]] = {}
    for key in REQUIRED_MANIFESTS:
        path = directory / f"{key}.json"
        if not path.is_file():
            continue
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            raise ValueError(f"manifest {path} must be a JSON object")
        manifests[key] = value
    return manifests


def _issue(path: str, message: str) -> str:
    return f"{path}: {message}"


def _is_positive_actor_id(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _gate_tokens(expected: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(str(expected["activation_gate"]).split("_"))


def _is_evidence_reference(value: str) -> bool:
    if value.startswith("https://"):
        return len(value) > len("https://")
    normalized = value.replace("\\", "/")
    return (
        normalized.startswith(EVIDENCE_PATH_PREFIXES)
        and "/../" not in f"/{normalized}/"
        and not normalized.endswith("/..")
    )


def _validate_gate_evidence(
    evidence: Any, path: str, required_gates: Sequence[str]
) -> list[str]:
    if not isinstance(evidence, Mapping):
        return [
            _issue(
                path,
                "must be an evidence object with gates and a local path or HTTPS URL",
            )
        ]

    issues: list[str] = []
    gates = evidence.get("gates")
    if (
        not isinstance(gates, list)
        or not all(isinstance(gate, str) for gate in gates)
        or set(gates) != set(required_gates)
        or len(gates) != len(set(gates))
    ):
        gate_text = ", ".join(required_gates)
        issues.append(_issue(f"{path}.gates", f"must cite exactly {gate_text}"))

    reference = evidence.get("reference")
    if not isinstance(reference, str) or not _is_evidence_reference(reference):
        issues.append(
            _issue(
                f"{path}.reference",
                "must be a repository-local evidence path or HTTPS URL",
            )
        )
    return issues


def _parse_utc_timestamp(value: Any) -> datetime | None:
    """Return a timezone-aware timestamp as UTC, or ``None`` when malformed."""
    if not isinstance(value, str) or not value.strip():
        return None
    timestamp = value.strip()
    if timestamp.endswith("Z"):
        timestamp = f"{timestamp[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _validate_bypass_actor(
    actor: Any, actor_path: str, *, target_kind: str
) -> list[str]:
    if not isinstance(actor, Mapping):
        return [_issue(actor_path, "must be an object from API readback")]

    issues: list[str] = []
    actor_type = actor.get("actor_type")
    if actor_type not in VALID_BYPASS_ACTOR_TYPES:
        issues.append(
            _issue(
                f"{actor_path}.actor_type",
                "is not a valid GitHub bypass actor type",
            )
        )

    actor_id = actor.get("actor_id")
    if actor_type in POSITIVE_ID_BYPASS_ACTOR_TYPES:
        if not _is_positive_actor_id(actor_id):
            issues.append(
                _issue(
                    f"{actor_path}.actor_id",
                    "must be a positive API-readback integer for this actor type",
                )
            )
    elif actor_type == "OrganizationAdmin":
        if actor_id is not None and not _is_positive_actor_id(actor_id):
            issues.append(
                _issue(
                    f"{actor_path}.actor_id",
                    "must be null or a positive integer; OrganizationAdmin IDs are ignored",
                )
            )
    elif actor_type == "DeployKey" and actor_id is not None:
        issues.append(
            _issue(
                f"{actor_path}.actor_id",
                "must be null for DeployKey",
            )
        )

    bypass_mode = actor.get("bypass_mode")
    if bypass_mode not in GITHUB_BYPASS_MODES:
        modes = ", ".join(sorted(GITHUB_BYPASS_MODES))
        issues.append(
            _issue(
                f"{actor_path}.bypass_mode",
                f"must be one of {modes}",
            )
        )
    elif bypass_mode not in ALLOWED_BYPASS_MODES:
        issues.append(
            _issue(
                f"{actor_path}.bypass_mode",
                "'exempt' is prohibited by the incident/reason/24-hour-postmortem emergency policy",
            )
        )
    elif bypass_mode == "pull_request" and target_kind != "branch":
        issues.append(
            _issue(
                f"{actor_path}.bypass_mode",
                "is valid only for branch Rulesets",
            )
        )
    elif bypass_mode == "pull_request" and actor_type == "DeployKey":
        issues.append(
            _issue(
                f"{actor_path}.bypass_mode",
                "is not valid for DeployKey",
            )
        )
    return issues


def _validate_bypass(
    key: str,
    bypass: Any,
    expected: Mapping[str, Any],
    *,
    now: datetime,
) -> list[str]:
    if not isinstance(bypass, Mapping):
        return [_issue(f"{key}.bypass", "must be an object")]

    issues: list[str] = []
    if bypass.get("normal_policy") != "none":
        issues.append(_issue(f"{key}.bypass.normal_policy", "must be 'none'"))

    actor_source = bypass.get("actor_source")
    expected_tokens = expected["actor_source_tokens"]
    if not isinstance(actor_source, str) or not actor_source.strip():
        issues.append(
            _issue(
                f"{key}.bypass.actor_source",
                "must cite future GitHub API readback rather than none or empty text",
            )
        )
    elif any(
        token.casefold() not in actor_source.casefold() for token in expected_tokens
    ):
        token_text = ", ".join(expected_tokens)
        issues.append(
            _issue(
                f"{key}.bypass.actor_source",
                f"must cite {token_text} while actors remain unverified",
            )
        )

    emergency = bypass.get("emergency_policy")
    emergency_window_hours = 24
    if not isinstance(emergency, Mapping):
        issues.append(_issue(f"{key}.bypass.emergency_policy", "must be an object"))
    elif (
        emergency.get("incident_required") is not True
        or emergency.get("reason_required") is not True
        or emergency.get("postmortem_within_hours") != 24
    ):
        issues.append(
            _issue(
                f"{key}.bypass.emergency_policy",
                "must require incident, reason, and a 24-hour postmortem",
            )
        )
    else:
        emergency_window_hours = emergency["postmortem_within_hours"]

    actors = bypass.get("actors")
    if not isinstance(actors, list):
        return issues + [_issue(f"{key}.bypass.actors", "must be a list")]
    for index, actor in enumerate(actors):
        issues.extend(
            _validate_bypass_actor(
                actor,
                f"{key}.bypass.actors[{index}]",
                target_kind=str(expected["target_kind"]),
            )
        )

    exceptions = bypass.get("emergency_exceptions")
    exception_path = f"{key}.bypass.emergency_exceptions"
    if not isinstance(exceptions, list):
        issues.append(_issue(exception_path, "must be a list"))
        return issues

    exception_actors: list[dict[str, Any]] = []
    for index, exception in enumerate(exceptions):
        individual_path = f"{exception_path}[{index}]"
        if not isinstance(exception, Mapping):
            issues.append(_issue(individual_path, "must be an object"))
            continue
        actor = exception.get("actor")
        issues.extend(
            _validate_bypass_actor(
                actor,
                f"{individual_path}.actor",
                target_kind=str(expected["target_kind"]),
            )
        )
        exception_actors.extend(normalize_bypass_actors([actor]))
        for field in ("incident", "reason"):
            value = exception.get(field)
            if not isinstance(value, str) or not value.strip():
                issues.append(_issue(f"{individual_path}.{field}", "must be non-empty"))
        has_issued_at = "issued_at" in exception
        has_starts_at = "starts_at" in exception
        if has_issued_at and has_starts_at:
            issues.append(
                _issue(
                    f"{individual_path}.issued_at",
                    "must not be combined with starts_at; use one unambiguous start timestamp",
                )
            )
        start_field = "issued_at" if has_issued_at else "starts_at"
        start_at = _parse_utc_timestamp(exception.get(start_field))
        if start_at is None:
            issues.append(
                _issue(
                    f"{individual_path}.{start_field}",
                    "must be a timezone-aware ISO-8601 start timestamp",
                )
            )

        expires_at = _parse_utc_timestamp(exception.get("expires_at"))
        if expires_at is None:
            issues.append(
                _issue(
                    f"{individual_path}.expires_at",
                    "must be a timezone-aware ISO-8601 expiry timestamp",
                )
            )
        else:
            if expires_at <= now:
                issues.append(
                    _issue(
                        f"{individual_path}.expires_at",
                        "must be later than the validation time",
                    )
                )
            if start_at is not None:
                if expires_at <= start_at:
                    issues.append(
                        _issue(
                            f"{individual_path}.expires_at",
                            "must be later than issued_at or starts_at",
                        )
                    )
                elif expires_at > start_at + timedelta(hours=emergency_window_hours):
                    issues.append(
                        _issue(
                            f"{individual_path}.expires_at",
                            "must be within the emergency policy's 24-hour window",
                        )
                    )
        issues.extend(
            _validate_gate_evidence(
                exception.get("readback_evidence"),
                f"{individual_path}.readback_evidence",
                _gate_tokens(expected),
            )
        )

    normalized_actors = normalize_bypass_actors(actors)
    if normalized_actors != normalize_bypass_actors(exception_actors):
        issues.append(
            _issue(
                exception_path,
                "must provide one auditable emergency exception for every bypass actor",
            )
        )
    return issues


def _validate_required_checks(key: str, required_checks: Any) -> list[str]:
    if not isinstance(required_checks, Mapping):
        return [_issue(f"{key}.required_checks", "must be an object")]

    status = required_checks.get("status")
    contexts = required_checks.get("contexts")
    source = required_checks.get("source")
    issues: list[str] = []
    if not isinstance(contexts, list):
        issues.append(
            _issue(
                f"{key}.required_checks.contexts",
                "must be a list of check context/integration identities",
            )
        )
        return issues
    if not isinstance(source, str) or not source.strip():
        issues.append(
            _issue(f"{key}.required_checks.source", "must record the evidence source")
        )
    if required_checks.get("strict") is not True:
        issues.append(_issue(f"{key}.required_checks.strict", "must be true"))
    if required_checks.get("do_not_enforce_on_create") is not False:
        issues.append(
            _issue(
                f"{key}.required_checks.do_not_enforce_on_create",
                "must be false",
            )
        )
    if status == "pending_D4":
        if contexts:
            issues.append(
                _issue(
                    f"{key}.required_checks.contexts",
                    "must stay empty while D4 is pending",
                )
            )
    elif status == "verified":
        if not contexts:
            issues.append(
                _issue(
                    f"{key}.required_checks.contexts",
                    "must list confirmed check contexts when status is verified",
                )
            )
        else:
            identities: list[tuple[str, int]] = []
            for index, context_entry in enumerate(contexts):
                context_path = f"{key}.required_checks.contexts[{index}]"
                if not isinstance(context_entry, Mapping):
                    issues.append(
                        _issue(
                            context_path,
                            "must be an object with context and integration_id",
                        )
                    )
                    continue
                context = context_entry.get("context")
                if not isinstance(context, str) or not context.strip():
                    issues.append(
                        _issue(
                            f"{context_path}.context",
                            "must be a non-empty verified check context",
                        )
                    )
                    continue
                integration_id = context_entry.get("integration_id")
                if not _is_positive_actor_id(integration_id):
                    issues.append(
                        _issue(
                            f"{context_path}.integration_id",
                            "must be a positive Check Run integration ID",
                        )
                    )
                    continue
                identities.append((context, integration_id))
            if len(identities) != len(set(identities)):
                issues.append(
                    _issue(
                        f"{key}.required_checks.contexts",
                        "must not contain duplicate context/integration identities",
                    )
                )
        issues.extend(
            _validate_gate_evidence(
                required_checks.get("evidence"),
                f"{key}.required_checks.evidence",
                ("D4",),
            )
        )
    else:
        issues.append(
            _issue(
                f"{key}.required_checks.status",
                "must be pending_D4 or verified",
            )
        )
    return issues


def _validate_activation(
    key: str, activation: Any, expected: Mapping[str, Any]
) -> list[str]:
    """Validate current and evidenced-future Ruleset activation states."""
    if not isinstance(activation, Mapping):
        return [_issue(f"{key}.activation", "must be an object")]

    issues: list[str] = []
    remote_state = activation.get("remote_state")
    if remote_state not in {"not_applied", "applied"}:
        issues.append(
            _issue(
                f"{key}.activation.remote_state",
                "must be not_applied or applied",
            )
        )
    if activation.get("gate") != expected["activation_gate"]:
        issues.append(
            _issue(
                f"{key}.activation.gate",
                f"must be {expected['activation_gate']!r} for the current gate state",
            )
        )
    reason = activation.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        issues.append(
            _issue(
                f"{key}.activation.reason",
                "must record the activation rationale",
            )
        )
    if remote_state == "applied":
        issues.extend(
            _validate_gate_evidence(
                activation.get("readback_evidence"),
                f"{key}.activation.readback_evidence",
                _gate_tokens(expected),
            )
        )
    return issues


def _validate_branch_manifest(
    key: str, manifest: Mapping[str, Any], expected: Mapping[str, Any]
) -> list[str]:
    issues: list[str] = []
    pull_request = manifest.get("pull_request")
    if not isinstance(pull_request, Mapping):
        return [_issue(f"{key}.pull_request", "must be an object")]
    if pull_request.get("required") is not True:
        issues.append(_issue(f"{key}.pull_request.required", "must be true"))
    if pull_request.get("required_approvals") != expected["required_approvals"]:
        issues.append(
            _issue(
                f"{key}.pull_request.required_approvals",
                f"must be {expected['required_approvals']}",
            )
        )
    if pull_request.get("conversation_resolution") is not True:
        issues.append(
            _issue(f"{key}.pull_request.conversation_resolution", "must be true")
        )

    code_owner = pull_request.get("code_owner_review")
    if not isinstance(code_owner, Mapping):
        issues.append(
            _issue(f"{key}.pull_request.code_owner_review", "must be an object")
        )
    elif code_owner.get("desired_when_d2_ready") is not True:
        issues.append(
            _issue(
                f"{key}.pull_request.code_owner_review",
                "must declare the D2 readiness contract",
            )
        )
    elif code_owner.get("enabled") is False:
        if (
            not isinstance(code_owner.get("reason"), str)
            or not code_owner["reason"].strip()
        ):
            issues.append(
                _issue(
                    f"{key}.pull_request.code_owner_review.reason",
                    "must explain why D2 keeps required code-owner review disabled",
                )
            )
    elif code_owner.get("enabled") is True:
        issues.extend(
            _validate_gate_evidence(
                code_owner.get("evidence"),
                f"{key}.pull_request.code_owner_review.evidence",
                ("D2",),
            )
        )
    else:
        issues.append(
            _issue(
                f"{key}.pull_request.code_owner_review.enabled",
                "must be a boolean",
            )
        )

    protection = manifest.get("protection")
    if not isinstance(protection, Mapping):
        issues.append(_issue(f"{key}.protection", "must be an object"))
    elif (
        protection.get("block_force_push") is not True
        or protection.get("block_deletion") is not True
    ):
        issues.append(
            _issue(f"{key}.protection", "must block force pushes and deletion")
        )

    issues.extend(_validate_required_checks(key, manifest.get("required_checks")))
    return issues


def _validate_tag_manifest(
    key: str, manifest: Mapping[str, Any], expected: Mapping[str, Any]
) -> list[str]:
    tag_protection = manifest.get("tag_protection")
    if not isinstance(tag_protection, Mapping):
        return [_issue(f"{key}.tag_protection", "must be an object")]
    bypass = manifest.get("bypass")
    bypass_actors = bypass.get("actors") if isinstance(bypass, Mapping) else None
    issues: list[str] = []
    for field in ("block_creation", "block_update", "block_deletion"):
        if tag_protection.get(field) is not True:
            issues.append(_issue(f"{key}.tag_protection.{field}", "must be true"))
    authorized = tag_protection.get("authorized_actors")
    if not isinstance(authorized, Mapping):
        issues.append(
            _issue(f"{key}.tag_protection.authorized_actors", "must be an object")
        )
    else:
        status = authorized.get("status")
        actors = authorized.get("actors")
        actor_path = f"{key}.tag_protection.authorized_actors.actors"
        if status == "pending_D3_D6":
            if actors != []:
                issues.append(
                    _issue(
                        actor_path,
                        "must stay empty while D3/D6 actor capability is pending",
                    )
                )
            if bypass_actors != []:
                issues.append(
                    _issue(
                        f"{key}.bypass.actors",
                        "must stay empty while D3/D6 tag actor capability is pending",
                    )
                )
        elif status == "verified":
            if not isinstance(actors, list) or not actors:
                issues.append(
                    _issue(
                        actor_path,
                        "must contain API-readback actors when status is verified",
                    )
                )
            else:
                for index, actor in enumerate(actors):
                    issues.extend(
                        _validate_bypass_actor(
                            actor,
                            f"{actor_path}[{index}]",
                            target_kind="tag",
                        )
                    )
                if normalize_bypass_actors(actors) != normalize_bypass_actors(
                    bypass_actors
                ):
                    issues.append(
                        _issue(
                            actor_path,
                            "must exactly match bypass.actors as the API-readback actor source",
                        )
                    )
        else:
            issues.append(
                _issue(
                    f"{key}.tag_protection.authorized_actors.status",
                    "must be pending_D3_D6 or verified",
                )
            )
    source = authorized.get("source") if isinstance(authorized, Mapping) else None
    if not isinstance(source, str) or not source.strip():
        issues.append(
            _issue(
                f"{key}.tag_protection.authorized_actors.source",
                "must record D3/D6 capability evidence",
            )
        )
    elif "D3" not in source or "D6" not in source:
        issues.append(
            _issue(
                f"{key}.tag_protection.authorized_actors.source",
                "must cite both D3 and D6 capability evidence",
            )
        )
    if isinstance(authorized, Mapping) and authorized.get("status") == "verified":
        issues.extend(
            _validate_gate_evidence(
                authorized.get("evidence"),
                f"{key}.tag_protection.authorized_actors.evidence",
                _gate_tokens(expected),
            )
        )
    return issues


def validate_manifests(
    manifests: Mapping[str, Mapping[str, Any]], *, now: datetime | None = None
) -> list[str]:
    """Validate desired-state manifests before they are compared to GitHub."""
    if now is None:
        validation_now = datetime.now(timezone.utc)
    elif not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("now must be a timezone-aware datetime")
    else:
        validation_now = now.astimezone(timezone.utc)

    issues: list[str] = []
    for key, expected in REQUIRED_MANIFESTS.items():
        manifest = manifests.get(key)
        if manifest is None:
            issues.append(f"missing required manifest: {key}")
            continue
        if manifest.get("schema_version") != 1:
            issues.append(_issue(f"{key}.schema_version", "must be 1"))
        if manifest.get("name") != expected["name"]:
            issues.append(_issue(f"{key}.name", f"must be {expected['name']!r}"))
        target = manifest.get("target")
        if not isinstance(target, Mapping):
            issues.append(_issue(f"{key}.target", "must be an object"))
        else:
            if target.get("kind") != expected["target_kind"]:
                issues.append(
                    _issue(f"{key}.target.kind", f"must be {expected['target_kind']!r}")
                )
            if target.get("include") != expected["target_include"]:
                issues.append(
                    _issue(
                        f"{key}.target.include",
                        f"must be {expected['target_include']!r}",
                    )
                )
            if target.get("exclude") != expected["target_exclude"]:
                issues.append(
                    _issue(
                        f"{key}.target.exclude",
                        f"must be {expected['target_exclude']!r}",
                    )
                )
        if manifest.get("enforcement") != "active":
            issues.append(
                _issue(f"{key}.enforcement", "must be 'active' desired state")
            )
        issues.extend(_validate_activation(key, manifest.get("activation"), expected))
        issues.extend(
            _validate_bypass(
                key,
                manifest.get("bypass"),
                expected,
                now=validation_now,
            )
        )
        if key == "release-tags":
            issues.extend(_validate_tag_manifest(key, manifest, expected))
        else:
            issues.extend(_validate_branch_manifest(key, manifest, expected))
    return issues


def normalize_required_check_contexts(contexts: Any) -> list[dict[str, Any]]:
    """Normalize Check Run identities without dropping their integration source."""
    if not isinstance(contexts, list):
        return []
    canonical: list[dict[str, Any]] = []
    for entry in contexts:
        if isinstance(entry, str):
            canonical.append({"context": entry, "integration_id": None})
        elif isinstance(entry, Mapping):
            canonical.append(
                {
                    "context": entry.get("context"),
                    "integration_id": entry.get("integration_id"),
                }
            )
    return sorted(
        canonical,
        key=lambda entry: (str(entry["context"]), str(entry["integration_id"])),
    )


def normalize_bypass_actors(actors: Any) -> list[dict[str, Any]]:
    """Normalize GitHub bypass actors while retaining enforcement-relevant mode."""
    if not isinstance(actors, list):
        return []
    canonical: list[dict[str, Any]] = []
    for actor in actors:
        if not isinstance(actor, Mapping):
            continue
        actor_type = actor.get("actor_type")
        canonical.append(
            {
                "actor_type": actor_type,
                "actor_id": (
                    None if actor_type == "OrganizationAdmin" else actor.get("actor_id")
                ),
                "bypass_mode": actor.get("bypass_mode"),
            }
        )
    return sorted(
        canonical,
        key=lambda actor: (
            str(actor["actor_type"]),
            str(actor["actor_id"]),
            str(actor["bypass_mode"]),
        ),
    )


def normalized_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Return only the Ruleset fields that GitHub's API can read back."""
    target = manifest.get("target", {})
    bypass = manifest.get("bypass", {})
    target_mapping = target if isinstance(target, Mapping) else {}
    canonical: dict[str, Any] = {
        "name": manifest.get("name"),
        "target": {
            "kind": target_mapping.get("kind"),
            "include": sorted(target_mapping.get("include", [])),
            "exclude": sorted(target_mapping.get("exclude", [])),
        },
        "enforcement": manifest.get("enforcement"),
        "bypass_actors": normalize_bypass_actors(
            bypass.get("actors", []) if isinstance(bypass, Mapping) else []
        ),
    }
    if target_mapping.get("kind") == "branch":
        pull_request = manifest.get("pull_request", {})
        protection = manifest.get("protection", {})
        required_checks = manifest.get("required_checks", {})
        pr_mapping = pull_request if isinstance(pull_request, Mapping) else {}
        protection_mapping = protection if isinstance(protection, Mapping) else {}
        checks_mapping = required_checks if isinstance(required_checks, Mapping) else {}
        code_owner = pr_mapping.get("code_owner_review", {})
        code_owner_mapping = code_owner if isinstance(code_owner, Mapping) else {}
        canonical.update(
            {
                "pull_request": {
                    "required": pr_mapping.get("required"),
                    "required_approvals": pr_mapping.get("required_approvals"),
                    "code_owner_review_enabled": code_owner_mapping.get("enabled"),
                    "conversation_resolution": pr_mapping.get(
                        "conversation_resolution"
                    ),
                },
                "protection": {
                    "block_force_push": protection_mapping.get("block_force_push"),
                    "block_deletion": protection_mapping.get("block_deletion"),
                },
                "required_checks": {
                    "contexts": normalize_required_check_contexts(
                        checks_mapping.get("contexts", [])
                    ),
                    "strict": checks_mapping.get("strict"),
                    "do_not_enforce_on_create": checks_mapping.get(
                        "do_not_enforce_on_create"
                    ),
                },
            }
        )
    else:
        tag_protection = manifest.get("tag_protection", {})
        tag_mapping = tag_protection if isinstance(tag_protection, Mapping) else {}
        canonical["tag_protection"] = {
            "block_creation": tag_mapping.get("block_creation"),
            "block_update": tag_mapping.get("block_update"),
            "block_deletion": tag_mapping.get("block_deletion"),
        }
    return canonical
