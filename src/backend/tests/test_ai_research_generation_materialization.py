"""Focused contracts for server-owned protocol-v2 GENERATE materialization."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.db.database import async_session_maker
from app.models.ai_research_v2 import (
    ResearchArtifact,
    ResearchArtifactContent,
    ResearchCandidate,
    ResearchExperimentEpoch,
    ResearchGenerationMaterialization,
    ResearchModelInvocation,
    ResearchRun,
    ResearchStageArtifactBinding,
    ResearchStageAttempt,
    ResearchTask,
    ResearchTrial,
)
from app.models.user import User
from app.services.research import generation_materialization as materialization_module
from app.services.research.canonical import content_hash
from app.services.research.dataset_integrity import (
    DatasetObjectAttestation,
    InMemoryDatasetObjectResolver,
)
from app.services.research.dataset_registry import DatasetRegistry
from app.services.research.generation_materialization import (
    GenerationMaterializationPolicy,
    GenerationMaterializationProposal,
    ResearchGenerationMaterializer,
)
from app.services.research.hypothesis_registry import HypothesisRegistry
from app.services.research.workflow_worker import StageExecutionContext


@pytest.mark.asyncio
async def test_materializer_atomically_binds_a_model_output_to_one_mutable_candidate(
    auth_user,
) -> None:
    """A valid leased GENERATE result becomes one auditable mutable candidate."""

    context = await _context(auth_user, suffix="success")
    materializer = _materializer(context)

    result = await materializer.materialize(
        context=context["stage_context"],
        proposal=GenerationMaterializationProposal(
            model_invocation_id=context["invocation"].id,
            model_output=context["model_output"],
        ),
    )

    async with async_session_maker() as session:
        candidate = await session.get(ResearchCandidate, result.candidate_id)
        relation = await session.get(ResearchGenerationMaterialization, result.id)
        manifest = await session.get(ResearchArtifact, result.output_artifact_id)
        manifest_content = await session.get(ResearchArtifactContent, result.output_artifact_id)
        binding = await session.scalar(
            select(ResearchStageArtifactBinding).where(
                ResearchStageArtifactBinding.stage_attempt_id == context["attempt"].id
            )
        )
        artifacts = list(
            (
                await session.execute(
                    select(ResearchArtifact).where(
                        ResearchArtifact.id.in_(
                            [
                                candidate.code_artifact_id if candidate is not None else "",
                                candidate.dependency_artifact_id if candidate is not None else "",
                                result.output_artifact_id,
                            ]
                        )
                    )
                )
            ).scalars()
        )
        trial_count = await session.scalar(
            select(func.count(ResearchTrial.id)).where(ResearchTrial.run_id == context["run"].id)
        )

    assert candidate is not None
    assert candidate.freeze_status == "MUTABLE"
    assert candidate.run_id == context["run"].id
    assert candidate.environment_hash == content_hash(_environment_manifest())
    assert candidate.cost_model_hash == content_hash(
        {
            "cost_model": context["hypothesis"].canonical_payload["cost_model"],
            "execution_policy": context["dataset"].execution_policy,
        }
    )
    assert relation is not None
    assert relation.task_id == context["task"].id
    assert relation.stage_attempt_id == context["attempt"].id
    assert relation.candidate_id == candidate.id
    assert relation.model_invocation_id == context["invocation"].id
    assert relation.manifest_artifact_id == result.output_artifact_id
    assert binding is not None
    assert binding.artifact_id == result.output_artifact_id
    assert manifest is not None
    assert manifest.kind == "generation_manifest"
    assert manifest_content is not None
    receipt = json.loads(manifest_content.content)
    assert receipt["candidate_id"] == candidate.id
    assert receipt["model_invocation_id"] == context["invocation"].id
    assert receipt["model_output_hash"] == context["invocation"].output_hash
    assert receipt["execution_state"] == "MATERIALIZED_NOT_EXECUTED"
    assert {artifact.kind for artifact in artifacts} == {
        "strategy_code",
        "dependency_lock",
        "generation_manifest",
    }
    assert trial_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "malformed", ["duplicate_code", "duplicate_nested", "NaN", "Infinity", "-Infinity"]
)
async def test_materializer_rejects_ambiguous_or_nonfinite_model_json_without_partial_writes(
    auth_user,
    malformed,
) -> None:
    context = await _context(auth_user, suffix=f"strict-json-{malformed}")
    valid = json.loads(context["model_output"])
    params = (
        '{"nested":{"lookback":10,"lookback":20}}'
        if malformed == "duplicate_nested"
        else '{"lookback":' + ("20" if malformed == "duplicate_code" else malformed) + "}"
    )
    code = json.dumps(valid["strategy_code"])
    output = (
        '{"schema_version":"research-generation-v1","strategy_code":'
        + code
        + (',"strategy_code":' + code if malformed == "duplicate_code" else "")
        + ',"dependency_lock":'
        + json.dumps(valid["dependency_lock"])
        + ',"params":'
        + params
        + "}"
    )
    models = (
        ResearchCandidate,
        ResearchGenerationMaterialization,
        ResearchArtifact,
        ResearchArtifactContent,
        ResearchStageArtifactBinding,
    )
    async with async_session_maker() as session:
        invocation = await session.get(ResearchModelInvocation, context["invocation"].id)
        invocation.output_hash = content_hash({"output": output})
        await session.commit()
        before = [await session.scalar(select(func.count()).select_from(model)) for model in models]
    with pytest.raises(ValueError, match="RESEARCH_GENERATION_OUTPUT_SCHEMA_INVALID"):
        await _materializer(context).materialize(
            context=context["stage_context"],
            proposal=GenerationMaterializationProposal(
                model_invocation_id=context["invocation"].id,
                model_output=output,
            ),
        )
    async with async_session_maker() as session:
        after = [await session.scalar(select(func.count()).select_from(model)) for model in models]
    assert after == before


@pytest.mark.asyncio
async def test_materializer_rejects_model_output_that_does_not_match_its_invocation(
    auth_user,
) -> None:
    """A caller cannot bind a candidate to an invocation for different output bytes."""

    context = await _context(auth_user, suffix="wrong-output")

    with pytest.raises(ValueError, match="RESEARCH_GENERATION_INVOCATION_OUTPUT_HASH_MISMATCH"):
        await _materializer(context).materialize(
            context=context["stage_context"],
            proposal=GenerationMaterializationProposal(
                model_invocation_id=context["invocation"].id,
                model_output=json.dumps(
                    {
                        "schema_version": "research-generation-v1",
                        "strategy_code": "def next(self):\n    return None\n",
                        "dependency_lock": "backtrader==1.9.78.123\n",
                        "params": {"lookback": 99},
                    },
                    sort_keys=True,
                ),
            ),
        )

    async with async_session_maker() as session:
        assert (
            await session.scalar(
                select(ResearchCandidate).where(ResearchCandidate.run_id == context["run"].id)
            )
            is None
        )
        assert (
            await session.scalar(
                select(ResearchGenerationMaterialization).where(
                    ResearchGenerationMaterialization.stage_attempt_id == context["attempt"].id
                )
            )
            is None
        )
        assert (
            await session.scalar(
                select(ResearchStageArtifactBinding).where(
                    ResearchStageArtifactBinding.stage_attempt_id == context["attempt"].id
                )
            )
            is None
        )


@pytest.mark.asyncio
async def test_materializer_rejects_an_expired_task_lease_before_creating_a_candidate(
    auth_user,
) -> None:
    """A stale worker cannot materialize model output after its lease boundary."""

    context = await _context(auth_user, suffix="expired-lease", expired_lease=True)

    with pytest.raises(ValueError, match="RESEARCH_GENERATION_MATERIALIZATION_LEASE_DENIED"):
        await _materializer(context).materialize(
            context=context["stage_context"],
            proposal=GenerationMaterializationProposal(
                model_invocation_id=context["invocation"].id,
                model_output=context["model_output"],
            ),
        )

    async with async_session_maker() as session:
        assert (
            await session.scalar(
                select(ResearchCandidate).where(ResearchCandidate.run_id == context["run"].id)
            )
            is None
        )
        assert (
            await session.scalar(
                select(ResearchGenerationMaterialization).where(
                    ResearchGenerationMaterialization.stage_attempt_id == context["attempt"].id
                )
            )
            is None
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("application_skew", "expired_lease", "should_materialize"),
    (
        pytest.param(
            timedelta(minutes=10),
            False,
            True,
            id="application-clock-fast-by-ten-minutes",
        ),
        pytest.param(
            timedelta(minutes=-10),
            True,
            False,
            id="application-clock-slow-by-ten-minutes",
        ),
    ),
)
async def test_materializer_uses_database_utc_lease_clock_despite_application_skew(
    auth_user,
    monkeypatch: pytest.MonkeyPatch,
    application_skew: timedelta,
    expired_lease: bool,
    should_materialize: bool,
) -> None:
    """Lease authorization follows the database, not the materializer host clock."""

    context = await _context(
        auth_user,
        suffix=f"database-clock-{int(application_skew.total_seconds())}",
        expired_lease=expired_lease,
    )
    database_like_now = datetime.now(timezone.utc)
    monkeypatch.setattr(
        materialization_module,
        "_now",
        lambda: database_like_now + application_skew,
        raising=False,
    )

    call = _materializer(context).materialize(
        context=context["stage_context"],
        proposal=GenerationMaterializationProposal(
            model_invocation_id=context["invocation"].id,
            model_output=context["model_output"],
        ),
    )
    if should_materialize:
        result = await call
        assert result.candidate_id
    else:
        with pytest.raises(ValueError, match="RESEARCH_GENERATION_MATERIALIZATION_LEASE_DENIED"):
            await call


@pytest.mark.asyncio
async def test_materializer_rechecks_database_lease_before_candidate_persistence(
    auth_user,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Expiry during validation rolls back candidate and manifest writes."""

    context = await _context(auth_user, suffix="lease-expires-during-materialization")
    original_server_bound_inputs = materialization_module._server_bound_inputs

    async def expire_lease_after_initial_validation(session, *, run, user_id):
        result = await original_server_bound_inputs(session, run=run, user_id=user_id)
        task = await session.get(ResearchTask, context["task"].id)
        assert task is not None
        task.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        return result

    monkeypatch.setattr(
        materialization_module,
        "_server_bound_inputs",
        expire_lease_after_initial_validation,
    )

    with pytest.raises(ValueError, match="RESEARCH_GENERATION_MATERIALIZATION_LEASE_DENIED"):
        await _materializer(context).materialize(
            context=context["stage_context"],
            proposal=GenerationMaterializationProposal(
                model_invocation_id=context["invocation"].id,
                model_output=context["model_output"],
            ),
        )

    async with async_session_maker() as session:
        assert (
            await session.scalar(
                select(ResearchCandidate).where(ResearchCandidate.run_id == context["run"].id)
            )
            is None
        )
        assert (
            await session.scalar(
                select(ResearchGenerationMaterialization).where(
                    ResearchGenerationMaterialization.stage_attempt_id == context["attempt"].id
                )
            )
            is None
        )


