from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.db import database
from app.models.ai_research_v2 import (
    ResearchCandidate,
    ResearchDiscoveryExecution,
    ResearchExperimentEpoch,
    ResearchQuotaReservation,
    ResearchRun,
    ResearchStageAttempt,
    ResearchTask,
    ResearchTrial,
)
from app.services.research import discovery_execution_journal as journal_module
from app.services.research.canonical import content_hash
from app.services.research.discovery_execution_journal import DiscoveryExecutionJournal
from tests.test_ai_research_discovery_execution_journal import (
    _bind_reservation_intent,
    _command,
    _context,
    _run,
    _user_id,
    independent_journal_database,  # noqa: F401 - shared independent-connection fixture
)


async def _budget(context, value) -> None:
    async with database.async_session_maker() as session:
        epoch = await session.get(ResearchExperimentEpoch, _run(context).experiment_epoch_id)
        epoch.search_budget = value
        await session.commit()


async def _another_run(context):
    """A distinct live execution of the same owner's immutable search family."""
    result = dict(context)
    async with database.async_session_maker() as session:
        for key, model in (
            ("run", ResearchRun),
            ("candidate", ResearchCandidate),
            ("task", ResearchTask),
            ("attempt", ResearchStageAttempt),
            ("reservation", ResearchQuotaReservation),
        ):
            original = context[key]
            values = {
                column.name: getattr(original, column.name) for column in model.__table__.columns
            }
            values["id"] = str(uuid4())
            for reference in ("run", "task"):
                if f"{reference}_id" in values:
                    values[f"{reference}_id"] = result[reference].id
            if "stage_attempt_id" in values:
                values["stage_attempt_id"] = result["attempt"].id
            if "idempotency_key" in values:
                values["idempotency_key"] = str(uuid4())
            result[key] = model(**values)
            session.add(result[key])
            await session.flush()
        await session.commit()
    return result


async def _prepare(context):
    command = _command(context, operation_id=f"discovery:{context['attempt'].id}")
    await _bind_reservation_intent(context, command)
    return await DiscoveryExecutionJournal().prepare(user_id=_user_id(context), command=command)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value", ({}, {"max_trials": 0}, {"max_trials": True}, {"max_trials": 1.5})
)
async def test_prepare_denies_invalid_search_budget_before_creating_journal(value) -> None:
    context = await _context()
    await _budget(context, value)
    with pytest.raises(ValueError, match="DISCOVERY_SEARCH_BUDGET_INVALID"):
        await _prepare(context)
    async with database.async_session_maker() as session:
        assert await session.scalar(select(func.count(ResearchDiscoveryExecution.id))) == 0


@pytest.mark.asyncio
async def test_prepared_command_occupies_budget_across_runs_and_exact_retry_is_free() -> None:
    context = await _context()
    other = await _another_run(context)
    await _budget(context, {"max_trials": 1})
    first = await _prepare(context)
    repeated = await _prepare(context)
    assert first.id == repeated.id
    with pytest.raises(ValueError, match="DISCOVERY_SEARCH_BUDGET_EXHAUSTED"):
        await _prepare(other)
    assert first.search_epoch_id == _run(context).experiment_epoch_id
    assert first.search_ordinal == 1
    assert first.search_budget_hash == content_hash({"max_trials": 1})
    assert first.trial_id is None


@pytest.mark.asyncio
async def test_allocated_search_budget_cannot_be_increased_in_place() -> None:
    context = await _context()
    other = await _another_run(context)
    await _budget(context, {"max_trials": 1})
    await _prepare(context)
    await _budget(context, {"max_trials": 100})
    with pytest.raises(ValueError, match="DISCOVERY_SEARCH_BUDGET_DRIFT"):
        await _prepare(other)


@pytest.mark.asyncio
async def test_legacy_trial_already_consumes_a_search_slot() -> None:
    context = await _context()
    await _budget(context, {"max_trials": 1})
    async with database.async_session_maker() as session:
        session.add(
            ResearchTrial(
                user_id=_user_id(context),
                run_id=_run(context).id,
                candidate_id=context["candidate"].id,
                ordinal=1,
                idempotency_key="legacy",
                stage="VALIDATE",
                status="FAILED",
                input_hash="1" * 64,
                metrics={},
                observed_market_performance=False,
                counts_as_market_trial=False,
                counting_reason="pre-result failure still submitted a trial",
            )
        )
        await session.commit()
    with pytest.raises(ValueError, match="DISCOVERY_SEARCH_BUDGET_EXHAUSTED"):
        await _prepare(context)


