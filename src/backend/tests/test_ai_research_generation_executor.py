"""Trusted, deployment-owned GENERATE executor contracts.

The provider double in this module is deliberately only a transport seam.  The
tests exercise the real local database, quota service, gateway, task lease,
and filesystem-attested dataset path; they do not constitute a live-provider
acceptance result.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from app.db import database
from app.models.ai_research_v2 import (
    ResearchExperimentEpoch,
    ResearchModelInvocation,
    ResearchQuotaBucket,
    ResearchQuotaReservation,
    ResearchRun,
    ResearchTask,
)
from app.models.user import User
from app.services.research.canonical import content_hash
from app.services.research.capabilities import CapabilityProfile
from app.services.research.capability_registry import CapabilityRegistry
from app.services.research.data_precheck import ResearchDataPrecheckService
from app.services.research.dataset_registry import DatasetRegistry
from app.services.research.filesystem_dataset_resolver import FilesystemDatasetObjectResolver
from app.services.research.hypothesis_registry import HypothesisRegistry
from app.services.research.llm_gateway import (
    LlmGateway,
    ModelCatalog,
    ProviderRequest,
    ProviderResponse,
)
from app.services.research.stage_attempt import ResearchStageAttemptService
from app.services.research.task_runner import DurableResearchTaskRunner, ResearchTaskService
from app.services.research.workflow_worker import StageExecutionContext


@pytest.mark.asyncio
async def test_generation_executor_returns_gateway_backed_typed_proposal(
    auth_user, tmp_path: Path
) -> None:
    """A current leased GENERATE stage records a real gateway invocation and proposal."""

    # The feature import intentionally lives here for the first RED cycle:
    # before production code exists, this test reaches the missing executor
    # instead of using a test-only substitute.
    from app.services.research.generation_executor import (
        GenerationExecutorPolicy,
        ResearchGenerationExecutor,
    )

    context = await _generation_context(auth_user, tmp_path)
    provider = _ProviderSeam()
    prompt = "Return only the reviewed research-generation-v1 JSON object."
    policy = GenerationExecutorPolicy(
        model_alias="trusted-research",
        prompt_template_version="research-generate-fixed-v1",
        prompt_content=prompt,
        prompt_content_hash=content_hash({"prompt": prompt}),
        sampling_params={"temperature": 0.1, "max_tokens": 64},
        quota_policy_version="generation-quota-v1",
        reserved_tokens=64,
        quota_lease_seconds=120,
    )
    executor = ResearchGenerationExecutor(
        gateway=LlmGateway(
            provider=provider,
            catalog=ModelCatalog({"trusted-research": "provider-model-v1"}),
        ),
        dataset_registry=context["datasets"],
        policy=policy,
    )

    outcome = await executor.execute(context["stage_context"])

    assert outcome.status == "SUCCEEDED"
    assert outcome.next_stage is None
    assert outcome.generation_proposal is not None
    assert outcome.generation_proposal.model_output == provider.output
    assert provider.calls and provider.calls[0].resolved_model == "provider-model-v1"
    assert provider.calls[0].prompt_template_version == "research-generate-fixed-v1"
    assert provider.calls[0].system_input["prompt_content_hash"] == policy.prompt_content_hash
    assert provider.calls[0].typed_input["dataset"]["partition_kind"] == "DISCOVERY"
    assert "storage_uri" not in provider.calls[0].typed_input["dataset"]

    async with database.async_session_maker() as session:
        invocation = await session.scalar(
            select(ResearchModelInvocation).where(
                ResearchModelInvocation.id == outcome.generation_proposal.model_invocation_id
            )
        )
        reservations = list(
            await session.scalars(
                select(ResearchQuotaReservation).where(
                    ResearchQuotaReservation.task_id == context["task"].id
                )
            )
        )
    assert invocation is not None
    assert invocation.output_hash == content_hash({"output": provider.output})
    assert len(reservations) == 1
    assert reservations[0].status == "SETTLED"
    assert reservations[0].reserved_amount == 64


@pytest.mark.asyncio
async def test_generation_executor_rejects_cross_owner_context_before_provider_call(
    auth_user, tmp_path: Path
) -> None:
    """A forged owner field cannot spend the true owner's server quota."""

    from app.services.research.generation_executor import (
        GenerationExecutorPolicy,
        ResearchGenerationExecutor,
    )

    context = await _generation_context(auth_user, tmp_path)
    provider = _ProviderSeam()
    executor = _executor(ResearchGenerationExecutor, GenerationExecutorPolicy, context, provider)

    outcome = await executor.execute(replace(context["stage_context"], user_id="other-owner"))

    assert outcome.status == "FAILED"
    assert outcome.error_code == "RESEARCH_GENERATION_CONTEXT_DENIED"
    assert provider.calls == []


