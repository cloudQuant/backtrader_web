"""Fail-closed Iteration 197 data-platform acceptance runner.

The runner records one result row for every selected ``case × asset`` slice and
writes a machine-readable ``result.json``.  It deliberately separates a mode
slice from the complete acceptance case: an offline G1 fixture can pass its
local deterministic contract, but cannot claim that the same AC's G2/G3/G4
requirements have been completed.

``offline`` only starts named deterministic pytest nodes in a child Python
process with an in-process socket denial/audit guard.  It never invokes a
provider command.  The other modes require an explicit isolated-environment
approval; ``live`` also requires an approved, scope-bound route manifest.  No
external case driver is registered yet, so an externally approved invocation
remains ``BLOCKED`` instead of becoming a false PASS.

Run from ``src/backend`` using the repository interpreter, for example::

    /Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base \
      python scripts/acceptance/iteration197_data_platform.py \
      --mode offline --case AC-01 --asset-type stock --output /tmp/iter197

A dirty candidate must be covered by ``--dirty-allowlist`` before a non-dry
run can execute.  The result records hashes for the runner, the case map and
backend dependency manifest, but never configuration paths, credentials, or
file contents.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.market_data.scope_manifest import (  # noqa: E402
    ScopeManifestError,
    load_iter196_baseline,
    load_scope_manifest,
    validate_scope_manifest,
)

RESULT_SCHEMA_VERSION = "iteration197-data-platform-acceptance-result-v2"
# This runner intentionally targets the 48-case unified-data-platform matrix.
# It must not be conflated with the separate local-first package whose IDs are
# named ``AC-197-001`` etc.  The namespaced formal ID is stable in artifacts.
ACCEPTANCE_SPEC_ID = "iteration197-unified-data-platform-openbb-matrix-v1"
ACCEPTANCE_SPEC_PATH = (
    "docs/iterations/迭代197-统一数据中台与OpenBB本地优先集成/ACCEPTANCE.md"
)
CASE_MAPPING_VERSION = "iteration197-unified-matrix-id-v1"
ENVIRONMENT_SCHEMA_VERSION = "iteration197-acceptance-environment-v1"
SOURCE_MANIFEST_SCHEMA_VERSION = "iteration197-approved-source-manifest-v2"

MODE_OFFLINE = "offline"
MODE_INTEGRATION = "integration"
MODE_LIVE = "live"
MODE_RECOVERY = "recovery"
MODE_PERFORMANCE = "performance"
VALID_MODES = frozenset(
    {MODE_OFFLINE, MODE_INTEGRATION, MODE_LIVE, MODE_RECOVERY, MODE_PERFORMANCE}
)
GATE_BY_MODE = {
    MODE_OFFLINE: "G1",
    MODE_INTEGRATION: "G2",
    MODE_LIVE: "G3",
    MODE_RECOVERY: "G4",
    MODE_PERFORMANCE: "G4",
}

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_BLOCKED = "BLOCKED"
STATUS_NOT_RUN = "NOT_RUN"
VALID_STATUSES = frozenset({STATUS_PASS, STATUS_FAIL, STATUS_BLOCKED, STATUS_NOT_RUN})

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_BLOCKED = 2
EXIT_INCOMPLETE = 3

ASSET_TYPES = frozenset({"stock", "futures", "bond", "fund", "option", "fx", "crypto"})
_CASE_ID_RE = re.compile(r"^AC-(?:0[1-9]|[1-4][0-9])$")
_FORMAL_CASE_ID_RE = re.compile(r"^AC-197-MATRIX-(?:00[1-9]|0[1-4][0-9])$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_OBJECT_ID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_APPROVAL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,127}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_MAX_MANIFEST_BYTES = 1_048_576
_SENSITIVE_PATH_PART_RE = re.compile(r"(?:^|[._-])(env|secret|credential|token|password|private|key)(?:$|[._-])", re.I)

# The candidate is sealed to this exact single migration tip. The mandatory
# ancestry below gives an actionable failure when a checkout has an incomplete
# or forked chain, while the exact tip prevents an unreviewed successor from
# being counted as Iteration 197 acceptance evidence.
EXPECTED_ALEMBIC_HEAD = "20260910_market_data_capability_ledger"
REQUIRED_ALEMBIC_REVISIONS = frozenset(
    {
        "20260908_ai_research_approval_authority",
        "20260908_market_data_source_governance",
        "20260909_market_data_fetch_leases",
        "20260909_market_data_exact_identity_collation",
        "20260909_market_data_constraint_name_portability",
        "20260909_ai_research_market_data_merge",
        "20260909_market_data_research_bindings",
        "20260909_market_data_research_binding_consumers",
        "20260910_market_data_shared_source_payloads",
        "20260910_market_data_capability_ledger",
    }
)

DEFAULT_SCOPE_MANIFEST_RELATIVE = Path(
    "docs/iterations/迭代197-本地优先市场数据中台/"
    "iteration197-market-data-scope-manifest-20260909.json"
)
DEFAULT_ITER196_BASELINE_RELATIVE = Path(
    "docs/iterations/迭代197-本地优先市场数据中台/"
    "iter196-market-data-baseline-20260909.json"
)
# The Iteration 196 freeze receipt names this merge as the immutable boundary
# that Iteration 197 is allowed to inherit.  Its second parent must therefore
# be the baseline implementation candidate exactly, never merely an ancestor.
ITER196_FREEZE_MERGE_COMMIT = "fec74728ad4469ae6481b134323a6dd7d1401d32"
ITER196_IMPLEMENTATION_CANDIDATE_COMMIT = "3ebe7717a0bfe7ebf1cde2dfc501d6842034c253"
ITER196_ORIGINAL_RECORDED_CANDIDATE_COMMIT = "3ebe7717f6f901932591f59e6f1bb8244827b493"
ITER196_ORIGINAL_FREEZE_RECEIPT_RELATIVE = Path(
    "docs/iterations/迭代196-改进优化ai生成策略流程/CANDIDATE_FREEZE_20260909.md"
)
ITER196_ORIGINAL_FREEZE_RECEIPT_SHA256 = (
    "f47d8ff435a36f53a43049a209c0b614f4bde59f8c50e2dd76d56385e42646d1"
)
ITER196_CORRECTION_RECEIPT_RELATIVE = Path(
    "docs/iterations/迭代196-改进优化ai生成策略流程/CANDIDATE_FREEZE_CORRECTION_20260910.md"
)
_ITER196_CORRECTION_REQUIRED_TOKENS = (
    ITER196_ORIGINAL_RECORDED_CANDIDATE_COMMIT,
    ITER196_IMPLEMENTATION_CANDIDATE_COMMIT,
    ITER196_FREEZE_MERGE_COMMIT,
    ITER196_ORIGINAL_FREEZE_RECEIPT_SHA256,
    f"| 合并提交第二父 | 未单列 | `{ITER196_IMPLEMENTATION_CANDIDATE_COMMIT}` |",
)

# Every offline target is an exact pytest node and explicitly assigned to the
# asset it proves.  Absent mappings are intentionally NOT_RUN rather than
# relabeling a stock fixture as proof for another asset.
_OFFLINE_TESTS_BY_CASE_ASSET: dict[tuple[str, str], tuple[str, ...]] = {
    (
        "AC-01",
        "stock",
    ): (
        "tests/market_data_platform/test_local_first_persistence.py::"
        "test_local_first_persists_once_then_reuses_complete_older_revision_without_network",
    ),
    (
        "AC-01",
        "fund",
    ): (
        "tests/market_data_platform/test_local_first_persistence.py::"
        "test_imported_reference_series_grid_supports_local_first_reread_without_network",
        "tests/market_data_platform/test_local_first_persistence.py::"
        "test_imported_etf_nav_grid_persists_then_rereads_the_source_reported_facts",
    ),
    (
        "AC-09",
        "stock",
    ): (
        "tests/market_data_platform/test_identity.py::"
        "test_resolver_binds_stock_and_futures_to_validated_master_versions",
    ),
    (
        "AC-09",
        "futures",
    ): (
        "tests/market_data_platform/test_identity.py::"
        "test_resolver_binds_stock_and_futures_to_validated_master_versions",
    ),
    (
        "AC-15",
        "stock",
    ): (
        "tests/market_data_platform/test_dataset_contracts.py::"
        "test_registry_declares_all_twenty_one_current_market_page_families",
        "tests/market_data_platform/test_akshare_provider.py::"
        "test_akshare_provider_uses_exact_symbol_route_and_preserves_provenance",
    ),
    (
        "AC-15",
        "fund",
    ): (
        "tests/market_data_platform/test_dataset_contracts.py::"
        "test_registry_declares_all_twenty_one_current_market_page_families",
        "tests/market_data_platform/test_akshare_provider.py::"
        "test_akshare_provider_fetches_exact_etf_nav_reference_series",
        "tests/market_data_platform/test_akshare_provider.py::"
        "test_akshare_provider_rejects_nav_requests_without_an_etf_listing_identity",
    ),
    (
        "AC-15",
        "futures",
    ): (
        "tests/market_data_platform/test_dataset_contracts.py::"
        "test_registry_declares_all_twenty_one_current_market_page_families",
        "tests/market_data_platform/test_akshare_provider.py::"
        "test_akshare_provider_filters_the_known_full_history_route_to_the_window",
    ),
    (
        "AC-15",
        "option",
    ): (
        "tests/market_data_platform/test_dataset_contracts.py::"
        "test_registry_declares_all_twenty_one_current_market_page_families",
        "tests/market_data_platform/test_akshare_provider.py::"
        "test_akshare_provider_selects_cffex_option_history_from_an_exact_contract",
    ),
    (
        "AC-15",
        "fx",
    ): (
        "tests/market_data_platform/test_dataset_contracts.py::"
        "test_registry_declares_all_twenty_one_current_market_page_families",
        "tests/market_data_platform/test_akshare_provider.py::"
        "test_akshare_provider_fetches_the_exact_fx_range_ohlc_shape",
    ),
    (
        "AC-17",
        "stock",
    ): ("tests/market_data_platform/test_source_policy.py::test_openbb_runtime_permit_matrix_is_explicitly_empty",),
    (
        "AC-17",
        "futures",
    ): ("tests/market_data_platform/test_source_policy.py::test_openbb_runtime_permit_matrix_is_explicitly_empty",),
    (
        "AC-17",
        "bond",
    ): ("tests/market_data_platform/test_source_policy.py::test_openbb_runtime_permit_matrix_is_explicitly_empty",),
    (
        "AC-17",
        "fund",
    ): ("tests/market_data_platform/test_source_policy.py::test_openbb_runtime_permit_matrix_is_explicitly_empty",),
    (
        "AC-17",
        "option",
    ): ("tests/market_data_platform/test_source_policy.py::test_openbb_runtime_permit_matrix_is_explicitly_empty",),
    (
        "AC-17",
        "fx",
    ): ("tests/market_data_platform/test_source_policy.py::test_openbb_runtime_permit_matrix_is_explicitly_empty",),
    (
        "AC-17",
        "crypto",
    ): ("tests/market_data_platform/test_source_policy.py::test_openbb_runtime_permit_matrix_is_explicitly_empty",),
    (
        "AC-32",
        "stock",
    ): (
        "tests/market_data_platform/test_legacy_contract.py::"
        "test_legacy_bridge_derives_a_ready_realtime_family_for_an_unbound_stock_request",
    ),
    (
        "AC-32",
        "crypto",
    ): (
        "tests/market_data_platform/test_legacy_contract.py::"
        "test_legacy_bridge_does_not_issue_an_openbb_crypto_contract_without_a_ready_family",
    ),
    (
        "AC-35",
        "stock",
    ): (
        "tests/market_data_platform/test_research_binding.py::"
        "test_runtime_binding_rechecks_owner_signature_subset_and_artifact_digest",
    ),
    (
        "AC-36",
        "stock",
    ): (
        "tests/market_data_platform/test_research_binding.py::"
        "test_runtime_binding_rechecks_current_read_permission_and_source_policy",
    ),
    (
        "AC-39",
        "stock",
    ): (
        "tests/market_data_platform/test_access_authorization.py::"
        "test_local_read_rechecks_current_source_and_entitlement_after_collection",
    ),
}


@dataclass(frozen=True, slots=True)
class AcceptanceCase:
    """One acceptance matrix contract and its required closure gates."""

    case_id: str
    required_gates: frozenset[str]
    modes: frozenset[str]
    asset_types: frozenset[str] = ASSET_TYPES
    required: bool = True

    @property
    def formal_case_id(self) -> str:
        return f"AC-197-MATRIX-{int(self.case_id[3:]):03d}"


@dataclass(frozen=True, slots=True)
class CaseSlice:
    """One selected acceptance contract, asset and current mode gate."""

    case: AcceptanceCase
    asset_type: str
    mode: str

    @property
    def case_key(self) -> str:
        return f"{self.case.case_id}:{self.asset_type}:{GATE_BY_MODE[self.mode]}"


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Non-sensitive result from a child command."""

    returncode: int | None
    elapsed_ms: int