@pytest.mark.asyncio
async def test_two_independent_connections_cannot_take_last_search_slot(
    independent_journal_database,  # noqa: F811
) -> None:
    context = await _context()
    other = await _another_run(context)
    await _budget(context, {"max_trials": 1})
    commands = [
        _command(item, operation_id=f"discovery:{item['attempt'].id}") for item in (context, other)
    ]
    for item, command in zip((context, other), commands, strict=True):
        await _bind_reservation_intent(item, command)
    results = await asyncio.gather(
        *(
            DiscoveryExecutionJournal().prepare(user_id=_user_id(context), command=command)
            for command in commands
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(result, ResearchDiscoveryExecution) for result in results) == 1
    assert [str(result) for result in results if isinstance(result, Exception)] == [
        "DISCOVERY_SEARCH_BUDGET_EXHAUSTED"
    ]


@pytest.mark.asyncio
async def test_run_moving_after_epoch_lookup_cannot_charge_original_family(monkeypatch) -> None:
    context = await _context()
    async with database.async_session_maker() as session:
        original = await session.get(ResearchExperimentEpoch, _run(context).experiment_epoch_id)
        other = ResearchExperimentEpoch(
            user_id=original.user_id,
            hypothesis_version_id=original.hypothesis_version_id,
            family_hash="c" * 64,
            search_budget={"max_trials": 10},
            dataset_policy_version=original.dataset_policy_version,
        )
        session.add(other)
        await session.commit()
    require_binding = journal_module._require_prepare_binding

    async def move_then_validate(session, **kwargs):
        # Schedule the mutation at the lookup/locked-run boundary, retaining
        # valid candidate/run equality to isolate the missing epoch binding.
        run = await session.get(ResearchRun, _run(context).id)
        candidate = await session.get(ResearchCandidate, context["candidate"].id)
        run.experiment_epoch_id = candidate.experiment_epoch_id = other.id
        await session.flush()
        await require_binding(session, **kwargs)

    monkeypatch.setattr(journal_module, "_require_prepare_binding", move_then_validate)
    with pytest.raises(ValueError, match="DISCOVERY_EXECUTION_PREPARE_DENIED"):
        await _prepare(context)
    async with database.async_session_maker() as session:
        assert await session.scalar(select(func.count(ResearchDiscoveryExecution.id))) == 0


@pytest.mark.asyncio
async def test_legacy_null_allocation_cannot_authorize_a_new_dispatch() -> None:
    context = await _context()
    prepared = await _prepare(context)
    async with database.async_session_maker() as session:
        journal = await session.get(ResearchDiscoveryExecution, prepared.id)
        journal.search_epoch_id = journal.search_ordinal = journal.search_budget_hash = None
        await session.commit()
    with pytest.raises(ValueError, match="DISCOVERY_SEARCH_ALLOCATION_REQUIRED"):
        await _prepare(context)


@pytest.mark.asyncio
async def test_linked_trial_does_not_double_charge_an_execution() -> None:
    context = await _context()
    other = await _another_run(context)
    await _budget(context, {"max_trials": 2})
    prepared = await _prepare(context)
    async with database.async_session_maker() as session:
        trial = ResearchTrial(
            user_id=_user_id(context),
            run_id=_run(context).id,
            candidate_id=context["candidate"].id,
            ordinal=1,
            idempotency_key="linked-trial",
            stage="VALIDATE_DISCOVERY",
            status="FAILED",
            input_hash=prepared.command_hash,
            metrics={},
            observed_market_performance=True,
            counts_as_market_trial=True,
            counting_reason="observed failure",
        )
        session.add(trial)
        await session.flush()
        journal = await session.get(ResearchDiscoveryExecution, prepared.id)
        journal.trial_id = trial.id
        await session.commit()
    second = await _prepare(other)
    assert second.search_ordinal == 2
