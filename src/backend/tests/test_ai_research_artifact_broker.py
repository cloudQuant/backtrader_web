from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256

import pytest
from sqlalchemy import select, text

from app.db.database import async_session_maker
from app.models.ai_research_v2 import (
    ResearchArtifact,
    ResearchArtifactContent,
    ResearchRun,
    ResearchTask,
)
from app.models.user import User
from app.services.research.artifact_broker import ArtifactBroker, ArtifactDescriptor
from app.services.research.stage_attempt import ResearchStageAttemptService
from app.services.research.workflow_worker import StageExecutionContext


def test_artifact_broker_accepts_only_controlled_content_addressed_outputs() -> None:
    descriptor = ArtifactDescriptor(
        kind="backtest_metrics",
        content_hash="a" * 64,
        storage_uri="controlled://research-output/metrics.json",
        size_bytes=128,
        media_type="application/json",
        schema_version="v1",
        producer_identity="sandbox-runner",
    )

    accepted = ArtifactBroker().validate_descriptor(descriptor)

    assert accepted.storage_uri == descriptor.storage_uri


@pytest.mark.parametrize(
    ("storage_uri", "media_type", "size_bytes", "error_code"),
    [
        (
            "controlled://research-output/../../secrets",
            "application/json",
            1,
            "ARTIFACT_URI_INVALID",
        ),
        (
            "controlled://research-output/%2e%2e/secrets",
            "application/json",
            1,
            "ARTIFACT_URI_INVALID",
        ),
        (
            "controlled://research-output/%2fetc%2fpasswd",
            "application/json",
            1,
            "ARTIFACT_URI_INVALID",
        ),
        ("controlled://research-output/%255csecret", "application/json", 1, "ARTIFACT_URI_INVALID"),
        ("file:///tmp/result.pkl", "application/octet-stream", 1, "ARTIFACT_URI_INVALID"),
        (
            "controlled://research-output/result.pkl",
            "application/x-python-pickle",
            1,
            "ARTIFACT_MEDIA_TYPE_DENIED",
        ),
        (
            "controlled://research-output/huge.json",
            "application/json",
            10_000_001,
            "ARTIFACT_SIZE_EXCEEDED",
        ),
    ],
)
def test_artifact_broker_rejects_unsafe_or_unbounded_outputs(
    storage_uri: str,
    media_type: str,
    size_bytes: int,
    error_code: str,
) -> None:
    descriptor = ArtifactDescriptor(
        kind="backtest_metrics",
        content_hash="a" * 64,
        storage_uri=storage_uri,
        size_bytes=size_bytes,
        media_type=media_type,
        schema_version="v1",
        producer_identity="sandbox-runner",
    )

    with pytest.raises(ValueError, match=error_code):
        ArtifactBroker().validate_descriptor(descriptor)


@pytest.mark.asyncio
async def test_artifact_broker_hashes_persists_and_binds_local_stage_output(auth_user) -> None:
    """An executor context alone can create a verifiable, bound local output."""

    context = await _stage_context(auth_user, suffix="persist")
    content = '{"candidate":"mean-reversion"}'

    artifact = await ArtifactBroker().register_stage_output(
        context=context,
        kind="strategy_source",
        content=content,
        media_type="application/json",
        schema_version="v1",
        producer_identity="deterministic-executor",
    )

    expected_hash = sha256(content.encode("utf-8")).hexdigest()
    assert artifact.content_hash == expected_hash
    assert artifact.size_bytes == len(content.encode("utf-8"))
    assert artifact.storage_uri == f"controlled://local-stage-output/{expected_hash}"

    async with async_session_maker() as session:
        stored_artifact = await session.get(ResearchArtifact, artifact.id)
        content_row = (
            await session.execute(
                text(
                    "SELECT content FROM ai_research_artifact_contents "
                    "WHERE artifact_id = :artifact_id"
                ),
                {"artifact_id": artifact.id},
            )
        ).scalar_one()
        binding_row = (
            (
                await session.execute(
                    text(
                        "SELECT user_id, run_id, task_id, stage_attempt_id, artifact_id "
                        "FROM ai_research_stage_artifact_bindings "
                        "WHERE stage_attempt_id = :stage_attempt_id"
                    ),
                    {"stage_attempt_id": context.stage_attempt_id},
                )
            )
            .mappings()
            .one()
        )

    assert stored_artifact is not None
    assert content_row == content.encode("utf-8")
    assert dict(binding_row) == {
        "user_id": context.user_id,
        "run_id": context.run_id,
        "task_id": context.task_id,
        "stage_attempt_id": context.stage_attempt_id,
        "artifact_id": artifact.id,
    }


@pytest.mark.asyncio
async def test_artifact_broker_stage_output_is_idempotent_but_rejects_a_different_binding(
    auth_user,
) -> None:
    """One stage attempt has one immutable output binding, even after a retry."""

    context = await _stage_context(auth_user, suffix="idempotent")
    broker = ArtifactBroker()
    kwargs = {
        "context": context,
        "kind": "strategy_source",
        "content": b"def next(self):\n    pass\n",
        "media_type": "text/x-python",
        "schema_version": "v1",
        "producer_identity": "deterministic-executor",
    }

    first = await broker.register_stage_output(**kwargs)
    repeated = await broker.register_stage_output(**kwargs)

    assert repeated.id == first.id
    with pytest.raises(ValueError, match="ARTIFACT_STAGE_OUTPUT_BINDING_CONFLICT"):
        await broker.register_stage_output(
            **{**kwargs, "content": b"def next(self):\n    return None\n"}
        )

    async with async_session_maker() as session:
        binding_count = await session.scalar(
            text(
                "SELECT COUNT(*) FROM ai_research_stage_artifact_bindings "
                "WHERE stage_attempt_id = :stage_attempt_id"
            ).bindparams(stage_attempt_id=context.stage_attempt_id)
        )
    assert binding_count == 1