@dataclass(frozen=True, slots=True)
class ScopeFamily:
    """A public, validated scope row used to bind source approval metadata."""

    family_id: str
    asset_type: str
    source_policy_id: str | None
    data_kind: str
    frequencies: frozenset[str]


@dataclass(frozen=True, slots=True)
class ScopeEvidence:
    """Validated scope manifest facts permitted in a public result."""

    valid: bool
    code: str
    manifest_sha256: str | None = None
    asset_types: frozenset[str] = frozenset()
    families: tuple[ScopeFamily, ...] = ()

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"valid": self.valid, "code": self.code}
        if self.manifest_sha256 is not None:
            payload["manifest_sha256"] = self.manifest_sha256
        if self.asset_types:
            payload["asset_types"] = sorted(self.asset_types)
        if self.families:
            payload["family_count"] = len(self.families)
        return payload


@dataclass(frozen=True, slots=True)
class AlembicEvidence:
    """Read-only migration graph inspection evidence."""

    valid: bool
    code: str
    heads: tuple[str, ...] = ()
    expected_head: str = EXPECTED_ALEMBIC_HEAD
    missing_revisions: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "code": self.code,
            "heads": list(self.heads),
            "expected_head": self.expected_head,
            "missing_required_revisions": list(self.missing_revisions),
        }


@dataclass(frozen=True, slots=True)
class Iter196BaselineEvidence:
    """Read-only proof that the frozen Iteration 196 input is internally sound."""

    valid: bool
    code: str
    baseline_ref: str | None = None
    artifact_ref: str | None = None
    artifact_sha256: str | None = None
    original_receipt_sha256: str | None = None
    merge_second_parent: str | None = None

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "valid": self.valid,
            "code": self.code,
            "expected_merge_commit": ITER196_FREEZE_MERGE_COMMIT,
        }
        if self.baseline_ref is not None:
            payload["baseline_ref"] = self.baseline_ref
        if self.artifact_ref is not None:
            payload["artifact_ref"] = self.artifact_ref
        if self.artifact_sha256 is not None:
            payload["artifact_sha256"] = self.artifact_sha256
        if self.original_receipt_sha256 is not None:
            payload["original_receipt_sha256"] = self.original_receipt_sha256
        if self.merge_second_parent is not None:
            payload["merge_second_parent"] = self.merge_second_parent
        return payload


@dataclass(frozen=True, slots=True)
class ExternalGate:
    """Result of validating a non-secret operator approval envelope."""

    allowed: bool
    code: str
    approval_id: str | None = None
    config_sha256: str | None = None

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"allowed": self.allowed, "code": self.code}
        if self.approval_id is not None:
            payload["approval_id"] = self.approval_id
        if self.config_sha256 is not None:
            payload["config_sha256"] = self.config_sha256
        return payload


@dataclass(frozen=True, slots=True)
class CandidateEvidence:
    """Candidate provenance sufficient to decide whether tests may execute."""

    valid: bool
    code: str
    git_sha: str | None
    dirty_count: int
    unallowlisted_dirty_count: int
    dirty_paths: tuple[dict[str, object], ...]
    dirty_allowlist: tuple[str, ...]
    runner_sha256: str | None
    case_map_sha256: str
    dependency_manifest_sha256: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "code": self.code,
            "git_sha": self.git_sha,
            "dirty_count": self.dirty_count,
            "unallowlisted_dirty_count": self.unallowlisted_dirty_count,
            "dirty_paths": list(self.dirty_paths),
            "dirty_allowlist": list(self.dirty_allowlist),
            "runner_sha256": self.runner_sha256,
            "case_map_sha256": self.case_map_sha256,
            "dependency_manifest_sha256": self.dependency_manifest_sha256,
            "python_executable": sys.executable,
            "python_version": sys.version.split()[0],
        }


@dataclass(frozen=True, slots=True)
class JUnitEvidence:
    """Parsed test facts; a return code alone is never sufficient for PASS."""

    valid: bool
    testcase_count: int = 0
    failures: int = 0
    errors: int = 0
    skipped: int = 0


