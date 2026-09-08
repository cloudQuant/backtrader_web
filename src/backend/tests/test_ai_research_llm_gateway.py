from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db import database
from app.models.ai_research_v2 import (
    ResearchModelInvocation,
    ResearchQuotaBucket,
    ResearchQuotaReservation,
    ResearchRun,
    ResearchStageAttempt,
    ResearchTask,
)
from app.services.research import quota as quota_module
from app.services.research.capabilities import CapabilityProfile
from app.services.research.capability_registry import CapabilityRegistry
from app.services.research.llm_gateway import (
    LlmGateway,
    ModelCatalog,
    ProviderResponse,
)
from app.services.research.quota import (
    QuotaReservationReceipt,
    QuotaReservationRequest,
    QuotaService,
)


@pytest.mark.asyncio
async def test_gateway_redacts_input_records_resolved_model_and_preserves_alias_history() -> None:
    context = await _context()
    catalog = ModelCatalog({"research-default": "provider-model-2026-09-01"})
    provider = _FakeProvider()
    gateway = LlmGateway(provider=provider, catalog=catalog)
    first_receipt = await _reservation(context, "one")

    first = await gateway.invoke(
        run_id=context["run"].id,
        requested_model="research-default",
        prompt_template_version="strategy-v2",
        system_input={"role": "researcher"},
        typed_input={"question": "验证动量", "api_key": "secret-value"},
        sampling_params={"temperature": 0.1},
        task_id=context["task"].id,
        stage_attempt_id=context["stage_attempt"].id,
        lease_token=context["lease_token"],
        stage="GENERATE",
        quota_reservation_id=first_receipt.reservation_id,
        quota_fencing_token=first_receipt.fencing_token,
    )

    assert first.resolved_model == "provider-model-2026-09-01"
    assert "secret-value" not in str(provider.calls[0].typed_input)
    assert "secret-value" not in first.output
    catalog.set_alias("research-default", "provider-model-2026-09-02")
    second_receipt = await _reservation(context, "three")
    second = await gateway.invoke(
        run_id=context["run"].id,
        requested_model="research-default",
        prompt_template_version="strategy-v2",
        system_input={"role": "researcher"},
        typed_input={"question": "验证反转"},
        sampling_params={"temperature": 0.1},
        task_id=context["task"].id,
        stage_attempt_id=context["stage_attempt"].id,
        lease_token=context["lease_token"],
        stage="GENERATE",
        quota_reservation_id=second_receipt.reservation_id,
        quota_fencing_token=second_receipt.fencing_token,
    )

    assert second.resolved_model == "provider-model-2026-09-02"
    async with database.async_session_maker() as session:
        result = await session.execute(
            select(ResearchModelInvocation)
            .where(ResearchModelInvocation.run_id == context["run"].id)
            .order_by(ResearchModelInvocation.created_at, ResearchModelInvocation.id)
        )
        invocations = list(result.scalars())
    assert [item.resolved_model for item in invocations] == [
        "provider-model-2026-09-01",
        "provider-model-2026-09-02",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["system_input", "typed_input", "sampling_params"])
@pytest.mark.parametrize(
    "secret_key",
    ["api_key=sk-abcdefghijk", "Bearer secret-auth-value", "https://u:password@example.invalid/x"],
)
async def test_gateway_rejects_nested_secret_bearing_keys_before_dispatch(
    field: str, secret_key: str
) -> None:
    context = await _context()
    provider = _FakeProvider()
    gateway = LlmGateway(provider=provider, catalog=ModelCatalog({"research-default": "model-v1"}))
    receipt = await _reservation(context, "secret-key-input")
    arguments = _invocation_arguments(context, receipt)
    arguments[field] = {"nested": [{secret_key: "ordinary value"}]}

    with pytest.raises(ValueError, match="^LLM_TYPED_INPUT_INVALID$"):
        await gateway.invoke(**arguments)

    assert provider.calls == []
    async with database.async_session_maker() as session:
        reservation = await session.get(ResearchQuotaReservation, receipt.reservation_id)
        invocation = await session.scalar(
            select(ResearchModelInvocation).where(
                ResearchModelInvocation.run_id == context["run"].id
            )
        )
    assert reservation is not None and reservation.status == "RESERVED"
    assert invocation is None


