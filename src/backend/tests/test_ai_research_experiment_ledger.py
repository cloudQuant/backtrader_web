from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db import database
from app.models.ai_research_v2 import (
    ResearchArtifact,
    ResearchExperimentEpoch,
    ResearchRun,
    ResearchTrial,
)
from app.models.user import User
from app.services.research.candidate_registry import CandidateRegistry
from app.services.research.dataset_integrity import (
    DatasetObjectAttestation,
    InMemoryDatasetObjectResolver,
)
from app.services.research.dataset_registry import DatasetRegistry
from app.services.research.experiment_ledger import ExperimentLedger
from app.services.research.hypothesis_registry import HypothesisRegistry


@pytest.mark.asyncio
async def test_ledger_appends_success_and_failure_and_uses_idempotent_trial_key(auth_user) -> None:
    context = await _context(await _user_id(auth_user))
    ledger = ExperimentLedger()
    successful = await ledger.record_trial(
        user_id=context["user_id"],
        run_id=context["run"].id,
        candidate_id=context["candidate"].id,
        idempotency_key="market-attempt-1",
        stage="VALIDATE",
        status="SUCCEEDED",
        input_hash="1" * 64,
        metrics={"sharpe": 1.1},
        observed_market_performance=True,
        counts_as_market_trial=True,
        counting_reason="candidate validation consumed a market sample",
    )
    same = await ledger.record_trial(
        user_id=context["user_id"],
        run_id=context["run"].id,
        candidate_id=context["candidate"].id,
        idempotency_key="market-attempt-1",
        stage="VALIDATE",
        status="SUCCEEDED",
        input_hash="1" * 64,
        metrics={"sharpe": 1.1},
        observed_market_performance=True,
        counts_as_market_trial=True,
        counting_reason="candidate validation consumed a market sample",
    )
    failed = await ledger.record_trial(
        user_id=context["user_id"],
        run_id=context["run"].id,
        candidate_id=context["candidate"].id,
        idempotency_key="market-attempt-2",
        stage="VALIDATE",
        status="FAILED",
        input_hash="2" * 64,
        metrics={},
        observed_market_performance=True,
        counts_as_market_trial=True,
        counting_reason="failed validation still observed market performance",
        error_code="BACKTEST_FAILURE",
    )

    assert same.id == successful.id
    assert failed.ordinal == successful.ordinal + 1
    assert await ledger.count_market_trials(context["user_id"], context["run"].id) == 2


@pytest.mark.asyncio
async def test_ledger_refuses_market_trial_count_without_evidence_reason(auth_user) -> None:
    context = await _context(await _user_id(auth_user))

    with pytest.raises(ValueError, match="MARKET_TRIAL_COUNTING_REASON_REQUIRED"):
        await ExperimentLedger().record_trial(
            user_id=context["user_id"],
            run_id=context["run"].id,
            candidate_id=context["candidate"].id,
            idempotency_key="missing-reason",
            stage="VALIDATE",
            status="SUCCEEDED",
            input_hash="3" * 64,
            metrics={},
            observed_market_performance=True,
            counts_as_market_trial=True,
            counting_reason="",
        )


@pytest.mark.asyncio
async def test_record_trial_in_session_rolls_back_with_the_ambient_transaction(auth_user) -> None:
    """An enclosing rollback must remove the trial and leave ordinal one available."""

    context = await _context(await _user_id(auth_user))
    ledger = ExperimentLedger()
    async with database.async_session_maker() as session:
        trial = await ledger.record_trial_in_session(
            session,
            user_id=context["user_id"],
            run_id=context["run"].id,
            candidate_id=context["candidate"].id,
            idempotency_key="ambient-rollback",
            stage="VALIDATE",
            status="SUCCEEDED",
            input_hash="4" * 64,
            metrics={"sharpe": 0.9},
            observed_market_performance=True,
            counts_as_market_trial=True,
            counting_reason="ambient transaction observed a market sample",
        )
        assert trial.ordinal == 1
        await session.rollback()

    async with database.async_session_maker() as session:
        persisted = await session.scalar(select(func.count(ResearchTrial.id)))
    assert persisted == 0

    committed = await ledger.record_trial(
        user_id=context["user_id"],
        run_id=context["run"].id,
        candidate_id=context["candidate"].id,
        idempotency_key="after-ambient-rollback",
        stage="VALIDATE",
        status="SUCCEEDED",
        input_hash="5" * 64,
        metrics={"sharpe": 1.0},
        observed_market_performance=True,
        counts_as_market_trial=True,
        counting_reason="post-rollback market sample",
    )
    assert committed.ordinal == 1