# Required gates come directly from the AC table in the unified data-platform
# acceptance document.  Modes are executable slices, not a statement that all
# required gates have already completed.
_CASE_GATE_ROWS: tuple[tuple[str, frozenset[str], frozenset[str]], ...] = (
    ("AC-01", frozenset({"G1", "G2"}), frozenset({MODE_OFFLINE, MODE_INTEGRATION})),
    ("AC-02", frozenset({"G2", "G3"}), frozenset({MODE_INTEGRATION, MODE_LIVE})),
    ("AC-03", frozenset({"G1", "G2"}), frozenset({MODE_OFFLINE, MODE_INTEGRATION})),
    ("AC-04", frozenset({"G1", "G2"}), frozenset({MODE_OFFLINE, MODE_INTEGRATION})),
    ("AC-05", frozenset({"G1"}), frozenset({MODE_OFFLINE})),
    ("AC-06", frozenset({"G1", "G2"}), frozenset({MODE_OFFLINE, MODE_INTEGRATION})),
    ("AC-07", frozenset({"G1", "G2"}), frozenset({MODE_OFFLINE, MODE_INTEGRATION})),
    ("AC-08", frozenset({"G1", "G2"}), frozenset({MODE_OFFLINE, MODE_INTEGRATION})),
    ("AC-09", frozenset({"G1", "G2"}), frozenset({MODE_OFFLINE, MODE_INTEGRATION})),
    ("AC-10", frozenset({"G1", "G2"}), frozenset({MODE_OFFLINE, MODE_INTEGRATION})),
    ("AC-11", frozenset({"G1", "G2"}), frozenset({MODE_OFFLINE, MODE_INTEGRATION})),
    ("AC-12", frozenset({"G1", "G2"}), frozenset({MODE_OFFLINE, MODE_INTEGRATION})),
    ("AC-13", frozenset({"G1", "G2"}), frozenset({MODE_OFFLINE, MODE_INTEGRATION})),
    ("AC-14", frozenset({"G1", "G2"}), frozenset({MODE_OFFLINE, MODE_INTEGRATION})),
    ("AC-15", frozenset({"G1", "G2", "G3"}), frozenset({MODE_OFFLINE, MODE_INTEGRATION, MODE_LIVE})),
    ("AC-16", frozenset({"G1", "G3"}), frozenset({MODE_OFFLINE, MODE_LIVE})),
    ("AC-17", frozenset({"G1", "G3"}), frozenset({MODE_OFFLINE, MODE_LIVE})),
    ("AC-18", frozenset({"G1", "G2"}), frozenset({MODE_OFFLINE, MODE_INTEGRATION})),
    ("AC-19", frozenset({"G2"}), frozenset({MODE_INTEGRATION})),
    ("AC-20", frozenset({"G2"}), frozenset({MODE_INTEGRATION})),
    ("AC-21", frozenset({"G2"}), frozenset({MODE_INTEGRATION})),
    ("AC-22", frozenset({"G1", "G2"}), frozenset({MODE_OFFLINE, MODE_INTEGRATION})),
    ("AC-23", frozenset({"G2"}), frozenset({MODE_INTEGRATION})),
    ("AC-24", frozenset({"G2"}), frozenset({MODE_INTEGRATION})),
    ("AC-25", frozenset({"G2"}), frozenset({MODE_INTEGRATION})),
    ("AC-26", frozenset({"G2"}), frozenset({MODE_INTEGRATION})),
    ("AC-27", frozenset({"G2"}), frozenset({MODE_INTEGRATION})),
    ("AC-28", frozenset({"G2"}), frozenset({MODE_INTEGRATION})),
    ("AC-29", frozenset({"G2"}), frozenset({MODE_INTEGRATION})),
    ("AC-30", frozenset({"G1", "G2"}), frozenset({MODE_OFFLINE, MODE_INTEGRATION})),
    ("AC-31", frozenset({"G2"}), frozenset({MODE_INTEGRATION})),
    ("AC-32", frozenset({"G1", "G2"}), frozenset({MODE_OFFLINE, MODE_INTEGRATION})),
    ("AC-33", frozenset({"G2", "G3"}), frozenset({MODE_INTEGRATION, MODE_LIVE})),
    ("AC-34", frozenset({"G2", "G3"}), frozenset({MODE_INTEGRATION, MODE_LIVE})),
    ("AC-35", frozenset({"G1", "G2", "G3"}), frozenset({MODE_OFFLINE, MODE_INTEGRATION, MODE_LIVE})),
    ("AC-36", frozenset({"G1", "G3"}), frozenset({MODE_OFFLINE, MODE_LIVE})),
    ("AC-37", frozenset({"G1", "G3"}), frozenset({MODE_OFFLINE, MODE_LIVE})),
    ("AC-38", frozenset({"G2", "G3"}), frozenset({MODE_INTEGRATION, MODE_LIVE})),
    ("AC-39", frozenset({"G1", "G2", "G3"}), frozenset({MODE_OFFLINE, MODE_INTEGRATION, MODE_LIVE})),
    ("AC-40", frozenset({"G1", "G2"}), frozenset({MODE_OFFLINE, MODE_INTEGRATION})),
    ("AC-41", frozenset({"G2", "G4"}), frozenset({MODE_INTEGRATION, MODE_RECOVERY})),
    ("AC-42", frozenset({"G2", "G4"}), frozenset({MODE_INTEGRATION, MODE_RECOVERY})),
    ("AC-43", frozenset({"G2", "G4"}), frozenset({MODE_INTEGRATION, MODE_RECOVERY})),
    ("AC-44", frozenset({"G4"}), frozenset({MODE_RECOVERY})),
    ("AC-45", frozenset({"G4"}), frozenset({MODE_RECOVERY})),
    ("AC-46", frozenset({"G4"}), frozenset({MODE_PERFORMANCE})),
    ("AC-47", frozenset({"G2", "G4"}), frozenset({MODE_INTEGRATION, MODE_RECOVERY, MODE_PERFORMANCE})),
    ("AC-48", frozenset({"G4"}), frozenset({MODE_RECOVERY})),
)
_CASES = tuple(AcceptanceCase(case_id, gates, modes) for case_id, gates, modes in _CASE_GATE_ROWS)
_CASE_BY_ID = {case.case_id: case for case in _CASES}
_CASE_BY_FORMAL_ID = {case.formal_case_id: case for case in _CASES}


def _arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=sorted(VALID_MODES), required=True)
    parser.add_argument(
        "--case",
        dest="cases",
        action="append",
        default=[],
        metavar="AC-XX|AC-197-MATRIX-XXX[,ID]",
        help="Restrict to matrix or formal case IDs; repeat or comma-separate values.",
    )
    parser.add_argument(
        "--asset-type",
        dest="asset_types",
        action="append",
        default=[],
        metavar="TYPE[,TYPE]|all",
        help="Restrict to stock, futures, bond, fund, option, fx, crypto, or all.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        metavar="PATH",
        help="Evidence directory or explicit result.json path.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate selection and external gates only; never execute pytest or external work.",
    )
    parser.add_argument(
        "--scope-manifest",
        type=Path,
        metavar="PATH",
        help="Validated frozen scope manifest; defaults to the checked-in Iteration 197 artifact.",
    )
    parser.add_argument(
        "--dirty-allowlist",
        action="append",
        default=[],
        metavar="RELATIVE_PATH[,RELATIVE_PATH]",
        help="Explicit candidate-owned dirty paths allowed for this non-dry-run invocation.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        metavar="PATH",
        help=argparse.SUPPRESS,
    )
    return parser.parse_args(argv)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _parse_csv_values(values: Iterable[str]) -> tuple[tuple[str, ...], bool]:
    """Return non-empty comma tokens and whether an explicit blank was supplied."""
    parsed: list[str] = []
    explicit_blank = False
    for raw in values:
        if not isinstance(raw, str):
            explicit_blank = True
            continue
        parts = raw.split(",")
        if not parts:
            explicit_blank = True
        for part in parts:
            normalized = part.strip()
            if normalized:
                parsed.append(normalized)
            else:
                explicit_blank = True
    return tuple(parsed), explicit_blank


def _safe_unknown_case_id(value: str) -> str:
    candidate = value.upper()
    if _CASE_ID_RE.fullmatch(candidate) or _FORMAL_CASE_ID_RE.fullmatch(candidate):
        return candidate
    return f"UNKNOWN-{_sha256(value.encode('utf-8'))[:16]}"