@pytest.mark.asyncio
async def test_materializer_revalidates_the_logical_dataset_object_before_candidate_write(
    auth_user,
) -> None:
    """A queued GENERATE result cannot materialize against a replaced object."""

    context = await _context(auth_user, suffix="object-drift")
    initial = context["attestation"]
    context["resolver"].register(
        DatasetObjectAttestation(
            receipt_id="generation-materialization-object-drift-receipt-v2",
            user_id=initial.user_id,
            logical_object_id=initial.logical_object_id,
            object_version="v2",
            object_digest="e" * 64,
            object_size_bytes=8192,
            storage_uri=initial.storage_uri,
            attested_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
        )
    )

    with pytest.raises(ValueError, match="DATASET_OBJECT_ATTESTATION_MISMATCH"):
        await _materializer(context).materialize(
            context=context["stage_context"],
            proposal=GenerationMaterializationProposal(
                model_invocation_id=context["invocation"].id,
                model_output=context["model_output"],
            ),
        )

    async with async_session_maker() as session:
        candidate_count = await session.scalar(
            select(func.count(ResearchCandidate.id)).where(
                ResearchCandidate.run_id == context["run"].id
            )
        )
    assert candidate_count == 0


@pytest.mark.asyncio
async def test_materializer_fails_closed_without_a_deployment_object_resolver(auth_user) -> None:
    """A policy alone is insufficient to turn a typed output into a candidate."""

    context = await _context(auth_user, suffix="resolver-required")
    no_resolver_materializer = ResearchGenerationMaterializer(
        policy=GenerationMaterializationPolicy(
            version="generation-materialization-policy-v1",
            environment_manifest=_environment_manifest(),
        )
    )

    with pytest.raises(ValueError, match="DATASET_OBJECT_RESOLVER_REQUIRED"):
        await no_resolver_materializer.materialize(
            context=context["stage_context"],
            proposal=GenerationMaterializationProposal(
                model_invocation_id=context["invocation"].id,
                model_output=context["model_output"],
            ),
        )


