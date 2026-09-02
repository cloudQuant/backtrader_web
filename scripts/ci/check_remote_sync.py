#!/usr/bin/env python3
"""Compare GitHub-authoritative refs with a read-only mirror."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REF_PREFIX = "refs/heads/"
APPROVED_BRANCH = "master"
APPROVED_SOURCE_SHA = "605d4d0e1cf1ad6627483aab6c4cef2a742b3d0f"
APPROVED_MIRROR_SHA = "3d05130635f50c45adeaa4514af246380ff00451"
APPROVED_INCIDENT = ".github/governance/decisions/remote-sync-incident.md"
APPROVED_OWNER = "@cloudQuant"
MAX_EXCEPTION_EXPIRY = datetime(2026, 9, 30, tzinfo=timezone.utc)


class RemoteSyncError(ValueError):
    """Raised when remote evidence or its approved exception file is invalid."""


RunCommand = Callable[..., subprocess.CompletedProcess[str]]


def parse_ls_remote_heads(output: str) -> dict[str, str]:
    """Parse the exact head-ref rows emitted by ``git ls-remote --heads``."""
    heads: dict[str, str] = {}
    for line in output.splitlines():
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) != 2 or not SHA_RE.fullmatch(parts[0]) or not parts[1].startswith(REF_PREFIX):
            raise RemoteSyncError(f"malformed git ls-remote --heads output: {line!r}")
        branch = parts[1][len(REF_PREFIX) :]
        if not branch or branch in heads:
            raise RemoteSyncError(f"malformed git ls-remote --heads ref: {parts[1]!r}")
        heads[branch] = parts[0]
    return heads


def _read_remote_heads(remote: str, run: RunCommand) -> dict[str, str]:
    command = ["git", "ls-remote", "--heads", remote]
    completed = run(command, check=False, capture_output=True, text=True, timeout=60)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "no stderr"
        raise RemoteSyncError(f"git ls-remote --heads failed for {remote}: {detail}")
    return parse_ls_remote_heads(completed.stdout)


def _parse_timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise RemoteSyncError(f"exception {field} must be an RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise RemoteSyncError(f"exception {field} is not a valid timestamp") from error
    if parsed.tzinfo is None:
        raise RemoteSyncError(f"exception {field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def load_exceptions(path: Path | None, *, now: datetime | None = None) -> list[dict[str, str]]:
    """Load the single D1-approved exception without widening its scope."""
    if path is None:
        return []
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise RemoteSyncError(f"cannot read exceptions file {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise RemoteSyncError(f"exceptions file {path} is not valid JSON") from error
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise RemoteSyncError("exceptions file must be a version 1 JSON object")
    entries = payload.get("exceptions")
    if not isinstance(entries, list):
        raise RemoteSyncError("exceptions file must contain an exceptions list")

    required = {
        "branch",
        "source_sha",
        "mirror_sha",
        "issue",
        "owner",
        "reason",
        "created_at",
        "expires_at",
    }
    checked_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    validated: list[dict[str, str]] = []
    for entry in entries:
        if not isinstance(entry, dict) or not required.issubset(entry):
            raise RemoteSyncError(
                "each exception must include branch, SHAs, issue, owner, reason, and dates"
            )
        normalized = {key: entry[key] for key in required}
        if not all(isinstance(value, str) and value.strip() for value in normalized.values()):
            raise RemoteSyncError("exception fields must be non-empty strings")
        if not SHA_RE.fullmatch(normalized["source_sha"]) or not SHA_RE.fullmatch(
            normalized["mirror_sha"]
        ):
            raise RemoteSyncError("exception SHAs must be complete 40-character lowercase SHAs")
        if normalized["branch"] != APPROVED_BRANCH:
            raise RemoteSyncError("only the approved master branch may be excepted")
        if normalized["source_sha"] != APPROVED_SOURCE_SHA:
            raise RemoteSyncError("exception source SHA must equal the approved source SHA")
        if normalized["mirror_sha"] != APPROVED_MIRROR_SHA:
            raise RemoteSyncError("exception mirror SHA must equal the approved mirror SHA")
        if normalized["issue"] != APPROVED_INCIDENT:
            raise RemoteSyncError("exception issue must cite the approved local incident")
        if normalized["owner"] != APPROVED_OWNER:
            raise RemoteSyncError("exception owner must be @cloudQuant")
        created = _parse_timestamp(normalized["created_at"], "created_at")
        expires = _parse_timestamp(normalized["expires_at"], "expires_at")
        if expires <= created:
            raise RemoteSyncError("exception expires_at must be after created_at")
        if created > checked_at:
            raise RemoteSyncError("exception created_at must not be in the future")
        if expires > MAX_EXCEPTION_EXPIRY:
            raise RemoteSyncError("exception expires_at must not exceed 2026-09-30T00:00:00Z")
        validated.append(normalized)
    return validated


def _matching_exception(
    exceptions: Sequence[dict[str, str]],
    branch: str,
    source_sha: str | None,
    mirror_sha: str | None,
) -> dict[str, str] | None:
    return next(
        (
            entry
            for entry in exceptions
            if entry["branch"] == branch
            and entry["source_sha"] == source_sha
            and entry["mirror_sha"] == mirror_sha
        ),
        None,
    )


def check_remote_sync(
    *,
    source: str,
    mirror: str,
    branches: Sequence[str],
    exceptions_path: Path | None = None,
    now: datetime | None = None,
    run: RunCommand = subprocess.run,
) -> dict[str, object]:
    """Compare requested branch heads without changing either remote."""
    if not branches or any(not branch or branch.startswith("-") for branch in branches):
        raise RemoteSyncError("at least one non-option branch name is required")
    source_heads = _read_remote_heads(source, run)
    mirror_heads = _read_remote_heads(mirror, run)
    checked_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    exceptions = load_exceptions(exceptions_path, now=checked_at)
    warnings: list[str] = []
    mismatches: list[dict[str, str | None]] = []

    for branch in branches:
        source_sha = source_heads.get(branch)
        mirror_sha = mirror_heads.get(branch)
        if source_sha == mirror_sha and source_sha is not None:
            continue
        exception = _matching_exception(exceptions, branch, source_sha, mirror_sha)
        if exception is not None and checked_at < _parse_timestamp(
            exception["expires_at"], "expires_at"
        ):
            warnings.append(
                "approved temporary divergence "
                f"branch={branch} issue={exception['issue']} owner={exception['owner']} "
                f"expires_at={exception['expires_at']}"
            )
            continue
        status = "expired_exception" if exception is not None else "failed"
        mismatches.append(
            {
                "branch": branch,
                "source_sha": source_sha,
                "mirror_sha": mirror_sha,
                "status": status,
            }
        )

    return {
        "ok": not mismatches,
        "checked_at": checked_at.isoformat().replace("+00:00", "Z"),
        "source": source,
        "mirror": mirror,
        "branches": list(branches),
        "warnings": warnings,
        "mismatches": mismatches,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="authoritative GitHub remote URL")
    parser.add_argument("--mirror", required=True, help="read-only mirror remote URL")
    parser.add_argument("--branches", nargs="+", required=True, help="branch names to compare")
    parser.add_argument("--exceptions", type=Path, help="temporary exact-SHA exception JSON")
    parser.add_argument("--output", type=Path, help="write machine-readable JSON evidence here")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = check_remote_sync(
            source=args.source,
            mirror=args.mirror,
            branches=args.branches,
            exceptions_path=args.exceptions,
        )
    except RemoteSyncError as error:
        print(f"REMOTE_SYNC_ERROR: {error}")
        return 2
    evidence = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.write_text(evidence, encoding="utf-8")
    else:
        print(evidence, end="")
    for warning in result["warnings"]:
        print(f"REMOTE_SYNC_WARNING: {warning}")
    for mismatch in result["mismatches"]:
        print(
            "REMOTE_SYNC_MISMATCH: "
            f"branch={mismatch['branch']} source={mismatch['source_sha']} "
            f"mirror={mismatch['mirror_sha']} status={mismatch['status']}"
        )
    if result["ok"]:
        print("REMOTE_SYNC_SUMMARY: requested branch heads are equal or temporarily excepted")
        return 0
    print("REMOTE_SYNC_SUMMARY: unresolved mirror drift requires human review")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