def _normalize_case_selection(
    values: Iterable[str],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Resolve matrix/formal IDs and retain safe unknown selections as result rows."""
    requested, explicit_blank = _parse_csv_values(values)
    known: list[str] = []
    unknown: list[str] = []
    errors: list[str] = []
    if explicit_blank:
        errors.append("ACCEPTANCE_CASE_EMPTY")
    for value in requested:
        normalized = value.upper()
        case = _CASE_BY_ID.get(normalized) or _CASE_BY_FORMAL_ID.get(normalized)
        if case is None:
            errors.append("ACCEPTANCE_CASE_UNKNOWN")
            safe = _safe_unknown_case_id(value)
            if safe not in unknown:
                unknown.append(safe)
            continue
        if case.case_id not in known:
            known.append(case.case_id)
    return tuple(known), tuple(unknown), tuple(sorted(set(errors)))


def _normalize_asset_selection(values: Iterable[str]) -> tuple[frozenset[str], tuple[str, ...]]:
    """Parse an explicit asset filter without broadening invalid input."""
    requested, explicit_blank = _parse_csv_values(values)
    if not requested and not explicit_blank:
        return ASSET_TYPES, ()
    errors: list[str] = []
    if explicit_blank:
        errors.append("ACCEPTANCE_ASSET_TYPE_EMPTY")
    normalized = {value.lower() for value in requested}
    if "all" in normalized:
        if len(normalized) == 1 and not explicit_blank:
            return ASSET_TYPES, ()
        errors.append("ACCEPTANCE_ASSET_TYPE_AMBIGUOUS")
        return frozenset(), tuple(sorted(set(errors)))
    unsupported = normalized - ASSET_TYPES
    if unsupported:
        errors.append("ACCEPTANCE_ASSET_TYPE_UNKNOWN")
    if errors:
        return frozenset(), tuple(sorted(set(errors)))
    return frozenset(normalized), ()


def _select_slices(
    *,
    mode: str,
    requested_case_ids: tuple[str, ...],
    asset_types: frozenset[str],
    select_all_when_empty: bool = True,
) -> tuple[tuple[CaseSlice, ...], tuple[CaseSlice, ...]]:
    """Return executable and mode-incompatible case/asset slices separately."""
    candidate_cases = (
        tuple(_CASE_BY_ID[case_id] for case_id in requested_case_ids)
        if requested_case_ids
        else (_CASES if select_all_when_empty else ())
    )
    selected: list[CaseSlice] = []
    incompatible: list[CaseSlice] = []
    for case in candidate_cases:
        for asset_type in sorted(case.asset_types.intersection(asset_types)):
            slice_ = CaseSlice(case=case, asset_type=asset_type, mode=mode)
            if mode in case.modes:
                selected.append(slice_)
            else:
                incompatible.append(slice_)
    return tuple(selected), tuple(incompatible)


def _result_path(output: Path) -> Path:
    expanded = output.expanduser()
    return expanded if expanded.name == "result.json" else expanded / "result.json"


def _write_result(path: Path, payload: Mapping[str, object]) -> None:
    """Atomically replace only the requested machine-readable result file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(encoded + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _collect_scope_evidence(project_root: Path, manifest_path: Path) -> ScopeEvidence:
    """Validate the checked scope artifact against this exact checkout, read-only."""
    try:
        manifest = load_scope_manifest(manifest_path)
        validate_scope_manifest(manifest=manifest, project_root=project_root)
        manifest_sha256 = manifest.get("manifest_sha256")
        rows = manifest.get("rows")
        if not isinstance(manifest_sha256, str) or not _SHA256_RE.fullmatch(manifest_sha256):
            return ScopeEvidence(valid=False, code="SCOPE_MANIFEST_INVALID")
        if not isinstance(rows, list):
            return ScopeEvidence(valid=False, code="SCOPE_MANIFEST_INVALID")
        families: list[ScopeFamily] = []
        for row in rows:
            if not isinstance(row, Mapping):
                return ScopeEvidence(valid=False, code="SCOPE_MANIFEST_INVALID")
            family_id = row.get("family_id")
            asset_type = row.get("asset_type")
            data_kind = row.get("data_kind")
            frequencies = row.get("frequencies")
            source_policy_id = row.get("source_policy_id")
            if (
                not isinstance(family_id, str)
                or not _IDENTIFIER_RE.fullmatch(family_id)
                or asset_type not in ASSET_TYPES
                or not isinstance(data_kind, str)
                or not _IDENTIFIER_RE.fullmatch(data_kind)
                or not isinstance(frequencies, list)
                or not frequencies
                or not all(isinstance(value, str) and _IDENTIFIER_RE.fullmatch(value) for value in frequencies)
                or (source_policy_id is not None and not isinstance(source_policy_id, str))
            ):
                return ScopeEvidence(valid=False, code="SCOPE_MANIFEST_INVALID")
            families.append(
                ScopeFamily(
                    family_id=family_id,
                    asset_type=asset_type,
                    source_policy_id=source_policy_id,
                    data_kind=data_kind,
                    frequencies=frozenset(frequencies),
                )
            )
        if not families:
            return ScopeEvidence(valid=False, code="SCOPE_MANIFEST_INVALID")
        return ScopeEvidence(
            valid=True,
            code="SCOPE_MANIFEST_VALID",
            manifest_sha256=manifest_sha256,
            asset_types=frozenset(family.asset_type for family in families),
            families=tuple(families),
        )
    except ScopeManifestError as exc:
        return ScopeEvidence(valid=False, code=exc.code)
    except (OSError, TypeError, ValueError):
        return ScopeEvidence(valid=False, code="SCOPE_MANIFEST_VALIDATION_FAILED")


def _safe_git_artifact_ref(value: str) -> str | None:
    """Return one canonical repository-relative artifact path or ``None``."""
    if not value or "\\" in value or "\x00" in value or ":" in value:
        return None
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != value
    ):
        return None
    return path.as_posix()


def _read_regular_file_bytes(path: Path) -> bytes | None:
    """Read one non-symlink checkout file without following a replacement link."""
    try:
        if not path.is_file() or path.is_symlink():
            return None
        return path.read_bytes()
    except OSError:
        return None


def _resolve_git_commit(project_root: Path, ref: str) -> str | None:
    """Resolve one already validated Git object reference to its commit identity."""
    completed = _git_command(project_root, ("rev-parse", "--verify", f"{ref}^{{commit}}"))
    if completed is None or completed.returncode != 0:
        return None
    resolved = completed.stdout.decode("ascii", errors="ignore").strip()
    return resolved if _GIT_OBJECT_ID_RE.fullmatch(resolved) else None


def _collect_iter196_baseline_evidence(project_root: Path) -> Iter196BaselineEvidence:
    """Fail closed unless the checked-in Iteration 196 baseline has an exact Git chain."""
    baseline_path = project_root / DEFAULT_ITER196_BASELINE_RELATIVE
    try:
        baseline = load_iter196_baseline(baseline_path)
    except ScopeManifestError as exc:
        return Iter196BaselineEvidence(valid=False, code=exc.code)

    artifact_ref = _safe_git_artifact_ref(baseline.artifact_ref)
    if artifact_ref is None:
        return Iter196BaselineEvidence(
            valid=False,
            code="ITER196_BASELINE_ARTIFACT_REF_INVALID",
            baseline_ref=baseline.baseline_ref,
        )
    if artifact_ref != ITER196_CORRECTION_RECEIPT_RELATIVE.as_posix():
        return Iter196BaselineEvidence(
            valid=False,
            code="ITER196_BASELINE_ARTIFACT_REF_UNEXPECTED",
            baseline_ref=baseline.baseline_ref,
            artifact_ref=artifact_ref,
        )

    if _resolve_git_commit(project_root, baseline.baseline_ref) is None:
        return Iter196BaselineEvidence(
            valid=False,
            code="ITER196_BASELINE_REF_UNRESOLVABLE",
            baseline_ref=baseline.baseline_ref,
            artifact_ref=artifact_ref,
        )

    merge_commit = _resolve_git_commit(project_root, ITER196_FREEZE_MERGE_COMMIT)
    if merge_commit is None:
        return Iter196BaselineEvidence(
            valid=False,
            code="ITER196_BASELINE_MERGE_UNRESOLVABLE",
            baseline_ref=baseline.baseline_ref,
            artifact_ref=artifact_ref,
        )
    merge_parents = _git_command(project_root, ("show", "-s", "--format=%P", merge_commit))
    parents = (
        tuple(merge_parents.stdout.decode("ascii", errors="ignore").split())
        if merge_parents is not None and merge_parents.returncode == 0
        else ()
    )
    if len(parents) < 2 or not all(_GIT_OBJECT_ID_RE.fullmatch(parent) for parent in parents):
        return Iter196BaselineEvidence(
            valid=False,
            code="ITER196_BASELINE_MERGE_SECOND_PARENT_MISSING",
            baseline_ref=baseline.baseline_ref,
            artifact_ref=artifact_ref,
        )
    second_parent = parents[1]
    if second_parent != baseline.baseline_ref:
        return Iter196BaselineEvidence(
            valid=False,
            code="ITER196_BASELINE_MERGE_SECOND_PARENT_MISMATCH",
            baseline_ref=baseline.baseline_ref,
            artifact_ref=artifact_ref,
            merge_second_parent=second_parent,
        )

    original_receipt = _read_regular_file_bytes(
        project_root / ITER196_ORIGINAL_FREEZE_RECEIPT_RELATIVE
    )
    if original_receipt is None:
        return Iter196BaselineEvidence(
            valid=False,
            code="ITER196_BASELINE_ORIGINAL_RECEIPT_UNAVAILABLE",
            baseline_ref=baseline.baseline_ref,
            artifact_ref=artifact_ref,
            merge_second_parent=second_parent,
        )
    original_receipt_sha256 = _sha256(original_receipt)
    if original_receipt_sha256 != ITER196_ORIGINAL_FREEZE_RECEIPT_SHA256:
        return Iter196BaselineEvidence(
            valid=False,
            code="ITER196_BASELINE_ORIGINAL_RECEIPT_SHA256_MISMATCH",
            baseline_ref=baseline.baseline_ref,
            artifact_ref=artifact_ref,
            original_receipt_sha256=original_receipt_sha256,
            merge_second_parent=second_parent,
        )

    correction_receipt = _read_regular_file_bytes(project_root / artifact_ref)
    if correction_receipt is None:
        return Iter196BaselineEvidence(
            valid=False,
            code="ITER196_BASELINE_CORRECTION_RECEIPT_UNAVAILABLE",
            baseline_ref=baseline.baseline_ref,
            artifact_ref=artifact_ref,
            original_receipt_sha256=original_receipt_sha256,
            merge_second_parent=second_parent,
        )
    artifact_sha256 = _sha256(correction_receipt)
    if artifact_sha256 != baseline.baseline_sha256:
        return Iter196BaselineEvidence(
            valid=False,
            code="ITER196_BASELINE_ARTIFACT_SHA256_MISMATCH",
            baseline_ref=baseline.baseline_ref,
            artifact_ref=artifact_ref,
            artifact_sha256=artifact_sha256,
            original_receipt_sha256=original_receipt_sha256,
            merge_second_parent=second_parent,
        )
    try:
        correction_text = correction_receipt.decode("utf-8")
    except UnicodeDecodeError:
        correction_text = ""
    if not all(token in correction_text for token in _ITER196_CORRECTION_REQUIRED_TOKENS):
        return Iter196BaselineEvidence(
            valid=False,
            code="ITER196_BASELINE_CORRECTION_RECEIPT_RELATION_INVALID",
            baseline_ref=baseline.baseline_ref,
            artifact_ref=artifact_ref,
            artifact_sha256=artifact_sha256,
            original_receipt_sha256=original_receipt_sha256,
            merge_second_parent=second_parent,
        )
    return Iter196BaselineEvidence(
        valid=True,
        code="ITER196_BASELINE_PROVENANCE_VALID",
        baseline_ref=baseline.baseline_ref,
        artifact_ref=artifact_ref,
        artifact_sha256=artifact_sha256,
        original_receipt_sha256=original_receipt_sha256,
        merge_second_parent=second_parent,
    )


def _collect_alembic_evidence(backend_root: Path) -> AlembicEvidence:
    """Inspect the sealed migration tip and required ancestry without connecting to a database."""
    try:
        config = Config(str(backend_root / "alembic.ini"))
        config.set_main_option("script_location", str(backend_root / "alembic"))
        script = ScriptDirectory.from_config(config)
        heads = tuple(sorted(script.get_heads()))
    except Exception:
        return AlembicEvidence(valid=False, code="ALEMBIC_HEAD_INSPECTION_FAILED")
    if heads != (EXPECTED_ALEMBIC_HEAD,):
        return AlembicEvidence(valid=False, code="ALEMBIC_HEAD_UNEXPECTED", heads=heads)
    try:
        ancestry = {
            revision.revision
            for revision in script.iterate_revisions(EXPECTED_ALEMBIC_HEAD, "base")
        }
    except Exception:
        return AlembicEvidence(
            valid=False,
            code="ALEMBIC_ANCESTRY_INSPECTION_FAILED",
            heads=heads,
        )
    missing = tuple(sorted(REQUIRED_ALEMBIC_REVISIONS - ancestry))
    if missing:
        return AlembicEvidence(
            valid=False,
            code="ALEMBIC_REQUIRED_ANCESTRY_MISSING",
            heads=heads,
            missing_revisions=missing,
        )
    return AlembicEvidence(
        valid=True,
        code="ALEMBIC_HEAD_AND_ANCESTRY_VALID",
        heads=heads,
    )


def _safe_json_file(path_value: str | None) -> tuple[dict[str, Any] | None, str | None, str]:
    """Load a small metadata-only JSON file without returning its path or content."""
    if not isinstance(path_value, str) or not path_value.strip():
        return None, None, "ACCEPTANCE_ENVIRONMENT_CONFIG_REQUIRED"
    try:
        path = Path(path_value).expanduser()
        if not path.is_absolute():
            return None, None, "ACCEPTANCE_ENVIRONMENT_CONFIG_INVALID"
        metadata = path.lstat()
        if not path.is_file() or path.is_symlink() or metadata.st_size > _MAX_MANIFEST_BYTES:
            return None, None, "ACCEPTANCE_ENVIRONMENT_CONFIG_INVALID"
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None, None, "ACCEPTANCE_ENVIRONMENT_CONFIG_INVALID"
    if not isinstance(payload, dict):
        return None, None, "ACCEPTANCE_ENVIRONMENT_CONFIG_INVALID"
    return payload, _sha256(raw), "ACCEPTANCE_ENVIRONMENT_CONFIG_VALID"


def _valid_utc_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _external_gate(mode: str, environment: Mapping[str, str] | None = None) -> ExternalGate:
    """Validate a mode's explicit approval/configuration gate without executing it."""
    if mode == MODE_OFFLINE:
        return ExternalGate(allowed=True, code="OFFLINE_MODE_NO_EXTERNAL_GATE")
    env = os.environ if environment is None else environment
    prefix = f"ITER197_{mode.upper()}"
    if env.get(f"{prefix}_APPROVAL") != "approved":
        return ExternalGate(allowed=False, code="ACCEPTANCE_EXTERNAL_APPROVAL_REQUIRED")
    payload, config_sha256, code = _safe_json_file(env.get(f"{prefix}_CONFIG"))
    if payload is None:
        return ExternalGate(allowed=False, code=code)
    expected_keys = {"schema_version", "mode", "environment", "approval_id", "approved_at"}
    approval_id = payload.get("approval_id")
    if (
        set(payload) != expected_keys
        or payload.get("schema_version") != ENVIRONMENT_SCHEMA_VERSION
        or payload.get("mode") != mode
        or payload.get("environment") != "isolated"
        or not isinstance(approval_id, str)
        or not _APPROVAL_ID_RE.fullmatch(approval_id)
        or not _valid_utc_timestamp(payload.get("approved_at"))
    ):
        return ExternalGate(allowed=False, code="ACCEPTANCE_ENVIRONMENT_CONFIG_INVALID")
    return ExternalGate(
        allowed=True,
        code="ACCEPTANCE_EXTERNAL_CONFIG_APPROVED",
        approval_id=approval_id,
        config_sha256=config_sha256,
    )


def _string_list(value: object, *, allow_none: bool = False) -> tuple[str | None, ...] | None:
    if not isinstance(value, list) or not value:
        return None
    normalized: list[str | None] = []
    for item in value:
        if item is None and allow_none:
            candidate: str | None = None
        elif isinstance(item, str) and _IDENTIFIER_RE.fullmatch(item):
            candidate = item
        else:
            return None
        if candidate in normalized:
            return None
        normalized.append(candidate)
    return tuple(normalized)


def _validate_source_manifest_entry(
    value: object,
    *,
    families_by_id: Mapping[str, ScopeFamily],
) -> dict[str, object] | None:
    """Validate one route approval against exact scope family facts.

    This verifies approval metadata only.  A future external driver must still
    resolve the server-owned policy/route and produce live evidence before it
    can mark a G3 slice PASS.
    """
    expected_keys = {
        "source_id",
        "source_policy_id",
        "route_id",
        "request_provider",
        "expected_result_provider_ids",
        "asset_types",
        "family_ids",
        "data_kinds",
        "frequencies",
        "markets",
        "adjustments",
        "price_bases",
        "currencies",
        "units",
        "provider_endpoint",
        "case_ids",
    }
    if not isinstance(value, dict) or set(value) != expected_keys:
        return None
    required_text = (
        "source_id",
        "source_policy_id",
        "route_id",
        "request_provider",
        "provider_endpoint",
    )
    if any(not isinstance(value.get(field), str) or not _IDENTIFIER_RE.fullmatch(value[field]) for field in required_text):
        return None
    expected_provider_ids = _string_list(value.get("expected_result_provider_ids"))
    asset_types = _string_list(value.get("asset_types"))
    family_ids = _string_list(value.get("family_ids"))
    data_kinds = _string_list(value.get("data_kinds"))
    frequencies = _string_list(value.get("frequencies"))
    markets = _string_list(value.get("markets"))
    case_ids = _string_list(value.get("case_ids"))
    semantic_lists = {
        field: _string_list(value.get(field), allow_none=True)
        for field in ("adjustments", "price_bases", "currencies", "units")
    }
    if (
        expected_provider_ids is None
        or asset_types is None
        or family_ids is None
        or data_kinds is None
        or frequencies is None
        or markets is None
        or case_ids is None
        or any(items is None for items in semantic_lists.values())
        or not set(asset_types).issubset(ASSET_TYPES)
        or not all(isinstance(case_id, str) and case_id in _CASE_BY_ID for case_id in case_ids)
    ):
        return None
    source_policy_id = value["source_policy_id"]
    for family_id in family_ids:
        family = families_by_id.get(str(family_id))
        if (
            family is None
            or family.asset_type not in asset_types
            or family.source_policy_id != source_policy_id
            or family.data_kind not in data_kinds
            or not family.frequencies.issubset({str(frequency) for frequency in frequencies})
        ):
            return None
    return {
        "source_id": value["source_id"],
        "asset_types": tuple(str(asset_type) for asset_type in asset_types),
        "family_ids": tuple(str(family_id) for family_id in family_ids),
        "case_ids": tuple(str(case_id) for case_id in case_ids),
    }


def _live_source_gate(
    *,
    environment: Mapping[str, str],
    scope_evidence: ScopeEvidence,
    approval_id: str,
    selected_slices: Sequence[CaseSlice],
) -> tuple[bool, str, dict[str, object]]:
    """Require an approved, exact route manifest covering every requested slice."""
    payload, source_manifest_sha256, code = _safe_json_file(
        environment.get("ITER197_LIVE_SOURCE_MANIFEST")
    )
    if payload is None:
        return False, code.replace("ENVIRONMENT_CONFIG", "SOURCE_MANIFEST"), {}
    expected_keys = {
        "schema_version",
        "status",
        "approval_id",
        "approved_at",
        "scope_manifest_sha256",
        "sources",
    }
    sources = payload.get("sources")
    if (
        set(payload) != expected_keys
        or payload.get("schema_version") != SOURCE_MANIFEST_SCHEMA_VERSION
        or payload.get("status") != "approved"
        or payload.get("approval_id") != approval_id
        or not _valid_utc_timestamp(payload.get("approved_at"))
        or payload.get("scope_manifest_sha256") != scope_evidence.manifest_sha256
        or not isinstance(sources, list)
        or not sources
    ):
        return False, "ACCEPTANCE_SOURCE_MANIFEST_INVALID", {}
    families_by_id = {family.family_id: family for family in scope_evidence.families}
    validated = [
        _validate_source_manifest_entry(source, families_by_id=families_by_id)
        for source in sources
    ]
    if any(source is None for source in validated):
        return False, "ACCEPTANCE_SOURCE_MANIFEST_INVALID", {}
    safe_sources = [source for source in validated if source is not None]
    source_ids = [str(source["source_id"]) for source in safe_sources]
    if len(source_ids) != len(set(source_ids)):
        return False, "ACCEPTANCE_SOURCE_MANIFEST_INVALID", {}
    uncovered: list[str] = []
    for slice_ in selected_slices:
        covered = any(
            slice_.case.case_id in source["case_ids"]
            and slice_.asset_type in source["asset_types"]
            and any(
                families_by_id[family_id].asset_type == slice_.asset_type
                for family_id in source["family_ids"]
            )
            for source in safe_sources
        )
        if not covered:
            uncovered.append(slice_.case_key)
    evidence: dict[str, object] = {
        "metadata_valid": not uncovered,
        "source_manifest_sha256": source_manifest_sha256,
        "source_count": len(safe_sources),
        "uncovered_case_keys": uncovered,
    }
    if uncovered:
        return False, "ACCEPTANCE_SOURCE_MANIFEST_SCOPE_INSUFFICIENT", evidence
    return True, "ACCEPTANCE_SOURCE_MANIFEST_APPROVED", evidence


_OFFLINE_NETWORK_GUARD = r'''# Generated only for one Iteration 197 offline child process.
import os as _os
if _os.environ.get("ITER197_OFFLINE_NETWORK_DISABLED") == "1":
    import socket as _socket
    _audit_path = _os.environ.get("ITER197_OFFLINE_NETWORK_AUDIT_FILE")
    _original_socket = _socket.socket
    _inet_families = {_socket.AF_INET, _socket.AF_INET6}
    def _audit(kind):
        if _audit_path:
            try:
                with open(_audit_path, "a", encoding="utf-8") as _handle:
                    _handle.write(kind + "\n")
            except OSError:
                pass
    def _deny(kind):
        _audit(kind)
        raise OSError("ITER197_OFFLINE_NETWORK_DENIED")
    class _Iteration197OfflineSocket(_original_socket):
        def _deny_if_inet(self, kind):
            if self.family in _inet_families:
                _deny(kind)
        def connect(self, address):
            self._deny_if_inet("socket.connect")
            return super().connect(address)
        def connect_ex(self, address):
            self._deny_if_inet("socket.connect_ex")
            return super().connect_ex(address)
        def send(self, data, *args, **kwargs):
            self._deny_if_inet("socket.send")
            return super().send(data, *args, **kwargs)
        def sendall(self, data, *args, **kwargs):
            self._deny_if_inet("socket.sendall")
            return super().sendall(data, *args, **kwargs)
        def sendto(self, data, *args, **kwargs):
            self._deny_if_inet("socket.sendto")
            return super().sendto(data, *args, **kwargs)
    def _denied_create_connection(*args, **kwargs):
        _deny("socket.create_connection")
    def _denied_getaddrinfo(*args, **kwargs):
        _deny("socket.getaddrinfo")
    def _denied_gethostbyname(*args, **kwargs):
        _deny("socket.gethostbyname")
    def _denied_gethostbyname_ex(*args, **kwargs):
        _deny("socket.gethostbyname_ex")
    def _denied_getnameinfo(*args, **kwargs):
        _deny("socket.getnameinfo")
    _socket.socket = _Iteration197OfflineSocket
    _socket.create_connection = _denied_create_connection
    _socket.getaddrinfo = _denied_getaddrinfo
    _socket.gethostbyname = _denied_gethostbyname
    _socket.gethostbyname_ex = _denied_gethostbyname_ex
    _socket.getnameinfo = _denied_getnameinfo
'''


@contextmanager
def _offline_network_environment(backend_root: Path) -> Iterator[tuple[dict[str, str], Path]]:
    """Create a child-only Python socket denial/audit guard.

    This is intentionally described as a Python-child guard, not OS-level
    network isolation.  The registered targets are deterministic Python tests;
    any guarded network API attempt is recorded and causes the slice to FAIL.
    """
    with tempfile.TemporaryDirectory(prefix="iteration197-offline-network-") as directory:
        guard_dir = Path(directory)
        audit_path = guard_dir / "network-attempts.log"
        (guard_dir / "sitecustomize.py").write_text(_OFFLINE_NETWORK_GUARD, encoding="utf-8")
        inherited = os.environ
        environment = {
            key: value
            for key, value in inherited.items()
            if not key.upper().startswith("PYTHON")
            and not key.upper().startswith("PYTEST")
            and "PROXY" not in key.upper()
            and not key.upper().startswith("ITER197_")
        }
        environment.update(
            {
                "ITER197_OFFLINE_NETWORK_DISABLED": "1",
                "ITER197_OFFLINE_NETWORK_AUDIT_FILE": str(audit_path),
                "PYTHONPATH": os.pathsep.join((str(guard_dir), str(backend_root))),
                "PYTHONNOUSERSITE": "1",
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                "PYTEST_ADDOPTS": "",
                "PYTEST_PLUGINS": "",
                "NO_PROXY": "*",
                "no_proxy": "*",
            }
        )
        yield environment, audit_path


def _read_network_audit(audit_path: Path) -> tuple[str, ...]:
    try:
        content = audit_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ()
    except OSError:
        return ("audit_unreadable",)
    return tuple(line for line in content.splitlines() if line)


def _run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
) -> CommandResult:
    """Run one non-shell child process while discarding potentially sensitive output."""
    started = time.monotonic()
    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            env=dict(environment),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=900,
        )
        return CommandResult(
            returncode=completed.returncode,
            elapsed_ms=round((time.monotonic() - started) * 1000),
        )
    except (OSError, subprocess.TimeoutExpired):
        return CommandResult(returncode=None, elapsed_ms=round((time.monotonic() - started) * 1000))