@pytest.mark.asyncio
async def test_gateway_preserves_numeric_output_cap_without_unredacting_credentials() -> None:
    context = await _context()
    provider = _FakeProvider()
    gateway = LlmGateway(provider=provider, catalog=ModelCatalog({"research-default": "model-v1"}))
    receipt = await _reservation(context, "numeric-sampling-cap")
    arguments = _invocation_arguments(context, receipt)
    arguments["sampling_params"] = {"max_tokens": 32, "api_key": "private-credential"}

    result = await gateway.invoke(**arguments)

    assert provider.calls[0].sampling_params == {"max_tokens": 32, "api_key": "[REDACTED]"}
    async with database.async_session_maker() as session:
        invocation = await session.get(ResearchModelInvocation, result.invocation_id)
    assert invocation is not None
    assert invocation.sampling_params == {"max_tokens": 32, "api_key": "[REDACTED]"}


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_cap", [True, None, -1, 0, "private-credential"])
async def test_gateway_rejects_non_positive_or_non_integer_output_caps(invalid_cap: object) -> None:
    context = await _context()
    provider = _FakeProvider()
    gateway = LlmGateway(provider=provider, catalog=ModelCatalog({"research-default": "model-v1"}))
    receipt = await _reservation(context, "invalid-sampling-cap")
    arguments = _invocation_arguments(context, receipt)
    arguments["sampling_params"] = {"max_tokens": invalid_cap}

    with pytest.raises(ValueError, match="^LLM_SAMPLING_PARAMS_INVALID$"):
        await gateway.invoke(**arguments)

    assert provider.calls == []


@pytest.mark.asyncio
async def test_gateway_rejects_unfenced_request_before_provider_call() -> None:
    context = await _context()
    provider = _FakeProvider()
    gateway = LlmGateway(provider=provider, catalog=ModelCatalog({"research-default": "model-v1"}))

    with pytest.raises(ValueError, match="LLM_STAGE_ATTEMPT_FENCING_DENIED"):
        await gateway.invoke(
            run_id=context["run"].id,
            requested_model="research-default",
            prompt_template_version="strategy-v2",
            system_input={"role": "researcher"},
            typed_input={"question": "验证动量"},
            sampling_params={},
            task_id="missing",
            stage_attempt_id="missing",
            lease_token="missing",
            stage="GENERATE",
            quota_reservation_id="missing",
            quota_fencing_token=1,
        )
    assert provider.calls == []


@pytest.mark.asyncio
async def test_gateway_does_not_redispatch_an_already_claimed_reservation() -> None:
    """A retry must not charge the provider twice on one durable reservation."""

    context = await _context()
    provider = _FakeProvider()
    gateway = LlmGateway(provider=provider, catalog=ModelCatalog({"research-default": "model-v1"}))
    receipt = await _reservation(context, "dispatch-once")
    arguments = _invocation_arguments(context, receipt)

    await gateway.invoke(**arguments)
    with pytest.raises(ValueError, match="LLM_STAGE_ATTEMPT_FENCING_DENIED"):
        await gateway.invoke(**arguments)

    assert len(provider.calls) == 1
    async with database.async_session_maker() as session:
        invocations = list(
            (
                await session.scalars(
                    select(ResearchModelInvocation).where(
                        ResearchModelInvocation.run_id == context["run"].id
                    )
                )
            ).all()
        )
    assert len(invocations) == 1


