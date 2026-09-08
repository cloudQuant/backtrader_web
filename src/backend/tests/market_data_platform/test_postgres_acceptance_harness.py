"""Safety contracts for the opt-in Iteration 197 PostgreSQL acceptance harness."""

from __future__ import annotations

import argparse
import asyncio
import json

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
