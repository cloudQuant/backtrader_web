"""Evidence contracts for immutable, non-guessable provider requests."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.services.market_data.providers import MarketDataProviderRequest

UTC = timezone.utc
POLICY_HASH = "d" * 64
ACCESS_GRANT_HASH = "e" * 64


def _request(**changes: object) -> MarketDataProviderRequest:
    values: dict[str, object] = {
        "query_fingerprint": "a" * 64,
        "canonical_id": "instrument:stock:CN-SSE:600000",
        "asset_type": "stock",
        "provider_symbol": "600000",
        "market": "CN-SSE",
        "data_kind": "bars",
        "frequency": "1d",
        "start_at": datetime(2026, 9, 7, tzinfo=UTC),
        "end_at": datetime(2026, 9, 8, tzinfo=UTC),
        "required_fields": frozenset({"close", "open"}),
        "provider": "akshare",
        "source_policy_id": "market-default-v1",
        "route_id": "akshare-stock-primary-v1",
        "policy_descriptor_hash": POLICY_HASH,
        "access_grant_descriptor_hash": ACCESS_GRANT_HASH,
    }
    values.update(changes)
    return MarketDataProviderRequest(**values)  # type: ignore[arg-type]


def test_each_provider_attempt_has_a_distinct_csprng_request_id_and_receipt_dto_hash() -> None:
    """The public query identity cannot predict or replace provider-attempt evidence."""
    first = _request()
    second = _request()

    assert first.query_fingerprint == second.query_fingerprint
    assert first.request_id != second.request_id
    assert len(first.request_id) >= 32
    assert len(second.request_id) >= 32
    assert first.provider_request_fingerprint_sha256 != second.provider_request_fingerprint_sha256
    assert first.dto_payload["request_id"] == first.request_id
    assert first.dto_payload["route_id"] == "akshare-stock-primary-v1"
    assert first.dto_payload["policy_descriptor_hash"] == POLICY_HASH
    assert first.dto_payload["access_grant_descriptor_hash"] == ACCESS_GRANT_HASH


def test_request_fingerprint_covers_route_and_every_outbound_dto_dimension() -> None:
    """Changing a route or semantic axis changes the receipt fingerprint."""
    request = _request(request_id="A" * 43)

    assert replace(
        request, route_id="akshare-stock-secondary-v1"
    ).provider_request_fingerprint_sha256 != (request.provider_request_fingerprint_sha256)
    assert replace(
        request, policy_descriptor_hash="b" * 64
    ).provider_request_fingerprint_sha256 != (request.provider_request_fingerprint_sha256)
    assert replace(
        request, access_grant_descriptor_hash="c" * 64
    ).provider_request_fingerprint_sha256 != (request.provider_request_fingerprint_sha256)
    assert replace(request, provider_symbol="600001").provider_request_fingerprint_sha256 != (
        request.provider_request_fingerprint_sha256
    )
    assert replace(
        request, required_fields=frozenset({"close"})
    ).provider_request_fingerprint_sha256 != (request.provider_request_fingerprint_sha256)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("request_id", "short"),
        ("request_id", "!" * 43),
        ("policy_descriptor_hash", "not-a-digest"),
        ("access_grant_descriptor_hash", "not-a-digest"),
    ],
)
def test_provider_request_rejects_noncanonical_internal_evidence(
    field_name: str,
    value: str,
) -> None:
    """Callers cannot supply malformed correlation or policy evidence."""
    with pytest.raises(ValueError):
        _request(**{field_name: value})