def _parse_junit(path: Path) -> JUnitEvidence:
    """Read the JUnit file independently so collection/skip cannot become PASS."""
    try:
        root = ET.parse(path).getroot()
    except (FileNotFoundError, OSError, ET.ParseError):
        return JUnitEvidence(valid=False)
    testcases = list(root.iter("testcase"))
    if not testcases:
        return JUnitEvidence(valid=False)
    failures = sum(len(testcase.findall("failure")) for testcase in testcases)
    errors = sum(len(testcase.findall("error")) for testcase in testcases)
    skipped = sum(len(testcase.findall("skipped")) for testcase in testcases)
    return JUnitEvidence(
        valid=True,
        testcase_count=len(testcases),
        failures=failures,
        errors=errors,
        skipped=skipped,
    )


def _target_path(target: str) -> str:
    return target.split("::", 1)[0]


def _offline_case_result(
    *,
    slice_: CaseSlice,
    backend_root: Path,
    result_directory: Path,
    command_runner: Callable[..., CommandResult],
) -> dict[str, object]:
    """Execute one explicit deterministic test target set for a case/asset slice."""
    targets = _OFFLINE_TESTS_BY_CASE_ASSET.get((slice_.case.case_id, slice_.asset_type))
    if not targets:
        return _case_result(
            slice_,
            status=STATUS_NOT_RUN,
            code="OFFLINE_ASSET_CASE_DRIVER_UNAVAILABLE",
            evidence=[],
        )
    missing = [target for target in targets if not (backend_root / _target_path(target)).is_file()]
    if missing:
        return _case_result(
            slice_,
            status=STATUS_FAIL,
            code="OFFLINE_TEST_TARGET_MISSING",
            evidence=[],
        )
    junit_directory = result_directory / "tests"
    junit_directory.mkdir(parents=True, exist_ok=True)
    junit_path = junit_directory / f"{slice_.case.case_id}-{slice_.asset_type}.xml"
    command = (
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-p",
        "pytest_asyncio.plugin",
        *targets,
        f"--junitxml={junit_path}",
    )
    with _offline_network_environment(backend_root) as (environment, audit_path):
        outcome = command_runner(command, cwd=backend_root, environment=environment)
        network_attempts = _read_network_audit(audit_path)
    junit = _parse_junit(junit_path)
    evidence = [
        {
            "kind": "pytest_junit",
            "path": f"tests/{junit_path.name}",
            "network_policy": "python_child_socket_audit_guard",
            "network_attempt_count": len(network_attempts),
            "testcase_count": junit.testcase_count,
            "failures": junit.failures,
            "errors": junit.errors,
            "skipped": junit.skipped,
        }
    ]
    if network_attempts:
        return _case_result(
            slice_,
            status=STATUS_FAIL,
            code="OFFLINE_NETWORK_ATTEMPT_DETECTED",
            evidence=evidence,
            duration_ms=outcome.elapsed_ms,
        )
    if outcome.returncode is None:
        return _case_result(
            slice_,
            status=STATUS_FAIL,
            code="OFFLINE_PYTEST_EXECUTION_FAILED",
            evidence=evidence,
            duration_ms=outcome.elapsed_ms,
        )
    if not junit.valid:
        return _case_result(
            slice_,
            status=STATUS_FAIL,
            code="OFFLINE_JUNIT_EVIDENCE_INVALID",
            evidence=evidence,
            duration_ms=outcome.elapsed_ms,
        )
    if junit.failures or junit.errors or outcome.returncode != 0:
        return _case_result(
            slice_,
            status=STATUS_FAIL,
            code="OFFLINE_PYTEST_FAILED",
            evidence=evidence,
            duration_ms=outcome.elapsed_ms,
        )
    if junit.skipped:
        return _case_result(
            slice_,
            status=STATUS_NOT_RUN,
            code="OFFLINE_JUNIT_SKIPPED",
            evidence=evidence,
            duration_ms=outcome.elapsed_ms,
        )
    return _case_result(
        slice_,
        status=STATUS_PASS,
        code="OFFLINE_PYTEST_PASSED",
        evidence=evidence,
        duration_ms=outcome.elapsed_ms,
    )