@pytest.mark.asyncio
async def test_materializer_in_session_defers_the_commit_to_its_caller(auth_user) -> None:
    """The stage-attempt owner can make materialization and terminal receipt atomic."""

    context = await _context(auth_user, suffix="caller-transaction")
    materializer = _materializer(context)

    async with async_session_maker() as session:
        task = await session.scalar(
            select(ResearchTask).where(ResearchTask.id == context["task"].id).with_for_update()
        )
        attempt = await session.scalar(
            select(ResearchStageAttempt)
            .where(ResearchStageAttempt.id == context["attempt"].id)
            .with_for_update()
        )
        assert task is not None
        assert attempt is not None

        result = await materializer.materialize_in_session(
            session,
            task=task,
            attempt=attempt,
            context=context["stage_context"],
            proposal=GenerationMaterializationProposal(
                model_invocation_id=context["invocation"].id,
                model_output=context["model_output"],
            ),
        )

        assert await session.get(ResearchGenerationMaterialization, result.id) is not None
        assert await session.get(ResearchCandidate, result.candidate_id) is not None
        await session.rollback()

    async with async_session_maker() as session:
        assert await session.get(ResearchGenerationMaterialization, result.id) is None
        assert await session.get(ResearchCandidate, result.candidate_id) is None


@pytest.mark.asyncio
async def test_materializer_retries_only_the_exact_same_generation_receipt(auth_user) -> None:
    """A duplicate delivery returns the original relationship instead of another candidate."""

    context = await _context(auth_user, suffix="retry")
    materializer = _materializer(context)

    first = await materializer.materialize(
        context=context["stage_context"],
        proposal=GenerationMaterializationProposal(
            model_invocation_id=context["invocation"].id,
            model_output=context["model_output"],
        ),
    )
    repeated = await materializer.materialize(
        context=context["stage_context"],
        proposal=GenerationMaterializationProposal(
            model_invocation_id=context["invocation"].id,
            model_output=context["model_output"],
        ),
    )

    assert repeated == first
    async with async_session_maker() as session:
        candidates = list(
            (
                await session.execute(
                    select(ResearchCandidate).where(ResearchCandidate.run_id == context["run"].id)
                )
            ).scalars()
        )
        relations = list(
            (
                await session.execute(
                    select(ResearchGenerationMaterialization).where(
                        ResearchGenerationMaterialization.stage_attempt_id == context["attempt"].id
                    )
                )
            ).scalars()
        )

    assert [candidate.id for candidate in candidates] == [first.candidate_id]
    assert [relation.id for relation in relations] == [first.id]


