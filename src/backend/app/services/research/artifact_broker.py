"""Controlled registration boundary for untrusted runner artifacts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Protocol
from urllib.parse import unquote, urlsplit

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import database
from app.models.ai_research_v2 import (
    ResearchArtifact,
    ResearchArtifactContent,
    ResearchRun,
    ResearchStageArtifactBinding,
    ResearchStageAttempt,
    ResearchTask,
)
from app.services.research.database_clock import DatabaseUtcNow

_ALLOWED_MEDIA_TYPES = frozenset(
    {
        "application/json",
        "application/vnd.apache.parquet",
        "application/x-parquet",
        "text/csv",
        "text/plain",
        "text/x-python",
    }
)
_MAX_ARTIFACT_BYTES = 10_000_000


@dataclass(frozen=True, slots=True)
class ArtifactDescriptor:
    """Metadata passed across the sandbox boundary, never an open filesystem path."""

    kind: str
    content_hash: str
    storage_uri: str
    size_bytes: int
    media_type: str
    schema_version: str
    producer_identity: str
    container_image_digest: str | None = None


class StageOutputContext(Protocol):
    """The leased identity fields a stage executor already receives."""

    user_id: str
    run_id: str
    task_id: str
    stage_attempt_id: str
    lease_token: str
    stage: str
    request_hash: str


class ArtifactBroker:
    """Allow only bounded, content-addressed artifacts in controlled storage."""

    def validate_descriptor(self, descriptor: ArtifactDescriptor) -> ArtifactDescriptor:
        """Reject path traversal, unsafe serialization, and unbounded output."""

        if not descriptor.kind or not descriptor.schema_version or not descriptor.producer_identity:
            raise ValueError("ARTIFACT_DESCRIPTOR_IDENTITY_REQUIRED")
        if len(descriptor.content_hash) != 64 or not _is_hex(descriptor.content_hash):
            raise ValueError("ARTIFACT_CONTENT_HASH_INVALID")
        if descriptor.size_bytes < 0:
            raise ValueError("ARTIFACT_SIZE_INVALID")
        if descriptor.size_bytes > _MAX_ARTIFACT_BYTES:
            raise ValueError("ARTIFACT_SIZE_EXCEEDED")
        parsed = urlsplit(descriptor.storage_uri)
        path_parts = tuple(unquote(part) for part in parsed.path.split("/") if part)
        if (
            parsed.scheme != "controlled"
            or not parsed.netloc
            or parsed.query
            or parsed.fragment
            or not path_parts
            or any(
                part in {".", ".."}
                or any(forbidden in part for forbidden in ("/", "\\", "\x00", "%"))
                for part in path_parts
            )
        ):
            raise ValueError("ARTIFACT_URI_INVALID")
        if descriptor.media_type not in _ALLOWED_MEDIA_TYPES:
            raise ValueError("ARTIFACT_MEDIA_TYPE_DENIED")
        return descriptor

    async def register(self, descriptor: ArtifactDescriptor) -> ResearchArtifact:
        """Persist an immutable descriptor idempotently by content hash and kind."""

        descriptor = self.validate_descriptor(descriptor)
        async with database.async_session_maker() as session:
            result = await session.execute(
                select(ResearchArtifact).where(
                    ResearchArtifact.content_hash == descriptor.content_hash,
                    ResearchArtifact.kind == descriptor.kind,
                )
            )
            existing = result.scalar_one_or_none()
            if existing is not None:
                if _model_descriptor(existing) != descriptor:
                    raise ValueError("ARTIFACT_CONTENT_COLLISION")
                return existing
            model = ResearchArtifact(**asdict(descriptor))
            session.add(model)
            await session.commit()
            await session.refresh(model)
            return model

    async def register_stage_output(
        self,
        *,
        context: StageOutputContext,
        kind: str,
        content: bytes | str,
        media_type: str,
        schema_version: str,
        producer_identity: str,
        container_image_digest: str | None = None,
    ) -> ResearchArtifact:
        """Hash, retain, and bind a local output before its stage can complete.

        This API deliberately accepts bytes or text instead of a caller-provided
        hash or storage URI.  The broker derives both from the retained content,
        so a deployment-owned stage executor can call it with its existing
        ``StageExecutionContext`` and cannot turn a remote descriptor into a
        trusted stage output.
        """

        payload = _content_bytes(content)
        content_digest = sha256(payload).hexdigest()
        descriptor = self.validate_descriptor(
            ArtifactDescriptor(
                kind=kind,
                content_hash=content_digest,
                storage_uri=f"controlled://local-stage-output/{content_digest}",
                size_bytes=len(payload),
                media_type=media_type,
                schema_version=schema_version,
                producer_identity=producer_identity,
                container_image_digest=container_image_digest,
            )
        )
        identity = _stage_output_identity(context)

        # A concurrent retry can race on the global content-addressed artifact
        # or the one-output-per-attempt constraint.  Retrying once converts an
        # identical winner into the idempotent result; a different winner is
        # rejected by the explicit binding conflict below.
        for retry in range(2):
            try:
                async with database.async_session_maker() as session:
                    artifact = await _register_stage_output_once(
                        session,
                        identity=identity,
                        descriptor=descriptor,
                        payload=payload,
                    )
                    await session.commit()
                    await session.refresh(artifact)
                    return artifact
            except IntegrityError:
                if retry == 0:
                    continue
                raise ValueError("ARTIFACT_STAGE_OUTPUT_CONCURRENT_CONFLICT") from None
        raise AssertionError("unreachable")

    async def register_stage_output_in_session(
        self,
        session: AsyncSession,
        *,
        context: StageOutputContext,
        kind: str,
        content: bytes | str,
        media_type: str,
        schema_version: str,
        producer_identity: str,
        container_image_digest: str | None = None,
    ) -> ResearchArtifact:
        """Retain bytes and a stage binding inside the caller's transaction.

        Never commits, retries, or rolls back the caller's other aggregate
        writes. The same private fenced writer serves the standalone API.
        """
        payload = _content_bytes(content)
        digest = sha256(payload).hexdigest()
        descriptor = self.validate_descriptor(
            ArtifactDescriptor(
                kind=kind,
                content_hash=digest,
                storage_uri=f"controlled://local-stage-output/{digest}",
                size_bytes=len(payload),
                media_type=media_type,
                schema_version=schema_version,
                producer_identity=producer_identity,
                container_image_digest=container_image_digest,
            )
        )
        return await _register_stage_output_once(
            session,
            identity=_stage_output_identity(context),
            descriptor=descriptor,
            payload=payload,
        )


def _model_descriptor(model: ResearchArtifact) -> ArtifactDescriptor:
    return ArtifactDescriptor(
        kind=model.kind,
        content_hash=model.content_hash,
        storage_uri=model.storage_uri,
        size_bytes=model.size_bytes,
        media_type=model.media_type,
        schema_version=model.schema_version,
        producer_identity=model.producer_identity,
        container_image_digest=model.container_image_digest,
    )


def _is_hex(value: str) -> bool:
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


@dataclass(frozen=True, slots=True)
class _StageOutputIdentity:
    user_id: str
    run_id: str
    task_id: str
    stage_attempt_id: str
    lease_token: str
    stage: str
    request_hash: str


def _stage_output_identity(context: StageOutputContext) -> _StageOutputIdentity:
    """Copy and minimally validate the executor's opaque lease context."""

    try:
        identity = _StageOutputIdentity(
            user_id=context.user_id,
            run_id=context.run_id,
            task_id=context.task_id,
            stage_attempt_id=context.stage_attempt_id,
            lease_token=context.lease_token,
            stage=context.stage,
            request_hash=context.request_hash,
        )
    except AttributeError as exc:
        raise ValueError("ARTIFACT_STAGE_OUTPUT_CONTEXT_REQUIRED") from exc
    if not all(
        isinstance(value, str) and value.strip()
        for value in (
            identity.user_id,
            identity.run_id,
            identity.task_id,
            identity.stage_attempt_id,
            identity.lease_token,
            identity.stage,
            identity.request_hash,
        )
    ):
        raise ValueError("ARTIFACT_STAGE_OUTPUT_CONTEXT_REQUIRED")
    return identity


