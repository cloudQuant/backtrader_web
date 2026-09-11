"""Safety contracts for the opt-in Iteration 197 PostgreSQL acceptance harness."""

from __future__ import annotations

import argparse
import asyncio
import json
import signal

import pytest
from sqlalchemy.engine import make_url

from scripts import verify_iteration197_postgres_acceptance as harness


def _two_process_report(
    *,
    pid: int,
    provider_call_count: int,
    initial_coverage_status: str,
    initial_fetch_count: int,
    initial_warning_codes: list[str],
    local_only_coverage_status: str = "complete",
    local_only_fetch_count: int = 0,
    local_only_observation_count: int = 2,
) -> dict[str, object]:
    return {
        "kind": "result",
        "status": "ok",
        "pid": pid,
        "provider_call_count": provider_call_count,
        "initial_coverage_status": initial_coverage_status,
        "initial_fetch_count": initial_fetch_count,
        "initial_warning_codes": initial_warning_codes,
        "initial_session_timezone": "UTC",
        "local_only_coverage_status": local_only_coverage_status,
        "local_only_fetch_count": local_only_fetch_count,
        "local_only_observation_count": local_only_observation_count,
        "local_only_session_timezone": "UTC",
    }


def _cancelled_fault_report(
    spec: harness._FaultPhaseSpec,
    *,
    release_completed: bool | None = None,
    reached_phases: list[str] | None = None,
) -> dict[str, object]:
    return {
        "kind": "fault_cancellation",
        "status": "cancelled",
        "phase": spec.phase,
        "pid": 303,
        "provider_call_count": 1,
        "reached_phases": (
            reached_phases
            if reached_phases is not None
            else list(harness._fault_reached_phases(spec))
        ),
        "lease_key_sha256": "a" * 64,
        "fence_token": 1,
        "release_started": True,
        "release_completed": (
            spec.release_expected_after_cancellation
            if release_completed is None
            else release_completed
        ),
    }


def _fault_follower_report(
    *,
    mode: str,
    provider_call_count: int,
    coverage_status: str,
    warning_codes: list[str] | None = None,
) -> dict[str, object]:
    return {
        "kind": "fault_follower",
        "status": "ok",
        "mode": mode,
        "pid": 404,
        "provider_call_count": provider_call_count,
        "fetch_count": provider_call_count,
        "coverage_status": coverage_status,
        "warning_codes": warning_codes or [],
        "observation_count": 2,
        "session_timezone": "UTC",
    }


def _stale_runner_leader_report(
    *,
    warning_codes: list[str] | None = None,
) -> dict[str, object]:
    return {
        "kind": "stale_runner_leader",
        "status": "ok",
        "pid": 505,
        "provider_call_count": 1,
        "fetch_count": 0,
        "warning_codes": (["FETCH_LEASE_FENCE_LOST"] if warning_codes is None else warning_codes),
        "session_timezone": "UTC",
    }


class _HarnessOwnedProcess:
    """Small process double for cleanup escalation contracts without a DB."""

    def __init__(
        self,
        *,
        survive_kill: bool = False,
        alive: bool = True,
        terminate_exitcode: int | None = None,
    ) -> None:
        self.pid: int | None = 701 if alive else 702
        self._alive = alive
        self._survive_kill = survive_kill
        self._terminate_exitcode = terminate_exitcode
        self.exitcode: int | None = None if alive else 1
        self.terminate_calls = 0
        self.kill_calls = 0
        self.join_timeouts: list[float] = []

    def is_alive(self) -> bool:
        return self._alive

    def terminate(self) -> None:
        self.terminate_calls += 1
        if self._terminate_exitcode is not None:
            self._alive = False
            self.exitcode = self._terminate_exitcode

    def kill(self) -> None:
        self.kill_calls += 1
        if not self._survive_kill:
            self._alive = False
            self.exitcode = -9

    def join(self, timeout: float) -> None:
        self.join_timeouts.append(timeout)


