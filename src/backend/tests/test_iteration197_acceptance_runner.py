"""Independent contracts for the Iteration 197 acceptance-matrix driver."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest

from app.services.market_data.scope_manifest import build_scope_manifest, load_iter196_baseline
from scripts.acceptance import iteration197_data_platform as runner

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BASELINE_PATH = (
    PROJECT_ROOT
    / "docs/iterations/迭代197-本地优先市场数据中台/iter196-market-data-baseline-20260909.json"
)


@pytest.fixture
def valid_scope_manifest(tmp_path: Path) -> Path:
    """Build a current-checkout scope artifact instead of trusting a stale fixture."""
    manifest = build_scope_manifest(
        project_root=PROJECT_ROOT,
        iter196_baseline=load_iter196_baseline(BASELINE_PATH),
    )
    path = tmp_path / "scope-manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _args(
    tmp_path: Path,
    *,
    mode: str,
    scope_manifest: Path | None = None,
    cases: list[str] | None = None,
    asset_types: list[str] | None = None,
    dirty_allowlist: list[str] | None = None,
    dry_run: bool = False,
) -> object:
    argv = [
        "--mode",
        mode,
        "--output",
        str(tmp_path / "evidence"),
        "--project-root",
        str(PROJECT_ROOT),
    ]
    if scope_manifest is not None:
        argv.extend(["--scope-manifest", str(scope_manifest)])
    for case in cases or []:
        argv.extend(["--case", case])
    for asset_type in asset_types or []:
        argv.extend(["--asset-type", asset_type])
    for path in dirty_allowlist or []:
        argv.extend(["--dirty-allowlist", path])
    if dry_run:
        argv.append("--dry-run")
    return runner._arguments(argv)


def _approved_config(path: Path, mode: str, approval_id: str = "change-197-acceptance") -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": runner.ENVIRONMENT_SCHEMA_VERSION,
                "mode": mode,
                "environment": "isolated",
                "approval_id": approval_id,
                "approved_at": "2026-09-10T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )


def _candidate_evidence(*, valid: bool, code: str) -> runner.CandidateEvidence:
    return runner.CandidateEvidence(
        valid=valid,
        code=code,
        git_sha="a" * 40,
        dirty_count=0,
        unallowlisted_dirty_count=0,
        dirty_paths=(),
        dirty_allowlist=(),
        runner_sha256="b" * 64,
        case_map_sha256="c" * 64,
        dependency_manifest_sha256="d" * 64,
    )


def _iter196_baseline_evidence(*, valid: bool, code: str) -> runner.Iter196BaselineEvidence:
    return runner.Iter196BaselineEvidence(
        valid=valid,
        code=code,
        baseline_ref="a" * 40,
        artifact_ref="docs/freeze.md",
        artifact_sha256="b" * 64,
        merge_second_parent="a" * 40,
    )


def _allow_clean_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Decouple execution-contract tests from checkout-specific G0 state."""
    evidence = _candidate_evidence(valid=True, code="CANDIDATE_CLEAN_OR_ALLOWLISTED")
    monkeypatch.setattr(runner, "_collect_candidate_evidence", lambda **_: evidence)
    baseline = _iter196_baseline_evidence(valid=True, code="ITER196_BASELINE_PROVENANCE_VALID")
    monkeypatch.setattr(runner, "_collect_iter196_baseline_evidence", lambda _: baseline)


def _junit_path(command: Sequence[object]) -> Path:
    for value in command:
        text = str(value)
        if text.startswith("--junitxml="):
            return Path(text.removeprefix("--junitxml="))
    raise AssertionError("offline command must require a JUnit artifact")


def _write_passing_junit(command: Sequence[object]) -> None:
    path = _junit_path(command)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?><testsuite tests="1">'
        '<testcase classname="iteration197" name="deterministic" />'
        "</testsuite>",
        encoding="utf-8",
    )