@pytest.mark.asyncio
async def test_record_trial_in_session_supports_a_legacy_run_without_an_epoch(auth_user) -> None:
    """Pre-epoch durable runs retain their original per-run trial behavior."""

    context = await _context(await _user_id(auth_user))
    async with database.async_session_maker() as session:
        run = await session.get(ResearchRun, context["run"].id)
        assert run is not None
        run.experiment_epoch_id = None
        await session.commit()

    async with database.async_session_maker() as session:
        trial = await ExperimentLedger().record_trial_in_session(
            session,
            user_id=context["user_id"],
            run_id=context["run"].id,
            candidate_id=context["candidate"].id,
            idempotency_key="legacy-no-epoch",
            stage="VALIDATE",
            status="FAILED",
            input_hash="6" * 64,
            metrics={},
            observed_market_performance=False,
            counts_as_market_trial=False,
            counting_reason="legacy technical failure",
            error_code="LEGACY_FAILURE",
        )
        await session.commit()

    assert trial.ordinal == 1


@pytest.mark.asyncio
async def test_independent_sqlite_connections_assign_unique_trial_ordinals(
    independent_ledger_database: str,
) -> None:
    """The epoch write lock serializes max-ordinal allocation across connections."""

    context = await _context(independent_ledger_database)
    ledger = ExperimentLedger()
    first, second = await asyncio.gather(
        ledger.record_trial(
            user_id=context["user_id"],
            run_id=context["run"].id,
            candidate_id=context["candidate"].id,
            idempotency_key="independent-ordinal-one",
            stage="VALIDATE",
            status="SUCCEEDED",
            input_hash="7" * 64,
            metrics={"sharpe": 0.7},
            observed_market_performance=True,
            counts_as_market_trial=True,
            counting_reason="first independent connection",
        ),
        ledger.record_trial(
            user_id=context["user_id"],
            run_id=context["run"].id,
            candidate_id=context["candidate"].id,
            idempotency_key="independent-ordinal-two",
            stage="VALIDATE",
            status="SUCCEEDED",
            input_hash="8" * 64,
            metrics={"sharpe": 0.8},
            observed_market_performance=True,
            counts_as_market_trial=True,
            counting_reason="second independent connection",
        ),
    )

    assert sorted((first.ordinal, second.ordinal)) == [1, 2]
    async with database.async_session_maker() as session:
        stored = list(
            (
                await session.execute(
                    select(ResearchTrial)
                    .where(ResearchTrial.run_id == context["run"].id)
                    .order_by(ResearchTrial.ordinal.asc())
                )
            ).scalars()
        )
    assert [trial.ordinal for trial in stored] == [1, 2]


@pytest_asyncio.fixture
async def independent_ledger_database(
    auth_user, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> AsyncIterator[str]:
    """Run ordinal races against independent SQLite connections and transactions."""

    user_id = await _user_id(auth_user)
    async with database.async_session_maker() as session:
        user = await session.get(User, user_id)
        assert user is not None
        session.expunge(user)
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'experiment-ledger.db'}",
        poolclass=NullPool,
        connect_args={"timeout": 30},
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.exec_driver_sql("PRAGMA journal_mode=WAL")
            await connection.run_sync(database.Base.metadata.create_all)
        async with sessions() as session:
            await session.merge(user)
            await session.commit()
        with monkeypatch.context() as local_patch:
            local_patch.setattr(database, "async_session_maker", sessions)
            yield user_id
    finally:
        await engine.dispose()