def _case_result(
    slice_: CaseSlice,
    *,
    status: str,
    code: str,
    evidence: Sequence[Mapping[str, object]],
    duration_ms: int | None = None,
) -> dict[str, object]:
    """Build a result that makes the mode-vs-complete-case boundary explicit."""
    if status not in VALID_STATUSES:
        raise ValueError("ACCEPTANCE_STATUS_INVALID")
    gate = GATE_BY_MODE[slice_.mode]
    remaining = tuple(sorted(slice_.case.required_gates - {gate}))
    satisfied = (gate,) if status == STATUS_PASS else ()
    overall_status = STATUS_PASS if status == STATUS_PASS and not remaining else (
        STATUS_NOT_RUN if status == STATUS_PASS else status
    )
    payload: dict[str, object] = {
        "case_id": slice_.case.case_id,
        "formal_case_id": slice_.case.formal_case_id,
        "case_mapping_version": CASE_MAPPING_VERSION,
        "case_key": slice_.case_key,
        "asset_type": slice_.asset_type,
        # Kept for consumers that used the initial runner prototype.
        "asset_types": [slice_.asset_type],
        "required": slice_.case.required,
        "required_gates": sorted(slice_.case.required_gates),
        "mode_gate": gate,
        "mode_slice_status": status,
        "overall_case_status": overall_status,
        "satisfied_gates": list(satisfied),
        "remaining_gates": list(remaining),
        "status": status,
        "code": code,
        "evidence": [dict(item) for item in evidence],
    }
    if remaining and status == STATUS_PASS:
        payload["overall_case_code"] = "ACCEPTANCE_OTHER_REQUIRED_GATES_PENDING"
    if duration_ms is not None:
        payload["duration_ms"] = duration_ms
    return payload


def _selection_problem_result(
    *,
    case_id: str,
    asset_type: str,
    mode: str,
    code: str,
) -> dict[str, object]:
    """Represent invalid explicit selection without silently dropping it."""
    formal = _CASE_BY_ID.get(case_id)
    return {
        "case_id": case_id,
        "formal_case_id": formal.formal_case_id if formal else None,
        "case_mapping_version": CASE_MAPPING_VERSION,
        "case_key": f"{case_id}:{asset_type}:{GATE_BY_MODE[mode]}",
        "asset_type": asset_type,
        "asset_types": [asset_type],
        "required": True,
        "required_gates": [],
        "mode_gate": GATE_BY_MODE[mode],
        "mode_slice_status": STATUS_NOT_RUN,
        "overall_case_status": STATUS_NOT_RUN,
        "satisfied_gates": [],
        "remaining_gates": [],
        "status": STATUS_NOT_RUN,
        "code": code,
        "evidence": [],
    }


def _static_case_results(
    *,
    slices: Sequence[CaseSlice],
    status: str,
    code: str,
) -> list[dict[str, object]]:
    return [_case_result(slice_, status=status, code=code, evidence=[]) for slice_ in slices]


