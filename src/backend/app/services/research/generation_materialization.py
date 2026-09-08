"""Server-owned materialization of a fenced GENERATE model response.

The materializer deliberately does not call a model provider, sandbox, or
evaluator.  A deployment-owned executor supplies a completed gateway response
through ``GenerationMaterializationProposal``; this service validates its
durable provenance and turns one typed output into immutable artifacts plus a
single mutable candidate.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import database
from app.models.ai_research_v2 import (
    ResearchArtifact,
    ResearchArtifactContent,
    ResearchCandidate,
    ResearchDatasetSnapshot,
    ResearchGenerationMaterialization,
    ResearchHypothesisVersion,
    ResearchModelInvocation,
    ResearchRun,
    ResearchStageArtifactBinding,
    ResearchStageAttempt,
    ResearchTask,
)
from app.services.research.artifact_broker import ArtifactBroker, ArtifactDescriptor
from app.services.research.candidate_registry import CandidateRegistry
from app.services.research.canonical import content_hash
from app.services.research.database_clock import DatabaseUtcNow
from app.services.research.dataset_registry import (
    DatasetRegistry,
    require_verified_snapshot_integrity,
)
from app.services.research.discovery_search_budget import lock_search_epoch

_GENERATE_STAGE = "GENERATE"
_DRAFT_SCHEMA_VERSION = "research-generation-v1"
_MANIFEST_SCHEMA_VERSION = "research-generation-manifest-v1"
_PRODUCER_IDENTITY = "protocol-v2-generation-materializer"
_MAX_GENERATION_OUTPUT_BYTES = 10_000_000
_MAX_COMPONENT_BYTES = 10_000_000


class GenerationStageContext(Protocol):
    """Leased identity supplied by the protocol worker, never by a browser."""

    task_id: str
    run_id: str
    user_id: str
    stage_attempt_id: str
    lease_token: str
    stage: str
    request_hash: str
    trace_id: str | None


@dataclass(frozen=True, slots=True)
class GenerationMaterializationPolicy:
    """Immutable deployment configuration used to derive a candidate environment hash."""

    version: str
    environment_manifest: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class GenerationMaterializationProposal:
    """A completed, already-redacted model response selected by server worker code."""

    model_invocation_id: str
    model_output: str


@dataclass(frozen=True, slots=True)
class GenerationMaterializationResult:
    """Stable identifiers returned to the stage-completion owner."""

    id: str
    candidate_id: str
    candidate_hash: str
    output_artifact_id: str


@dataclass(frozen=True, slots=True)
class _GeneratedCandidateDraft:
    strategy_code: str
    dependency_lock: str
    params: dict[str, Any]


class ResearchGenerationMaterializer:
    """Own candidate creation and manifest binding for one fenced GENERATE attempt."""

    def __init__(
        self,
        *,
        policy: GenerationMaterializationPolicy,
        dataset_registry: DatasetRegistry | None = None,
    ) -> None:
        if not isinstance(policy.version, str) or not policy.version.strip():
            raise ValueError("RESEARCH_GENERATION_POLICY_VERSION_REQUIRED")
        self._policy = policy
        self._environment_manifest = _mapping_copy(
            policy.environment_manifest,
            error_code="RESEARCH_GENERATION_ENVIRONMENT_MANIFEST_INVALID",
        )
        if not self._environment_manifest:
            raise ValueError("RESEARCH_GENERATION_ENVIRONMENT_MANIFEST_INVALID")
        # A typed generation result is executable only when the deployment
        # provides the same trusted-object resolver used by precheck/submit.
        # The default registry intentionally has no resolver and fails closed.
        self._datasets = dataset_registry or DatasetRegistry()

    async def materialize(
        self,
        *,
        context: GenerationStageContext,
        proposal: GenerationMaterializationProposal,
    ) -> GenerationMaterializationResult:
        """Materialize one current leased proposal in a dedicated transaction.

        Production stage completion should prefer ``materialize_in_session``
        inside its existing task/attempt transaction.  This convenience method
        exists for an isolated caller and retains the identical checks.
        """

        for retry in range(2):
            try:
                async with database.async_session_maker() as session:
                    task, attempt = await _locked_context_models(session, context)
                    result = await self.materialize_in_session(
                        session,
                        task=task,
                        attempt=attempt,
                        context=context,
                        proposal=proposal,
                    )
                    await session.commit()
                    return result
            except IntegrityError:
                if retry == 0:
                    continue
                raise ValueError(
                    "RESEARCH_GENERATION_MATERIALIZATION_CONCURRENT_CONFLICT"
                ) from None
        raise AssertionError("unreachable")

    async def materialize_in_session(
        self,
        session: AsyncSession,
        *,
        task: ResearchTask,
        attempt: ResearchStageAttempt,
        context: GenerationStageContext,
        proposal: GenerationMaterializationProposal,
    ) -> GenerationMaterializationResult:
        """Add an exact materialization to the caller-owned transaction.

        The caller must lock epoch -> task -> run -> attempt in that order.
        No commit is issued here, so the stage-attempt owner can make
        the manifest/candidate relation and its terminal checkpoint atomic.
        """

        _validate_context_shape(context)
        _validate_proposal_shape(proposal)
        run = await _validate_locked_context(session, task=task, attempt=attempt, context=context)
        model_output_hash = content_hash({"output": proposal.model_output})
        invocation = await _validated_invocation(
            session,
            run=run,
            proposal=proposal,
            model_output_hash=model_output_hash,
        )
        existing = await session.scalar(
            select(ResearchGenerationMaterialization)
            .where(ResearchGenerationMaterialization.stage_attempt_id == attempt.id)
            .with_for_update()
        )
        if existing is not None:
            return await _exact_existing_result(
                session,
                existing=existing,
                task=task,
                attempt=attempt,
                proposal=proposal,
                model_output_hash=model_output_hash,
            )

        await _require_live_materialization_lease(session, task=task, context=context)

        draft = _parse_draft(proposal.model_output)
        hypothesis, dataset = await _server_bound_inputs(session, run=run, user_id=task.user_id)
        await self._datasets.revalidate_snapshot_in_session(session, snapshot=dataset)
        require_verified_snapshot_integrity(dataset)
        environment_hash = content_hash(self._environment_manifest)
        cost_model_hash = _cost_model_hash(hypothesis=hypothesis, dataset=dataset)

        code_artifact = await _register_local_artifact(
            session,
            kind="strategy_code",
            content=draft.strategy_code,
            media_type="text/x-python",
            schema_version=_DRAFT_SCHEMA_VERSION,
        )
        dependency_artifact = await _register_local_artifact(
            session,
            kind="dependency_lock",
            content=draft.dependency_lock,
            media_type="text/plain",
            schema_version=_DRAFT_SCHEMA_VERSION,
        )
        candidate = await CandidateRegistry().create_mutable_in_session(
            session,
            user_id=task.user_id,
            run_id=run.id,
            experiment_epoch_id=run.experiment_epoch_id or "",
            dataset_snapshot_id=run.dataset_snapshot_id or "",
            code_artifact_id=code_artifact.id,
            dependency_artifact_id=dependency_artifact.id,
            environment_hash=environment_hash,
            cost_model_hash=cost_model_hash,
            params=draft.params,
        )
        manifest_payload = _manifest_payload(
            context=context,
            run=run,
            candidate=candidate,
            invocation=invocation,
            code_artifact=code_artifact,
            dependency_artifact=dependency_artifact,
            environment_hash=environment_hash,
            cost_model_hash=cost_model_hash,
            policy_version=self._policy.version,
        )
        manifest_artifact = await _register_local_artifact(
            session,
            kind="generation_manifest",
            content=json.dumps(
                manifest_payload,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ),
            media_type="application/json",
            schema_version=_MANIFEST_SCHEMA_VERSION,
        )
        await _bind_manifest(
            session,
            task=task,
            attempt=attempt,
            manifest_artifact=manifest_artifact,
        )
        # Candidate/artifact writes remain inside this transaction.  Recheck
        # immediately before the final durable relation so a worker whose
        # lease expired during validation cannot commit any of those writes.
        await _require_live_materialization_lease(session, task=task, context=context)
        materialization = ResearchGenerationMaterialization(
            user_id=task.user_id,
            run_id=run.id,
            task_id=task.id,
            stage_attempt_id=attempt.id,
            candidate_id=candidate.id,
            model_invocation_id=invocation.id,
            manifest_artifact_id=manifest_artifact.id,
            model_output_hash=model_output_hash,
            materialization_hash=_materialization_hash(
                task=task,
                attempt=attempt,
                candidate=candidate,
                invocation=invocation,
                manifest_artifact=manifest_artifact,
                model_output_hash=model_output_hash,
                policy_version=self._policy.version,
            ),
        )
        session.add(materialization)
        await session.flush()
        return GenerationMaterializationResult(
            id=materialization.id,
            candidate_id=candidate.id,
            candidate_hash=candidate.candidate_hash,
            output_artifact_id=manifest_artifact.id,
        )


async def _locked_context_models(
    session: AsyncSession,
    context: GenerationStageContext,
) -> tuple[ResearchTask, ResearchStageAttempt]:
    _validate_context_shape(context)
    epoch = await lock_search_epoch(
        session, user_id=context.user_id, run_id=context.run_id, require_open=False
    )
    task = await session.scalar(
        select(ResearchTask).where(ResearchTask.id == context.task_id).with_for_update()
    )
    if task is None:
        raise ValueError("RESEARCH_GENERATION_MATERIALIZATION_TASK_NOT_FOUND")
    run = await session.scalar(
        select(ResearchRun).where(ResearchRun.id == context.run_id).with_for_update()
    )
    if run is None or run.experiment_epoch_id != epoch.id:
        raise ValueError("RESEARCH_GENERATION_MATERIALIZATION_RUN_CONTEXT_MISMATCH")
    attempt = await session.scalar(
        select(ResearchStageAttempt)
        .where(ResearchStageAttempt.id == context.stage_attempt_id)
        .with_for_update()
    )
    if attempt is None:
        raise ValueError("RESEARCH_GENERATION_MATERIALIZATION_ATTEMPT_NOT_FOUND")
    return task, attempt


async def _validate_locked_context(
    session: AsyncSession,
    *,
    task: ResearchTask,
    attempt: ResearchStageAttempt,
    context: GenerationStageContext,
) -> ResearchRun:
    if (
        task.id != context.task_id
        or task.user_id != context.user_id
        or task.run_id != context.run_id
        or task.status != "RUNNING"
        or task.lease_token != context.lease_token
    ):
        raise ValueError("RESEARCH_GENERATION_MATERIALIZATION_LEASE_DENIED")
    if (
        attempt.id != context.stage_attempt_id
        or attempt.task_id != task.id
        or attempt.run_id != task.run_id
        or attempt.stage != _GENERATE_STAGE
        or context.stage != _GENERATE_STAGE
        or attempt.status != "RUNNING"
        or attempt.lease_token != context.lease_token
    ):
        raise ValueError("RESEARCH_GENERATION_MATERIALIZATION_ATTEMPT_INVALID")
    run = await session.scalar(
        select(ResearchRun).where(ResearchRun.id == task.run_id).with_for_update()
    )
    if run is None:
        raise ValueError("RESEARCH_GENERATION_MATERIALIZATION_RUN_NOT_FOUND")
    if run.user_id != task.user_id or run.request_hash != context.request_hash:
        raise ValueError("RESEARCH_GENERATION_MATERIALIZATION_RUN_CONTEXT_MISMATCH")
    if not run.experiment_epoch_id or not run.dataset_snapshot_id:
        raise ValueError("RESEARCH_GENERATION_MATERIALIZATION_RUN_BINDING_MISSING")
    return run


async def _require_live_materialization_lease(
    session: AsyncSession,
    *,
    task: ResearchTask,
    context: GenerationStageContext,
) -> None:
    """Authorize a new materialization only at the database's current UTC time."""

    live_task_id = await session.scalar(
        select(ResearchTask.id)
        .where(
            ResearchTask.id == task.id,
            ResearchTask.user_id == context.user_id,
            ResearchTask.run_id == context.run_id,
            ResearchTask.status == "RUNNING",
            ResearchTask.lease_token == context.lease_token,
            ResearchTask.lease_expires_at.is_not(None),
            ResearchTask.lease_expires_at > DatabaseUtcNow(),
        )
        .with_for_update()
    )
    if live_task_id is None:
        raise ValueError("RESEARCH_GENERATION_MATERIALIZATION_LEASE_DENIED")
    if task.cancel_requested_at is not None:
        raise ValueError("RESEARCH_GENERATION_MATERIALIZATION_CANCEL_REQUESTED")