@pytest.mark.asyncio
async def test_generation_executor_rejects_expired_lease_before_provider_call(
    auth_user, tmp_path: Path
) -> None:
    """An executor cannot transform a stale task lease into a model dispatch."""

    from app.services.research.generation_executor import (
        GenerationExecutorPolicy,
        ResearchGenerationExecutor,
    )

    context = await _generation_context(auth_user, tmp_path)
    provider = _ProviderSeam()
    executor = _executor(ResearchGenerationExecutor, GenerationExecutorPolicy, context, provider)
    async with database.async_session_maker() as session:
        task = await session.get(ResearchTask, context["task"].id)
        assert task is not None
        task.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()

    outcome = await executor.execute(context["stage_context"])

    assert outcome.status == "FAILED"
    assert outcome.error_code == "RESEARCH_GENERATION_LEASE_DENIED"
    assert provider.calls == []


@pytest.mark.asyncio
async def test_generation_executor_revalidates_drifted_dataset_before_provider_call(
    auth_user, tmp_path: Path
) -> None:
    """A valid submission cannot generate after its attested source bytes are replaced."""

    from app.services.research.generation_executor import (
        GenerationExecutorPolicy,
        ResearchGenerationExecutor,
    )

    context = await _generation_context(auth_user, tmp_path)
    provider = _ProviderSeam()
    executor = _executor(ResearchGenerationExecutor, GenerationExecutorPolicy, context, provider)
    replacement = context["source"].with_name("replacement.parquet")
    replacement.write_bytes(b"different controlled bytes\n")
    replacement.replace(context["source"])

    outcome = await executor.execute(context["stage_context"])

    assert outcome.status == "FAILED"
    assert outcome.error_code == "DATASET_OBJECT_REVALIDATION_UNAVAILABLE"
    assert provider.calls == []
    async with database.async_session_maker() as session:
        dataset = await session.get(type(context["dataset"]), context["dataset"].id)
    assert dataset is not None
    assert dataset.integrity_status == "FAILED"


@pytest.mark.asyncio
async def test_generation_executor_denies_forward_observation_dataset_before_provider_call(
    auth_user, tmp_path: Path
) -> None:
    """Explorer generation remains limited to discovery and iteration-validation partitions."""

    from app.services.research.generation_executor import (
        GenerationExecutorPolicy,
        ResearchGenerationExecutor,
    )

    context = await _generation_context(
        auth_user,
        tmp_path,
        partition_kind="FORWARD_OBSERVATION",
    )
    provider = _ProviderSeam()
    executor = _executor(ResearchGenerationExecutor, GenerationExecutorPolicy, context, provider)

    outcome = await executor.execute(context["stage_context"])

    assert outcome.status == "FAILED"
    assert outcome.error_code == "RESEARCH_GENERATION_DATASET_BINDING_INVALID"
    assert provider.calls == []


@pytest.mark.asyncio
async def test_generation_executor_refuses_insufficient_server_quota_before_provider_call(
    auth_user, tmp_path: Path
) -> None:
    """A browser cannot choose another bucket or bypass the policy's reserve ceiling."""

    from app.services.research.generation_executor import (
        GenerationExecutorPolicy,
        ResearchGenerationExecutor,
    )

    context = await _generation_context(auth_user, tmp_path, quota_hard_limit=63)
    provider = _ProviderSeam()
    executor = _executor(ResearchGenerationExecutor, GenerationExecutorPolicy, context, provider)

    outcome = await executor.execute(context["stage_context"])

    assert outcome.status == "FAILED"
    assert outcome.error_code == "RESEARCH_QUOTA_HARD_LIMIT_EXCEEDED"
    assert provider.calls == []


