"""Strict input contracts for Iteration 197 local-first market-data queries."""

from __future__ import annotations

from copy import deepcopy
from datetime import timezone

import pytest
from pydantic import ValidationError


def _query_payload() -> dict[str, object]:
    """Return a complete valid bars request for contract-focused tests."""
    return {
        "identity": {"canonical_id": "instrument:stock:cn:600000"},
        "data_kind": "bars",
        "dataset_code": "market.stock_daily",
        "frequency": "1d",
        "start": "2025-01-02T09:30:00+08:00",
        "end": "2025-01-03T09:30:00+08:00",
        "required_fields": ["open", "high", "low", "close", "volume"],
        "adjustment": "qfq",
        "price_basis": "close",
        "currency": "CNY",
        "unit": "share",
        "source_policy_id": "market-default-v1",
        "purpose": "display",
    }


def _build_query(**changes: object):
    from app.schemas.market_data_platform import MarketDataQueryRequest

    payload = _query_payload()
    payload.update(changes)
    return MarketDataQueryRequest.model_validate(payload)


def test_query_identity_requires_one_exact_selector() -> None:
    """Identity is either canonical or a fully specified asset/symbol/market triple."""
    from app.schemas.market_data_platform import QueryIdentity

    canonical = QueryIdentity.model_validate({"canonical_id": "  instrument:stock:cn:600000  "})
    triple = QueryIdentity.model_validate(
        {"asset_type": "stock", "symbol": "600000", "market": "CN-SSE"}
    )

    assert canonical.canonical_id == "instrument:stock:cn:600000"
    assert canonical.asset_type is None
    assert triple.canonical_id is None
    assert triple.asset_type == "stock"
    assert triple.symbol == "600000"
    assert triple.market == "CN-SSE"

    for invalid in (
        {},
        {"canonical_id": ""},
        {"asset_type": "stock", "symbol": "600000"},
        {
            "canonical_id": "instrument:stock:cn:600000",
            "asset_type": "stock",
            "symbol": "600000",
            "market": "CN-SSE",
        },
    ):
        with pytest.raises(ValidationError):
            QueryIdentity.model_validate(invalid)


def test_query_requires_aware_half_open_time_range_and_unambiguous_bar_frequency() -> None:
    """The v1 endpoint rejects old ambiguous periods and naive or inverted intervals."""
    query = _build_query()

    assert query.start.tzinfo == timezone.utc
    assert query.end.tzinfo == timezone.utc
    assert query.start < query.end

    for invalid_frequency in ("1m", "1M", "monthly", "5m"):
        with pytest.raises(ValidationError):
            _build_query(frequency=invalid_frequency)

    with pytest.raises(ValidationError):
        _build_query(frequency=None)
    with pytest.raises(ValidationError):
        _build_query(start="2025-01-02T09:30:00", end="2025-01-03T09:30:00+08:00")
    with pytest.raises(ValidationError):
        _build_query(start="2025-01-03T09:30:00+08:00", end="2025-01-03T09:30:00+08:00")
    with pytest.raises(ValidationError):
        _build_query(purpose="research")
    with pytest.raises(ValidationError):
        _build_query(purpose="backtest", consistency="strict")
    with pytest.raises(ValidationError):
        _build_query(consistency="strict")
    with pytest.raises(ValidationError):
        _build_query(mode="refresh", cursor="frozen-page")
    with pytest.raises(ValidationError):
        _build_query(end="2025-02-10T09:30:00+08:00", frequency="5min")

    strict_research = _build_query(
        purpose="research",
        consistency="strict",
        knowledge_cutoff="2025-01-03T10:00:00+08:00",
    )
    assert strict_research.knowledge_cutoff is not None
    cache_fill = _build_query(purpose="research_cache_fill", mode="local_first")
    assert cache_fill.purpose == "research_cache_fill"
    assert cache_fill.knowledge_cutoff is None
    for invalid_cache_fill in (
        {"mode": "local_only"},
        {"mode": "refresh"},
        {"consistency": "strict", "knowledge_cutoff": "2025-01-03T10:00:00+08:00"},
        {"cursor": "frozen-page"},
        {"knowledge_cutoff": "2025-01-03T10:00:00+08:00"},
    ):
        with pytest.raises(ValidationError):
            _build_query(purpose="research_cache_fill", **invalid_cache_fill)
    with pytest.raises(ValidationError):
        _build_query(
            purpose="backtest",
            consistency="strict",
            knowledge_cutoff="2026-01-03T10:00:00+08:00",
        )