async def _validated_invocation(
    session: AsyncSession,
    *,
    run: ResearchRun,
    proposal: GenerationMaterializationProposal,
    model_output_hash: str,
) -> ResearchModelInvocation:
    invocation = await session.scalar(
        select(ResearchModelInvocation)
        .where(ResearchModelInvocation.id == proposal.model_invocation_id)
        .with_for_update()
    )
    if invocation is None:
        raise ValueError("RESEARCH_GENERATION_INVOCATION_NOT_FOUND")
    if invocation.run_id != run.id:
        raise ValueError("RESEARCH_GENERATION_INVOCATION_RUN_MISMATCH")
    if (
        invocation.error_code is not None
        or not invocation.output_hash
        or invocation.output_hash != model_output_hash
    ):
        raise ValueError("RESEARCH_GENERATION_INVOCATION_OUTPUT_HASH_MISMATCH")
    if not all(
        isinstance(value, str) and value.strip()
        for value in (
            invocation.provider,
            invocation.requested_model,
            invocation.resolved_model,
            invocation.prompt_template_version,
        )
    ):
        raise ValueError("RESEARCH_GENERATION_INVOCATION_PROVENANCE_INVALID")
    return invocation


async def _server_bound_inputs(
    session: AsyncSession,
    *,
    run: ResearchRun,
    user_id: str,
) -> tuple[ResearchHypothesisVersion, ResearchDatasetSnapshot]:
    hypothesis = await session.get(ResearchHypothesisVersion, run.hypothesis_version_id)
    dataset = await session.get(ResearchDatasetSnapshot, run.dataset_snapshot_id)
    if hypothesis is None or hypothesis.user_id != user_id or hypothesis.status != "CONFIRMED":
        raise ValueError("RESEARCH_GENERATION_HYPOTHESIS_BINDING_INVALID")
    if dataset is None or dataset.user_id != user_id:
        raise ValueError("RESEARCH_GENERATION_DATASET_BINDING_INVALID")
    if dataset.partition_kind == "SEALED_HOLDOUT":
        raise ValueError("RESEARCH_GENERATION_SEALED_DATASET_DENIED")
    require_verified_snapshot_integrity(dataset)
    return hypothesis, dataset