async def _context(user_id: str) -> dict[str, object]:
    hypothesis = await HypothesisRegistry().create_draft(user_id, _payload())
    hypothesis = await HypothesisRegistry().confirm(
        user_id, hypothesis.id, request_hash=hypothesis.content_hash
    )
    resolver = InMemoryDatasetObjectResolver()
    receipt = resolver.register(
        DatasetObjectAttestation(
            receipt_id="ledger-discovery-receipt-v1",
            user_id=user_id,
            logical_object_id="ledger-discovery-object",
            object_version="version-1",
            object_digest="d" * 64,
            object_size_bytes=1024,
            storage_uri="controlled://ledger-fixtures/discovery.parquet",
            attested_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
        )
    )
    dataset = await DatasetRegistry(object_resolver=resolver).create_attested_snapshot(
        user_id=user_id,
        object_receipt_id=receipt.receipt_id,
        dataset_policy_version="policy-v1",
        partition_kind="DISCOVERY",
        instrument_manifest={"symbols": ["RB0"]},
        split_manifest={"start": "2022-01-01", "end": "2023-12-31"},
        source_manifest={"provider": "fixture"},
        execution_policy={"fill": "next_bar_open"},
        point_in_time_cutoff=datetime(2024, 1, 1, tzinfo=timezone.utc),
        license_tags=["fixture-license"],
    )
    epoch = ResearchExperimentEpoch(
        user_id=user_id,
        hypothesis_version_id=hypothesis.id,
        family_hash="f" * 64,
        search_budget={"max_trials": 3},
        dataset_policy_version="policy-v1",
    )
    async with database.async_session_maker() as session:
        session.add(epoch)
        await session.commit()
        await session.refresh(epoch)
    run = ResearchRun(
        user_id=user_id,
        hypothesis_version_id=hypothesis.id,
        dataset_snapshot_id=dataset.id,
        experiment_epoch_id=epoch.id,
        promotion_policy_version="promotion-v1",
        request_hash="r" * 64,
        capability_profile_id="dev-single-process",
        capability_profile_version="v1",
        capability_evidence_hash="p" * 64,
        trace_id="trace-ledger",
    )
    code = ResearchArtifact(
        kind="strategy_code",
        content_hash="a" * 64,
        storage_uri="controlled://code.py",
        size_bytes=10,
        media_type="text/x-python",
        schema_version="v1",
        producer_identity="test",
    )
    dependencies = ResearchArtifact(
        kind="dependency_lock",
        content_hash="b" * 64,
        storage_uri="controlled://requirements.lock",
        size_bytes=10,
        media_type="text/plain",
        schema_version="v1",
        producer_identity="test",
    )
    async with database.async_session_maker() as session:
        session.add_all([run, code, dependencies])
        await session.commit()
        await session.refresh(run)
        await session.refresh(code)
        await session.refresh(dependencies)
    candidate = await CandidateRegistry().create_mutable(
        user_id=user_id,
        run_id=run.id,
        experiment_epoch_id=epoch.id,
        dataset_snapshot_id=dataset.id,
        code_artifact_id=code.id,
        dependency_artifact_id=dependencies.id,
        environment_hash="e" * 64,
        cost_model_hash="c" * 64,
        params={"lookback": 20},
    )
    return {"user_id": user_id, "run": run, "candidate": candidate}


async def _user_id(auth_user) -> str:
    user, _headers = auth_user
    async with database.async_session_maker() as session:
        result = await session.execute(select(User.id).where(User.username == user["username"]))
        return str(result.scalar_one())


def _payload() -> dict[str, object]:
    return {
        "research_question": "成本与滑点后，趋势信号是否仍有可检验优势？",
        "economic_mechanism": "趋势持续由信息扩散与风险补偿共同驱动。",
        "asset_scope": {"symbols": ["RB0"], "asset_class": "futures"},
        "frequency": "1d",
        "time_window": {"start": "2022-01-01", "end": "2025-12-31"},
        "information_cutoff": "2025-12-31T00:00:00Z",
        "cost_model": {"commission_bps": 2.0, "slippage_bps": 1.0},
        "execution_model": {"fill": "next_bar_open"},
        "primary_metric": "deflated_sharpe",
        "secondary_metrics": ["max_drawdown", "turnover"],
        "capacity_assumptions": {"max_participation_rate": 0.1},
        "falsification_criteria": {"max_drawdown": 0.2},
        "search_space": {"lookback": [10, 20]},
        "max_budget": {"max_trials": 20},
        "dataset_policy_version": "dataset-policy-v1",
    }
