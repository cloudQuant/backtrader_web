"""Hard-bound accounting-contract tests; no provider or business DB is contacted."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.research.canonical import content_hash
from app.services.research.provider_contract import PreparedProviderRequest

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
_ENDPOINT_HASH = "a" * 64
_MAX_INT32 = 2**31 - 1


def _policy_payload(**changes: object) -> dict[str, object]:
    return {
        "schema_version": "model-accounting-v1",
        "version": "provider-accounting-2026-09",
        "provider_id": "provider-v1",
        "model_id": "model-v1",
        "endpoint_hash": _ENDPOINT_HASH,
        "max_billable_input_tokens": 20,
        "max_output_tokens": 16,
        "input_microusd_per_million": 1_000_001,
        "output_microusd_per_million": 2_000_001,
        "fixed_microusd": 7,
        "valid_from": "2026-09-01T00:00:00Z",
        "expires_at": "2026-09-06T00:00:00Z",
        "evidence_hash": "b" * 64,
        "accounting_contract": "ALL_INCLUSIVE_TEXT_CHAT_V1",
        "output_contract": "MAX_TOKENS_ALL_BILLABLE",
        "pricing_contract": "ADMISSION_PRICE_ALL_INCLUSIVE_V1",
        **changes,
    }


def _policy(**changes: object):
    from app.services.research.model_budget import ModelAccountingPolicy

    payload = _policy_payload(**changes)
    return ModelAccountingPolicy.from_mapping(payload, expected_hash=content_hash(payload))


def _prepared(*, payload: bytes = b'{"safe":"body"}', max_output_tokens: int = 16):
    return PreparedProviderRequest(
        payload=payload,
        provider_id="provider-v1",
        model_id="model-v1",
        endpoint_hash=_ENDPOINT_HASH,
        max_output_tokens=max_output_tokens,
    )


def test_policy_pin_snapshot_and_quote_context_are_detached_from_raw_request_bytes():
    from app.services.research.model_budget import quote_request

    policy = _policy()
    prepared = _prepared(payload=b'{"secret_prompt":"not persisted here"}')

    quote = quote_request(
        prepared,
        policy,
        token_limit=100,
        now=NOW,
        dispatch_timeout_seconds=60,
    )
    context = quote.context(
        run_request_hash="c" * 64,
        task_id="task-v1",
        stage_attempt_id="attempt-v1",
        quota_policy_version="quota-v1",
    )

    assert policy.content_hash == content_hash(policy.snapshot())
    assert context["body_hash"] == prepared.body_hash
    assert context["policy_content_hash"] == policy.content_hash
    assert context["policy"] == policy.snapshot()
    assert b"secret_prompt" not in repr(context).encode("utf-8")
    assert "payload" not in context and "prepared" not in context
    context["policy"]["version"] = "tampered"
    assert (
        quote.context(
            run_request_hash="c" * 64,
            task_id="task-v1",
            stage_attempt_id="attempt-v1",
            quota_policy_version="quota-v1",
        )["policy"]["version"]
        == "provider-accounting-2026-09"
    )


def test_quote_rounds_input_and_output_charges_separately_for_a_conservative_bound():
    from app.services.research.model_budget import quote_request

    quote = quote_request(
        _prepared(),
        _policy(),
        token_limit=100,
        now=NOW,
        dispatch_timeout_seconds=60,
    )

    assert quote.input_token_ceiling == 20
    assert quote.output_token_ceiling == 16
    assert quote.reserved_tokens == 36
    # A supplier may round each billable input/output category independently.
    # Combining both fractions and rounding only once would under-reserve here.
    assert quote.reserved_microusd == 61
    assert quote.settlement(input_tokens=1, output_tokens=1) == (2, 12)


@pytest.mark.parametrize(
    "changes",
    [
        {"unreviewed": "field"},
        {"max_billable_input_tokens": True},
        {"input_microusd_per_million": 1.0},
        {"max_billable_input_tokens": _MAX_INT32 + 1},
        {"max_output_tokens": 131_073},
        {"output_microusd_per_million": _MAX_INT32 + 1},
        {"valid_from": "2026-09-01T00:00:00"},
        {"expires_at": "2026-09-06T00:00:00+08:00"},
        {"provider_id": ""},
        {"evidence_hash": "not-a-hash"},
        {"accounting_contract": "unreviewed"},
    ],
)
def test_policy_rejects_unpinned_fields_invalid_types_and_non_utc_contract_values(changes):
    from app.services.research.model_budget import ModelAccountingPolicy

    payload = _policy_payload(**changes)
    if "unreviewed" in changes:
        expected_hash = content_hash(payload)
    else:
        expected_hash = content_hash(payload)
    with pytest.raises(ValueError, match="^MODEL_ACCOUNTING_POLICY_INVALID$"):
        ModelAccountingPolicy.from_mapping(payload, expected_hash=expected_hash)


def test_policy_rejects_tariff_when_the_deployment_audit_pin_is_stale():
    from app.services.research.model_budget import ModelAccountingPolicy

    original = _policy_payload()
    drifted = _policy_payload(input_microusd_per_million=1_000_002)

    with pytest.raises(ValueError, match="^MODEL_ACCOUNTING_POLICY_HASH_MISMATCH$"):
        ModelAccountingPolicy.from_mapping(drifted, expected_hash=content_hash(original))


@pytest.mark.parametrize(
    "policy_changes,now,timeout",
    [
        ({"valid_from": "2026-09-05T12:01:00Z"}, NOW, 60),
        ({"expires_at": "2026-09-05T12:01:00Z"}, NOW, 60),
        ({"max_output_tokens": 15}, NOW, 60),
    ],
)
def test_quote_rejects_policy_window_or_output_cap_drift(policy_changes, now, timeout):
    from app.services.research.model_budget import quote_request

    with pytest.raises(ValueError):
        quote_request(
            _prepared(),
            _policy(**policy_changes),
            token_limit=100,
            now=now,
            dispatch_timeout_seconds=timeout,
        )


def test_quote_rejects_token_and_cost_overflow_before_any_dispatch():
    from app.services.research.model_budget import quote_request

    with pytest.raises(ValueError, match="^MODEL_BUDGET_TOKEN_LIMIT_EXCEEDED$"):
        quote_request(
            _prepared(max_output_tokens=1),
            _policy(max_billable_input_tokens=20, max_output_tokens=16),
            token_limit=20,
            now=NOW,
            dispatch_timeout_seconds=60,
        )
    with pytest.raises(ValueError, match="^MODEL_BUDGET_AMOUNT_OVERFLOW$"):
        quote_request(
            _prepared(max_output_tokens=1),
            _policy(
                max_billable_input_tokens=1_000_000,
                max_output_tokens=16,
                input_microusd_per_million=_MAX_INT32,
                output_microusd_per_million=1,
                fixed_microusd=1,
            ),
            token_limit=1_000_001,
            now=NOW,
            dispatch_timeout_seconds=60,
        )


def test_settlement_requires_independent_known_input_and_output_usage_within_quote_caps():
    from app.services.research.model_budget import quote_request

    quote = quote_request(
        _prepared(), _policy(), token_limit=100, now=NOW, dispatch_timeout_seconds=60
    )

    for input_tokens, output_tokens in ((None, 1), (True, 1), (21, 1), (1, 17)):
        with pytest.raises(ValueError, match="^MODEL_BUDGET_SETTLEMENT_INVALID$"):
            quote.settlement(input_tokens=input_tokens, output_tokens=output_tokens)


def test_tariff_drift_cannot_reuse_a_previous_quote_or_its_reserved_amount():
    from app.services.research.model_budget import BudgetQuote, quote_request

    prepared = _prepared()
    original = _policy()
    quote = quote_request(prepared, original, token_limit=100, now=NOW, dispatch_timeout_seconds=60)
    drifted = _policy(input_microusd_per_million=2_000_001)

    assert drifted.content_hash != original.content_hash
    with pytest.raises(ValueError, match="^MODEL_BUDGET_QUOTE_INVALID$"):
        BudgetQuote(
            prepared=prepared,
            policy=drifted,
            input_token_ceiling=quote.input_token_ceiling,
            output_token_ceiling=quote.output_token_ceiling,
            reserved_tokens=quote.reserved_tokens,
            reserved_microusd=quote.reserved_microusd,
        )
