"""Offline contracts for the opt-in Iteration 197 AkShare acceptance harness."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from importlib import import_module

import pytest

from app.services.market_data import akshare_provider
from app.services.market_data.providers import (
    MarketDataProviderRequest,
    ProviderFetchResult,
    ProviderMarketObservation,
)

harness = import_module("scripts.accept_iteration197_akshare_stock_liquidity")
UTC = timezone.utc


class _FakeAkShareProvider:
    """A bounded exact-route provider; no test contacts AkShare."""

    def __init__(self) -> None:
        self.requests: list[MarketDataProviderRequest] = []

    async def fetch(self, request: MarketDataProviderRequest) -> ProviderFetchResult:
        self.requests.append(request)
        return ProviderFetchResult(
            provider_id="akshare",
            source_revision="offline-harness-fixture-v1",
            retrieved_at=datetime.now(UTC),
            observations=(
                ProviderMarketObservation(
                    event_at=request.start_at,
                    available_at=request.start_at + timedelta(hours=8),
                    fields={"volume": 1000, "turnover": 25000.0, "turnover_rate": 0.1},
                ),
            ),
            raw_payload={
                "access_token": "must-never-appear-in-summary",
                "response_rows": [{"sensitive_source_value": "must-never-appear-in-summary"}],
            },
            request=request,
        )


class _EmptyAkShareProvider:
    """Exercise the source-empty live failure without network traffic."""

    async def fetch(self, request: MarketDataProviderRequest) -> ProviderFetchResult:
        return ProviderFetchResult(
            provider_id="akshare",
            source_revision="offline-empty-fixture-v1",
            retrieved_at=datetime.now(UTC),
            observations=(),
            raw_payload={
                "access_token": "must-never-appear-in-empty-summary",
                "response_rows": [],
            },
            request=request,
        )


class _WindowFilteredAkShareProvider:
    """Model a source row that the adapter correctly excludes from the request window."""

    async def fetch(self, request: MarketDataProviderRequest) -> ProviderFetchResult:
        return ProviderFetchResult(
            provider_id="akshare",
            source_revision="offline-window-filtered-fixture-v1",
            retrieved_at=datetime.now(UTC),
            observations=(),
            raw_payload={
                "access_token": "must-never-appear-in-window-summary",
                "response_rows": [
                    {"sensitive_source_value": "must-never-appear-in-window-summary"}
                ],
            },
            request=request,
        )


def test_default_summary_requires_no_live_confirmation() -> None:
    """The default command contract cannot initialize a DB or provider."""
    assert harness._not_run_summary() == {
        "status": "not_run",
        "code": "LIVE_CONFIRMATION_REQUIRED",
        "network_called": False,
        "database_created": False,
        "credential_writes": False,
        "raw_payload_emitted": False,
    }


def test_default_cli_does_not_allocate_or_touch_a_database(monkeypatch, capsys) -> None:
    """An omitted --live switch stops before any temporary target is allocated."""

    def fail_if_allocated(*args, **kwargs):
        del args, kwargs
        pytest.fail("the non-live command must not allocate a database")

    monkeypatch.setattr(harness._DatabaseTarget, "allocate", fail_if_allocated)

    assert harness.main([]) == 0
    output = capsys.readouterr().out
    assert '"status":"not_run"' in output
    assert '"network_called":false' in output


def test_existing_or_url_database_targets_are_rejected(tmp_path) -> None:
    """The live command cannot be pointed at an application database or URL."""
    existing = tmp_path / "existing.sqlite3"
    existing.write_text("do-not-touch", encoding="utf-8")

    with pytest.raises(harness.HarnessError) as existing_error:
        harness._validate_requested_database_path(str(existing))
    assert existing_error.value.code == "HARNESS_DATABASE_NOT_FRESH"

    with pytest.raises(harness.HarnessError) as url_error:
        harness._validate_requested_database_path("sqlite+aiosqlite:///unsafe.sqlite3")
    assert url_error.value.code == "HARNESS_DATABASE_TARGET_UNSAFE"


def test_owned_caller_target_is_removed_after_cleanup(tmp_path) -> None:
    """A caller-designated fresh target remains disposable rather than retained."""
    requested = tmp_path / "disposable.sqlite3"

    target = harness._DatabaseTarget.allocate(str(requested))

    assert requested.exists()
    assert target.cleanup() is True
    assert not requested.exists()


def test_live_cli_removes_caller_target_after_a_terminal_failure(
    monkeypatch, tmp_path, capsys
) -> None:
    """Even a failed live run cannot leave a caller-designated database behind."""
    requested = tmp_path / "failed-live-run.sqlite3"

    def fake_asyncio_run(coroutine):
        coroutine.close()
        return {
            "status": "failed",
            "code": "AKSHARE_ZERO_USABLE_OBSERVATIONS",
            "stage": "live_fetch_or_persistence",
        }

    monkeypatch.setattr(harness.asyncio, "run", fake_asyncio_run)

    assert harness.main(["--live", "--database-path", str(requested)]) == 1
    output = capsys.readouterr().out
    assert '"removed":true' in output
    assert not requested.exists()


def test_live_cli_uses_fail_closed_environment_runner_without_spawning(
    monkeypatch, tmp_path, capsys
) -> None:
    """An empty runner configuration reports a stable failure before any child starts."""
    requested = tmp_path / "unconfigured-runner.sqlite3"

    for environment_key in (
        "AKSHARE_MARKET_DATA_RUNNER",
        "AKSHARE_RUNNER_HOME",
        "AKSHARE_RUNNER_WORKDIR",
        "AKSHARE_RUNNER_SITE_PACKAGES",
    ):
        monkeypatch.delenv(environment_key, raising=False)

    def fail_if_spawned(*args, **kwargs):
        del args, kwargs
        pytest.fail("an unconfigured runner must not start a subprocess")

    monkeypatch.setattr(akshare_provider.subprocess, "Popen", fail_if_spawned)

    assert harness.main(["--live", "--database-path", str(requested)]) == 1

    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "failed"
    assert output["code"] == "AKSHARE_RUNNER_COMMAND_UNCONFIGURED"
    assert output["stage"] == "live_fetch_or_persistence"
    assert output["provider_fetch_attempt_count"] == 1
    assert output["provider_result"] == {
        "result_count": 0,
        "response_row_count": 0,
        "normalized_observation_count": 0,
    }
    assert output["first_local_first"] == {
        "coverage_status": "incomplete",
        "observation_count": 0,
        "persisted_fetch_count": 0,
        "passing_observation_count": 0,
        "failed_observation_count": 0,
        "warning_codes": ["AKSHARE_RUNNER_COMMAND_UNCONFIGURED"],
    }
    assert output["database"] == {"kind": "caller_designated_temporary", "removed": True}
    assert not requested.exists()


@pytest.mark.asyncio
async def test_offline_fake_chain_persists_then_independently_rereads(tmp_path) -> None:
    """The service path persists a receipt and local_only cannot call a provider."""
    database_path = tmp_path / "fresh-harness.sqlite3"
    fake = _FakeAkShareProvider()

    output = await harness._run_live(
        database_path=database_path,
        trading_date=harness.DEFAULT_TRADING_DATE,
        provider_factory=lambda: fake,
    )

    assert output["status"] == "pass"
    assert output["code"] == "AKSHARE_LOCAL_FIRST_CHAIN_PASSED"
    assert output["provider_fetch_attempt_count"] == 1
    assert output["provider_result"] == {
        "result_count": 1,
        "response_row_count": 1,
        "normalized_observation_count": 1,
    }
    assert output["first_local_first"]["persisted_fetch_count"] == 1
    assert output["independent_local_only_reread"]["provider_fetch_attempt_count"] == 0
    assert output["persistence"] == {
        "source_snapshot_count": 1,
        "observation_revision_count": 1,
    }
    assert "must-never-appear-in-summary" not in str(output)
    assert len(fake.requests) == 1
    assert fake.requests[0].route_id == harness.ROUTE_ID
    assert fake.requests[0].data_kind == "reference_series"
    assert database_path.exists()


@pytest.mark.asyncio
async def test_empty_source_result_is_a_stable_non_sensitive_failure(tmp_path) -> None:
    """An accepted empty receipt cannot be mistaken for a complete local cache."""
    output = await harness._run_live(
        database_path=tmp_path / "empty-harness.sqlite3",
        trading_date=harness.DEFAULT_TRADING_DATE,
        provider_factory=_EmptyAkShareProvider,
    )

    assert output["status"] == "failed"
    assert output["code"] == "AKSHARE_ZERO_USABLE_OBSERVATIONS"
    assert output["provider_fetch_attempt_count"] == 1
    assert output["provider_result"] == {
        "result_count": 1,
        "response_row_count": 0,
        "normalized_observation_count": 0,
    }
    assert output["first_local_first"]["persisted_fetch_count"] == 1
    assert "must-never-appear-in-empty-summary" not in str(output)


@pytest.mark.asyncio
async def test_window_filtered_result_reports_counts_without_source_rows(tmp_path) -> None:
    """A non-empty response with zero usable rows remains distinguishable and private."""
    output = await harness._run_live(
        database_path=tmp_path / "window-filtered-harness.sqlite3",
        trading_date=harness.DEFAULT_TRADING_DATE,
        provider_factory=_WindowFilteredAkShareProvider,
    )

    assert output["status"] == "failed"
    assert output["code"] == "AKSHARE_ZERO_USABLE_OBSERVATIONS"
    assert output["provider_result"] == {
        "result_count": 1,
        "response_row_count": 1,
        "normalized_observation_count": 0,
    }
    assert "must-never-appear-in-window-summary" not in str(output)