def test_admin_url_accepts_only_explicit_asyncpg_postgres_database() -> None:
    accepted = harness._parse_admin_url("postgresql+asyncpg:///postgres?host=/tmp")

    assert accepted.database == "postgres"
    with pytest.raises(harness.PostgresAcceptanceHarnessError) as non_admin:
        harness._parse_admin_url("postgresql+asyncpg:///application")
    with pytest.raises(harness.PostgresAcceptanceHarnessError) as wrong_driver:
        harness._parse_admin_url("postgresql:///postgres")
    with pytest.raises(harness.PostgresAcceptanceHarnessError) as wrong_backend:
        harness._parse_admin_url("sqlite+aiosqlite:///postgres")

    assert non_admin.value.code == "POSTGRES_ACCEPTANCE_ADMIN_DATABASE_UNSAFE"
    assert wrong_driver.value.code == "POSTGRES_ACCEPTANCE_ASYNCPG_REQUIRED"
    assert wrong_backend.value.code == "POSTGRES_ACCEPTANCE_POSTGRES_REQUIRED"


def test_temporary_database_gate_refuses_any_operator_supplied_name() -> None:
    generated = harness._temporary_database_name()

    assert harness._require_own_temporary_database(generated) == generated
    assert harness._quoted_temporary_database(generated) == f'"{generated}"'
    for unsafe_name in ("postgres", "backtrader", "iter197_pg_acceptance_short", generated.upper()):
        with pytest.raises(harness.PostgresAcceptanceHarnessError) as rejected:
            harness._require_own_temporary_database(unsafe_name)
        assert rejected.value.code == "POSTGRES_ACCEPTANCE_DATABASE_NAME_UNSAFE"


def test_target_url_cannot_be_built_for_existing_database_name() -> None:
    admin_url = make_url("postgresql+asyncpg:///postgres?host=/tmp")

    with pytest.raises(harness.PostgresAcceptanceHarnessError) as rejected:
        harness._target_url(admin_url, "postgres")

    assert rejected.value.code == "POSTGRES_ACCEPTANCE_DATABASE_NAME_UNSAFE"