@pytest.mark.asyncio
async def test_artifact_broker_rejects_a_stage_context_with_the_wrong_run_request_hash(
    auth_user,
) -> None:
    """A forged context cannot bind content to a run with a different request hash."""

    context = await _stage_context(auth_user, suffix="wrong-request-hash")
    forged = StageExecutionContext(
        task_id=context.task_id,
        run_id=context.run_id,
        user_id=context.user_id,
        stage_attempt_id=context.stage_attempt_id,
        lease_token=context.lease_token,
        stage=context.stage,
        request_hash="f" * 64,
        trace_id=context.trace_id,
    )

    with pytest.raises(ValueError, match="ARTIFACT_STAGE_OUTPUT_REQUEST_HASH_MISMATCH"):
        await ArtifactBroker().register_stage_output(
            context=forged,
            kind="strategy_source",
            content="def next(self):\n    pass\n",
            media_type="text/x-python",
            schema_version="v1",
            producer_identity="test-stage-executor",
        )


@pytest.mark.asyncio
async def test_stage_completion_rejects_a_bound_artifact_whose_payload_was_tampered(
    auth_user,
) -> None:
    """Existence of a blob is insufficient after its recorded digest no longer matches."""

    context = await _stage_context(auth_user, suffix="tampered-content")
    artifact = await ArtifactBroker().register_stage_output(
        context=context,
        kind="strategy_source",
        content="def next(self):\n    pass\n",
        media_type="text/x-python",
        schema_version="v1",
        producer_identity="test-stage-executor",
    )
    async with async_session_maker() as session:
        content = await session.get(ResearchArtifactContent, artifact.id)
        assert content is not None
        content.content = b"tampered"
        await session.commit()

    with pytest.raises(
        ValueError, match="RESEARCH_STAGE_ATTEMPT_ARTIFACT_CONTENT_INTEGRITY_INVALID"
    ):
        await ResearchStageAttemptService().complete(
            task_id=context.task_id,
            lease_token=context.lease_token,
            attempt_id=context.stage_attempt_id,
            status="SUCCEEDED",
            output_artifact_id=artifact.id,
        )


@pytest.mark.asyncio
async def test_artifact_broker_rejects_an_expired_task_lease_before_binding_content(
    auth_user,
) -> None:
    """An expired worker cannot add an immutable output binding."""

    context = await _stage_context(auth_user, suffix="expired-lease")
    async with async_session_maker() as session:
        task = await session.get(ResearchTask, context.task_id)
        assert task is not None
        task.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()

    with pytest.raises(ValueError, match="ARTIFACT_STAGE_OUTPUT_LEASE_DENIED"):
        await ArtifactBroker().register_stage_output(
            context=context,
            kind="strategy_source",
            content="def next(self):\n    pass\n",
            media_type="text/x-python",
            schema_version="v1",
            producer_identity="test-stage-executor",
        )


async def _stage_context(auth_user, *, suffix: str) -> StageExecutionContext:
    user_id = await _user_id(auth_user)
    now = datetime.now(timezone.utc)
    run = ResearchRun(
        user_id=user_id,
        hypothesis_version_id=f"artifact-hypothesis-{suffix}",
        dataset_snapshot_id=f"artifact-dataset-{suffix}",
        experiment_epoch_id=f"artifact-epoch-{suffix}",
        promotion_policy_version="promotion-v1",
        request_hash="p" * 64,
        capability_profile_id="dev-single-process",
        capability_profile_version="v1",
        capability_evidence_hash="b" * 64,
        trace_id=f"trace-artifact-{suffix}",
    )
    task = ResearchTask(
        user_id=user_id,
        run_id="",
        status="RUNNING",
        stage_cursor="CLARIFY",
        request_json={},
        idempotency_key=f"task-artifact-{suffix}",
        idempotency_request_hash="r" * 64,
        lease_token=f"lease-artifact-{suffix}",
        lease_expires_at=now + timedelta(minutes=5),
        lease_heartbeat_at=now,
    )
    async with async_session_maker() as session:
        session.add(run)
        await session.flush()
        task.run_id = run.id
        session.add(task)
        await session.commit()
        await session.refresh(task)

    attempt = await ResearchStageAttemptService().begin(
        task_id=task.id,
        lease_token=task.lease_token or "",
        stage="GENERATE",
        idempotency_key=f"stage-artifact-{suffix}",
        input_payload={"request_hash": "p" * 64},
        now=now,
    )
    return StageExecutionContext(
        task_id=task.id,
        run_id=task.run_id,
        user_id=user_id,
        stage_attempt_id=attempt.id,
        lease_token=task.lease_token or "",
        stage=attempt.stage,
        request_hash="p" * 64,
        trace_id=None,
    )


async def _user_id(auth_user) -> str:
    user, _headers = auth_user
    async with async_session_maker() as session:
        result = await session.execute(select(User.id).where(User.username == user["username"]))
        return str(result.scalar_one())