async def _exact_existing_result(
    session: AsyncSession,
    *,
    existing: ResearchGenerationMaterialization,
    task: ResearchTask,
    attempt: ResearchStageAttempt,
    proposal: GenerationMaterializationProposal,
    model_output_hash: str,
) -> GenerationMaterializationResult:
    if (
        existing.user_id != task.user_id
        or existing.run_id != task.run_id
        or existing.task_id != task.id
        or existing.stage_attempt_id != attempt.id
        or existing.model_invocation_id != proposal.model_invocation_id
        or existing.model_output_hash != model_output_hash
    ):
        raise ValueError("RESEARCH_GENERATION_MATERIALIZATION_CONFLICT")
    candidate = await session.get(ResearchCandidate, existing.candidate_id)
    manifest = await session.get(ResearchArtifact, existing.manifest_artifact_id)
    binding = await session.scalar(
        select(ResearchStageArtifactBinding).where(
            ResearchStageArtifactBinding.stage_attempt_id == attempt.id,
            ResearchStageArtifactBinding.artifact_id == existing.manifest_artifact_id,
        )
    )
    if candidate is None or manifest is None or binding is None:
        raise ValueError("RESEARCH_GENERATION_MATERIALIZATION_BINDING_INVALID")
    if candidate.run_id != task.run_id or candidate.user_id != task.user_id:
        raise ValueError("RESEARCH_GENERATION_MATERIALIZATION_BINDING_INVALID")
    return GenerationMaterializationResult(
        id=existing.id,
        candidate_id=candidate.id,
        candidate_hash=candidate.candidate_hash,
        output_artifact_id=manifest.id,
    )