def test_dry_run_has_no_connection_side_effect_and_redacts_url(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    admin_url = "postgresql+asyncpg://sensitive-user:sensitive-password@secret-host/postgres"
    monkeypatch.setattr(
        harness,
        "_arguments",
        lambda: argparse.Namespace(postgres_admin_url=admin_url, apply=False),
    )
    monkeypatch.setattr(
        harness,
        "_apply",
        lambda _: (_ for _ in ()).throw(AssertionError("dry run must not apply")),
    )

    assert harness.main() == 0

    payload = json.loads(capsys.readouterr().out)
    encoded = json.dumps(payload)
    assert payload["mode"] == "dry_run"
    assert payload["apply_required"] is True
    assert "sensitive-user" not in encoded
    assert "sensitive-password" not in encoded
    assert "secret-host" not in encoded


@pytest.mark.asyncio
async def test_cleanup_rejects_an_unsafe_name_before_opening_any_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_url = make_url("postgresql+asyncpg:///postgres?host=/tmp")
    engine_requested = False

    def fail_if_engine_requested(_):
        nonlocal engine_requested
        engine_requested = True
        raise AssertionError("unsafe names must be rejected before engine construction")

    monkeypatch.setattr(harness, "_admin_engine", fail_if_engine_requested)

    with pytest.raises(harness.PostgresAcceptanceHarnessError) as rejected:
        await harness._drop_temporary_database(admin_url, "postgres")

    assert rejected.value.code == "POSTGRES_ACCEPTANCE_DATABASE_NAME_UNSAFE"
    assert engine_requested is False


def test_alembic_url_escapes_configparser_percent_sequences() -> None:
    url = make_url("postgresql+asyncpg:///postgres?host=%2Ftmp")

    assert "%%2F" in harness._alembic_url_text(url)
    assert "?host=" in harness._alembic_url_text(url)


def test_apply_cleanup_path_is_not_exercised_without_explicit_apply() -> None:
    """The command-line default is dry run; keep the side-effect gate visible."""
    parsed = harness._parse_admin_url("postgresql+asyncpg:///postgres?host=/tmp")
    output = harness._dry_run_output(parsed)

    assert output["status"] == "ok"
    assert output["mode"] == "dry_run"
    assert output["temporary_database_prefix"] == harness.TEMPORARY_DATABASE_PREFIX
    assert not asyncio.iscoroutine(output)


@pytest.mark.asyncio
async def test_worker_cleanup_escalates_to_kill_and_requires_reap_before_return() -> None:
    process = _HarnessOwnedProcess()

    await harness._stop_two_process_workers((process,))

    assert process.terminate_calls == 1
    assert process.kill_calls == 1
    assert process.join_timeouts == [
        harness._PROCESS_EVENT_TIMEOUT_SECONDS,
        harness._PROCESS_EVENT_TIMEOUT_SECONDS,
    ]
    assert process.is_alive() is False


@pytest.mark.asyncio
async def test_worker_cleanup_fails_closed_when_a_harness_child_survives_kill() -> None:
    process = _HarnessOwnedProcess(survive_kill=True)

    with pytest.raises(harness.PostgresAcceptanceHarnessError) as rejected:
        await harness._stop_two_process_workers((process,))

    assert rejected.value.code == "POSTGRES_ACCEPTANCE_WORKER_CLEANUP_FAILED"
    assert process.terminate_calls == 1
    assert process.kill_calls == 1
    assert process.is_alive() is True


@pytest.mark.asyncio
async def test_terminated_leader_requires_parent_termination_of_a_live_worker() -> None:
    process = _HarnessOwnedProcess(terminate_exitcode=-signal.SIGTERM)

    await harness._join_terminated_fault_leader(process)

    assert process.terminate_calls == 1
    assert process.kill_calls == 0
    assert process.is_alive() is False


@pytest.mark.asyncio
async def test_terminated_leader_rejects_a_worker_that_already_died() -> None:
    process = _HarnessOwnedProcess(alive=False)

    with pytest.raises(harness.PostgresAcceptanceHarnessError) as rejected:
        await harness._join_terminated_fault_leader(process)

    assert rejected.value.code == "POSTGRES_ACCEPTANCE_FAULT_LEADER_TERMINATION_FAILED"
    assert process.terminate_calls == 0


@pytest.mark.asyncio
async def test_terminated_leader_rejects_a_non_signal_exit_after_parent_terminate() -> None:
    process = _HarnessOwnedProcess(terminate_exitcode=1)

    with pytest.raises(harness.PostgresAcceptanceHarnessError) as rejected:
        await harness._join_terminated_fault_leader(process)

    assert rejected.value.code == "POSTGRES_ACCEPTANCE_FAULT_LEADER_TERMINATION_FAILED"
    assert process.terminate_calls == 1
    assert process.kill_calls == 0


def test_apply_registers_created_database_for_cleanup_before_create_returns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_names = iter(
        (
            f"{harness.TEMPORARY_DATABASE_PREFIX}{'a' * 32}",
            f"{harness.TEMPORARY_DATABASE_PREFIX}{'b' * 32}",
        )
    )
    dropped: list[str] = []

    async def create_then_fail(
        _admin_url: object,
        database_name: str,
        *,
        on_created: object | None = None,
    ) -> None:
        assert callable(on_created)
        on_created(database_name)
        raise RuntimeError("synthetic post-create failure")

    async def record_drop(_admin_url: object, database_name: str) -> None:
        dropped.append(database_name)

    monkeypatch.setattr(harness, "_temporary_database_name", lambda: next(database_names))
    monkeypatch.setattr(harness, "_create_temporary_database", create_then_fail)
    monkeypatch.setattr(harness, "_drop_temporary_database", record_drop)

    code, output = harness._apply(make_url("postgresql+asyncpg:///postgres?host=/tmp"))

    assert code == 2
    assert output["status"] == "error"
    assert output["cleanup"] == "complete"
    assert dropped == [f"{harness.TEMPORARY_DATABASE_PREFIX}{'a' * 32}"]


def test_two_process_report_validator_requires_one_leader_and_one_follower_reread() -> None:
    leader, follower = harness._validate_two_process_worker_reports(
        (
            _two_process_report(
                pid=101,
                provider_call_count=1,
                initial_coverage_status="complete",
                initial_fetch_count=1,
                initial_warning_codes=[],
            ),
            _two_process_report(
                pid=202,
                provider_call_count=0,
                initial_coverage_status="partial",
                initial_fetch_count=0,
                initial_warning_codes=["FETCH_LEASE_HELD"],
            ),
        )
    )

    assert leader["pid"] == 101
    assert follower["pid"] == 202


@pytest.mark.parametrize(
    ("reports", "expected_code"),
    [
        (
            (
                _two_process_report(
                    pid=101,
                    provider_call_count=1,
                    initial_coverage_status="complete",
                    initial_fetch_count=1,
                    initial_warning_codes=[],
                ),
                _two_process_report(
                    pid=202,
                    provider_call_count=1,
                    initial_coverage_status="complete",
                    initial_fetch_count=1,
                    initial_warning_codes=[],
                ),
            ),
            "POSTGRES_ACCEPTANCE_TWO_PROCESS_PROVIDER_COUNT_INVALID",
        ),
        (
            (
                _two_process_report(
                    pid=101,
                    provider_call_count=1,
                    initial_coverage_status="complete",
                    initial_fetch_count=1,
                    initial_warning_codes=[],
                ),
                _two_process_report(
                    pid=202,
                    provider_call_count=0,
                    initial_coverage_status="partial",
                    initial_fetch_count=0,
                    initial_warning_codes=["FETCH_LEASE_HELD"],
                    local_only_coverage_status="partial",
                ),
            ),
            "POSTGRES_ACCEPTANCE_TWO_PROCESS_FOLLOWER_REREAD_FAILED",
        ),
    ],
)
def test_two_process_report_validator_rejects_missing_provider_or_follower_reread(
    reports: tuple[dict[str, object], dict[str, object]],
    expected_code: str,
) -> None:
    with pytest.raises(harness.PostgresAcceptanceHarnessError) as rejected:
        harness._validate_two_process_worker_reports(reports)

    assert rejected.value.code == expected_code


def test_two_process_evidence_describes_only_database_level_contention() -> None:
    evidence = harness._TwoProcessExactGapEvidence(
        process_count=2,
        distinct_process_count=2,
        provider_call_count=1,
        follower_provider_call_count=0,
        follower_initial_lease_held=True,
        follower_local_only_fetch_count=0,
        follower_local_only_complete=True,
        follower_local_only_observation_count=2,
        source_snapshot_count=1,
        observation_revision_count=2,
    )

    assert evidence.as_dict()["follower_separate_session_local_only"] == {
        "coverage_complete": True,
        "fetch_count": 0,
        "observation_count": 2,
    }


def test_fault_phase_specs_cover_runner_receipt_store_and_release_in_order() -> None:
    assert tuple(spec.phase for spec in harness._FAULT_PHASE_SPECS) == (
        "runner_started",
        "runner_receipt_ready",
        "store_before_persist",
        "store_after_persist",
        "lease_release_started",
    )
    assert len({spec.canonical_id for spec in harness._FAULT_PHASE_SPECS}) == len(
        harness._FAULT_PHASE_SPECS
    )
    assert harness.CANONICAL_ID not in {spec.canonical_id for spec in harness._FAULT_PHASE_SPECS}
    assert harness._TERMINATED_RUNNER_CANONICAL_ID not in {
        spec.canonical_id for spec in harness._FAULT_PHASE_SPECS
    }
    assert harness._STALE_RUNNER_CANONICAL_ID not in {
        harness.CANONICAL_ID,
        harness._TERMINATED_RUNNER_CANONICAL_ID,
        *(spec.canonical_id for spec in harness._FAULT_PHASE_SPECS),
    }
    assert [spec.receipt_durable_before_fault for spec in harness._FAULT_PHASE_SPECS] == [
        False,
        False,
        False,
        True,
        True,
    ]
    assert [spec.release_expected_after_cancellation for spec in harness._FAULT_PHASE_SPECS] == [
        True,
        True,
        True,
        True,
        False,
    ]


@pytest.mark.asyncio
async def test_fault_checkpoint_controller_cancels_at_exact_reviewed_phase() -> None:
    spec = harness._FAULT_PHASE_SPECS[3]
    controller = harness._FaultCheckpointController(cancellation_phase=spec.phase)

    for phase in harness._fault_reached_phases(spec)[:-1]:
        await controller.checkpoint(phase)
    with pytest.raises(asyncio.CancelledError):
        await controller.checkpoint(spec.phase)

    assert controller.reached_phases == list(harness._fault_reached_phases(spec))


def test_fault_checkpoint_controller_rejects_unreviewed_or_ambiguous_actions() -> None:
    with pytest.raises(ValueError):
        harness._FaultCheckpointController()
    with pytest.raises(ValueError):
        harness._FaultCheckpointController(
            cancellation_phase="runner_started",
            blocked_phase="runner_started",
        )
    with pytest.raises(harness.PostgresAcceptanceHarnessError) as rejected:
        harness._FaultCheckpointController(cancellation_phase="unreviewed")

    assert rejected.value.code == "POSTGRES_ACCEPTANCE_FAULT_PHASE_INVALID"


@pytest.mark.parametrize("spec", harness._FAULT_PHASE_SPECS)
def test_cancelled_fault_report_validator_requires_real_boundary_order(
    spec: harness._FaultPhaseSpec,
) -> None:
    lease_key, fence_token = harness._validate_cancelled_fault_report(
        _cancelled_fault_report(spec),
        spec=spec,
    )

    assert lease_key == "a" * 64
    assert fence_token == 1


def test_cancelled_fault_report_validator_rejects_false_release_completion() -> None:
    spec = harness._FAULT_PHASE_SPECS[-1]

    with pytest.raises(harness.PostgresAcceptanceHarnessError) as rejected:
        harness._validate_cancelled_fault_report(
            _cancelled_fault_report(spec, release_completed=True),
            spec=spec,
        )

    assert rejected.value.code == "POSTGRES_ACCEPTANCE_FAULT_REPORT_INVALID"


def test_cancelled_fault_report_validator_rejects_skipped_receipt_or_store_boundary() -> None:
    spec = harness._FAULT_PHASE_SPECS[-1]

    with pytest.raises(harness.PostgresAcceptanceHarnessError) as rejected:
        harness._validate_cancelled_fault_report(
            _cancelled_fault_report(spec, reached_phases=["runner_started"]),
            spec=spec,
        )

    assert rejected.value.code == "POSTGRES_ACCEPTANCE_FAULT_REPORT_INVALID"


def test_fault_follower_validator_distinguishes_held_lease_from_takeover() -> None:
    blocked = _fault_follower_report(
        mode="local_first",
        provider_call_count=0,
        coverage_status="incomplete",
        warning_codes=["FETCH_LEASE_HELD"],
    )
    takeover = _fault_follower_report(
        mode="local_first",
        provider_call_count=1,
        coverage_status="complete",
    )
    local_only = _fault_follower_report(
        mode="local_only",
        provider_call_count=0,
        coverage_status="complete",
    )

    assert (
        harness._validate_fault_follower_report(
            blocked,
            mode="local_first",
            provider_call_count=0,
            coverage_status="incomplete",
            lease_held=True,
        )
        == 404
    )
    assert (
        harness._validate_fault_follower_report(
            takeover,
            mode="local_first",
            provider_call_count=1,
            coverage_status="complete",
        )
        == 404
    )
    assert (
        harness._validate_fault_follower_report(
            local_only,
            mode="local_only",
            provider_call_count=0,
            coverage_status="complete",
        )
        == 404
    )


def test_stale_runner_validator_requires_a_fenced_write_rejection() -> None:
    process_id, warning_codes = harness._validate_stale_runner_leader_report(
        _stale_runner_leader_report()
    )

    assert process_id == 505
    assert "FETCH_LEASE_FENCE_LOST" in warning_codes
    with pytest.raises(harness.PostgresAcceptanceHarnessError) as rejected:
        harness._validate_stale_runner_leader_report(_stale_runner_leader_report(warning_codes=[]))
    assert rejected.value.code == "POSTGRES_ACCEPTANCE_FAULT_STALE_LEADER_INVALID"


def test_fault_evidence_labels_fixture_only_boundaries() -> None:
    cancelled = harness._CancelledFaultPhaseEvidence(
        phase="runner_started",
        leader_process_id=101,
        leader_provider_call_count=1,
        release_completed_after_cancellation=True,
        follower_process_id=102,
        follower_provider_call_count=1,
        follower_local_only_complete=False,
        source_snapshot_delta=1,
        observation_revision_delta=2,
        expired_lease_takeover_fence_token=None,
    )
    terminated = harness._TerminatedRunnerTakeoverEvidence(
        leader_process_id=201,
        blocked_follower_process_id=202,
        takeover_process_id=203,
        provider_attempt_count=2,
        blocked_follower_provider_call_count=0,
        takeover_provider_call_count=1,
        source_snapshot_delta=1,
        observation_revision_delta=2,
    )
    stale = harness._StaleRunnerTakeoverEvidence(
        leader_process_id=301,
        blocked_follower_process_id=302,
        takeover_process_id=303,
        provider_attempt_count=2,
        stale_leader_warning_codes=("FETCH_LEASE_FENCE_LOST",),
        source_snapshot_delta=1,
        observation_revision_delta=2,
    )

    assert (
        harness._FaultTakeoverEvidence(
            cancelled_phases=(cancelled,),
            stale_runner_start=stale,
            terminated_runner_start=terminated,
        ).as_dict()["fixture"]
        == "deterministic_fake_runner_no_network"
    )


def test_legacy_constraint_cases_model_postgresql_truncated_names() -> None:
    assert len(harness._LEGACY_CONSTRAINT_CASES) == 3

    for case in harness._LEGACY_CONSTRAINT_CASES:
        assert len(case.legacy_name) > harness._POSTGRES_IDENTIFIER_LIMIT
        assert len(case.postgres_truncated_legacy_name) == harness._POSTGRES_IDENTIFIER_LIMIT
        assert case.postgres_truncated_legacy_name != case.portable_name


def test_legacy_portability_evidence_reports_real_acceptance_claims() -> None:
    mapping = {
        case.postgres_truncated_legacy_name: case.portable_name
        for case in harness._LEGACY_CONSTRAINT_CASES
    }
    evidence = harness._LegacyConstraintPortabilityEvidence(
        predecessor_revision=harness._PORTABILITY_PREDECESSOR_REVISION,
        current_head="iteration197-head",
        legacy_truncated_constraint_count=3,
        portable_constraint_count=3,
        source_snapshot_count=1,
        calendar_snapshot_count=1,
        sentinels_preserved=True,
        short_digest_rejected=True,
        truncated_legacy_to_portable=mapping,
    )

    assert evidence.as_dict() == {
        "predecessor_revision": harness._PORTABILITY_PREDECESSOR_REVISION,
        "current_head": "iteration197-head",
        "legacy_truncated_constraint_count": 3,
        "portable_constraint_count": 3,
        "source_snapshot_count": 1,
        "calendar_snapshot_count": 1,
        "sentinels_preserved": True,
        "short_digest_rejected": True,
        "truncated_legacy_to_portable": mapping,
    }
