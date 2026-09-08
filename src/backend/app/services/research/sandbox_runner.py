"""Client-side contract for a separately deployed restricted sandbox runner.

This module does not start containers and never mounts a Docker socket.  It
validates a complete, fenced command before handing it to an injected remote
runner client.  Production enablement still requires deployment-level evidence
that the remote implementation enforces the policy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from app.db import database
from app.models.ai_research_v2 import ResearchArtifact, ResearchCandidate
from app.services.research.artifact_broker import ArtifactBroker, ArtifactDescriptor
from app.services.research.capability_registry import CapabilityRegistry
from app.services.research.quota import QuotaService

_IMAGE_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_VALID_STAGES = frozenset({"PREFLIGHT", "TRAIN", "VALIDATE", "SEALED_EVALUATE", "PAPER"})
_VALID_STATUSES = frozenset({"SUCCEEDED", "FAILED", "TIMED_OUT", "CANCELLED"})


@dataclass(frozen=True, slots=True)
class SandboxPolicy:
    """Non-negotiable resource and filesystem controls for one execution."""

    version: str
    image_digest: str
    network_mode: str
    input_read_only: bool
    output_path: str
    cpu_limit: int
    memory_limit_mb: int
    pid_limit: int
    wall_timeout_seconds: int
    output_limit_bytes: int


@dataclass(frozen=True, slots=True)
class SandboxExecutionRequest:
    """Opaque frozen-artifact execution request; it deliberately carries no URI."""

    task_id: str
    stage_attempt_id: str
    lease_token: str
    candidate_id: str
    profile_id: str
    profile_version: str
    runner_identity: str
    stage: str
    policy: SandboxPolicy
    code_artifact_hash: str
    dependency_artifact_hash: str
    environment_hash: str
    quota_reservation_id: str
    quota_fencing_token: int


@dataclass(frozen=True, slots=True)
class SandboxExecutionReceipt:
    """Remote runner result that must echo all frozen identity bindings."""

    status: str
    exit_code: int | None
    image_digest: str
    policy_version: str
    code_artifact_hash: str
    dependency_artifact_hash: str
    environment_hash: str
    artifacts: tuple[ArtifactDescriptor, ...]


class SandboxExecutor(Protocol):
    """Separate deployment boundary; implementations may be RPC clients only."""

    async def run(self, request: SandboxExecutionRequest) -> SandboxExecutionReceipt:
        """Execute one fully validated command in the remote sandbox."""


class SandboxRunner:
    """Validate and dispatch fenced requests to a non-local sandbox executor."""

    def __init__(self, executor: SandboxExecutor) -> None:
        self._executor = executor
        self._quota = QuotaService()
        self._artifacts = ArtifactBroker()

    async def execute(self, request: SandboxExecutionRequest) -> SandboxExecutionReceipt:
        """Dispatch only an isolated, frozen, quota-fenced execution request."""

        _validate_policy(request.policy)
        if request.stage not in _VALID_STAGES:
            raise ValueError("SANDBOX_STAGE_INVALID")
        await self._validate_profile(request)
        candidate = await self._validate_candidate_identity(request)
        if not await self._quota.validate_stage_attempt_fencing(
            request.quota_reservation_id,
            request.quota_fencing_token,
            task_id=request.task_id,
            run_id=candidate.run_id,
            stage_attempt_id=request.stage_attempt_id,
            lease_token=request.lease_token,
            stage=request.stage,
        ):
            raise ValueError("SANDBOX_STAGE_ATTEMPT_FENCING_DENIED")
        operation_id = f"sandbox:{request.quota_reservation_id}:{request.quota_fencing_token}"
        if not await self._quota.claim_external_dispatch(
            request.quota_reservation_id,
            request.quota_fencing_token,
            provider_operation_id=operation_id,
            task_id=request.task_id,
            run_id=candidate.run_id,
            stage_attempt_id=request.stage_attempt_id,
            lease_token=request.lease_token,
            stage=request.stage,
            resource_type="sandbox_seconds",
            unit="seconds",
        ):
            raise ValueError("SANDBOX_DISPATCH_ALREADY_CLAIMED")

        receipt = await self._executor.run(request)
        _validate_receipt(request, receipt)
        for descriptor in receipt.artifacts:
            if descriptor.producer_identity != request.runner_identity:
                raise ValueError("SANDBOX_RECEIPT_PRODUCER_IDENTITY_MISMATCH")
            if descriptor.container_image_digest != request.policy.image_digest:
                raise ValueError("SANDBOX_RECEIPT_IMAGE_DIGEST_MISMATCH")
            self._artifacts.validate_descriptor(descriptor)
        return receipt

    async def _validate_profile(self, request: SandboxExecutionRequest) -> None:
        profile = await CapabilityRegistry().get(request.profile_id, request.profile_version)
        decision = await CapabilityRegistry().evaluate(
            request.profile_id,
            request.profile_version,
            required=("sandbox",),
        )
        if not decision.allowed or profile is None:
            raise ValueError("SANDBOX_PROFILE_CAPABILITY_DENIED")
        if profile.service_identities.get("runner") != request.runner_identity:
            raise ValueError("SANDBOX_RUNNER_IDENTITY_DENIED")

    async def _validate_candidate_identity(
        self, request: SandboxExecutionRequest
    ) -> ResearchCandidate:
        async with database.async_session_maker() as session:
            candidate = await session.get(ResearchCandidate, request.candidate_id)
            if candidate is None:
                raise ValueError("SANDBOX_CANDIDATE_NOT_FOUND")
            if candidate.freeze_status != "FROZEN":
                raise ValueError("SANDBOX_CANDIDATE_NOT_FROZEN")
            code = await session.get(ResearchArtifact, candidate.code_artifact_id)
            dependencies = await session.get(ResearchArtifact, candidate.dependency_artifact_id)
        if code is None or dependencies is None:
            raise ValueError("SANDBOX_FROZEN_ARTIFACT_NOT_FOUND")
        if code.content_hash != request.code_artifact_hash:
            raise ValueError("SANDBOX_CODE_HASH_MISMATCH")
        if dependencies.content_hash != request.dependency_artifact_hash:
            raise ValueError("SANDBOX_DEPENDENCY_HASH_MISMATCH")
        if candidate.environment_hash != request.environment_hash:
            raise ValueError("SANDBOX_ENVIRONMENT_HASH_MISMATCH")
        return candidate


def _validate_policy(policy: SandboxPolicy) -> None:
    if not policy.version or not _IMAGE_DIGEST.fullmatch(policy.image_digest):
        raise ValueError("SANDBOX_POLICY_IMAGE_DIGEST_INVALID")
    if policy.network_mode != "none":
        raise ValueError("SANDBOX_POLICY_NETWORK_DENIED")
    if not policy.input_read_only:
        raise ValueError("SANDBOX_POLICY_INPUT_NOT_READ_ONLY")
    if not policy.output_path.startswith("/sandbox/output") or ".." in policy.output_path.split(
        "/"
    ):
        raise ValueError("SANDBOX_POLICY_OUTPUT_PATH_INVALID")
    if (
        policy.cpu_limit < 1
        or policy.memory_limit_mb < 16
        or policy.pid_limit < 1
        or policy.wall_timeout_seconds < 1
        or policy.output_limit_bytes < 1
    ):
        raise ValueError("SANDBOX_POLICY_RESOURCE_LIMIT_INVALID")


def _validate_receipt(request: SandboxExecutionRequest, receipt: SandboxExecutionReceipt) -> None:
    if receipt.status not in _VALID_STATUSES:
        raise ValueError("SANDBOX_RECEIPT_STATUS_INVALID")
    if receipt.image_digest != request.policy.image_digest:
        raise ValueError("SANDBOX_RECEIPT_IMAGE_DIGEST_MISMATCH")
    if receipt.policy_version != request.policy.version:
        raise ValueError("SANDBOX_RECEIPT_POLICY_VERSION_MISMATCH")
    if receipt.code_artifact_hash != request.code_artifact_hash:
        raise ValueError("SANDBOX_RECEIPT_CODE_HASH_MISMATCH")
    if receipt.dependency_artifact_hash != request.dependency_artifact_hash:
        raise ValueError("SANDBOX_RECEIPT_DEPENDENCY_HASH_MISMATCH")
    if receipt.environment_hash != request.environment_hash:
        raise ValueError("SANDBOX_RECEIPT_ENVIRONMENT_HASH_MISMATCH")