@pytest.mark.asyncio
async def test_gateway_rechecks_cancellation_when_atomically_claiming_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancellation after the initial read must still fence the external call."""

    context = await _context()
    provider = _FakeProvider()
    gateway = LlmGateway(provider=provider, catalog=ModelCatalog({"research-default": "model-v1"}))
    receipt = await _reservation(context, "cancel-before-dispatch")
    original_validation = gateway._quota.validate_stage_attempt_fencing

    async def cancel_after_initial_validation(*args: Any, **kwargs: Any) -> bool:
        allowed = await original_validation(*args, **kwargs)
        assert allowed
        async with database.async_session_maker() as session:
            task = await session.get(ResearchTask, context["task"].id)
            assert task is not None
            task.cancel_requested_at = datetime.now(timezone.utc)
            await session.commit()
        return allowed

    monkeypatch.setattr(
        gateway._quota, "validate_stage_attempt_fencing", cancel_after_initial_validation
    )
    with pytest.raises(ValueError, match="LLM_DISPATCH_ALREADY_CLAIMED"):
        await gateway.invoke(**_invocation_arguments(context, receipt))
    assert provider.calls == []


@pytest.mark.asyncio
async def test_concurrent_gateways_dispatch_once_across_independent_connections(
    independent_gateway_database: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two service instances pass the read check; just one durable claim wins."""

    context = await _context()
    provider = _FakeProvider()
    gateways = [
        LlmGateway(provider=provider, catalog=ModelCatalog({"research-default": "model-v1"}))
        for _ in range(2)
    ]
    receipt = await _reservation(context, "concurrent")
    both_validated = asyncio.Event()
    validated = 0

    def read_barrier(gateway: LlmGateway) -> Any:
        original = gateway._quota.validate_stage_attempt_fencing

        async def validate_then_wait(*args: Any, **kwargs: Any) -> bool:
            nonlocal validated
            allowed = await original(*args, **kwargs)
            assert allowed
            validated += 1
            if validated == 2:
                both_validated.set()
            await asyncio.wait_for(both_validated.wait(), timeout=5)
            return allowed

        return validate_then_wait

    for gateway in gateways:
        monkeypatch.setattr(gateway._quota, "validate_stage_attempt_fencing", read_barrier(gateway))
    results = await asyncio.gather(
        *(gateway.invoke(**_invocation_arguments(context, receipt)) for gateway in gateways),
        return_exceptions=True,
    )
    errors = [result for result in results if isinstance(result, Exception)]
    assert len(errors) == 1
    assert isinstance(errors[0], ValueError)
    assert str(errors[0]) == "LLM_DISPATCH_ALREADY_CLAIMED"
    assert len(provider.calls) == 1
    async with database.async_session_maker() as session:
        reservation = await session.get(ResearchQuotaReservation, receipt.reservation_id)
        assert reservation is not None
        assert reservation.status == "SETTLED"
        assert reservation.settled_amount == 17
        assert reservation.provider_operation_id == (
            f"llm:{receipt.reservation_id}:{receipt.fencing_token}"
        )
        invocations = list(
            await session.scalars(
                select(ResearchModelInvocation).where(
                    ResearchModelInvocation.run_id == context["run"].id
                )
            )
        )
        assert len(invocations) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "revocation",
    [
        "expired_reservation",
        "inactive_bucket",
        "expired_task",
        "task_status",
        "task_lease",
        "attempt_status",
        "attempt_lease",
        "attempt_stage",
        "attempt_run",
        "attempt_task",
    ],
)
async def test_dispatch_claim_rechecks_current_stage_authority(
    revocation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Revocation after read validation still prevents the provider side effect."""

    context = await _context()
    provider = _FakeProvider()
    gateway = LlmGateway(provider=provider, catalog=ModelCatalog({"research-default": "model-v1"}))
    receipt = await _reservation(context, "revoked")
    original = gateway._quota.validate_stage_attempt_fencing

    async def revoke_after_read(*args: Any, **kwargs: Any) -> bool:
        allowed = await original(*args, **kwargs)
        assert allowed
        async with database.async_session_maker() as session:
            reservation = await session.get(ResearchQuotaReservation, receipt.reservation_id)
            bucket = await session.get(ResearchQuotaBucket, context["bucket"].id)
            task = await session.get(ResearchTask, context["task"].id)
            attempt = await session.get(ResearchStageAttempt, context["stage_attempt"].id)
            assert reservation is not None and bucket is not None
            assert task is not None and attempt is not None
            past = datetime.now(timezone.utc) - timedelta(minutes=1)
            if revocation == "expired_reservation":
                reservation.lease_expires_at = past
            elif revocation == "inactive_bucket":
                bucket.status = "BLOCKED_UNKNOWN"
            elif revocation == "expired_task":
                task.lease_expires_at = past
            elif revocation == "task_status":
                task.status = "CANCELLED"
            elif revocation == "task_lease":
                task.lease_token = "new-lease"
            elif revocation == "attempt_status":
                attempt.status = "FAILED"
            elif revocation == "attempt_lease":
                attempt.lease_token = "new-lease"
            elif revocation == "attempt_stage":
                attempt.stage = "CLARIFY"
            elif revocation == "attempt_run":
                attempt.run_id = "another-run"
            elif revocation == "attempt_task":
                attempt.task_id = "another-task"
            await session.commit()
        return allowed

    monkeypatch.setattr(gateway._quota, "validate_stage_attempt_fencing", revoke_after_read)
    with pytest.raises(ValueError, match="LLM_DISPATCH_ALREADY_CLAIMED"):
        await gateway.invoke(**_invocation_arguments(context, receipt))
    assert provider.calls == []


@pytest_asyncio.fixture
async def independent_gateway_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[None]:
    """Use real independent transactions rather than shared StaticPool sessions."""

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'gateway-dispatch.db'}",
        poolclass=NullPool,
        connect_args={"timeout": 30},
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(database.Base.metadata.create_all)
        with monkeypatch.context() as local_patch:
            local_patch.setattr(database, "async_session_maker", sessions)
            yield
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_gateway_settles_verified_usage_before_returning_success() -> None:
    context = await _context()
    provider = _FakeProvider()
    gateway = LlmGateway(provider=provider, catalog=ModelCatalog({"research-default": "model-v1"}))
    receipt = await _reservation(context, "settle")

    await gateway.invoke(**_invocation_arguments(context, receipt))

    async with database.async_session_maker() as session:
        reservation = await session.get(ResearchQuotaReservation, receipt.reservation_id)
        bucket = await session.get(ResearchQuotaBucket, receipt.bucket_id)
        assert reservation is not None and bucket is not None
        assert reservation.status == "SETTLED"
        assert reservation.settled_amount == 17
        assert bucket.reserved_amount == 0
        assert bucket.settled_amount == 17
        assert bucket.active_reservations == 0
        assert bucket.status == "ACTIVE"
    assert (
        await QuotaService().reconcile_expired(now=receipt.lease_expires_at + timedelta(seconds=1))
        == 0
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "usage",
    [
        {},
        {"input": 12},
        {"input": True, "output": 5},
        {"input": -1, "output": 5},
        {"input": 12, "output": 5, "total_tokens": 16},
        {"total_tokens": 17.5},
    ],
)
async def test_gateway_does_not_report_success_or_release_unknown_usage(
    usage: dict[str, Any],
) -> None:
    context = await _context()
    provider = _FakeProvider()
    provider.token_usage = usage
    gateway = LlmGateway(provider=provider, catalog=ModelCatalog({"research-default": "model-v1"}))
    receipt = await _reservation(context, "unknown-usage")

    with pytest.raises(ValueError, match="LLM_PROVIDER_USAGE_UNVERIFIED"):
        await gateway.invoke(**_invocation_arguments(context, receipt))

    async with database.async_session_maker() as session:
        reservation = await session.get(ResearchQuotaReservation, receipt.reservation_id)
        bucket = await session.get(ResearchQuotaBucket, receipt.bucket_id)
        assert reservation is not None and bucket is not None
        assert reservation.status == "IN_FLIGHT"
        assert bucket.reserved_amount == receipt.reserved_amount
        assert bucket.settled_amount == 0
        invocation = await session.scalar(
            select(ResearchModelInvocation).where(
                ResearchModelInvocation.run_id == context["run"].id
            )
        )
        assert invocation is not None
        assert invocation.error_code == "LLM_PROVIDER_USAGE_UNVERIFIED"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value,error_code",
    [
        ("token_usage", None, "LLM_PROVIDER_USAGE_UNVERIFIED"),
        ("token_usage", [], "LLM_PROVIDER_USAGE_UNVERIFIED"),
        ("token_usage", {"total_tokens": 17, "extra": object()}, "LLM_PROVIDER_USAGE_UNVERIFIED"),
        ("cost", None, "LLM_PROVIDER_RESPONSE_INVALID"),
        ("cost", {"usd": float("nan")}, "LLM_PROVIDER_RESPONSE_INVALID"),
        ("cost", {"usd": object()}, "LLM_PROVIDER_RESPONSE_INVALID"),
        ("cost", {1: "not-a-string-key"}, "LLM_PROVIDER_RESPONSE_INVALID"),
        ("cost", {"extra": "x" * 65537}, "LLM_PROVIDER_RESPONSE_INVALID"),
        ("output", None, "LLM_PROVIDER_OUTPUT_INVALID"),
        ("output", "x" * 1048577, "LLM_PROVIDER_OUTPUT_INVALID"),
        ("output", "http://[invalid", "LLM_PROVIDER_OUTPUT_INVALID"),
        ("provider_request_id", {}, "LLM_PROVIDER_RESPONSE_INVALID"),
        ("provider_request_id", "x" * 257, "LLM_PROVIDER_RESPONSE_INVALID"),
        ("fallback_chain", None, "LLM_PROVIDER_RESPONSE_INVALID"),
        ("fallback_chain", (object(),), "LLM_PROVIDER_RESPONSE_INVALID"),
        ("provider_request_id", "request\x00id", "LLM_PROVIDER_RESPONSE_INVALID"),
        ("fallback_chain", ("model\x00id",), "LLM_PROVIDER_RESPONSE_INVALID"),
        ("cost", {"currency": "usd\x00"}, "LLM_PROVIDER_RESPONSE_INVALID"),
        ("cost", {"currency\x00": "usd"}, "LLM_PROVIDER_RESPONSE_INVALID"),
        ("output", "draft\x00", "LLM_PROVIDER_OUTPUT_INVALID"),
        (
            "token_usage",
            {"total_tokens": 17, "api_key=sk-secret": "x"},
            "LLM_PROVIDER_USAGE_UNVERIFIED",
        ),
        ("cost", {"authorization: Bearer secret": "x"}, "LLM_PROVIDER_RESPONSE_INVALID"),
    ],
    ids=[
        "usage-null",
        "usage-list",
        "usage-non-json",
        "cost-null",
        "cost-nan",
        "cost-non-json",
        "cost-key",
        "cost-too-large",
        "output-null",
        "output-too-large",
        "output-malformed-url",
        "request-id-object",
        "request-id-too-large",
        "fallback-null",
        "fallback-object",
        "request-id-nul",
        "fallback-nul",
        "cost-nul",
        "cost-key-nul",
        "output-nul",
        "usage-sensitive-key",
        "cost-sensitive-key",
    ],
)
async def test_malformed_provider_response_is_audited_before_any_settlement(
    field: str, value: Any, error_code: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = await _context()
    provider = _FakeProvider()
    response = replace(
        ProviderResponse("draft", "request-1", {"total_tokens": 17}, {"usd": 0.001}),
        **{field: value},
    )

    async def malformed_response(request: Any) -> ProviderResponse:
        provider.calls.append(request)
        return response

    monkeypatch.setattr(provider, "generate", malformed_response)
    gateway = LlmGateway(provider=provider, catalog=ModelCatalog({"research-default": "model-v1"}))
    receipt = await _reservation(context, "malformed-response")
    with pytest.raises(ValueError, match=f"^{error_code}$"):
        await gateway.invoke(**_invocation_arguments(context, receipt))
    assert len(provider.calls) == 1
    async with database.async_session_maker() as session:
        reservation = await session.get(ResearchQuotaReservation, receipt.reservation_id)
        bucket = await session.get(ResearchQuotaBucket, receipt.bucket_id)
        invocations = list(await session.scalars(select(ResearchModelInvocation)))
        assert reservation is not None and reservation.status == "IN_FLIGHT"
        assert bucket is not None
        assert (bucket.reserved_amount, bucket.settled_amount) == (32, 0)
        assert len(invocations) == 1
        assert invocations[0].error_code == error_code
        assert invocations[0].output_hash is None
        assert invocations[0].token_usage == {}
        assert invocations[0].cost == {}


@pytest.mark.asyncio
async def test_provider_response_metadata_is_redacted_and_token_counters_remain_auditable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = await _context()
    provider = _FakeProvider()

    async def sensitive_response(request: Any) -> ProviderResponse:
        return ProviderResponse(
            "draft",
            "token=request-secret",
            {
                "prompt_tokens": 12,
                "completion_tokens": 5,
                "total_tokens": 17,
                "api_key": "usage-secret",
            },
            {"usd": 0.001, "password": "cost-secret"},
            ("token=fallback-secret",),
        )

    monkeypatch.setattr(provider, "generate", sensitive_response)
    gateway = LlmGateway(provider=provider, catalog=ModelCatalog({"research-default": "model-v1"}))
    receipt = await _reservation(context, "response-redaction")
    await gateway.invoke(**_invocation_arguments(context, receipt))
    async with database.async_session_maker() as session:
        invocation = await session.scalar(select(ResearchModelInvocation))
        assert invocation is not None
        assert invocation.token_usage["total_tokens"] == 17
        assert invocation.token_usage["prompt_tokens"] == 12
        assert invocation.token_usage["completion_tokens"] == 5
        assert invocation.token_usage["api_key"] == "[REDACTED]"
        assert invocation.cost["password"] == "[REDACTED]"
        assert invocation.provider_request_id == "[REDACTED]"
        assert invocation.fallback_chain == ["[REDACTED]"]


@pytest.mark.asyncio
async def test_dispatch_claim_does_not_reuse_an_old_application_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = await _context()
    receipt = await _reservation(context, "old-clock")
    actual_now = datetime.now(timezone.utc)
    async with database.async_session_maker() as session:
        task = await session.get(ResearchTask, context["task"].id)
        assert task is not None
        task.lease_expires_at = actual_now - timedelta(seconds=1)
        await session.commit()
    monkeypatch.setattr(quota_module, "_now", lambda: actual_now - timedelta(minutes=1))

    assert not await QuotaService().claim_external_dispatch(
        receipt.reservation_id,
        receipt.fencing_token,
        provider_operation_id="llm-old-clock",
        task_id=context["task"].id,
        run_id=context["run"].id,
        stage_attempt_id=context["stage_attempt"].id,
        lease_token=context["lease_token"],
        stage="GENERATE",
        resource_type="model_tokens",
        unit="tokens",
    )


@pytest.mark.asyncio
async def test_concurrent_successful_calls_do_not_lose_bucket_accounting(
    independent_gateway_database: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Successful calls using different receipts must both debit the same bucket."""

    context = await _context()
    receipts = [await _reservation(context, suffix) for suffix in ("concurrent-a", "concurrent-b")]
    gateways = [
        LlmGateway(provider=_FakeProvider(), catalog=ModelCatalog({"research-default": "model-v1"}))
        for _ in receipts
    ]
    # Both real calls reach settlement before either transaction begins.
    # This proves concurrent admission and final accounting, not a particular
    # database lock ordering or a forced stale-snapshot interleaving.
    both_ready = asyncio.Event()
    arrivals = 0

    def settlement_barrier(gateway: LlmGateway) -> Any:
        original = gateway._quota.settle

        async def wait_then_settle(*args: Any, **kwargs: Any) -> bool:
            nonlocal arrivals
            arrivals += 1
            if arrivals == 2:
                both_ready.set()
            await asyncio.wait_for(both_ready.wait(), timeout=5)
            return await original(*args, **kwargs)

        return wait_then_settle

    for gateway in gateways:
        monkeypatch.setattr(gateway._quota, "settle", settlement_barrier(gateway))
    results = await asyncio.gather(
        *(
            gateway.invoke(**_invocation_arguments(context, receipt))
            for gateway, receipt in zip(gateways, receipts, strict=True)
        ),
        return_exceptions=True,
    )
    assert not [result for result in results if isinstance(result, Exception)], results
    assert arrivals == 2
    async with database.async_session_maker() as session:
        bucket = await session.get(ResearchQuotaBucket, receipts[0].bucket_id)
        assert bucket is not None
        assert (bucket.reserved_amount, bucket.settled_amount, bucket.active_reservations) == (
            0,
            34,
            0,
        )


def _invocation_arguments(
    context: dict[str, Any], receipt: QuotaReservationReceipt
) -> dict[str, Any]:
    return {
        "run_id": context["run"].id,
        "requested_model": "research-default",
        "prompt_template_version": "strategy-v2",
        "system_input": {"role": "researcher"},
        "typed_input": {"question": "验证动量"},
        "sampling_params": {"temperature": 0.1},
        "task_id": context["task"].id,
        "stage_attempt_id": context["stage_attempt"].id,
        "lease_token": context["lease_token"],
        "stage": "GENERATE",
        "quota_reservation_id": receipt.reservation_id,
        "quota_fencing_token": receipt.fencing_token,
    }


@pytest.mark.asyncio
async def test_gateway_preserves_reservation_after_provider_failure() -> None:
    context = await _context()
    provider = _FailingProvider()
    gateway = LlmGateway(provider=provider, catalog=ModelCatalog({"research-default": "model-v1"}))
    receipt = await _reservation(context, "provider-failure")
    arguments = _invocation_arguments(context, receipt)

    with pytest.raises(RuntimeError, match="provider unavailable"):
        await gateway.invoke(**arguments)
    with pytest.raises(ValueError, match="LLM_DISPATCH_ALREADY_CLAIMED"):
        await gateway.invoke(**arguments)
    assert provider.calls == 1
    async with database.async_session_maker() as session:
        reservation = await session.get(ResearchQuotaReservation, receipt.reservation_id)
        assert reservation is not None and reservation.status == "IN_FLIGHT"
        invocation = await session.scalar(
            select(ResearchModelInvocation).where(
                ResearchModelInvocation.run_id == context["run"].id
            )
        )
        assert invocation is not None and invocation.error_code == "LLM_PROVIDER_FAILED"


@pytest.mark.asyncio
async def test_gateway_does_not_hide_usage_exceeding_reserved_budget() -> None:
    context = await _context()
    provider = _FakeProvider()
    provider.token_usage = {"total_tokens": 100}
    gateway = LlmGateway(provider=provider, catalog=ModelCatalog({"research-default": "model-v1"}))
    receipt = await _reservation(context, "over-budget")

    with pytest.raises(ValueError, match="LLM_QUOTA_SETTLEMENT_FAILED"):
        await gateway.invoke(**_invocation_arguments(context, receipt))

    async with database.async_session_maker() as session:
        reservation = await session.get(ResearchQuotaReservation, receipt.reservation_id)
        bucket = await session.get(ResearchQuotaBucket, receipt.bucket_id)
        assert reservation is not None and bucket is not None
        assert reservation.status == "IN_FLIGHT"
        assert (bucket.reserved_amount, bucket.settled_amount) == (32, 0)
        invocation = await session.scalar(
            select(ResearchModelInvocation).where(
                ResearchModelInvocation.run_id == context["run"].id
            )
        )
        assert invocation is not None and invocation.error_code == "LLM_QUOTA_SETTLEMENT_FAILED"


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("resource_type", "sandbox_seconds"), ("unit", "usd")])
async def test_gateway_rejects_a_receipt_for_a_different_resource_or_unit(
    field: str,
    value: str,
) -> None:
    context = await _context()
    provider = _FakeProvider()
    gateway = LlmGateway(provider=provider, catalog=ModelCatalog({"research-default": "model-v1"}))
    receipt = await _reservation(context, "wrong-resource")
    async with database.async_session_maker() as session:
        reservation = await session.get(ResearchQuotaReservation, receipt.reservation_id)
        assert reservation is not None
        setattr(reservation, field, value)
        await session.commit()

    with pytest.raises(ValueError, match="LLM_DISPATCH_ALREADY_CLAIMED"):
        await gateway.invoke(**_invocation_arguments(context, receipt))
    assert provider.calls == []