@pytest.mark.asyncio
async def test_generation_executor_does_not_mark_invalid_model_output_successful(
    auth_user, tmp_path: Path
) -> None:
    """A syntactically invalid model response is not a candidate proposal or template fallback."""

    from app.services.research.generation_executor import (
        GenerationExecutorPolicy,
        ResearchGenerationExecutor,
    )

    context = await _generation_context(auth_user, tmp_path)
    provider = _ProviderSeam(output="not research-generation JSON")
    executor = _executor(ResearchGenerationExecutor, GenerationExecutorPolicy, context, provider)

    outcome = await executor.execute(context["stage_context"])

    assert outcome.status == "FAILED"
    assert outcome.error_code == "RESEARCH_GENERATION_OUTPUT_SCHEMA_INVALID"
    assert outcome.generation_proposal is None
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_generation_executor_does_not_expose_provider_exception_text(
    auth_user, tmp_path: Path
) -> None:
    """An untrusted transport exception becomes one stable executor failure code."""

    from app.services.research.generation_executor import (
        GenerationExecutorPolicy,
        ResearchGenerationExecutor,
    )

    context = await _generation_context(auth_user, tmp_path)
    provider = _FailingProvider()
    executor = _executor(ResearchGenerationExecutor, GenerationExecutorPolicy, context, provider)

    outcome = await executor.execute(context["stage_context"])

    assert outcome.status == "FAILED"
    assert outcome.error_code == "RESEARCH_GENERATION_GATEWAY_FAILED"
    assert "PROVIDER_SECRET_LEAK" not in (outcome.error_code or "")
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_generation_executor_deep_snapshots_deployment_sampling_policy(
    auth_user, tmp_path: Path
) -> None:
    """Mutating the caller's nested config after construction cannot alter a dispatch."""

    from app.services.research.generation_executor import (
        GenerationExecutorPolicy,
        ResearchGenerationExecutor,
    )

    context = await _generation_context(auth_user, tmp_path)
    provider = _ProviderSeam()
    prompt = "Return only the reviewed research-generation-v1 JSON object."
    mutable_sampling = {"temperature": 0.1, "nested": {"top_p": 0.8}}
    policy = GenerationExecutorPolicy(
        model_alias="trusted-research",
        prompt_template_version="research-generate-fixed-v1",
        prompt_content=prompt,
        prompt_content_hash=content_hash({"prompt": prompt}),
        sampling_params=mutable_sampling,
        quota_policy_version="generation-quota-v1",
        reserved_tokens=64,
        quota_lease_seconds=120,
    )
    mutable_sampling["temperature"] = 0.9
    mutable_sampling["nested"]["top_p"] = 0.1
    executor = ResearchGenerationExecutor(
        gateway=LlmGateway(
            provider=provider,
            catalog=ModelCatalog({"trusted-research": "provider-model-v1"}),
        ),
        dataset_registry=context["datasets"],
        policy=policy,
    )

    outcome = await executor.execute(context["stage_context"])

    assert outcome.status == "SUCCEEDED"
    assert provider.calls[0].sampling_params == {
        "temperature": 0.1,
        "nested": {"top_p": 0.8},
    }