def _materializer(context: dict[str, object]) -> ResearchGenerationMaterializer:
    return ResearchGenerationMaterializer(
        policy=GenerationMaterializationPolicy(
            version="generation-materialization-policy-v1",
            environment_manifest=_environment_manifest(),
        ),
        dataset_registry=context["datasets"],
    )


def _environment_manifest() -> dict[str, object]:
    return {
        "runtime": "python-3.10",
        "strategy_api": "backtrader-v1",
        "base_image": "sha256:" + "a" * 64,
    }


async def _context(
    auth_user,
    *,
    suffix: str,
    expired_lease: bool = False,
) -> dict[str, object]:
    user_id = await _user_id(auth_user)
    hypothesis_registry = HypothesisRegistry()
    hypothesis = await hypothesis_registry.create_draft(user_id, _hypothesis_payload())
    hypothesis = await hypothesis_registry.confirm(
        user_id,
        hypothesis.id,
        request_hash=hypothesis.content_hash,
    )
    resolver = InMemoryDatasetObjectResolver()
    attestation = resolver.register(
        DatasetObjectAttestation(
            receipt_id=f"generation-materialization-{suffix}-receipt",
            user_id=user_id,
            logical_object_id=f"generation-materialization-{suffix}-dataset",
            object_version="v1",
            object_digest="d" * 64,
            object_size_bytes=4096,
            storage_uri=f"controlled://generation-materialization/{suffix}.parquet",
            attested_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
    )
    datasets = DatasetRegistry(object_resolver=resolver)
    dataset = await datasets.create_attested_snapshot(
        user_id=user_id,
        object_receipt_id=attestation.receipt_id,
        dataset_policy_version="policy-v1",
        partition_kind="DISCOVERY",
        instrument_manifest={"symbols": ["RB0"]},
        split_manifest={"start": "2024-01-01", "end": "2024-12-31"},
        source_manifest={"provider": "fixture"},
        execution_policy={"fill": "next_bar_open", "commission_bps": 2.0, "slippage_bps": 1.0},
        point_in_time_cutoff=datetime(2025, 1, 1, tzinfo=timezone.utc),
        license_tags=["fixture-license"],
    )
    epoch = ResearchExperimentEpoch(
        user_id=user_id,
        hypothesis_version_id=hypothesis.id,
        family_hash=(suffix[0] * 64),
        search_budget={"max_trials": 3},
        dataset_policy_version="policy-v1",
        status="OPEN",
    )
    model_output = json.dumps(
        {
            "schema_version": "research-generation-v1",
            "strategy_code": "class Strategy:\n    def next(self):\n        return None\n",
            "dependency_lock": "backtrader==1.9.78.123\n",
            "params": {"lookback": 20},
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    now = datetime.now(timezone.utc)
    run = ResearchRun(
        user_id=user_id,
        hypothesis_version_id=hypothesis.id,
        dataset_snapshot_id=dataset.id,
        experiment_epoch_id="",
        promotion_policy_version="promotion-v1",
        request_hash="r" * 64,
        capability_profile_id="dev-single-process",
        capability_profile_version="v1",
        capability_evidence_hash="e" * 64,
        trace_id=f"trace-generation-{suffix}",
    )
    async with async_session_maker() as session:
        session.add(epoch)
        await session.flush()
        run.experiment_epoch_id = epoch.id
        session.add(run)
        await session.flush()
        task = ResearchTask(
            user_id=user_id,
            run_id=run.id,
            status="RUNNING",
            stage_cursor="GENERATE",
            request_json={},
            idempotency_key=f"generation-materialization-{suffix}",
            idempotency_request_hash="i" * 64,
            trace_id=run.trace_id,
            lease_token=f"lease-generation-{suffix}",
            lease_expires_at=(
                now - timedelta(seconds=1) if expired_lease else now + timedelta(minutes=5)
            ),
            lease_heartbeat_at=now,
        )
        session.add(task)
        await session.flush()
        attempt = ResearchStageAttempt(
            run_id=run.id,
            task_id=task.id,
            stage="GENERATE",
            attempt_no=1,
            idempotency_key=f"generate-attempt-{suffix}",
            status="RUNNING",
            lease_token=task.lease_token,
            input_hash="h" * 64,
        )
        invocation = ResearchModelInvocation(
            run_id=run.id,
            provider="test-provider",
            requested_model="research-default",
            resolved_model="test-model-v1",
            provider_request_id=f"provider-{suffix}",
            prompt_template_version="generation-v1",
            system_input_hash="s" * 64,
            input_hash="i" * 64,
            output_hash=content_hash({"output": model_output}),
            sampling_params={"temperature": 0.1},
            tool_manifest=[],
            origin="LLM",
            transformation_chain=["typed_gateway"],
            fallback_chain=[],
            token_usage={"total": 10},
            cost={"usd": 0.001},
        )
        session.add_all([attempt, invocation])
        await session.commit()
        await session.refresh(run)
        await session.refresh(task)
        await session.refresh(attempt)
        await session.refresh(invocation)
    return {
        "run": run,
        "task": task,
        "attempt": attempt,
        "invocation": invocation,
        "hypothesis": hypothesis,
        "dataset": dataset,
        "datasets": datasets,
        "resolver": resolver,
        "attestation": attestation,
        "model_output": model_output,
        "stage_context": StageExecutionContext(
            task_id=task.id,
            run_id=run.id,
            user_id=user_id,
            stage_attempt_id=attempt.id,
            lease_token=task.lease_token or "",
            stage="GENERATE",
            request_hash=run.request_hash,
            trace_id=task.trace_id,
        ),
    }


async def _user_id(auth_user) -> str:
    user, _headers = auth_user
    async with async_session_maker() as session:
        return str(await session.scalar(select(User.id).where(User.username == user["username"])))


def _hypothesis_payload() -> dict[str, object]:
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
        "dataset_policy_version": "policy-v1",
    }