def _parse_draft(model_output: str) -> _GeneratedCandidateDraft:
    if not isinstance(model_output, str) or not model_output.strip():
        raise ValueError("RESEARCH_GENERATION_OUTPUT_INVALID")
    if len(model_output.encode("utf-8")) > _MAX_GENERATION_OUTPUT_BYTES:
        raise ValueError("RESEARCH_GENERATION_OUTPUT_TOO_LARGE")
    try:
        payload = json.loads(
            model_output,
            object_pairs_hook=_unique_json_object,
            parse_constant=_invalid_json_constant,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("RESEARCH_GENERATION_OUTPUT_SCHEMA_INVALID") from exc
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "strategy_code",
        "dependency_lock",
        "params",
    }:
        raise ValueError("RESEARCH_GENERATION_OUTPUT_SCHEMA_INVALID")
    if payload["schema_version"] != _DRAFT_SCHEMA_VERSION:
        raise ValueError("RESEARCH_GENERATION_OUTPUT_SCHEMA_INVALID")
    strategy_code = payload["strategy_code"]
    dependency_lock = payload["dependency_lock"]
    params = payload["params"]
    if not isinstance(strategy_code, str) or not strategy_code.strip():
        raise ValueError("RESEARCH_GENERATION_STRATEGY_CODE_INVALID")
    if not isinstance(dependency_lock, str) or not dependency_lock.strip():
        raise ValueError("RESEARCH_GENERATION_DEPENDENCY_LOCK_INVALID")
    if (
        len(strategy_code.encode("utf-8")) > _MAX_COMPONENT_BYTES
        or len(dependency_lock.encode("utf-8")) > _MAX_COMPONENT_BYTES
    ):
        raise ValueError("RESEARCH_GENERATION_COMPONENT_TOO_LARGE")
    params_copy = _mapping_copy(params, error_code="RESEARCH_GENERATION_PARAMS_INVALID")
    return _GeneratedCandidateDraft(
        strategy_code=strategy_code,
        dependency_lock=dependency_lock,
        params=params_copy,
    )


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject ambiguous keys at every nesting level of untrusted model output."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _invalid_json_constant(value: str) -> Any:
    """JSON permits neither NaN nor Infinity, including nested parameters."""
    raise ValueError("non-finite JSON constant")