def _content_bytes(content: bytes | str) -> bytes:
    """Normalize only local bytes/text; descriptors remain a separate API."""

    if isinstance(content, bytes):
        return content
    if isinstance(content, str):
        return content.encode("utf-8")
    raise ValueError("ARTIFACT_LOCAL_CONTENT_INVALID")


async def _register_stage_output_once(
    session,
    *,
    identity: _StageOutputIdentity,
    descriptor: ArtifactDescriptor,
    payload: bytes,
) -> ResearchArtifact:
    """Persist a content record and its stage binding in one transaction."""

    task = await session.scalar(
        select(ResearchTask).where(ResearchTask.id == identity.task_id).with_for_update()
    )
    if task is None:
        raise ValueError("ARTIFACT_STAGE_OUTPUT_TASK_NOT_FOUND")
    if task.user_id != identity.user_id or task.run_id != identity.run_id:
        raise ValueError("ARTIFACT_STAGE_OUTPUT_TASK_CONTEXT_MISMATCH")
    if task.status != "RUNNING" or task.lease_token != identity.lease_token:
        raise ValueError("ARTIFACT_STAGE_OUTPUT_LEASE_DENIED")
    await _require_live_task_lease(session, task.id, identity.lease_token)
    run = await session.scalar(
        select(ResearchRun).where(ResearchRun.id == task.run_id).with_for_update()
    )
    if run is None:
        raise ValueError("ARTIFACT_STAGE_OUTPUT_RUN_NOT_FOUND")
    if run.user_id != task.user_id:
        raise ValueError("ARTIFACT_STAGE_OUTPUT_RUN_CONTEXT_MISMATCH")
    if run.request_hash != identity.request_hash:
        raise ValueError("ARTIFACT_STAGE_OUTPUT_REQUEST_HASH_MISMATCH")

    stage_attempt = await session.scalar(
        select(ResearchStageAttempt)
        .where(ResearchStageAttempt.id == identity.stage_attempt_id)
        .with_for_update()
    )
    if stage_attempt is None:
        raise ValueError("ARTIFACT_STAGE_OUTPUT_ATTEMPT_NOT_FOUND")
    if stage_attempt.task_id != task.id or stage_attempt.run_id != task.run_id:
        raise ValueError("ARTIFACT_STAGE_OUTPUT_ATTEMPT_CONTEXT_MISMATCH")
    if stage_attempt.stage != identity.stage:
        raise ValueError("ARTIFACT_STAGE_OUTPUT_STAGE_MISMATCH")
    if stage_attempt.status != "RUNNING" or stage_attempt.lease_token != identity.lease_token:
        raise ValueError("ARTIFACT_STAGE_OUTPUT_LEASE_DENIED")

    binding = await session.scalar(
        select(ResearchStageArtifactBinding)
        .where(ResearchStageArtifactBinding.stage_attempt_id == identity.stage_attempt_id)
        .with_for_update()
    )
    if binding is not None:
        return await _bound_output_or_conflict(session, binding, identity, descriptor, payload)

    artifact = await session.scalar(
        select(ResearchArtifact)
        .where(
            ResearchArtifact.content_hash == descriptor.content_hash,
            ResearchArtifact.kind == descriptor.kind,
        )
        .with_for_update()
    )
    if artifact is None:
        artifact = ResearchArtifact(**asdict(descriptor))
        session.add(artifact)
        await session.flush()
        session.add(ResearchArtifactContent(artifact_id=artifact.id, content=payload))
    else:
        if _model_descriptor(artifact) != descriptor:
            raise ValueError("ARTIFACT_CONTENT_COLLISION")
        persisted_content = await session.get(ResearchArtifactContent, artifact.id)
        if persisted_content is None:
            raise ValueError("ARTIFACT_STAGE_OUTPUT_CONTENT_REQUIRED")
        if persisted_content.content != payload:
            raise ValueError("ARTIFACT_STAGE_OUTPUT_CONTENT_COLLISION")

    # All artifact and binding rows are part of this transaction. A second
    # database-clock fence ensures an executor cannot commit them after the
    # lease boundary crossed while content was being persisted.
    await _require_live_task_lease(session, task.id, identity.lease_token)
    session.add(
        ResearchStageArtifactBinding(
            user_id=identity.user_id,
            run_id=identity.run_id,
            task_id=identity.task_id,
            stage_attempt_id=identity.stage_attempt_id,
            artifact_id=artifact.id,
        )
    )
    return artifact