@pytest.mark.asyncio
async def test_gateway_refuses_cancelled_or_unbound_stage_before_provider_call() -> None:
    context = await _context()
    provider = _FakeProvider()
    gateway = LlmGateway(provider=provider, catalog=ModelCatalog({"research-default": "model-v1"}))
    receipt = await _reservation(context, "cancelled")
    task = context["task"]
    assert isinstance(task, ResearchTask)
    async with database.async_session_maker() as session:
        stored = await session.get(ResearchTask, task.id)
        assert stored is not None
        stored.cancel_requested_at = datetime.now(timezone.utc)
        await session.commit()

    with pytest.raises(ValueError, match="LLM_STAGE_ATTEMPT_FENCING_DENIED"):
        await gateway.invoke(
            run_id=context["run"].id,
            requested_model="research-default",
            prompt_template_version="strategy-v2",
            system_input={"role": "researcher"},
            typed_input={"question": "验证动量"},
            sampling_params={},
            task_id=task.id,
            stage_attempt_id=context["stage_attempt"].id,
            lease_token=context["lease_token"],
            stage="GENERATE",
            quota_reservation_id=receipt.reservation_id,
            quota_fencing_token=receipt.fencing_token,
        )
    assert provider.calls == []


class _FailingProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request: Any) -> ProviderResponse:
        self.calls += 1
        raise RuntimeError("provider unavailable")