def _parse_dirty_allowlist(values: Iterable[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Validate repository-relative allowlist entries before comparing dirty paths."""
    raw_values, explicit_blank = _parse_csv_values(values)
    normalized: list[str] = []
    errors: list[str] = ["CANDIDATE_DIRTY_ALLOWLIST_INVALID"] if explicit_blank else []
    for raw in raw_values:
        try:
            path = PurePosixPath(raw.replace("\\", "/"))
        except TypeError:
            errors.append("CANDIDATE_DIRTY_ALLOWLIST_INVALID")
            continue
        if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
            errors.append("CANDIDATE_DIRTY_ALLOWLIST_INVALID")
            continue
        value = path.as_posix()
        if value not in normalized:
            normalized.append(value)
    return tuple(normalized), tuple(sorted(set(errors)))


def _is_sensitive_relative_path(path: str) -> bool:
    return any(
        part.startswith(".") and "env" in part.lower() or _SENSITIVE_PATH_PART_RE.search(part)
        for part in path.replace("\\", "/").split("/")
    )


def _public_dirty_path(path: str) -> str:
    return f"REDACTED:{_sha256(path.encode('utf-8'))[:16]}" if _is_sensitive_relative_path(path) else path


def _path_sha256(path: Path, *, sensitive: bool) -> str | None:
    if sensitive:
        return None
    try:
        if not path.is_file() or path.is_symlink():
            return None
        return _sha256(path.read_bytes())
    except OSError:
        return None


def _git_command(project_root: Path, arguments: Sequence[str]) -> subprocess.CompletedProcess[bytes] | None:
    try:
        return subprocess.run(
            ["git", "-C", str(project_root), *arguments],
            capture_output=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _dirty_records(project_root: Path) -> tuple[tuple[str, str], ...] | None:
    completed = _git_command(project_root, ("status", "--porcelain=v1", "-z", "--untracked-files=all"))
    if completed is None or completed.returncode != 0:
        return None
    records = completed.stdout.split(b"\0")
    dirty: list[tuple[str, str]] = []
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        if len(record) < 4:
            return None
        status = record[:2].decode("ascii", errors="replace")
        path = record[3:].decode("utf-8", errors="surrogateescape")
        dirty.append((status, path))
        if "R" in status or "C" in status:
            if index >= len(records):
                return None
            original = records[index]
            index += 1
            if original:
                dirty.append((status, original.decode("utf-8", errors="surrogateescape")))
    return tuple(dirty)


def _is_allowlisted(path: str, allowlist: Sequence[str]) -> bool:
    normalized = path.replace("\\", "/")
    return any(normalized == entry or normalized.startswith(f"{entry}/") for entry in allowlist)


def _case_map_sha256() -> str:
    return _sha256(
        _canonical_json_bytes(
            {
                "cases": [
                    {
                        "case_id": case.case_id,
                        "formal_case_id": case.formal_case_id,
                        "required_gates": sorted(case.required_gates),
                        "modes": sorted(case.modes),
                    }
                    for case in _CASES
                ],
                "offline_targets": {
                    f"{case_id}:{asset_type}": list(targets)
                    for (case_id, asset_type), targets in sorted(_OFFLINE_TESTS_BY_CASE_ASSET.items())
                },
            }
        )
    )


def _collect_candidate_evidence(
    *,
    project_root: Path,
    backend_root: Path,
    dirty_allowlist: Sequence[str],
    allowlist_errors: Sequence[str] = (),
) -> CandidateEvidence:
    """Bind the invocation to Git state and candidate-driving file hashes."""
    runner_sha = _path_sha256(Path(__file__), sensitive=False)
    dependency_sha = _path_sha256(backend_root / "pyproject.toml", sensitive=False)
    if allowlist_errors:
        return CandidateEvidence(
            valid=False,
            code=allowlist_errors[0],
            git_sha=None,
            dirty_count=0,
            unallowlisted_dirty_count=0,
            dirty_paths=(),
            dirty_allowlist=tuple(dirty_allowlist),
            runner_sha256=runner_sha,
            case_map_sha256=_case_map_sha256(),
            dependency_manifest_sha256=dependency_sha,
        )
    head = _git_command(project_root, ("rev-parse", "HEAD"))
    git_sha = (
        head.stdout.decode("ascii", errors="ignore").strip()
        if head is not None and head.returncode == 0
        else None
    )
    if not git_sha or not re.fullmatch(r"[0-9a-f]{40}", git_sha):
        return CandidateEvidence(
            valid=False,
            code="CANDIDATE_GIT_METADATA_UNAVAILABLE",
            git_sha=None,
            dirty_count=0,
            unallowlisted_dirty_count=0,
            dirty_paths=(),
            dirty_allowlist=tuple(dirty_allowlist),
            runner_sha256=runner_sha,
            case_map_sha256=_case_map_sha256(),
            dependency_manifest_sha256=dependency_sha,
        )
    dirty = _dirty_records(project_root)
    if dirty is None:
        return CandidateEvidence(
            valid=False,
            code="CANDIDATE_GIT_METADATA_UNAVAILABLE",
            git_sha=git_sha,
            dirty_count=0,
            unallowlisted_dirty_count=0,
            dirty_paths=(),
            dirty_allowlist=tuple(dirty_allowlist),
            runner_sha256=runner_sha,
            case_map_sha256=_case_map_sha256(),
            dependency_manifest_sha256=dependency_sha,
        )
    public_records: list[dict[str, object]] = []
    unallowlisted = 0
    for status, path in dirty:
        sensitive = _is_sensitive_relative_path(path)
        allowed = _is_allowlisted(path, dirty_allowlist)
        if not allowed:
            unallowlisted += 1
        public_records.append(
            {
                "path": _public_dirty_path(path),
                "status": status,
                "allowlisted": allowed,
                "content_sha256": _path_sha256(project_root / path, sensitive=sensitive),
            }
        )
    code = "CANDIDATE_CLEAN_OR_ALLOWLISTED" if not unallowlisted else "CANDIDATE_DIRTY_ALLOWLIST_REQUIRED"
    return CandidateEvidence(
        valid=not unallowlisted,
        code=code,
        git_sha=git_sha,
        dirty_count=len(dirty),
        unallowlisted_dirty_count=unallowlisted,
        dirty_paths=tuple(public_records),
        dirty_allowlist=tuple(dirty_allowlist),
        runner_sha256=runner_sha,
        case_map_sha256=_case_map_sha256(),
        dependency_manifest_sha256=dependency_sha,
    )


def _summarize_exit(cases: Sequence[Mapping[str, object]], selection_errors: Sequence[str]) -> int:
    """Apply documented precedence without treating a passing slice as a passing case."""
    if selection_errors or not cases:
        return EXIT_INCOMPLETE
    slice_statuses = {case.get("status") for case in cases}
    # ``status`` remains the mode-slice result for backwards-compatible
    # consumers.  A G1 fixture may pass while required G2/G3/G4 gates remain;
    # the process status must follow the complete formal case so CI cannot
    # accidentally treat that local slice as release acceptance.
    overall_statuses = {
        case.get("overall_case_status", case.get("status"))
        for case in cases
    }
    effective_statuses = slice_statuses | overall_statuses
    if STATUS_FAIL in effective_statuses:
        return EXIT_FAIL
    if STATUS_BLOCKED in effective_statuses:
        return EXIT_BLOCKED
    if STATUS_NOT_RUN in effective_statuses:
        return EXIT_INCOMPLETE
    return (
        EXIT_PASS
        if slice_statuses == {STATUS_PASS} and overall_statuses == {STATUS_PASS}
        else EXIT_INCOMPLETE
    )


def _summary(cases: Sequence[Mapping[str, object]]) -> dict[str, int]:
    counts = Counter(str(case.get("status")) for case in cases)
    return {status: counts.get(status, 0) for status in sorted(VALID_STATUSES)}


def _overall_summary(cases: Sequence[Mapping[str, object]]) -> dict[str, int]:
    """Count complete-case statuses separately from mode-slice statuses."""
    counts = Counter(str(case.get("overall_case_status", case.get("status"))) for case in cases)
    return {status: counts.get(status, 0) for status in sorted(VALID_STATUSES)}


def _build_result(
    *,
    mode: str,
    dry_run: bool,
    requested_case_ids: tuple[str, ...],
    requested_unknown_case_ids: tuple[str, ...],
    asset_types: frozenset[str],
    scope_evidence: ScopeEvidence | None,
    alembic_evidence: AlembicEvidence | None,
    external_gate: ExternalGate | None,
    external_source_evidence: Mapping[str, object] | None,
    candidate_evidence: CandidateEvidence,
    selection_errors: Sequence[str],
    cases: Sequence[Mapping[str, object]],
    iter196_baseline_evidence: Iter196BaselineEvidence | None = None,
) -> dict[str, object]:
    exit_code = _summarize_exit(cases, selection_errors)
    payload: dict[str, object] = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "acceptance_spec_id": ACCEPTANCE_SPEC_ID,
        "acceptance_spec_path": ACCEPTANCE_SPEC_PATH,
        "case_mapping_version": CASE_MAPPING_VERSION,
        "run_id": f"iteration197-{uuid.uuid4().hex}",
        "generated_at": _utc_now(),
        "mode": mode,
        "mode_gate": GATE_BY_MODE[mode],
        "dry_run": dry_run,
        "candidate": candidate_evidence.as_dict(),
        "selection": {
            "requested_matrix_case_ids": list(requested_case_ids),
            "requested_unknown_case_ids": list(requested_unknown_case_ids),
            "asset_types": sorted(asset_types),
            "selection_errors": list(selection_errors),
        },
        "cases": list(cases),
        "summary": _summary(cases),
        "overall_summary": _overall_summary(cases),
        "exit_code": exit_code,
    }
    if scope_evidence is not None:
        payload["scope_manifest"] = scope_evidence.as_dict()
    if alembic_evidence is not None:
        payload["alembic"] = alembic_evidence.as_dict()
    if iter196_baseline_evidence is not None:
        payload["iter196_baseline"] = iter196_baseline_evidence.as_dict()
    if external_gate is not None:
        payload["external_gate"] = external_gate.as_dict()
    if external_source_evidence is not None:
        payload["external_source_gate"] = dict(external_source_evidence)
    return payload


def run_acceptance(
    args: argparse.Namespace,
    *,
    command_runner: Callable[..., CommandResult] = _run_command,
    environment: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Run or plan one bounded acceptance mode and return its complete payload."""
    mode = str(args.mode)
    project_root = Path(args.project_root).expanduser().resolve()
    backend_root = project_root / "src" / "backend"
    manifest_path = (
        Path(args.scope_manifest).expanduser()
        if getattr(args, "scope_manifest", None) is not None
        else project_root / DEFAULT_SCOPE_MANIFEST_RELATIVE
    )
    raw_case_values = args.cases or ()
    case_values = (
        (raw_case_values,) if isinstance(raw_case_values, str) else tuple(raw_case_values)
    )
    requested_case_ids, unknown_case_ids, case_errors = _normalize_case_selection(case_values)
    asset_types, asset_errors = _normalize_asset_selection(args.asset_types)
    reporting_assets = asset_types if asset_types else ASSET_TYPES
    selected_slices, incompatible_slices = _select_slices(
        mode=mode,
        requested_case_ids=requested_case_ids,
        asset_types=reporting_assets,
        select_all_when_empty=not bool(case_values),
    )
    selection_errors = tuple(
        sorted(
            {
                *case_errors,
                *asset_errors,
                *(("ACCEPTANCE_CASE_MODE_INCOMPATIBLE",) if incompatible_slices else ()),
            }
        )
    )
    dirty_allowlist, allowlist_errors = _parse_dirty_allowlist(getattr(args, "dirty_allowlist", ()))
    candidate_evidence = _collect_candidate_evidence(
        project_root=project_root,
        backend_root=backend_root,
        dirty_allowlist=dirty_allowlist,
        allowlist_errors=allowlist_errors,
    )
    runtime_environment = os.environ if environment is None else environment

    # An invalid explicit filter must never execute the valid-looking subset.
    if selection_errors:
        cases = _static_case_results(
            slices=selected_slices,
            status=STATUS_NOT_RUN,
            code="ACCEPTANCE_SELECTION_INCOMPLETE",
        )
        cases.extend(
            _case_result(
                slice_, status=STATUS_NOT_RUN, code="ACCEPTANCE_CASE_MODE_INCOMPATIBLE", evidence=[]
            )
            for slice_ in incompatible_slices
        )
        cases.extend(
            _selection_problem_result(
                case_id=case_id,
                asset_type=asset_type,
                mode=mode,
                code="ACCEPTANCE_CASE_UNKNOWN",
            )
            for case_id in unknown_case_ids
            for asset_type in sorted(reporting_assets)
        )
        return _build_result(
            mode=mode,
            dry_run=bool(args.dry_run),
            requested_case_ids=requested_case_ids,
            requested_unknown_case_ids=unknown_case_ids,
            asset_types=reporting_assets,
            scope_evidence=None,
            alembic_evidence=None,
            external_gate=None,
            external_source_evidence=None,
            candidate_evidence=candidate_evidence,
            selection_errors=selection_errors,
            cases=cases,
        )

    if not selected_slices:
        return _build_result(
            mode=mode,
            dry_run=bool(args.dry_run),
            requested_case_ids=requested_case_ids,
            requested_unknown_case_ids=unknown_case_ids,
            asset_types=reporting_assets,
            scope_evidence=None,
            alembic_evidence=None,
            external_gate=None,
            external_source_evidence=None,
            candidate_evidence=candidate_evidence,
            selection_errors=("ACCEPTANCE_NO_VALID_CASES",),
            cases=[],
        )

    external_gate = _external_gate(mode, runtime_environment)
    if mode != MODE_OFFLINE and not external_gate.allowed:
        cases = _static_case_results(
            slices=selected_slices,
            status=STATUS_BLOCKED,
            code=external_gate.code,
        )
        return _build_result(
            mode=mode,
            dry_run=bool(args.dry_run),
            requested_case_ids=requested_case_ids,
            requested_unknown_case_ids=unknown_case_ids,
            asset_types=reporting_assets,
            scope_evidence=None,
            alembic_evidence=None,
            external_gate=external_gate,
            external_source_evidence=None,
            candidate_evidence=candidate_evidence,
            selection_errors=(),
            cases=cases,
        )

    if bool(args.dry_run):
        cases = _static_case_results(
            slices=selected_slices,
            status=STATUS_NOT_RUN,
            code="ACCEPTANCE_DRY_RUN",
        )
        return _build_result(
            mode=mode,
            dry_run=True,
            requested_case_ids=requested_case_ids,
            requested_unknown_case_ids=unknown_case_ids,
            asset_types=reporting_assets,
            scope_evidence=None,
            alembic_evidence=None,
            external_gate=external_gate if mode != MODE_OFFLINE else None,
            external_source_evidence=None,
            candidate_evidence=candidate_evidence,
            selection_errors=(),
            cases=cases,
        )

    # Candidate checks run before scope/tests so a local dirty tree cannot
    # produce an evidence artifact associated only with a stale HEAD hash.
    if not candidate_evidence.valid:
        cases = _static_case_results(
            slices=selected_slices,
            status=STATUS_NOT_RUN,
            code=candidate_evidence.code,
        )
        return _build_result(
            mode=mode,
            dry_run=False,
            requested_case_ids=requested_case_ids,
            requested_unknown_case_ids=unknown_case_ids,
            asset_types=reporting_assets,
            scope_evidence=None,
            alembic_evidence=None,
            external_gate=external_gate if mode != MODE_OFFLINE else None,
            external_source_evidence=None,
            candidate_evidence=candidate_evidence,
            selection_errors=(),
            cases=cases,
        )

    # The immutable 196/197 boundary is G0 provenance.  It runs after the
    # candidate ownership check but before manifest inspection or any child
    # test so stale or self-contradictory freeze metadata cannot mint evidence.
    iter196_baseline_evidence = _collect_iter196_baseline_evidence(project_root)
    if not iter196_baseline_evidence.valid:
        cases = _static_case_results(
            slices=selected_slices,
            status=STATUS_FAIL,
            code=iter196_baseline_evidence.code,
        )
        return _build_result(
            mode=mode,
            dry_run=False,
            requested_case_ids=requested_case_ids,
            requested_unknown_case_ids=unknown_case_ids,
            asset_types=reporting_assets,
            scope_evidence=None,
            alembic_evidence=None,
            external_gate=external_gate if mode != MODE_OFFLINE else None,
            external_source_evidence=None,
            candidate_evidence=candidate_evidence,
            selection_errors=(),
            cases=cases,
            iter196_baseline_evidence=iter196_baseline_evidence,
        )

    scope_evidence = _collect_scope_evidence(project_root, manifest_path)
    alembic_evidence = _collect_alembic_evidence(backend_root)
    if not scope_evidence.valid:
        cases = _static_case_results(slices=selected_slices, status=STATUS_FAIL, code=scope_evidence.code)
        return _build_result(
            mode=mode,
            dry_run=False,
            requested_case_ids=requested_case_ids,
            requested_unknown_case_ids=unknown_case_ids,
            asset_types=reporting_assets,
            scope_evidence=scope_evidence,
            alembic_evidence=alembic_evidence,
            external_gate=external_gate if mode != MODE_OFFLINE else None,
            external_source_evidence=None,
            candidate_evidence=candidate_evidence,
            selection_errors=(),
            cases=cases,
            iter196_baseline_evidence=iter196_baseline_evidence,
        )
    if not alembic_evidence.valid:
        cases = _static_case_results(slices=selected_slices, status=STATUS_FAIL, code=alembic_evidence.code)
        return _build_result(
            mode=mode,
            dry_run=False,
            requested_case_ids=requested_case_ids,
            requested_unknown_case_ids=unknown_case_ids,
            asset_types=reporting_assets,
            scope_evidence=scope_evidence,
            alembic_evidence=alembic_evidence,
            external_gate=external_gate if mode != MODE_OFFLINE else None,
            external_source_evidence=None,
            candidate_evidence=candidate_evidence,
            selection_errors=(),
            cases=cases,
            iter196_baseline_evidence=iter196_baseline_evidence,
        )

    external_source_evidence: dict[str, object] | None = None
    if mode == MODE_LIVE:
        source_allowed, source_code, source_evidence = _live_source_gate(
            environment=runtime_environment,
            scope_evidence=scope_evidence,
            approval_id=external_gate.approval_id or "",
            selected_slices=selected_slices,
        )
        external_source_evidence = {
            "allowed": source_allowed,
            "code": source_code,
            **source_evidence,
        }
        if not source_allowed:
            cases = _static_case_results(slices=selected_slices, status=STATUS_BLOCKED, code=source_code)
            return _build_result(
                mode=mode,
                dry_run=False,
                requested_case_ids=requested_case_ids,
                requested_unknown_case_ids=unknown_case_ids,
                asset_types=reporting_assets,
                scope_evidence=scope_evidence,
                alembic_evidence=alembic_evidence,
                external_gate=external_gate,
                external_source_evidence=external_source_evidence,
                candidate_evidence=candidate_evidence,
                selection_errors=(),
                cases=cases,
                iter196_baseline_evidence=iter196_baseline_evidence,
            )

    if mode == MODE_OFFLINE:
        result_directory = _result_path(Path(args.output)).parent
        cases = [
            _offline_case_result(
                slice_=slice_,
                backend_root=backend_root,
                result_directory=result_directory,
                command_runner=command_runner,
            )
            for slice_ in selected_slices
        ]
    else:
        # A metadata approval does not execute an external provider/database
        # path.  Registering one requires a dedicated reviewed driver and
        # evidence contract, so this remains fail-closed.
        cases = _static_case_results(
            slices=selected_slices,
            status=STATUS_BLOCKED,
            code="EXTERNAL_CASE_DRIVER_UNAVAILABLE",
        )
    return _build_result(
        mode=mode,
        dry_run=False,
        requested_case_ids=requested_case_ids,
        requested_unknown_case_ids=unknown_case_ids,
        asset_types=reporting_assets,
        scope_evidence=scope_evidence,
        alembic_evidence=alembic_evidence,
        external_gate=external_gate if mode != MODE_OFFLINE else None,
        external_source_evidence=external_source_evidence,
        candidate_evidence=candidate_evidence,
        selection_errors=(),
        cases=cases,
        iter196_baseline_evidence=iter196_baseline_evidence,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Write ``result.json`` and print a minimal non-sensitive terminal summary."""
    args = _arguments(argv)
    payload = run_acceptance(args)
    result_path = _result_path(Path(args.output))
    _write_result(result_path, payload)
    status = {
        EXIT_PASS: STATUS_PASS,
        EXIT_FAIL: STATUS_FAIL,
        EXIT_BLOCKED: STATUS_BLOCKED,
        EXIT_INCOMPLETE: STATUS_NOT_RUN,
    }[int(payload["exit_code"])]
    print(
        json.dumps(
            {
                "status": status,
                "exit_code": payload["exit_code"],
                "result_sha256": _sha256(result_path.read_bytes()),
            },
            sort_keys=True,
        )
    )
    return int(payload["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