async def _require_live_task_lease(session, task_id: str, lease_token: str) -> None:
    """Fence an artifact submission with the database's UTC clock."""

    live_task_id = await session.scalar(
        select(ResearchTask.id)
        .where(
            ResearchTask.id == task_id,
            ResearchTask.status == "RUNNING",
            ResearchTask.lease_token == lease_token,
            ResearchTask.lease_expires_at.is_not(None),
            ResearchTask.lease_expires_at > DatabaseUtcNow(),
        )
        .with_for_update()
    )
    if live_task_id is None:
        raise ValueError("ARTIFACT_STAGE_OUTPUT_LEASE_DENIED")


async def _bound_output_or_conflict(
    session,
    binding: ResearchStageArtifactBinding,
    identity: _StageOutputIdentity,
    descriptor: ArtifactDescriptor,
    payload: bytes,
) -> ResearchArtifact:
    """Return an exact retry only; never overwrite a stage receipt's output."""

    if (
        binding.user_id != identity.user_id
        or binding.run_id != identity.run_id
        or binding.task_id != identity.task_id
        or binding.stage_attempt_id != identity.stage_attempt_id
    ):
        raise ValueError("ARTIFACT_STAGE_OUTPUT_CONTEXT_MISMATCH")
    artifact = await session.get(ResearchArtifact, binding.artifact_id)
    content = await session.get(ResearchArtifactContent, binding.artifact_id)
    if artifact is None or content is None:
        raise ValueError("ARTIFACT_STAGE_OUTPUT_BINDING_INVALID")
    if _model_descriptor(artifact) != descriptor or content.content != payload:
        raise ValueError("ARTIFACT_STAGE_OUTPUT_BINDING_CONFLICT")
    return artifact