def test_public_v2_query_requires_a_complete_family_binding() -> None:
    """The HTTP-facing DTO cannot retain the internal unbound compatibility shape."""
    from app.schemas.market_data_platform import PublicMarketDataQueryRequest

    payload = _query_payload()
    payload.update(
        family_id="stock.realtime",
        family_contract_version="market-data-family-v1",
    )
    request = PublicMarketDataQueryRequest.model_validate(payload)

    assert request.family_id == "stock.realtime"
    assert request.family_contract_version == "market-data-family-v1"

    for field_name in ("family_id", "family_contract_version"):
        invalid = deepcopy(payload)
        invalid.pop(field_name)
        with pytest.raises(ValidationError):
            PublicMarketDataQueryRequest.model_validate(invalid)


def test_required_fields_are_nonempty_distinct_and_canonically_ordered() -> None:
    """Coverage field sets cannot hide a blank or duplicate requirement."""
    query = _build_query(required_fields=[" volume ", "close", "open"])

    assert query.required_fields == ("close", "open", "volume")

    for invalid_fields in ([], [""], ["close", " close "], "close"):
        with pytest.raises(ValidationError):
            _build_query(required_fields=invalid_fields)


def test_query_fingerprint_is_deterministic_semantic_and_ignores_transport_controls() -> None:
    """Equivalent semantic queries deduplicate while materially different ones do not."""
    query = _build_query()
    reordered = _build_query(required_fields=["volume", "close", "low", "high", "open"])
    transport_only = _build_query(cursor="next-page", page_size=25)

    assert query.query_fingerprint == reordered.query_fingerprint
    assert query.query_fingerprint == transport_only.query_fingerprint

    for field, value in (
        ("frequency", "1w"),
        ("end", "2025-01-10T09:30:00+08:00"),
        ("price_basis", "settle"),
        ("source_policy_id", "market-premium-v2"),
        ("purpose", "export"),
        ("mode", "refresh"),
        ("required_fields", ["open", "high", "low", "close"]),
    ):
        changed = _build_query(**{field: value})
        assert changed.query_fingerprint != query.query_fingerprint


def test_resolved_query_binds_the_authoritative_identity_and_dataset_to_its_fingerprint() -> None:
    """Services may only use a post-resolution hash after catalog and identity lookup."""
    from app.schemas.market_data_platform import ResolvedMarketDataQuery

    unresolved = _build_query(
        identity={"asset_type": "stock", "symbol": "600000", "market": "CN-SSE"}
    )
    resolved = ResolvedMarketDataQuery.from_request(
        unresolved,
        canonical_id="instrument:stock:cn:600000",
        dataset_code="market.stock_daily",
        instrument_metadata_version="instrument-v3",
    )
    changed_metadata = ResolvedMarketDataQuery.model_validate(
        {
            **deepcopy(resolved.model_dump(mode="json")),
            "instrument_metadata_version": "instrument-v4",
        }
    )

    assert resolved.canonical_id == "instrument:stock:cn:600000"
    assert resolved.identity.canonical_id == "instrument:stock:cn:600000"
    assert resolved.dataset_code == "market.stock_daily"
    assert changed_metadata.query_fingerprint != resolved.query_fingerprint

    with pytest.raises(ValidationError):
        ResolvedMarketDataQuery.model_validate(
            {
                **_query_payload(),
                "canonical_id": "instrument:stock:cn:600001",
                "instrument_metadata_version": "instrument-v3",
            }
        )
    with pytest.raises(ValidationError):
        ResolvedMarketDataQuery.model_validate(
            {
                **_query_payload(),
                "identity": {"asset_type": "stock", "symbol": "600000", "market": "CN-SSE"},
                "canonical_id": "instrument:stock:cn:600000",
                "instrument_metadata_version": "instrument-v3",
            }
        )