@pytest.mark.asyncio
@pytest.mark.parametrize("observed_model", ["model-v1", "unexpected-model", None])
async def test_strict_gateway_records_reported_model_and_rejects_unverified_identity(
    observed_model: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = await _context()
    provider = _FakeProvider()

    async def respond(request: Any) -> ProviderResponse:
        return ProviderResponse(
            "draft", "request-1", {"total_tokens": 17}, {}, observed_model=observed_model
        )

    monkeypatch.setattr(provider, "generate", respond)
    gateway = LlmGateway(
        provider=provider,
        catalog=ModelCatalog({"research-default": "model-v1"}),
        provider_identity="operator-route-v1",
        require_model_identity=True,
    )
    receipt = await _reservation(context, "strict-identity")
    if observed_model == "model-v1":
        await gateway.invoke(**_invocation_arguments(context, receipt))
    else:
        code = (
            "LLM_PROVIDER_MODEL_UNVERIFIED"
            if observed_model is None
            else "LLM_PROVIDER_MODEL_MISMATCH"
        )
        with pytest.raises(ValueError, match=f"^{code}$"):
            await gateway.invoke(**_invocation_arguments(context, receipt))
    async with database.async_session_maker() as session:
        invocation = await session.scalar(select(ResearchModelInvocation))
        reservation = await session.get(ResearchQuotaReservation, receipt.reservation_id)
        assert invocation is not None and reservation is not None
        assert invocation.provider == "operator-route-v1"
        assert (
            invocation.resolved_model == "model-v1"
        )  # Configured request pin, not fabricated observation.
        assert invocation.provider_reported_model == observed_model
        assert reservation.status == ("SETTLED" if observed_model == "model-v1" else "IN_FLIGHT")


class _FakeProvider:
    def __init__(self) -> None:
        self.calls = []
        self.token_usage: dict[str, Any] = {"input": 12, "output": 5}

    async def generate(self, request):
        self.calls.append(request)
        return ProviderResponse(
            output="strategy draft; token=should-be-redacted",
            provider_request_id=f"provider-{len(self.calls)}",
            token_usage=self.token_usage,
            cost={"usd": 0.001},
        )


async def _context() -> dict[str, object]:
    profile = CapabilityProfile(
        profile_id="model-profile",
        version="v1",
        service_identities={"explorer": "explorer", "evaluator": "evaluator"},
        queue_isolation=False,
        storage_isolation=False,
        network_isolation=False,
        sandbox_runner=False,
        approval_mode="single_actor",
        evidence_hash="e" * 64,
        verified_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    await CapabilityRegistry().register(profile)
    run = ResearchRun(
        user_id="model-user",
        hypothesis_version_id="hypothesis-1",
        dataset_snapshot_id="dataset-1",
        experiment_epoch_id="epoch-1",
        promotion_policy_version="promotion-v1",
        request_hash="r" * 64,
        capability_profile_id=profile.profile_id,
        capability_profile_version=profile.version,
        capability_evidence_hash=profile.evidence_hash,
        trace_id="trace-model",
    )
    now = datetime.now(timezone.utc)
    lease_token = "lease-model"
    bucket = ResearchQuotaBucket(
        scope_type="user",
        scope_id="model-user",
        policy_version="quota-v1",
        resource_type="model_tokens",
        window_start=now - timedelta(minutes=1),
        window_end=now + timedelta(hours=1),
        hard_limit=1000,
        concurrency_limit=10,
    )
    async with database.async_session_maker() as session:
        session.add_all([run, bucket])
        await session.commit()
        await session.refresh(run)
        await session.refresh(bucket)
        task = ResearchTask(
            user_id="model-user",
            run_id=run.id,
            status="RUNNING",
            stage_cursor="GENERATE",
            request_json={},
            idempotency_key="model-task",
            idempotency_request_hash="a" * 64,
            lease_token=lease_token,
            lease_expires_at=now + timedelta(hours=1),
            lease_heartbeat_at=now,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        stage_attempt = ResearchStageAttempt(
            run_id=run.id,
            task_id=task.id,
            stage="GENERATE",
            attempt_no=1,
            idempotency_key="model-generate",
            status="RUNNING",
            lease_token=lease_token,
            input_hash="b" * 64,
        )
        session.add(stage_attempt)
        await session.commit()
        await session.refresh(stage_attempt)
    return {
        "run": run,
        "bucket": bucket,
        "task": task,
        "stage_attempt": stage_attempt,
        "lease_token": lease_token,
    }


async def _reservation(context: dict[str, object], suffix: str):
    bucket = context["bucket"]
    task = context["task"]
    stage_attempt = context["stage_attempt"]
    assert isinstance(bucket, ResearchQuotaBucket)
    assert isinstance(task, ResearchTask)
    assert isinstance(stage_attempt, ResearchStageAttempt)
    return (
        await QuotaService().reserve(
            task_id=task.id,
            policy_version="quota-v1",
            idempotency_key=f"model-stage-{suffix}",
            request_hash=(suffix * 64)[:64],
            requests=(QuotaReservationRequest(bucket.id, "model_tokens", 32, "tokens"),),
            stage_attempt_id=stage_attempt.id,
        )
    )[0]