async def _register_local_artifact(
    session: AsyncSession,
    *,
    kind: str,
    content: str,
    media_type: str,
    schema_version: str,
) -> ResearchArtifact:
    payload = content.encode("utf-8")
    digest = sha256(payload).hexdigest()
    descriptor = ArtifactBroker().validate_descriptor(
        ArtifactDescriptor(
            kind=kind,
            content_hash=digest,
            storage_uri=f"controlled://local-generation/{digest}",
            size_bytes=len(payload),
            media_type=media_type,
            schema_version=schema_version,
            producer_identity=_PRODUCER_IDENTITY,
        )
    )
    artifact = await session.scalar(
        select(ResearchArtifact)
        .where(
            ResearchArtifact.content_hash == descriptor.content_hash,
            ResearchArtifact.kind == descriptor.kind,
        )
        .with_for_update()
    )
    if artifact is None:
        artifact = ResearchArtifact(
            kind=descriptor.kind,
            content_hash=descriptor.content_hash,
            storage_uri=descriptor.storage_uri,
            size_bytes=descriptor.size_bytes,
            media_type=descriptor.media_type,
            schema_version=descriptor.schema_version,
            producer_identity=descriptor.producer_identity,
            container_image_digest=descriptor.container_image_digest,
        )
        session.add(artifact)
        await session.flush()
        session.add(ResearchArtifactContent(artifact_id=artifact.id, content=payload))
        await session.flush()
        return artifact
    if not _descriptor_matches(artifact, descriptor):
        raise ValueError("RESEARCH_GENERATION_ARTIFACT_CONTENT_COLLISION")
    stored_content = await session.get(ResearchArtifactContent, artifact.id)
    if stored_content is None or stored_content.content != payload:
        raise ValueError("RESEARCH_GENERATION_ARTIFACT_CONTENT_COLLISION")
    return artifact


async def _bind_manifest(
    session: AsyncSession,
    *,
    task: ResearchTask,
    attempt: ResearchStageAttempt,
    manifest_artifact: ResearchArtifact,
) -> None:
    binding = await session.scalar(
        select(ResearchStageArtifactBinding)
        .where(ResearchStageArtifactBinding.stage_attempt_id == attempt.id)
        .with_for_update()
    )
    if binding is not None:
        raise ValueError("RESEARCH_GENERATION_MANIFEST_BINDING_CONFLICT")
    session.add(
        ResearchStageArtifactBinding(
            user_id=task.user_id,
            run_id=task.run_id,
            task_id=task.id,
            stage_attempt_id=attempt.id,
            artifact_id=manifest_artifact.id,
        )
    )
    await session.flush()