def _approved_source_manifest(
    path: Path,
    scope_manifest_path: Path,
    *,
    asset_type: str,
    case_ids: list[str],
    approval_id: str = "change-197-acceptance",
) -> None:
    """Create strict metadata-only live source approval for one exact slice."""
    scope_manifest = json.loads(scope_manifest_path.read_text(encoding="utf-8"))
    family = next(
        row
        for row in scope_manifest["rows"]
        if row["asset_type"] == asset_type and row["source_policy_id"] is not None
    )
    path.write_text(
        json.dumps(
            {
                "schema_version": runner.SOURCE_MANIFEST_SCHEMA_VERSION,
                "status": "approved",
                "approval_id": approval_id,
                "approved_at": "2026-09-10T00:00:00Z",
                "scope_manifest_sha256": scope_manifest["manifest_sha256"],
                "sources": [
                    {
                        "source_id": f"approved-{asset_type}-source",
                        "source_policy_id": family["source_policy_id"],
                        "route_id": f"approved-{asset_type}-route",
                        "request_provider": "akshare",
                        "expected_result_provider_ids": ["akshare"],
                        "asset_types": [asset_type],
                        "family_ids": [family["family_id"]],
                        "data_kinds": [family["data_kind"]],
                        "frequencies": family["frequencies"],
                        "markets": ["CN-SSE"],
                        "adjustments": ["none"],
                        "price_bases": ["last"],
                        "currencies": ["CNY"],
                        "units": ["share"],
                        "provider_endpoint": "approved_fixture_endpoint",
                        "case_ids": case_ids,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_registry_covers_all_named_acceptance_cases_and_formal_matrix_ids() -> None:
    """Every documented matrix ID must resolve one-to-one without omission."""
    assert [case.case_id for case in runner._CASES] == [
        f"AC-{number:02d}" for number in range(1, 49)
    ]
    assert [case.formal_case_id for case in runner._CASES] == [
        f"AC-197-MATRIX-{number:03d}" for number in range(1, 49)
    ]
    assert set(runner._CASE_BY_FORMAL_ID) == {case.formal_case_id for case in runner._CASES}
    assert runner._CASE_BY_FORMAL_ID["AC-197-MATRIX-001"] is runner._CASE_BY_ID["AC-01"]
    assert runner.CASE_MAPPING_VERSION == "iteration197-unified-matrix-id-v4-offline-g1-coverage"
    assert set(runner.VALID_MODES) == {
        "offline",
        "integration",
        "live",
        "recovery",
        "performance",
    }
    assert runner._CASE_BY_ID["AC-46"].modes == frozenset({"performance"})
    assert "offline" in runner._CASE_BY_ID["AC-01"].modes
    assert "live" in runner._CASE_BY_ID["AC-02"].modes


def test_each_executable_mode_maps_only_to_a_formal_required_gate() -> None:
    """The matrix driver must not invent a recovery/performance gate for an AC."""
    for case in runner._CASES:
        assert {runner.GATE_BY_MODE[mode] for mode in case.modes} == case.required_gates


def test_alembic_evidence_uses_the_sealed_iteration197_checkout_tip() -> None:
    """The candidate runner accepts only its reviewed migration tip."""
    evidence = runner._collect_alembic_evidence(PROJECT_ROOT / "src/backend")

    assert evidence.valid is True
    assert evidence.code == "ALEMBIC_HEAD_AND_ANCESTRY_VALID"
    assert evidence.heads == (runner.EXPECTED_ALEMBIC_HEAD,)
    assert evidence.expected_head == runner.EXPECTED_ALEMBIC_HEAD
    assert evidence.missing_revisions == ()


def test_alembic_evidence_rejects_an_unreviewed_successor_tip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successor needs a new sealed candidate rather than silently passing this one."""
    successor_head = "20260999_reviewed_successor"

    class _SuccessorGraph:
        def get_heads(self) -> tuple[str, ...]:
            return (successor_head,)

    monkeypatch.setattr(runner.ScriptDirectory, "from_config", lambda _: _SuccessorGraph())

    evidence = runner._collect_alembic_evidence(PROJECT_ROOT / "src/backend")

    assert evidence.valid is False
    assert evidence.code == "ALEMBIC_HEAD_UNEXPECTED"
    assert evidence.heads == (successor_head,)
    assert evidence.expected_head == runner.EXPECTED_ALEMBIC_HEAD


def _current_original_receipt_bytes() -> bytes:
    """Read the immutable original receipt used by the real provenance contract."""
    value = (PROJECT_ROOT / runner.ITER196_ORIGINAL_FREEZE_RECEIPT_RELATIVE).read_bytes()
    assert runner._sha256(value) == runner.ITER196_ORIGINAL_FREEZE_RECEIPT_SHA256
    return value


def _current_correction_receipt_bytes() -> bytes:
    """Read the checked-in append-only correction receipt used by the real contract."""
    return (PROJECT_ROOT / runner.ITER196_CORRECTION_RECEIPT_RELATIVE).read_bytes()


def _write_iter196_baseline(
    project_root: Path,
    *,
    baseline_ref: str,
    correction_bytes: bytes,
    artifact_ref: str | None = None,
    original_bytes: bytes | None = None,
) -> str:
    """Write a complete receipt chain for isolated Git-provenance tests."""
    resolved_artifact_ref = (
        runner.ITER196_CORRECTION_RECEIPT_RELATIVE.as_posix()
        if artifact_ref is None
        else artifact_ref
    )
    original_path = project_root / runner.ITER196_ORIGINAL_FREEZE_RECEIPT_RELATIVE
    original_path.parent.mkdir(parents=True, exist_ok=True)
    original_path.write_bytes(
        _current_original_receipt_bytes() if original_bytes is None else original_bytes
    )
    correction_path = project_root / resolved_artifact_ref
    correction_path.parent.mkdir(parents=True, exist_ok=True)
    correction_path.write_bytes(correction_bytes)
    baseline_path = project_root / runner.DEFAULT_ITER196_BASELINE_RELATIVE
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(
        json.dumps(
            {
                "schema_version": "iter196-market-data-baseline-v1",
                "iteration": 196,
                "status": "frozen",
                "baseline_ref": baseline_ref,
                "baseline_sha256": runner._sha256(correction_bytes),
                "artifact_ref": resolved_artifact_ref,
                "frozen_at": "2026-09-09T00:34:46Z",
            }
        ),
        encoding="utf-8",
    )
    return resolved_artifact_ref


def _iter196_git_command(
    project_root: Path,
    *,
    baseline_ref: str,
    second_parent: str | None = None,
) -> Callable[[Path, Sequence[str]], subprocess.CompletedProcess[bytes]]:
    """Return deterministic Git facts for one isolated Iteration 196 chain."""
    expected_second_parent = baseline_ref if second_parent is None else second_parent

    def git_command(root: Path, arguments: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
        assert root == project_root
        if arguments == ("rev-parse", "--verify", f"{baseline_ref}^{{commit}}"):
            return subprocess.CompletedProcess(
                [], 0, stdout=f"{baseline_ref}\n".encode(), stderr=b""
            )
        if arguments == (
            "rev-parse",
            "--verify",
            f"{runner.ITER196_FREEZE_MERGE_COMMIT}^{{commit}}",
        ):
            return subprocess.CompletedProcess(
                [], 0, stdout=f"{runner.ITER196_FREEZE_MERGE_COMMIT}\n".encode(), stderr=b""
            )
        if arguments == ("show", "-s", "--format=%P", runner.ITER196_FREEZE_MERGE_COMMIT):
            return subprocess.CompletedProcess(
                [],
                0,
                stdout=f"{'b' * 40} {expected_second_parent}\n".encode(),
                stderr=b"",
            )
        pytest.fail(f"unexpected Git command: {arguments!r}")

    return git_command


def test_iter196_baseline_provenance_requires_the_fixed_append_only_receipt_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid G0 baseline binds the original receipt and its specific correction."""
    baseline_ref = runner.ITER196_IMPLEMENTATION_CANDIDATE_COMMIT
    artifact_bytes = _current_correction_receipt_bytes()
    artifact_ref = _write_iter196_baseline(
        tmp_path,
        baseline_ref=baseline_ref,
        correction_bytes=artifact_bytes,
    )
    monkeypatch.setattr(
        runner,
        "_git_command",
        _iter196_git_command(tmp_path, baseline_ref=baseline_ref),
    )

    evidence = runner._collect_iter196_baseline_evidence(tmp_path)

    assert evidence.valid is True
    assert evidence.code == "ITER196_BASELINE_PROVENANCE_VALID"
    assert evidence.baseline_ref == baseline_ref
    assert evidence.artifact_ref == artifact_ref
    assert evidence.artifact_sha256 == runner._sha256(artifact_bytes)
    assert evidence.original_receipt_sha256 == runner.ITER196_ORIGINAL_FREEZE_RECEIPT_SHA256
    assert evidence.merge_second_parent == baseline_ref


def test_iter196_baseline_provenance_rejects_an_unexpected_correction_reference(
    tmp_path: Path,
) -> None:
    """A matching hash on an arbitrary replacement receipt cannot authorize G0."""
    artifact_ref = _write_iter196_baseline(
        tmp_path,
        baseline_ref=runner.ITER196_IMPLEMENTATION_CANDIDATE_COMMIT,
        correction_bytes=_current_correction_receipt_bytes(),
        artifact_ref="docs/iteration196/replacement.md",
    )

    evidence = runner._collect_iter196_baseline_evidence(tmp_path)

    assert evidence.valid is False
    assert evidence.code == "ITER196_BASELINE_ARTIFACT_REF_UNEXPECTED"
    assert evidence.artifact_ref == artifact_ref


def test_iter196_baseline_provenance_rejects_a_changed_original_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The correction cannot rewrite the immutable contents of the original receipt."""
    baseline_ref = runner.ITER196_IMPLEMENTATION_CANDIDATE_COMMIT
    _write_iter196_baseline(
        tmp_path,
        baseline_ref=baseline_ref,
        correction_bytes=_current_correction_receipt_bytes(),
        original_bytes=b"modified original receipt\n",
    )
    monkeypatch.setattr(
        runner,
        "_git_command",
        _iter196_git_command(tmp_path, baseline_ref=baseline_ref),
    )

    evidence = runner._collect_iter196_baseline_evidence(tmp_path)

    assert evidence.valid is False
    assert evidence.code == "ITER196_BASELINE_ORIGINAL_RECEIPT_SHA256_MISMATCH"
    assert evidence.original_receipt_sha256 == runner._sha256(b"modified original receipt\n")


def test_iter196_baseline_provenance_rejects_a_correction_without_the_second_parent_relation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The correction hash alone is insufficient without its explicit historical relation."""
    baseline_ref = runner.ITER196_IMPLEMENTATION_CANDIDATE_COMMIT
    _write_iter196_baseline(
        tmp_path,
        baseline_ref=baseline_ref,
        correction_bytes=b"append-only receipt without required relationship\n",
    )
    monkeypatch.setattr(
        runner,
        "_git_command",
        _iter196_git_command(tmp_path, baseline_ref=baseline_ref),
    )

    evidence = runner._collect_iter196_baseline_evidence(tmp_path)

    assert evidence.valid is False
    assert evidence.code == "ITER196_BASELINE_CORRECTION_RECEIPT_RELATION_INVALID"


def test_iter196_baseline_provenance_rejects_a_different_merge_second_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reachable receipt cannot substitute for the exact frozen implementation candidate."""
    baseline_ref = runner.ITER196_IMPLEMENTATION_CANDIDATE_COMMIT
    other_parent = "c" * 40
    _write_iter196_baseline(
        tmp_path,
        baseline_ref=baseline_ref,
        correction_bytes=_current_correction_receipt_bytes(),
    )
    monkeypatch.setattr(
        runner,
        "_git_command",
        _iter196_git_command(
            tmp_path,
            baseline_ref=baseline_ref,
            second_parent=other_parent,
        ),
    )

    evidence = runner._collect_iter196_baseline_evidence(tmp_path)

    assert evidence.valid is False
    assert evidence.code == "ITER196_BASELINE_MERGE_SECOND_PARENT_MISMATCH"
    assert evidence.baseline_ref == baseline_ref
    assert evidence.merge_second_parent == other_parent


def test_recovery_is_incompatible_for_a_formal_g2_only_case(tmp_path: Path) -> None:
    """A recovery invocation must not manufacture G4 evidence for AC-19."""
    result = runner.run_acceptance(
        _args(
            tmp_path,
            mode="recovery",
            cases=["AC-19"],
            asset_types=["stock"],
            dry_run=True,
        )
    )

    assert result["exit_code"] == runner.EXIT_INCOMPLETE
    assert result["selection"]["selection_errors"] == ["ACCEPTANCE_CASE_MODE_INCOMPATIBLE"]
    assert result["cases"] == [
        {
            "case_id": "AC-19",
            "formal_case_id": "AC-197-MATRIX-019",
            "case_mapping_version": runner.CASE_MAPPING_VERSION,
            "case_key": "AC-19:stock:G4",
            "asset_type": "stock",
            "asset_types": ["stock"],
            "required": True,
            "required_gates": ["G2"],
            "mode_gate": "G4",
            "mode_slice_status": "NOT_RUN",
            "overall_case_status": "NOT_RUN",
            "satisfied_gates": [],
            "remaining_gates": ["G2"],
            "status": "NOT_RUN",
            "code": "ACCEPTANCE_CASE_MODE_INCOMPATIBLE",
            "evidence": [],
        }
    ]


def test_formal_case_selection_emits_one_result_per_case_asset_gate_slice(tmp_path: Path) -> None:
    """Formal IDs must preserve exact case identity and never aggregate asset evidence."""
    result = runner.run_acceptance(
        _args(
            tmp_path,
            mode="offline",
            cases=["AC-197-MATRIX-001"],
            asset_types=["stock,fund"],
            dry_run=True,
        )
    )

    assert result["exit_code"] == runner.EXIT_INCOMPLETE
    assert result["selection"] == {
        "requested_matrix_case_ids": ["AC-01"],
        "requested_unknown_case_ids": [],
        "asset_types": ["fund", "stock"],
        "selection_errors": [],
    }
    assert result["summary"] == {"BLOCKED": 0, "FAIL": 0, "NOT_RUN": 2, "PASS": 0}
    assert [
        (case["formal_case_id"], case["asset_type"], case["case_key"], case["mode_gate"])
        for case in result["cases"]
    ] == [
        ("AC-197-MATRIX-001", "fund", "AC-01:fund:G1", "G1"),
        ("AC-197-MATRIX-001", "stock", "AC-01:stock:G1", "G1"),
    ]
    assert all(case["code"] == "ACCEPTANCE_DRY_RUN" for case in result["cases"])
    assert all(
        case["case_mapping_version"] == runner.CASE_MAPPING_VERSION for case in result["cases"]
    )


def test_offline_dry_run_emits_not_run_slices_and_never_invokes_a_case_command(
    tmp_path: Path,
) -> None:
    """Planning remains non-executing even when each selected asset has a result row."""
    commands: list[tuple[tuple[str, ...], Mapping[str, str]]] = []

    def command_runner(command, *, cwd, environment):
        del cwd
        commands.append((tuple(command), dict(environment)))
        pytest.fail("dry-run must not execute a child command")

    result = runner.run_acceptance(
        _args(
            tmp_path,
            mode="offline",
            cases=["AC-01"],
            asset_types=["stock,fund"],
            dry_run=True,
        ),
        command_runner=command_runner,
    )

    assert result["exit_code"] == runner.EXIT_INCOMPLETE
    assert result["summary"] == {"BLOCKED": 0, "FAIL": 0, "NOT_RUN": 2, "PASS": 0}
    assert [case["case_key"] for case in result["cases"]] == ["AC-01:fund:G1", "AC-01:stock:G1"]
    assert commands == []


def test_offline_case_uses_child_socket_audit_and_required_junit_evidence(
    tmp_path: Path,
    valid_scope_manifest: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A G1 PASS needs deterministic pytest, JUnit facts, and zero audited network attempts."""
    _allow_clean_candidate(monkeypatch)
    captured: dict[str, object] = {}

    def command_runner(command, *, cwd, environment):
        captured["command"] = tuple(command)
        captured["cwd"] = cwd
        captured["environment"] = dict(environment)
        guard_path = Path(str(environment["PYTHONPATH"]).split(":")[0]) / "sitecustomize.py"
        assert guard_path.is_file()
        guard_source = guard_path.read_text(encoding="utf-8")
        assert "ITER197_OFFLINE_NETWORK_DENIED" in guard_source
        assert environment["ITER197_OFFLINE_NETWORK_DISABLED"] == "1"
        assert environment["NO_PROXY"] == "*"
        _write_passing_junit(command)
        return runner.CommandResult(returncode=0, elapsed_ms=17)

    result = runner.run_acceptance(
        _args(
            tmp_path,
            mode="offline",
            scope_manifest=valid_scope_manifest,
            cases=["AC-01"],
            asset_types=["stock"],
        ),
        command_runner=command_runner,
    )

    # The G1 pytest slice passed, but AC-01 also requires G2.  The process
    # exit must stay incomplete so CI cannot mistake this local proof for
    # complete acceptance.
    assert result["exit_code"] == runner.EXIT_INCOMPLETE
    case = result["cases"][0]
    assert case["status"] == "PASS"
    assert case["code"] == "OFFLINE_PYTEST_PASSED"
    assert case["formal_case_id"] == "AC-197-MATRIX-001"
    assert case["case_key"] == "AC-01:stock:G1"
    assert case["asset_type"] == "stock"
    assert case["required_gates"] == ["G1", "G2"]
    assert case["satisfied_gates"] == ["G1"]
    assert case["remaining_gates"] == ["G2"]
    assert case["overall_case_status"] == "NOT_RUN"
    assert case["overall_case_code"] == "ACCEPTANCE_OTHER_REQUIRED_GATES_PENDING"
    assert result["summary"] == {"BLOCKED": 0, "FAIL": 0, "NOT_RUN": 0, "PASS": 1}
    assert result["overall_summary"] == {"BLOCKED": 0, "FAIL": 0, "NOT_RUN": 1, "PASS": 0}
    assert case["evidence"] == [
        {
            "kind": "pytest_junit",
            "network_policy": "python_child_socket_audit_guard",
            "network_attempt_count": 0,
            "path": "tests/AC-01-stock.xml",
            "testcase_count": 1,
            "failures": 0,
            "errors": 0,
            "skipped": 0,
        }
    ]
    command = captured["command"]
    assert command[:6] == (
        runner.sys.executable,
        "-m",
        "pytest",
        "-q",
        "-p",
        "pytest_asyncio.plugin",
    )
    assert (
        "tests/market_data_platform/test_local_first_persistence.py::"
        "test_local_first_persists_once_then_reuses_complete_older_revision_without_network"
    ) in command
    assert any(str(value).startswith("--junitxml=") for value in command)


def test_ac17_offline_driver_binds_each_asset_to_runner_and_exact_source_boundary(
    tmp_path: Path,
    valid_scope_manifest: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-17 records G1 policy/runner proof without treating it as G3 source success."""
    _allow_clean_candidate(monkeypatch)
    commands_by_asset: dict[str, tuple[object, ...]] = {}

    def command_runner(command, *, cwd, environment):
        del cwd, environment
        asset_type = _junit_path(command).stem.removeprefix("AC-17-")
        commands_by_asset[asset_type] = tuple(command[6:-1])
        _write_passing_junit(command)
        return runner.CommandResult(returncode=0, elapsed_ms=13)

    result = runner.run_acceptance(
        _args(
            tmp_path,
            mode="offline",
            scope_manifest=valid_scope_manifest,
            cases=["AC-17"],
            asset_types=["all"],
        ),
        command_runner=command_runner,
    )

    expected_targets = {
        asset_type: runner._OFFLINE_TESTS_BY_CASE_ASSET[("AC-17", asset_type)]
        for asset_type in ("stock", "futures", "bond", "fund", "option", "fx", "crypto")
    }
    assert result["exit_code"] == runner.EXIT_INCOMPLETE
    assert commands_by_asset == expected_targets
    assert all(runner._OPENBB_RUNNER_G1_TARGET in targets for targets in expected_targets.values())
    assert all(
        runner._OPENBB_RUNNER_SOCKET_G1_TARGET in targets for targets in expected_targets.values()
    )
    assert expected_targets["futures"][0].endswith("[cn-futures-rb]")
    assert expected_targets["bond"][0].endswith("[cn-convertible-bond]")
    assert expected_targets["fx"][0].endswith("[cnh-pair]")
    assert all(
        case["status"] == "PASS"
        and case["code"] == "OFFLINE_PYTEST_PASSED"
        and case["formal_case_id"] == "AC-197-MATRIX-017"
        and case["required_gates"] == ["G1", "G3"]
        and case["satisfied_gates"] == ["G1"]
        and case["remaining_gates"] == ["G3"]
        and case["overall_case_status"] == "NOT_RUN"
        and case["overall_case_code"] == "ACCEPTANCE_OTHER_REQUIRED_GATES_PENDING"
        for case in result["cases"]
    )
    assert result["summary"] == {"BLOCKED": 0, "FAIL": 0, "NOT_RUN": 0, "PASS": 7}
    assert result["overall_summary"] == {"BLOCKED": 0, "FAIL": 0, "NOT_RUN": 7, "PASS": 0}


def test_ac36_offline_is_not_run_without_research_or_b2_fixture_evidence(
    tmp_path: Path,
    valid_scope_manifest: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The formal sealed-URI case cannot mint G1 evidence from local fixture tests."""
    _allow_clean_candidate(monkeypatch)
    command_calls: list[object] = []
    result = runner.run_acceptance(
        _args(
            tmp_path,
            mode="offline",
            scope_manifest=valid_scope_manifest,
            cases=["AC-197-MATRIX-036"],
            asset_types=["all"],
        ),
        command_runner=lambda *args, **kwargs: command_calls.append((args, kwargs)),
    )

    assert result["exit_code"] == runner.EXIT_INCOMPLETE
    assert command_calls == []
    assert [case["case_key"] for case in result["cases"]] == [
        "AC-36:bond:G1",
        "AC-36:crypto:G1",
        "AC-36:fund:G1",
        "AC-36:futures:G1",
        "AC-36:fx:G1",
        "AC-36:option:G1",
        "AC-36:stock:G1",
    ]
    assert all(case["formal_case_id"] == "AC-197-MATRIX-036" for case in result["cases"])
    assert all(case["status"] == "NOT_RUN" for case in result["cases"])
    assert all(case["overall_case_status"] == "NOT_RUN" for case in result["cases"])
    assert all(case["code"] == "OFFLINE_ASSET_CASE_DRIVER_UNAVAILABLE" for case in result["cases"])
    assert all(case["evidence"] == [] for case in result["cases"])
    assert not any(
        case_id == "AC-36" for case_id, _asset_type in runner._OFFLINE_TESTS_BY_CASE_ASSET
    )


def test_offline_network_guard_blocks_tcp_and_writes_an_audit_record() -> None:
    """The child-level guard rejects a socket call before any endpoint is contacted."""
    script = """
import socket
try:
    socket.create_connection(("198.51.100.1", 443), timeout=0.1)
except OSError as exc:
    raise SystemExit(0 if str(exc) == "ITER197_OFFLINE_NETWORK_DENIED" else 1)
raise SystemExit(1)
"""
    with runner._offline_network_environment(runner.BACKEND_ROOT) as (environment, audit_path):
        completed = subprocess.run(
            [sys.executable, "-c", script],
            env=environment,
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
        audit = runner._read_network_audit(audit_path)

    assert completed.returncode == 0
    assert audit == ("socket.create_connection",)


def test_offline_zero_exit_without_junit_is_fail_closed(
    tmp_path: Path,
    valid_scope_manifest: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A subprocess return code alone is not valid acceptance evidence."""
    _allow_clean_candidate(monkeypatch)
    result = runner.run_acceptance(
        _args(
            tmp_path,
            mode="offline",
            scope_manifest=valid_scope_manifest,
            cases=["AC-01"],
            asset_types=["stock"],
        ),
        command_runner=lambda *args, **kwargs: runner.CommandResult(returncode=0, elapsed_ms=9),
    )

    assert result["exit_code"] == runner.EXIT_FAIL
    assert result["cases"][0]["status"] == "FAIL"
    assert result["cases"][0]["code"] == "OFFLINE_JUNIT_EVIDENCE_INVALID"


def test_offline_network_audit_attempt_is_fail_even_with_passing_junit(
    tmp_path: Path,
    valid_scope_manifest: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A forbidden socket attempt must override a green child return code and JUnit file."""
    _allow_clean_candidate(monkeypatch)

    def command_runner(command, *, cwd, environment):
        del cwd
        _write_passing_junit(command)
        Path(environment["ITER197_OFFLINE_NETWORK_AUDIT_FILE"]).write_text(
            "socket.connect\n", encoding="utf-8"
        )
        return runner.CommandResult(returncode=0, elapsed_ms=11)

    result = runner.run_acceptance(
        _args(
            tmp_path,
            mode="offline",
            scope_manifest=valid_scope_manifest,
            cases=["AC-01"],
            asset_types=["stock"],
        ),
        command_runner=command_runner,
    )

    assert result["exit_code"] == runner.EXIT_FAIL
    case = result["cases"][0]
    assert case["status"] == "FAIL"
    assert case["code"] == "OFFLINE_NETWORK_ATTEMPT_DETECTED"
    assert case["evidence"][0]["network_attempt_count"] == 1


def test_offline_command_failure_is_fail_after_valid_junit(
    tmp_path: Path,
    valid_scope_manifest: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A deterministic test failure preserves the required FAIL exit code."""
    _allow_clean_candidate(monkeypatch)

    def command_runner(command, *, cwd, environment):
        del cwd, environment
        _write_passing_junit(command)
        return runner.CommandResult(returncode=1, elapsed_ms=9)

    result = runner.run_acceptance(
        _args(
            tmp_path,
            mode="offline",
            scope_manifest=valid_scope_manifest,
            cases=["AC-01"],
            asset_types=["stock"],
        ),
        command_runner=command_runner,
    )

    assert result["exit_code"] == runner.EXIT_FAIL
    assert result["cases"][0]["status"] == "FAIL"
    assert result["cases"][0]["code"] == "OFFLINE_PYTEST_FAILED"


def test_dirty_candidate_requires_explicit_allowlist_and_redacts_sensitive_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dirty files bind an execution run to candidate ownership before any test starts."""
    dirty_records = (
        (" M", "src/backend/app/services/example.py"),
        ("??", ".env"),
    )
    monkeypatch.setattr(runner, "_dirty_records", lambda project_root: dirty_records)

    missing = runner._collect_candidate_evidence(
        project_root=PROJECT_ROOT,
        backend_root=PROJECT_ROOT / "src/backend",
        dirty_allowlist=(),
    )
    partial = runner._collect_candidate_evidence(
        project_root=PROJECT_ROOT,
        backend_root=PROJECT_ROOT / "src/backend",
        dirty_allowlist=("src/backend",),
    )
    allowed = runner._collect_candidate_evidence(
        project_root=PROJECT_ROOT,
        backend_root=PROJECT_ROOT / "src/backend",
        dirty_allowlist=("src/backend", ".env"),
    )

    assert missing.valid is False
    assert missing.code == "CANDIDATE_DIRTY_ALLOWLIST_REQUIRED"
    assert missing.dirty_count == 2
    assert missing.unallowlisted_dirty_count == 2
    assert partial.valid is False
    assert partial.unallowlisted_dirty_count == 1
    assert allowed.valid is True
    assert allowed.code == "CANDIDATE_CLEAN_OR_ALLOWLISTED"
    assert allowed.unallowlisted_dirty_count == 0
    assert allowed.dirty_paths[0]["path"] == "src/backend/app/services/example.py"
    assert allowed.dirty_paths[1]["path"].startswith("REDACTED:")
    assert allowed.dirty_paths[1]["content_sha256"] is None


def test_non_dry_run_stops_before_scope_or_command_when_dirty_paths_are_unallowlisted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The runner must not emit test evidence when candidate ownership is unresolved."""
    dirty = _candidate_evidence(valid=False, code="CANDIDATE_DIRTY_ALLOWLIST_REQUIRED")
    monkeypatch.setattr(runner, "_collect_candidate_evidence", lambda **_: dirty)

    result = runner.run_acceptance(
        _args(tmp_path, mode="offline", cases=["AC-01"], asset_types=["stock"]),
        command_runner=lambda *args, **kwargs: pytest.fail(
            "dirty candidate must stop before pytest"
        ),
    )

    assert result["exit_code"] == runner.EXIT_INCOMPLETE
    assert result["candidate"]["code"] == "CANDIDATE_DIRTY_ALLOWLIST_REQUIRED"
    assert result["cases"][0]["status"] == "NOT_RUN"
    assert result["cases"][0]["code"] == "CANDIDATE_DIRTY_ALLOWLIST_REQUIRED"
    assert "scope_manifest" not in result


def test_unknown_and_mode_incompatible_case_selection_are_incomplete_and_not_dropped(
    tmp_path: Path,
) -> None:
    """Invalid selection keeps exact problem slices instead of defaulting to a broad run."""
    unknown = runner.run_acceptance(
        _args(tmp_path, mode="offline", cases=["AC-99"], asset_types=["fund"], dry_run=True)
    )
    safe_unknown_id = runner._safe_unknown_case_id("AC-99")
    assert unknown["exit_code"] == runner.EXIT_INCOMPLETE
    assert unknown["selection"]["selection_errors"] == ["ACCEPTANCE_CASE_UNKNOWN"]
    assert unknown["cases"] == [
        {
            "asset_type": "fund",
            "asset_types": ["fund"],
            "case_id": safe_unknown_id,
            "case_key": f"{safe_unknown_id}:fund:G1",
            "case_mapping_version": runner.CASE_MAPPING_VERSION,
            "code": "ACCEPTANCE_CASE_UNKNOWN",
            "evidence": [],
            "formal_case_id": None,
            "mode_gate": "G1",
            "mode_slice_status": "NOT_RUN",
            "overall_case_status": "NOT_RUN",
            "remaining_gates": [],
            "required": True,
            "required_gates": [],
            "satisfied_gates": [],
            "status": "NOT_RUN",
        }
    ]

    incompatible = runner.run_acceptance(
        _args(tmp_path, mode="offline", cases=["AC-02"], asset_types=["stock"], dry_run=True)
    )
    assert incompatible["exit_code"] == runner.EXIT_INCOMPLETE
    assert incompatible["selection"]["selection_errors"] == ["ACCEPTANCE_CASE_MODE_INCOMPATIBLE"]
    assert incompatible["cases"][0]["formal_case_id"] == "AC-197-MATRIX-002"
    assert incompatible["cases"][0]["case_key"] == "AC-02:stock:G1"
    assert incompatible["cases"][0]["code"] == "ACCEPTANCE_CASE_MODE_INCOMPATIBLE"


def test_invalid_asset_filter_is_incomplete_without_scope_or_provider_work(tmp_path: Path) -> None:
    """Unknown types cannot broaden a case to every asset family."""
    result = runner.run_acceptance(
        _args(tmp_path, mode="offline", cases=["AC-01"], asset_types=["stock,unknown"])
    )

    assert result["exit_code"] == runner.EXIT_INCOMPLETE
    assert result["selection"]["selection_errors"] == ["ACCEPTANCE_ASSET_TYPE_UNKNOWN"]
    assert all(case["code"] == "ACCEPTANCE_SELECTION_INCOMPLETE" for case in result["cases"])


def test_live_missing_explicit_approval_is_blocked_before_scope_or_command(
    tmp_path: Path,
) -> None:
    """An absent external authorization cannot look like a valid live acceptance run."""
    invoked = False

    def command_runner(*args, **kwargs):
        nonlocal invoked
        invoked = True
        pytest.fail("live gate failure must precede every child command")

    result = runner.run_acceptance(
        _args(tmp_path, mode="live", cases=["AC-02"], asset_types=["stock"]),
        command_runner=command_runner,
        environment={},
    )

    assert result["exit_code"] == runner.EXIT_BLOCKED
    assert result["external_gate"] == {
        "allowed": False,
        "code": "ACCEPTANCE_EXTERNAL_APPROVAL_REQUIRED",
    }
    assert result["cases"][0]["status"] == "BLOCKED"
    assert result["cases"][0]["code"] == "ACCEPTANCE_EXTERNAL_APPROVAL_REQUIRED"
    assert invoked is False


def test_external_configuration_requires_an_isolated_timezone_aware_approval_envelope(
    tmp_path: Path,
) -> None:
    """A loose JSON file or naive timestamp cannot authorize an external mode."""
    config_path = tmp_path / "integration-config.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": runner.ENVIRONMENT_SCHEMA_VERSION,
                "mode": "integration",
                "environment": "isolated",
                "approval_id": "change-197-acceptance",
                "approved_at": "2026-09-10T00:00:00",
            }
        ),
        encoding="utf-8",
    )
    result = runner.run_acceptance(
        _args(tmp_path, mode="integration", cases=["AC-02"], asset_types=["stock"]),
        environment={
            "ITER197_INTEGRATION_APPROVAL": "approved",
            "ITER197_INTEGRATION_CONFIG": str(config_path),
        },
    )

    assert result["exit_code"] == runner.EXIT_BLOCKED
    assert result["external_gate"] == {
        "allowed": False,
        "code": "ACCEPTANCE_ENVIRONMENT_CONFIG_INVALID",
    }


def test_live_approved_environment_still_requires_a_bound_source_manifest(
    tmp_path: Path,
    valid_scope_manifest: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A generic approval envelope cannot authorize live provider access by itself."""
    _allow_clean_candidate(monkeypatch)
    config_path = tmp_path / "live-config.json"
    _approved_config(config_path, "live")
    result = runner.run_acceptance(
        _args(
            tmp_path,
            mode="live",
            scope_manifest=valid_scope_manifest,
            cases=["AC-02"],
            asset_types=["stock"],
        ),
        environment={
            "ITER197_LIVE_APPROVAL": "approved",
            "ITER197_LIVE_CONFIG": str(config_path),
        },
    )

    assert result["exit_code"] == runner.EXIT_BLOCKED
    assert result["external_gate"]["allowed"] is True
    assert result["external_source_gate"] == {
        "allowed": False,
        "code": "ACCEPTANCE_SOURCE_MANIFEST_REQUIRED",
    }
    assert result["cases"][0]["code"] == "ACCEPTANCE_SOURCE_MANIFEST_REQUIRED"


def test_live_source_manifest_must_cover_the_exact_case_asset_slice(
    tmp_path: Path,
    valid_scope_manifest: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stock route approved for a different AC cannot silently cover AC-02 stock."""
    _allow_clean_candidate(monkeypatch)
    config_path = tmp_path / "live-config.json"
    source_path = tmp_path / "approved-sources.json"
    _approved_config(config_path, "live")
    _approved_source_manifest(
        source_path, valid_scope_manifest, asset_type="stock", case_ids=["AC-15"]
    )

    result = runner.run_acceptance(
        _args(
            tmp_path,
            mode="live",
            scope_manifest=valid_scope_manifest,
            cases=["AC-02"],
            asset_types=["stock"],
        ),
        environment={
            "ITER197_LIVE_APPROVAL": "approved",
            "ITER197_LIVE_CONFIG": str(config_path),
            "ITER197_LIVE_SOURCE_MANIFEST": str(source_path),
        },
    )

    assert result["exit_code"] == runner.EXIT_BLOCKED
    assert result["external_source_gate"]["allowed"] is False
    assert result["external_source_gate"]["code"] == "ACCEPTANCE_SOURCE_MANIFEST_SCOPE_INSUFFICIENT"
    assert result["external_source_gate"]["uncovered_case_keys"] == ["AC-02:stock:G3"]
    assert result["cases"][0]["code"] == "ACCEPTANCE_SOURCE_MANIFEST_SCOPE_INSUFFICIENT"


def test_live_valid_approval_never_becomes_pass_without_a_reviewed_case_driver(
    tmp_path: Path,
    valid_scope_manifest: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid source approval is a prerequisite, not live execution evidence."""
    _allow_clean_candidate(monkeypatch)
    config_path = tmp_path / "live-config.json"
    source_path = tmp_path / "approved-sources.json"
    _approved_config(config_path, "live")
    _approved_source_manifest(
        source_path, valid_scope_manifest, asset_type="stock", case_ids=["AC-02"]
    )
    command_calls: list[object] = []
    result = runner.run_acceptance(
        _args(
            tmp_path,
            mode="live",
            scope_manifest=valid_scope_manifest,
            cases=["AC-02"],
            asset_types=["stock"],
        ),
        command_runner=lambda *args, **kwargs: command_calls.append((args, kwargs)),
        environment={
            "ITER197_LIVE_APPROVAL": "approved",
            "ITER197_LIVE_CONFIG": str(config_path),
            "ITER197_LIVE_SOURCE_MANIFEST": str(source_path),
        },
    )

    assert result["exit_code"] == runner.EXIT_BLOCKED
    assert result["external_source_gate"]["allowed"] is True
    assert result["external_source_gate"]["code"] == "ACCEPTANCE_SOURCE_MANIFEST_APPROVED"
    assert result["cases"][0]["status"] == "BLOCKED"
    assert result["cases"][0]["code"] == "EXTERNAL_CASE_DRIVER_UNAVAILABLE"
    assert command_calls == []


def test_scope_drift_is_a_fail_not_a_provider_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tampered/stale scope evidence fails local acceptance before any test target runs."""
    _allow_clean_candidate(monkeypatch)
    bad_scope = tmp_path / "bad-scope.json"
    bad_scope.write_text("{}", encoding="utf-8")
    result = runner.run_acceptance(
        _args(
            tmp_path,
            mode="offline",
            scope_manifest=bad_scope,
            cases=["AC-01"],
            asset_types=["stock"],
        ),
        command_runner=lambda *args, **kwargs: pytest.fail("scope drift must stop first"),
    )

    assert result["exit_code"] == runner.EXIT_FAIL
    assert result["scope_manifest"]["valid"] is False
    assert result["cases"][0]["status"] == "FAIL"
    assert result["cases"][0]["code"] in {
        "SCOPE_MANIFEST_INVALID",
        "SCOPE_MANIFEST_VALIDATION_FAILED",
    }


def test_invalid_iter196_baseline_stops_before_scope_or_child_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """G0 provenance is a fail-closed prerequisite for every non-dry local slice."""
    _allow_clean_candidate(monkeypatch)
    rejected = _iter196_baseline_evidence(
        valid=False,
        code="ITER196_BASELINE_REF_UNRESOLVABLE",
    )
    monkeypatch.setattr(runner, "_collect_iter196_baseline_evidence", lambda _: rejected)
    monkeypatch.setattr(
        runner,
        "_collect_scope_evidence",
        lambda *_: pytest.fail("G0 failure must precede scope validation"),
    )

    result = runner.run_acceptance(
        _args(tmp_path, mode="offline", cases=["AC-01"], asset_types=["stock"]),
        command_runner=lambda *args, **kwargs: pytest.fail("G0 failure must precede pytest"),
    )

    assert result["exit_code"] == runner.EXIT_FAIL
    assert result["iter196_baseline"] == rejected.as_dict()
    assert "scope_manifest" not in result
    assert result["cases"][0]["status"] == "FAIL"
    assert result["cases"][0]["code"] == "ITER196_BASELINE_REF_UNRESOLVABLE"


def test_main_writes_result_json_and_keeps_missing_live_configuration_non_sensitive(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CLI summary has no configuration values and the artifact has the required shape."""
    monkeypatch.delenv("ITER197_LIVE_APPROVAL", raising=False)
    monkeypatch.delenv("ITER197_LIVE_CONFIG", raising=False)
    monkeypatch.delenv("ITER197_LIVE_SOURCE_MANIFEST", raising=False)
    output = tmp_path / "nested" / "result.json"
    exit_code = runner.main(["--mode", "live", "--case", "AC-02", "--output", str(output)])

    assert exit_code == runner.EXIT_BLOCKED
    printed = json.loads(capsys.readouterr().out)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert printed["status"] == "BLOCKED"
    assert "result_sha256" in printed
    assert payload["schema_version"] == runner.RESULT_SCHEMA_VERSION
    assert payload["acceptance_spec_id"] == runner.ACCEPTANCE_SPEC_ID
    assert payload["exit_code"] == runner.EXIT_BLOCKED
    assert all(case["status"] == "BLOCKED" for case in payload["cases"])
    assert "ITER197_LIVE_CONFIG" not in json.dumps(payload)
