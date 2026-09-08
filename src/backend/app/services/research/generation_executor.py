"""Deployment-owned, fail-closed GENERATE execution for protocol-v2 research.

This module deliberately does not select a provider, read a user AI preference,
render an active prompt, execute generated code, or create a candidate.  A
deployment composes it with a preconfigured :class:`LlmGateway`, an attested
dataset registry, and one immutable policy.  The worker's stage-completion
service remains the only component that materializes a returned proposal.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any

from sqlalchemy import select

from app.db import database
from app.models.ai_research_v2 import (
    ResearchDatasetSnapshot,
    ResearchExperimentEpoch,
    ResearchHypothesisVersion,
    ResearchQuotaBucket,
    ResearchRun,
    ResearchStageAttempt,
    ResearchTask,
)
from app.services.research.canonical import content_hash, normalize_payload
from app.services.research.capability_registry import CapabilityRegistry
from app.services.research.data_precheck import ResearchDataPrecheckService
from app.services.research.database_clock import database_utc_now
from app.services.research.dataset_registry import DatasetRegistry
from app.services.research.generation_materialization import GenerationMaterializationProposal
from app.services.research.llm_gateway import GatewayResult, LlmGateway
from app.services.research.quota import QuotaReservationRequest, QuotaService
from app.services.research.redaction import redact_sensitive_payload
from app.services.research.workflow_worker import StageExecutionContext, StageExecutionOutcome

_GENERATE_STAGE = "GENERATE"
_OUTPUT_SCHEMA_VERSION = "research-generation-v1"
_OUTPUT_FIELDS = frozenset({"schema_version", "strategy_code", "dependency_lock", "params"})
_MAX_PROMPT_BYTES = 256 * 1024
_MAX_RESERVED_TOKENS = 1_000_000
_MAX_QUOTA_LEASE_SECONDS = 24 * 60 * 60
_MAX_OUTPUT_BYTES = 1_048_576
_SAFE_ERROR_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,127}\Z")


@dataclass(frozen=True, slots=True)
class GenerationExecutorPolicy:
    """Immutable deployment policy for one provider-fenced GENERATE stage.

    ``model_alias`` and prompt fields are deliberately deployment configuration,
    rather than task/request fields.  ``sampling_params`` is deeply snapshotted
    in ``__post_init__`` because a frozen dataclass alone does not freeze nested
    mutable mappings.
    """

    model_alias: str
    prompt_template_version: str
    prompt_content: str
    prompt_content_hash: str
    sampling_params: Mapping[str, Any]
    quota_policy_version: str
    reserved_tokens: int
    quota_lease_seconds: int = 900

    def __post_init__(self) -> None:
        _require_text(self.model_alias, "RESEARCH_GENERATION_MODEL_ALIAS_INVALID", 256)
        _require_text(
            self.prompt_template_version,
            "RESEARCH_GENERATION_PROMPT_VERSION_INVALID",
            128,
        )
        _require_text(
            self.prompt_content, "RESEARCH_GENERATION_PROMPT_CONTENT_INVALID", _MAX_PROMPT_BYTES
        )
        _require_text(
            self.prompt_content_hash,
            "RESEARCH_GENERATION_PROMPT_HASH_INVALID",
            64,
        )
        if self.prompt_content_hash != content_hash({"prompt": self.prompt_content}):
            raise ValueError("RESEARCH_GENERATION_PROMPT_HASH_INVALID")
        # A static prompt should not carry operator credentials into the model
        # request or an immutable invocation ledger.
        if redact_sensitive_payload(self.prompt_content) != self.prompt_content:
            raise ValueError("RESEARCH_GENERATION_PROMPT_CONTENT_INVALID")
        _require_text(
            self.quota_policy_version,
            "RESEARCH_GENERATION_QUOTA_POLICY_INVALID",
            128,
        )
        if (
            type(self.reserved_tokens) is not int
            or not 0 < self.reserved_tokens <= _MAX_RESERVED_TOKENS
        ):
            raise ValueError("RESEARCH_GENERATION_QUOTA_RESERVATION_INVALID")
        if (
            type(self.quota_lease_seconds) is not int
            or not 0 < self.quota_lease_seconds <= _MAX_QUOTA_LEASE_SECONDS
        ):
            raise ValueError("RESEARCH_GENERATION_QUOTA_LEASE_INVALID")
        object.__setattr__(self, "sampling_params", _freeze_sampling_params(self.sampling_params))


@dataclass(frozen=True, slots=True)
class _GenerationInputs:
    """Server-read state copied before the provider-facing dispatch boundary."""

    task_id: str
    run_id: str
    user_id: str
    request_hash: str
    trace_id: str | None
    hypothesis_payload: dict[str, Any]
    hypothesis_content_hash: str
    dataset: dict[str, Any]
    epoch: dict[str, Any]


class ResearchGenerationExecutor:
    """Create a typed model proposal only for a current, attested GENERATE lease."""

    def __init__(
        self,
        *,
        gateway: LlmGateway,
        dataset_registry: DatasetRegistry,
        policy: GenerationExecutorPolicy,
    ) -> None:
        if not isinstance(gateway, LlmGateway):
            raise ValueError("RESEARCH_GENERATION_GATEWAY_REQUIRED")
        if not isinstance(dataset_registry, DatasetRegistry):
            raise ValueError("RESEARCH_GENERATION_DATASET_REGISTRY_REQUIRED")
        if not isinstance(policy, GenerationExecutorPolicy):
            raise ValueError("RESEARCH_GENERATION_POLICY_REQUIRED")
        self._gateway = gateway
        self._datasets = dataset_registry
        self._policy = policy
        self._quota = QuotaService()
        self._prechecks = ResearchDataPrecheckService(dataset_registry=dataset_registry)
        self._capabilities = CapabilityRegistry()

    async def execute(self, context: StageExecutionContext) -> StageExecutionOutcome:
        """Invoke only one fixed model policy under a current server-owned lease.

        Expected policy, database, quota, and provider errors become a stable
        failed stage outcome.  There is intentionally no deterministic output
        or provider fallback after any failure.
        """

        try:
            inputs = await self._validated_inputs(context)
            bucket_id = await self._select_user_quota_bucket(inputs.user_id)
            system_input = _system_input(self._policy)
            typed_input = _typed_input(inputs)
            quote = None
            reservation_context = None
            token_amount = self._policy.reserved_tokens
            request_hash = inputs.request_hash
            additional_requests = ()
            if self._gateway.requires_budget_bundle:
                quote = await self._gateway.prepare_budget(
                    run_id=inputs.run_id,
                    requested_model=self._policy.model_alias,
                    prompt_template_version=self._policy.prompt_template_version,
                    system_input=system_input,
                    typed_input=typed_input,
                    sampling_params=self._policy.sampling_params,
                    token_limit=self._policy.reserved_tokens,
                )
                reservation_context = quote.context(
                    run_request_hash=inputs.request_hash,
                    task_id=inputs.task_id,
                    stage_attempt_id=context.stage_attempt_id,
                    quota_policy_version=self._policy.quota_policy_version,
                )
                request_hash = content_hash(reservation_context)
                token_amount = quote.reserved_tokens
                money_bucket_id = await self._select_user_quota_bucket(
                    inputs.user_id, resource_type="model_cost_microusd"
                )
                additional_requests = (
                    QuotaReservationRequest(
                        bucket_id=money_bucket_id,
                        resource_type="model_cost_microusd",
                        amount=quote.reserved_microusd,
                        unit="microusd",
                    ),
                )
            receipts = await self._quota.reserve(
                task_id=inputs.task_id,
                policy_version=self._policy.quota_policy_version,
                idempotency_key=f"generation:{context.stage_attempt_id}",
                request_hash=request_hash,
                reservation_context=reservation_context,
                requests=(
                    QuotaReservationRequest(
                        bucket_id=bucket_id,
                        resource_type="model_tokens",
                        amount=token_amount,
                        unit="tokens",
                    ),
                )
                + additional_requests,
                lease_seconds=self._policy.quota_lease_seconds,
                stage_attempt_id=context.stage_attempt_id,
                trace_id=inputs.trace_id,
            )
            receipt = next(item for item in receipts if item.resource_type == "model_tokens")
            if (
                receipt.bucket_id != bucket_id
                or receipt.resource_type != "model_tokens"
                or receipt.unit != "tokens"
                or receipt.reserved_amount != token_amount
            ):
                raise ValueError("RESEARCH_GENERATION_QUOTA_RECEIPT_INVALID")
            try:
                result = await self._gateway.invoke(
                    run_id=inputs.run_id,
                    requested_model=self._policy.model_alias,
                    prompt_template_version=self._policy.prompt_template_version,
                    system_input=system_input,
                    typed_input=typed_input,
                    sampling_params=self._policy.sampling_params,
                    task_id=inputs.task_id,
                    stage_attempt_id=context.stage_attempt_id,
                    lease_token=context.lease_token,
                    stage=_GENERATE_STAGE,
                    quota_reservation_id=receipt.reservation_id,
                    quota_fencing_token=receipt.fencing_token,
                    origin="LLM",
                    tool_manifest=(),
                    budget_quote=quote,
                    quota_receipts=receipts if quote is not None else (),
                    quota_policy_version=self._policy.quota_policy_version,
                )
            except Exception:
                # The adapter is an infrastructure trust boundary.  It may
                # expose a provider exception after recording its own durable
                # failure receipt; never let that exception become a stage or
                # API-visible error detail.
                return StageExecutionOutcome.failed("RESEARCH_GENERATION_GATEWAY_FAILED")
            _validate_gateway_result(result)
            _validate_generation_output(result.output)
            return StageExecutionOutcome.generated(
                proposal=GenerationMaterializationProposal(
                    model_invocation_id=result.invocation_id,
                    model_output=result.output,
                )
            )
        except ValueError as exc:
            return StageExecutionOutcome.failed(_stable_error_code(exc))
        except Exception:
            # Do not expose a provider adapter exception, database dialect
            # detail, path, endpoint, or credential-bearing message to clients.
            return StageExecutionOutcome.failed("RESEARCH_GENERATION_EXECUTOR_FAILED")

    async def _validated_inputs(self, context: StageExecutionContext) -> _GenerationInputs:
        """Read and validate all state that a browser may not authoritatively select."""

        _validate_context(context)
        dataset: ResearchDatasetSnapshot | None = None
        async with database.async_session_maker() as session:
            try:
                now = await database_utc_now(session)
                task = await session.scalar(
                    select(ResearchTask).where(ResearchTask.id == context.task_id).with_for_update()
                )
                if task is None or task.user_id != context.user_id or task.run_id != context.run_id:
                    raise ValueError("RESEARCH_GENERATION_CONTEXT_DENIED")
                if (
                    task.status != "RUNNING"
                    or task.lease_token != context.lease_token
                    or task.lease_expires_at is None
                    or _as_utc(task.lease_expires_at) <= now
                    or task.cancel_requested_at is not None
                    or task.stage_cursor != _GENERATE_STAGE
                ):
                    raise ValueError("RESEARCH_GENERATION_LEASE_DENIED")
                if task.trace_id != context.trace_id:
                    raise ValueError("RESEARCH_GENERATION_CONTEXT_DENIED")
                run = await session.scalar(
                    select(ResearchRun).where(ResearchRun.id == task.run_id).with_for_update()
                )
                if (
                    run is None
                    or run.user_id != context.user_id
                    or run.id != context.run_id
                    or run.status != "RUNNING"
                    or run.stage_cursor != _GENERATE_STAGE
                    or run.request_hash != context.request_hash
                    or task.idempotency_request_hash != run.request_hash
                    or run.protocol_version != "v2"
                ):
                    raise ValueError("RESEARCH_GENERATION_CONTEXT_DENIED")
                attempt = await session.scalar(
                    select(ResearchStageAttempt)
                    .where(ResearchStageAttempt.id == context.stage_attempt_id)
                    .with_for_update()
                )
                if (
                    attempt is None
                    or attempt.task_id != task.id
                    or attempt.run_id != run.id
                    or attempt.stage != _GENERATE_STAGE
                    or attempt.status != "RUNNING"
                    or attempt.lease_token != context.lease_token
                ):
                    raise ValueError("RESEARCH_GENERATION_CONTEXT_DENIED")
                if not run.dataset_snapshot_id or not run.experiment_epoch_id:
                    raise ValueError("RESEARCH_GENERATION_RUN_BINDING_INVALID")
                hypothesis = await session.scalar(
                    select(ResearchHypothesisVersion)
                    .where(
                        ResearchHypothesisVersion.id == run.hypothesis_version_id,
                        ResearchHypothesisVersion.user_id == context.user_id,
                    )
                    .with_for_update()
                )
                dataset = await session.scalar(
                    select(ResearchDatasetSnapshot)
                    .where(
                        ResearchDatasetSnapshot.id == run.dataset_snapshot_id,
                        ResearchDatasetSnapshot.user_id == context.user_id,
                    )
                    .with_for_update()
                )
                epoch = await session.scalar(
                    select(ResearchExperimentEpoch)
                    .where(
                        ResearchExperimentEpoch.id == run.experiment_epoch_id,
                        ResearchExperimentEpoch.user_id == context.user_id,
                    )
                    .with_for_update()
                )
                _validate_research_bindings(
                    hypothesis=hypothesis,
                    dataset=dataset,
                    epoch=epoch,
                    task=task,
                    run=run,
                )
                profile = await self._capabilities.get(
                    run.capability_profile_id,
                    run.capability_profile_version,
                )
                decision = await self._capabilities.evaluate(
                    run.capability_profile_id,
                    run.capability_profile_version,
                    required=("protocol_v2",),
                )
                if (
                    profile is None
                    or not decision.allowed
                    or profile.evidence_hash != run.capability_evidence_hash
                ):
                    raise ValueError("RESEARCH_GENERATION_PROFILE_NOT_CURRENT")
                assert hypothesis is not None and dataset is not None and epoch is not None
                await self._prechecks.require_current(
                    session,
                    user_id=context.user_id,
                    precheck_id=run.data_precheck_id,
                    hypothesis=hypothesis,
                    dataset=dataset,
                    epoch=epoch,
                    profile=profile,
                    profile_id=run.capability_profile_id,
                    profile_version=run.capability_profile_version,
                    promotion_policy_version=run.promotion_policy_version,
                    request_json=dict(task.request_json or {}),
                    workspace_id=run.workspace_id,
                    now=now,
                )
                inputs = _GenerationInputs(
                    task_id=task.id,
                    run_id=run.id,
                    user_id=task.user_id,
                    request_hash=run.request_hash,
                    trace_id=task.trace_id,
                    hypothesis_payload=_json_mapping_copy(hypothesis.canonical_payload),
                    hypothesis_content_hash=hypothesis.content_hash,
                    dataset=_dataset_input(dataset),
                    epoch=_epoch_input(epoch),
                )
                await session.commit()
                return inputs
            except ValueError:
                # Revalidation intentionally marks a drifted attested snapshot
                # FAILED.  Preserve that quarantine while rolling back unrelated
                # partial reads or writes.
                if dataset is not None and dataset.integrity_status == "FAILED":
                    await session.commit()
                else:
                    await session.rollback()
                raise
            except Exception:
                await session.rollback()
                raise

    async def _select_user_quota_bucket(
        self, user_id: str, *, resource_type: str = "model_tokens"
    ) -> str:
        """Select exactly one live user/resource bucket from server state only."""

        async with database.async_session_maker() as session:
            now = await database_utc_now(session)
            buckets = list(
                await session.scalars(
                    select(ResearchQuotaBucket)
                    .where(
                        ResearchQuotaBucket.scope_type == "user",
                        ResearchQuotaBucket.scope_id == user_id,
                        ResearchQuotaBucket.policy_version == self._policy.quota_policy_version,
                        ResearchQuotaBucket.resource_type == resource_type,
                        ResearchQuotaBucket.status == "ACTIVE",
                        ResearchQuotaBucket.window_start <= now,
                        ResearchQuotaBucket.window_end > now,
                    )
                    .order_by(ResearchQuotaBucket.id)
                    .with_for_update()
                )
            )
        if len(buckets) != 1:
            raise ValueError("RESEARCH_GENERATION_QUOTA_BUCKET_UNAVAILABLE")
        return buckets[0].id


def _validate_context(context: StageExecutionContext) -> None:
    """Reject malformed or wrong-stage worker contexts before any database read."""

    if not isinstance(context, StageExecutionContext):
        raise ValueError("RESEARCH_GENERATION_CONTEXT_DENIED")
    if context.stage != _GENERATE_STAGE:
        raise ValueError("RESEARCH_GENERATION_CONTEXT_DENIED")
    values = (
        context.task_id,
        context.run_id,
        context.user_id,
        context.stage_attempt_id,
        context.lease_token,
        context.request_hash,
    )
    if not all(isinstance(value, str) and value.strip() for value in values):
        raise ValueError("RESEARCH_GENERATION_CONTEXT_DENIED")
    if not re.fullmatch(r"[0-9a-f]{64}", context.request_hash):
        raise ValueError("RESEARCH_GENERATION_CONTEXT_DENIED")
    if context.trace_id is not None and (
        not isinstance(context.trace_id, str) or not context.trace_id.strip()
    ):
        raise ValueError("RESEARCH_GENERATION_CONTEXT_DENIED")


def _validate_research_bindings(
    *,
    hypothesis: ResearchHypothesisVersion | None,
    dataset: ResearchDatasetSnapshot | None,
    epoch: ResearchExperimentEpoch | None,
    task: ResearchTask,
    run: ResearchRun,
) -> None:
    """Validate owner, confirmed hypothesis, non-sealed dataset, and open epoch."""

    if hypothesis is None or hypothesis.user_id != task.user_id or hypothesis.status != "CONFIRMED":
        raise ValueError("RESEARCH_GENERATION_HYPOTHESIS_BINDING_INVALID")
    if dataset is None or dataset.user_id != task.user_id:
        raise ValueError("RESEARCH_GENERATION_DATASET_BINDING_INVALID")
    if dataset.partition_kind == "SEALED_HOLDOUT":
        raise ValueError("RESEARCH_GENERATION_SEALED_DATASET_DENIED")
    if dataset.partition_kind not in {"DISCOVERY", "ITERATION_VALIDATION"}:
        raise ValueError("RESEARCH_GENERATION_DATASET_BINDING_INVALID")
    if (
        epoch is None
        or epoch.user_id != task.user_id
        or epoch.status != "OPEN"
        or epoch.hypothesis_version_id != hypothesis.id
    ):
        raise ValueError("RESEARCH_GENERATION_EPOCH_BINDING_INVALID")
    policy_version = (hypothesis.canonical_payload or {}).get("dataset_policy_version")
    if (
        not isinstance(policy_version, str)
        or not policy_version.strip()
        or policy_version != dataset.dataset_policy_version
        or policy_version != epoch.dataset_policy_version
    ):
        raise ValueError("RESEARCH_GENERATION_DATASET_POLICY_MISMATCH")
    request = task.request_json
    if (
        not isinstance(request, dict)
        or request.get("hypothesis_content_hash") != hypothesis.content_hash
        or request.get("dataset_snapshot_id") != dataset.id
        or request.get("experiment_epoch_id") != epoch.id
    ):
        raise ValueError("RESEARCH_GENERATION_REQUEST_BINDING_INVALID")
    if run.hypothesis_version_id != hypothesis.id:
        raise ValueError("RESEARCH_GENERATION_HYPOTHESIS_BINDING_INVALID")


def _system_input(policy: GenerationExecutorPolicy) -> dict[str, Any]:
    """Build a fixed schema instruction without consulting a mutable template registry."""

    return {
        "schema_version": "research-generation-system-v1",
        "prompt_content": policy.prompt_content,
        "prompt_content_hash": policy.prompt_content_hash,
        "required_output_schema": {
            "schema_version": _OUTPUT_SCHEMA_VERSION,
            "required_fields": sorted(_OUTPUT_FIELDS),
            "additional_properties": False,
        },
    }


def _typed_input(inputs: _GenerationInputs) -> dict[str, Any]:
    """Expose only server-bound research metadata, never a URI or sealed bytes."""

    return {
        "schema_version": "research-generation-input-v1",
        "run": {
            "id": inputs.run_id,
            "request_hash": inputs.request_hash,
            "trace_id": inputs.trace_id,
        },
        "hypothesis": {
            "content_hash": inputs.hypothesis_content_hash,
            "canonical_payload": _json_mapping_copy(inputs.hypothesis_payload),
        },
        "dataset": _json_mapping_copy(inputs.dataset),
        "experiment_epoch": _json_mapping_copy(inputs.epoch),
    }


def _dataset_input(dataset: ResearchDatasetSnapshot) -> dict[str, Any]:
    """Build a non-sealed metadata summary without storage locators or object IDs."""

    source = dict(dataset.source_manifest or {})
    return {
        "snapshot_id": dataset.id,
        "content_hash": dataset.content_hash,
        "snapshot_identity_hash": dataset.snapshot_identity_hash,
        "partition_kind": dataset.partition_kind,
        "dataset_policy_version": dataset.dataset_policy_version,
        "instruments": {
            key: (dataset.instrument_manifest or {}).get(key)
            for key in ("symbols", "asset_class", "identity_scheme")
        },
        "source": {
            key: source.get(key)
            for key in (
                "provider",
                "frequency",
                "timezone",
                "adjustment_rule",
                "event_time_basis",
                "ingested_at",
                "as_of_at",
                "vintage",
            )
        },
        "split": _json_mapping_copy(dataset.split_manifest),
        "execution_policy": _json_mapping_copy(dataset.execution_policy),
        "point_in_time_cutoff": _iso_utc(dataset.point_in_time_cutoff),
        "license_tags": list(dataset.license_tags or []),
    }


def _epoch_input(epoch: ResearchExperimentEpoch) -> dict[str, Any]:
    return {
        "id": epoch.id,
        "family_hash": epoch.family_hash,
        "dataset_policy_version": epoch.dataset_policy_version,
        "search_budget": _json_mapping_copy(epoch.search_budget),
    }


def _validate_gateway_result(result: object) -> None:
    if (
        not isinstance(result, GatewayResult)
        or not isinstance(result.invocation_id, str)
        or not result.invocation_id.strip()
        or not isinstance(result.output, str)
    ):
        raise ValueError("RESEARCH_GENERATION_GATEWAY_RESULT_INVALID")


def _validate_generation_output(output: str) -> None:
    """Require the public materialization schema without executing generated code."""

    if not output.strip() or len(output.encode("utf-8")) > _MAX_OUTPUT_BYTES:
        raise ValueError("RESEARCH_GENERATION_OUTPUT_SCHEMA_INVALID")
    try:
        payload = json.loads(output)
    except (TypeError, ValueError):
        raise ValueError("RESEARCH_GENERATION_OUTPUT_SCHEMA_INVALID") from None
    if not isinstance(payload, dict) or set(payload) != _OUTPUT_FIELDS:
        raise ValueError("RESEARCH_GENERATION_OUTPUT_SCHEMA_INVALID")
    if payload.get("schema_version") != _OUTPUT_SCHEMA_VERSION:
        raise ValueError("RESEARCH_GENERATION_OUTPUT_SCHEMA_INVALID")
    if not isinstance(payload.get("strategy_code"), str) or not payload["strategy_code"].strip():
        raise ValueError("RESEARCH_GENERATION_OUTPUT_SCHEMA_INVALID")
    if (
        not isinstance(payload.get("dependency_lock"), str)
        or not payload["dependency_lock"].strip()
    ):
        raise ValueError("RESEARCH_GENERATION_OUTPUT_SCHEMA_INVALID")
    if not isinstance(payload.get("params"), dict):
        raise ValueError("RESEARCH_GENERATION_OUTPUT_SCHEMA_INVALID")


def _freeze_sampling_params(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("RESEARCH_GENERATION_SAMPLING_PARAMS_INVALID")
    try:
        normalized = normalize_payload(dict(value))
    except (TypeError, ValueError):
        raise ValueError("RESEARCH_GENERATION_SAMPLING_PARAMS_INVALID") from None
    if not isinstance(normalized, dict):
        raise ValueError("RESEARCH_GENERATION_SAMPLING_PARAMS_INVALID")
    return _deep_freeze(normalized)


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _deep_freeze(child) for key, child in value.items()})
    if isinstance(value, list):
        return tuple(_deep_freeze(child) for child in value)
    return value


def _json_mapping_copy(value: object) -> dict[str, Any]:
    try:
        normalized = normalize_payload(dict(value or {}))
    except (TypeError, ValueError):
        raise ValueError("RESEARCH_GENERATION_INPUT_INVALID") from None
    if not isinstance(normalized, dict):
        raise ValueError("RESEARCH_GENERATION_INPUT_INVALID")
    return normalized


def _require_text(value: object, error_code: str, max_bytes: int) -> None:
    if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > max_bytes:
        raise ValueError(error_code)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return _as_utc(value).isoformat().replace("+00:00", "Z")


def _stable_error_code(exc: ValueError) -> str:
    code = str(exc)
    if _SAFE_ERROR_CODE.fullmatch(code):
        return code
    return "RESEARCH_GENERATION_EXECUTOR_FAILED"