def _manifest_payload(
    *,
    context: GenerationStageContext,
    run: ResearchRun,
    candidate: ResearchCandidate,
    invocation: ResearchModelInvocation,
    code_artifact: ResearchArtifact,
    dependency_artifact: ResearchArtifact,
    environment_hash: str,
    cost_model_hash: str,
    policy_version: str,
) -> dict[str, Any]:
    return {
        "schema_version": _MANIFEST_SCHEMA_VERSION,
        "stage": _GENERATE_STAGE,
        "task_id": context.task_id,
        "run_id": run.id,
        "stage_attempt_id": context.stage_attempt_id,
        "request_hash": run.request_hash,
        "trace_id": context.trace_id,
        "origin": "llm",
        "policy_version": policy_version,
        "model_invocation_id": invocation.id,
        "model_output_hash": invocation.output_hash,
        "candidate_id": candidate.id,
        "candidate_hash": candidate.candidate_hash,
        "code_artifact": {
            "id": code_artifact.id,
            "kind": code_artifact.kind,
            "content_hash": code_artifact.content_hash,
        },
        "dependency_artifact": {
            "id": dependency_artifact.id,
            "kind": dependency_artifact.kind,
            "content_hash": dependency_artifact.content_hash,
        },
        "environment_hash": environment_hash,
        "cost_model_hash": cost_model_hash,
        "params_hash": content_hash(candidate.params),
        "execution_state": "MATERIALIZED_NOT_EXECUTED",
        "sandbox_receipt_id": None,
        "evaluation_id": None,
        "market_trial_id": None,
    }


def _materialization_hash(
    *,
    task: ResearchTask,
    attempt: ResearchStageAttempt,
    candidate: ResearchCandidate,
    invocation: ResearchModelInvocation,
    manifest_artifact: ResearchArtifact,
    model_output_hash: str,
    policy_version: str,
) -> str:
    return content_hash(
        {
            "task_id": task.id,
            "run_id": task.run_id,
            "stage_attempt_id": attempt.id,
            "candidate_id": candidate.id,
            "candidate_hash": candidate.candidate_hash,
            "model_invocation_id": invocation.id,
            "model_output_hash": model_output_hash,
            "manifest_artifact_id": manifest_artifact.id,
            "manifest_hash": manifest_artifact.content_hash,
            "policy_version": policy_version,
        }
    )


def _cost_model_hash(
    *,
    hypothesis: ResearchHypothesisVersion,
    dataset: ResearchDatasetSnapshot,
) -> str:
    cost_model = hypothesis.canonical_payload.get("cost_model")
    if not isinstance(cost_model, dict) or not isinstance(dataset.execution_policy, dict):
        raise ValueError("RESEARCH_GENERATION_COST_MODEL_BINDING_INVALID")
    return content_hash(
        {
            "cost_model": cost_model,
            "execution_policy": dataset.execution_policy,
        }
    )


def _descriptor_matches(model: ResearchArtifact, descriptor: ArtifactDescriptor) -> bool:
    return (
        model.kind == descriptor.kind
        and model.content_hash == descriptor.content_hash
        and model.storage_uri == descriptor.storage_uri
        and model.size_bytes == descriptor.size_bytes
        and model.media_type == descriptor.media_type
        and model.schema_version == descriptor.schema_version
        and model.producer_identity == descriptor.producer_identity
        and model.container_image_digest == descriptor.container_image_digest
    )


def _validate_context_shape(context: GenerationStageContext) -> None:
    try:
        values = (
            context.task_id,
            context.run_id,
            context.user_id,
            context.stage_attempt_id,
            context.lease_token,
            context.stage,
            context.request_hash,
        )
    except AttributeError as exc:
        raise ValueError("RESEARCH_GENERATION_MATERIALIZATION_CONTEXT_REQUIRED") from exc
    if not all(isinstance(value, str) and value.strip() for value in values):
        raise ValueError("RESEARCH_GENERATION_MATERIALIZATION_CONTEXT_REQUIRED")


def _validate_proposal_shape(proposal: GenerationMaterializationProposal) -> None:
    if (
        not isinstance(proposal.model_invocation_id, str)
        or not proposal.model_invocation_id.strip()
        or not isinstance(proposal.model_output, str)
        or not proposal.model_output.strip()
    ):
        raise ValueError("RESEARCH_GENERATION_PROPOSAL_INVALID")


def _mapping_copy(value: Any, *, error_code: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(error_code)
    try:
        normalized = json.loads(
            json.dumps(dict(value), ensure_ascii=True, sort_keys=True, allow_nan=False)
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(error_code) from exc
    if not isinstance(normalized, dict):
        raise ValueError(error_code)
    return normalized