@dataclass
class _ProviderSeam:
    """Transport boundary only; it mirrors the complete normalized gateway response."""

    output: str = field(
        default_factory=lambda: json.dumps(
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
    )
    calls: list[ProviderRequest] = field(default_factory=list)

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.calls.append(request)
        return ProviderResponse(
            output=self.output,
            provider_request_id="provider-request-1",
            token_usage={"prompt_tokens": 8, "completion_tokens": 12, "total_tokens": 20},
            cost={"currency": "USD", "amount": 0.001},
            fallback_chain=(),
        )


@dataclass
class _FailingProvider:
    """A hostile provider error must never become an API-visible stage detail."""

    calls: list[ProviderRequest] = field(default_factory=list)

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.calls.append(request)
        raise ValueError("PROVIDER_SECRET_LEAK")


def _executor(
    executor_type,
    policy_type,
    context: dict[str, Any],
    provider: Any,
):
    """Build the real quota/gateway path around only the provider transport seam."""

    prompt = "Return only the reviewed research-generation-v1 JSON object."
    policy = policy_type(
        model_alias="trusted-research",
        prompt_template_version="research-generate-fixed-v1",
        prompt_content=prompt,
        prompt_content_hash=content_hash({"prompt": prompt}),
        sampling_params={"temperature": 0.1, "max_tokens": 64},
        quota_policy_version="generation-quota-v1",
        reserved_tokens=64,
        quota_lease_seconds=120,
    )
    return executor_type(
        gateway=LlmGateway(
            provider=provider,
            catalog=ModelCatalog({"trusted-research": "provider-model-v1"}),
        ),
        dataset_registry=context["datasets"],
        policy=policy,
    )


async def _generation_context(
    auth_user,
    tmp_path: Path,
    *,
    quota_hard_limit: int = 256,
    partition_kind: str = "DISCOVERY",
    queued_only: bool = False,
) -> dict[str, Any]:
    """Create a real current task, trusted filesystem dataset, and server quota bucket."""

    user_id = await _user_id(auth_user)
    await CapabilityRegistry().register(
        CapabilityProfile(
            profile_id="generation-executor-profile",
            version="v1",
            service_identities={"explorer": "explorer", "evaluator": "evaluator"},
            queue_isolation=False,
            storage_isolation=False,
            network_isolation=False,
            sandbox_runner=False,
            approval_mode="single_actor",
            evidence_hash="e" * 64,
            verified_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )
    hypothesis = await HypothesisRegistry().create_draft(user_id, _hypothesis_payload())
    hypothesis = await HypothesisRegistry().confirm(
        user_id,
        hypothesis.id,
        request_hash=hypothesis.content_hash,
    )

    object_root = tmp_path / "objects"
    receipt_store = tmp_path / "receipts"
    object_root.mkdir()
    receipt_store.mkdir()
    source = object_root / "discovery.parquet"
    source.write_bytes(b"controlled research dataset bytes\n")
    resolver = FilesystemDatasetObjectResolver(
        object_root=object_root,
        receipt_store=receipt_store,
        max_object_bytes=1024,
    )
    attestation = resolver.import_file(
        user_id=user_id,
        source_path=source,
        partition_kind=partition_kind,
    )
    datasets = DatasetRegistry(object_resolver=resolver)
    dataset = await datasets.create_attested_snapshot(
        user_id=user_id,
        object_receipt_id=attestation.receipt_id,
        dataset_policy_version="generation-dataset-v1",
        partition_kind=partition_kind,
        instrument_manifest={
            "symbols": ["RB0"],
            "asset_class": "futures",
            "identity_scheme": "exchange_symbol",
        },
        split_manifest={
            "start": "2022-01-01",
            "end": "2023-12-31",
            "walk_forward": True,
            "purge_bars": 5,
            "embargo_bars": 5,
            "folds": [
                {
                    "train_start": "2022-01-01",
                    "train_end": "2022-12-31",
                    "validation_start": "2023-01-01",
                    "validation_end": "2023-12-31",
                }
            ],
        },
        source_manifest={
            "provider": "fixture",
            "frequency": "1d",
            "timezone": "UTC",
            "adjustment_rule": "none",
            "event_time_basis": "bar_close",
            "ingested_at": "2024-01-01T00:00:00Z",
            "as_of_at": "2024-01-01T00:00:00Z",
            "vintage": "fixture-v1",
        },
        execution_policy={
            "fill": "next_bar_open",
            "commission_bps": 2.0,
            "slippage_bps": 1.0,
            "volume_limit": 0.1,
            "suspension": "BLOCKED",
            "price_limit": "BLOCKED",
            "market_impact": "UNKNOWN",
        },
        point_in_time_cutoff=datetime(2024, 1, 1, tzinfo=timezone.utc),
        license_tags=["fixture-permitted"],
        candidate_frozen_at=(
            datetime(2023, 12, 31, tzinfo=timezone.utc)
            if partition_kind == "FORWARD_OBSERVATION"
            else None
        ),
    )
    epoch = ResearchExperimentEpoch(
        user_id=user_id,
        hypothesis_version_id=hypothesis.id,
        family_hash="f" * 64,
        search_budget={"max_trials": 3},
        dataset_policy_version="generation-dataset-v1",
        status="OPEN",
    )
    async with database.async_session_maker() as session:
        session.add(epoch)
        await session.commit()
        await session.refresh(epoch)

    request_json = {
        "hypothesis_content_hash": hypothesis.content_hash,
        "dataset_snapshot_id": dataset.id,
        "experiment_epoch_id": epoch.id,
    }
    prechecks = ResearchDataPrecheckService(dataset_registry=datasets)
    precheck = await prechecks.create(
        user_id=user_id,
        hypothesis_version_id=hypothesis.id,
        dataset_snapshot_id=dataset.id,
        experiment_epoch_id=epoch.id,
        profile_id="generation-executor-profile",
        profile_version="v1",
        promotion_policy_version="promotion-v1",
        request_json=request_json,
    )
    assert precheck.status == "PASS", precheck.details
    submitted = await ResearchTaskService(data_prechecks=prechecks).submit(
        user_id=user_id,
        hypothesis_version_id=hypothesis.id,
        dataset_snapshot_id=dataset.id,
        experiment_epoch_id=epoch.id,
        profile_id="generation-executor-profile",
        profile_version="v1",
        promotion_policy_version="promotion-v1",
        request_json=request_json,
        precheck_id=precheck.id,
        idempotency_key=f"generation-executor-{hypothesis.id}",
    )
    task = submitted.task
    async with database.async_session_maker() as session:
        bucket = ResearchQuotaBucket(
            scope_type="user",
            scope_id=user_id,
            policy_version="generation-quota-v1",
            resource_type="model_tokens",
            window_start=datetime.now(timezone.utc) - timedelta(minutes=1),
            window_end=datetime.now(timezone.utc) + timedelta(hours=1),
            hard_limit=quota_hard_limit,
            concurrency_limit=2,
        )
        session.add(bucket)
        await session.commit()
        await session.refresh(bucket)
    context = {
        "datasets": datasets,
        "resolver": resolver,
        "source": source,
        "dataset": dataset,
        "task": task,
        "run": submitted.run,
        "bucket": bucket,
    }
    if queued_only:
        return context
    claim = (await DurableResearchTaskRunner(lease_seconds=120).claim_due())[0]
    async with database.async_session_maker() as session:
        persisted_task = await session.get(ResearchTask, task.id)
        persisted_run = await session.get(ResearchRun, task.run_id)
        assert persisted_task is not None and persisted_run is not None
        persisted_task.stage_cursor = "GENERATE"
        persisted_run.stage_cursor = "GENERATE"
        await session.commit()
    attempt = await ResearchStageAttemptService().begin(
        task_id=task.id,
        lease_token=claim.lease_token,
        stage="GENERATE",
        idempotency_key=f"generation-attempt-{task.id}",
        input_payload={
            "protocol_version": "v2",
            "run_id": task.run_id,
            "stage": "GENERATE",
            "request_hash": submitted.run.request_hash,
            "expected_next_stage": None,
        },
    )
    return {
        **context,
        "attempt": attempt,
        "stage_context": StageExecutionContext(
            task_id=task.id,
            run_id=task.run_id,
            user_id=user_id,
            stage_attempt_id=attempt.id,
            lease_token=claim.lease_token,
            stage="GENERATE",
            request_hash=submitted.run.request_hash,
            trace_id=task.trace_id,
        ),
    }


async def _user_id(auth_user) -> str:
    user, _headers = auth_user
    async with database.async_session_maker() as session:
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
        "dataset_policy_version": "generation-dataset-v1",
    }
