"""Connected local worker proof using the real provider adapter and an HTTP seam.

No credentials, live provider, market-quality dataset, sandbox or evaluation
are asserted by these tests. Only HTTP transport is replaced; services,
filesystem receipts, SQLite transactions and worker checkpoints are real.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from app.db import database
from app.models.ai_research_v2 import (
    ResearchArtifactContent,
    ResearchCandidate,
    ResearchGenerationMaterialization,
    ResearchModelInvocation,
    ResearchQuotaBucket,
    ResearchQuotaReservation,
    ResearchStageAttempt,
    ResearchTask,
    ResearchTrial,
)
from app.research_deployments import generation
from app.services.research.canonical import content_hash
from app.services.research.openai_compatible_provider import OpenAICompatibleResearchProvider
from tests.test_ai_research_generation_deployment import _accounting_contract, _settings
from tests.test_ai_research_generation_executor import _generation_context


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "observed_model,usage,expected_error",
    [
        (
            "pinned-model-v1",
            {"prompt_tokens": 8, "completion_tokens": 12, "total_tokens": 20},
            None,
        ),
        (
            "unexpected-model-v2",
            {"prompt_tokens": 8, "completion_tokens": 12, "total_tokens": 20},
            "LLM_PROVIDER_MODEL_MISMATCH",
        ),
        ("pinned-model-v1", {}, "LLM_PROVIDER_USAGE_UNVERIFIED"),
        ("pinned-model-v1", {"total_tokens": 20}, "LLM_PROVIDER_USAGE_UNVERIFIED"),
        (
            "pinned-model-v1",
            {"prompt_tokens": 129, "completion_tokens": 12, "total_tokens": 141},
            "LLM_PROVIDER_USAGE_OUTSIDE_BUDGET",
        ),
        (
            "pinned-model-v1",
            {"prompt_tokens": 8, "completion_tokens": 33, "total_tokens": 41},
            "LLM_PROVIDER_USAGE_OUTSIDE_BUDGET",
        ),
    ],
)
async def test_configured_http_generation_worker_materializes_only_verified_model_output(
    auth_user,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    observed_model: str,
    usage: dict,
    expected_error: str | None,
) -> None:
    """Public worker polling connects real generation and atomic materialization."""

    context = await _generation_context(auth_user, tmp_path, queued_only=True)
    await _money_bucket(context)
    settings = _settings(
        tmp_path,
        AI_RESEARCH_PROTOCOL_V2_GENERATION_MAX_REQUEST_BYTES=65536,
        AI_RESEARCH_PROTOCOL_V2_GENERATION_MAX_RESPONSE_BYTES=65536,
    )
    output = json.dumps(
        {
            "schema_version": "research-generation-v1",
            "strategy_code": "class Strategy:\n    def next(self):\n        return None\n",
            "dependency_lock": "backtrader==1.9.78.123\n",
            "params": {"lookback": 20},
        },
        sort_keys=True,
    )
    requests: list[httpx.Request] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "pipeline-http-request-1",
                "model": observed_model,
                "choices": [{"finish_reason": "stop", "message": {"content": output}}],
                "usage": usage,
            },
        )

    monkeypatch.setattr(generation, "get_settings", lambda: settings)
    monkeypatch.setattr(
        generation,
        "OpenAICompatibleResearchProvider",
        lambda *, config: OpenAICompatibleResearchProvider(
            config=config, transport=httpx.MockTransport(respond)
        ),
    )
    worker = generation.create_worker()

    results = await worker.run_once()

    assert len(results) == 1
    assert len(requests) == 1, results
    sent = json.loads(requests[0].content)
    assert sent["model"] == "pinned-model-v1"
    assert "storage_uri" not in requests[0].content.decode()
    async with database.async_session_maker() as session:
        task = await session.get(ResearchTask, context["task"].id)
        invocation = await session.scalar(
            select(ResearchModelInvocation).where(
                ResearchModelInvocation.run_id == context["run"].id
            )
        )
        reservations = list(
            await session.scalars(
                select(ResearchQuotaReservation).where(
                    ResearchQuotaReservation.task_id == context["task"].id
                )
            )
        )
        stages = list(
            await session.scalars(
                select(ResearchStageAttempt).where(
                    ResearchStageAttempt.task_id == context["task"].id
                )
            )
        )
        candidate = await session.scalar(
            select(ResearchCandidate).where(ResearchCandidate.run_id == context["run"].id)
        )
        materialization = await session.scalar(
            select(ResearchGenerationMaterialization).where(
                ResearchGenerationMaterialization.task_id == context["task"].id
            )
        )
        trials = list(
            await session.scalars(
                select(ResearchTrial).where(ResearchTrial.run_id == context["run"].id)
            )
        )
        receipt = (
            await session.get(ResearchArtifactContent, materialization.manifest_artifact_id)
            if materialization is not None
            else None
        )

    assert task is not None and invocation is not None and len(reservations) == 2
    by_resource = {item.resource_type: item for item in reservations}
    assert set(by_resource) == {"model_tokens", "model_cost_microusd"}
    assert by_resource["model_tokens"].reserved_amount == 160
    assert by_resource["model_cost_microusd"].reserved_amount == 199
    for item in reservations:
        assert item.reservation_context is not None
        assert item.request_hash == content_hash(item.reservation_context)
        assert sha256(requests[0].content).hexdigest() in json.dumps(item.reservation_context)
    assert reservations[0].reservation_context == reservations[1].reservation_context
    assert invocation.provider == "operator-route-v1"
    assert invocation.resolved_model == "pinned-model-v1"
    assert invocation.provider_reported_model == observed_model
    assert invocation.provider_request_id == "pipeline-http-request-1"
    assert trials == []
    assert {stage.stage for stage in stages} == {"CLARIFY", "GENERATE"}
    if expected_error is not None:
        assert results[0].status == task.status == "FAILED"
        assert invocation.error_code == expected_error
        assert {item.status for item in reservations} == {"IN_FLIGHT"}
        assert "amount_microusd" not in invocation.cost
        assert candidate is None and materialization is None and receipt is None
    else:
        assert results[0].status == task.status == "SUCCEEDED"
        assert invocation.error_code is None
        assert invocation.output_hash == content_hash({"output": output})
        assert {item.status for item in reservations} == {"SETTLED"}
        assert by_resource["model_tokens"].settled_amount == 20
        assert by_resource["model_cost_microusd"].settled_amount == 39
        assert invocation.cost["amount_microusd"] == 39
        assert invocation.cost["accounting_basis"] == "CONSERVATIVE_TARIFF_BOUND"
        assert all(stage.status == "SUCCEEDED" for stage in stages)
        assert candidate is not None and materialization is not None and receipt is not None
        assert candidate.freeze_status == "MUTABLE"
        assert materialization.candidate_id == candidate.id
        assert materialization.model_invocation_id == invocation.id
        manifest = json.loads(receipt.content)
        assert manifest["candidate_id"] == candidate.id
        assert manifest["model_output_hash"] == invocation.output_hash
        assert manifest["execution_state"] == "MATERIALIZED_NOT_EXECUTED"

    # Terminal polling neither dispatches nor materializes a second time.
    assert await worker.run_once() == []
    assert len(requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("money_limit", [None, 198])
async def test_generation_missing_or_insufficient_money_denies_before_http(
    auth_user, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, money_limit: int | None
) -> None:
    context = await _generation_context(auth_user, tmp_path, queued_only=True)
    if money_limit is not None:
        await _money_bucket(context, hard_limit=money_limit)
    settings = _settings(tmp_path, AI_RESEARCH_PROTOCOL_V2_GENERATION_MAX_REQUEST_BYTES=65536)
    requests = []

    async def forbidden(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(500)

    monkeypatch.setattr(generation, "get_settings", lambda: settings)
    monkeypatch.setattr(
        generation,
        "OpenAICompatibleResearchProvider",
        lambda *, config: OpenAICompatibleResearchProvider(
            config=config, transport=httpx.MockTransport(forbidden)
        ),
    )
    results = await generation.create_worker().run_once()
    assert results[0].status == "FAILED"
    assert requests == []
    async with database.async_session_maker() as session:
        reservations = list(
            await session.scalars(
                select(ResearchQuotaReservation).where(
                    ResearchQuotaReservation.task_id == context["task"].id
                )
            )
        )
        token_bucket = await session.get(ResearchQuotaBucket, context["bucket"].id)
    assert reservations == []
    assert token_bucket.reserved_amount == token_bucket.active_reservations == 0


async def _money_bucket(context: dict, *, hard_limit: int = 1000) -> None:
    token_bucket = context["bucket"]
    async with database.async_session_maker() as session:
        session.add(
            ResearchQuotaBucket(
                scope_type="user",
                scope_id=token_bucket.scope_id,
                policy_version=token_bucket.policy_version,
                resource_type="model_cost_microusd",
                window_start=token_bucket.window_start,
                window_end=token_bucket.window_end,
                hard_limit=hard_limit,
                concurrency_limit=2,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_expired_accounting_contract_is_rejected_before_any_reservation(
    auth_user,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = await _generation_context(auth_user, tmp_path, queued_only=True)
    await _money_bucket(context)
    now = datetime.now(timezone.utc)
    accounting = _accounting_contract(
        valid_from=(now - timedelta(hours=2)).isoformat(),
        expires_at=(now - timedelta(hours=1)).isoformat(),
    )
    settings = _settings(
        tmp_path,
        AI_RESEARCH_PROTOCOL_V2_GENERATION_MAX_REQUEST_BYTES=65536,
        AI_RESEARCH_PROTOCOL_V2_GENERATION_ACCOUNTING_POLICY_JSON=json.dumps(accounting),
        AI_RESEARCH_PROTOCOL_V2_GENERATION_ACCOUNTING_POLICY_HASH=content_hash(accounting),
    )
    sent = []

    async def forbidden(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(500)

    monkeypatch.setattr(generation, "get_settings", lambda: settings)
    monkeypatch.setattr(
        generation,
        "OpenAICompatibleResearchProvider",
        lambda *, config: OpenAICompatibleResearchProvider(
            config=config, transport=httpx.MockTransport(forbidden)
        ),
    )
    result = await generation.create_worker().run_once()
    assert result[0].status == "FAILED"
    assert sent == []
    async with database.async_session_maker() as session:
        assert (
            list(
                await session.scalars(
                    select(ResearchQuotaReservation).where(
                        ResearchQuotaReservation.task_id == context["task"].id
                    )
                )
            )
            == []
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("drift", ["input", "price", "receipt_subset", "missing_snapshot"])
async def test_sealed_generation_quote_cannot_drift_before_dispatch(
    auth_user,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    drift: str,
) -> None:
    from app.services.research.model_budget import ModelAccountingPolicy

    context = await _generation_context(auth_user, tmp_path, queued_only=True)
    await _money_bucket(context)
    settings = _settings(tmp_path, AI_RESEARCH_PROTOCOL_V2_GENERATION_MAX_REQUEST_BYTES=65536)
    sent = []

    async def forbidden(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(500)

    monkeypatch.setattr(generation, "get_settings", lambda: settings)
    monkeypatch.setattr(
        generation,
        "OpenAICompatibleResearchProvider",
        lambda *, config: OpenAICompatibleResearchProvider(
            config=config, transport=httpx.MockTransport(forbidden)
        ),
    )
    worker = generation.create_worker()
    gateway = worker._executors["GENERATE"]._gateway
    invoke = gateway.invoke
    if drift == "missing_snapshot":
        from app.services.research.quota import QuotaService

        reserve = QuotaService.reserve

        async def reserve_without_snapshot(self, **kwargs):
            # An internal legacy caller can provide the correct quote hash
            # while omitting the durable policy; strict dispatch must deny it.
            kwargs["reservation_context"] = None
            return await reserve(self, **kwargs)

        monkeypatch.setattr(QuotaService, "reserve", reserve_without_snapshot)

    async def mutated_invoke(**kwargs):
        if drift == "input":
            kwargs["typed_input"]["late_instruction"] = "different request"
        elif drift == "price":
            policy = gateway._accounting_policy.snapshot()
            policy["input_microusd_per_million"] += 1
            gateway._accounting_policy = ModelAccountingPolicy.from_mapping(
                policy, expected_hash=content_hash(policy)
            )
        elif drift == "receipt_subset":
            kwargs["quota_receipts"] = kwargs["quota_receipts"][:1]
        return await invoke(**kwargs)

    monkeypatch.setattr(gateway, "invoke", mutated_invoke)
    result = await worker.run_once()
    assert result[0].status == "FAILED"
    assert sent == []
    async with database.async_session_maker() as session:
        reservations = list(
            await session.scalars(
                select(ResearchQuotaReservation).where(
                    ResearchQuotaReservation.task_id == context["task"].id
                )
            )
        )
        invocations = list(
            await session.scalars(
                select(ResearchModelInvocation).where(
                    ResearchModelInvocation.run_id == context["run"].id
                )
            )
        )
    # No call was admitted. The pair remains reserved, never silently spent or released.
    assert len(reservations) == 2
    assert {item.status for item in reservations} == {"RESERVED"}
    assert invocations == []
