"""Pure contracts for Iteration 197 B2 semantic record identities."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import pytest

from app.services.market_data.multi_record import (
    RECORD_IDENTITY_CONTRACT_VERSION,
    SINGLE_RECORD_SEMANTIC_KEY_CANONICAL_JSON,
    SINGLE_RECORD_SEMANTIC_KEY_SHA256,
    SemanticRecordKey,
    normalize_semantic_record_key,
    single_record_semantic_key,
)


def test_two_dimension_orderings_have_one_canonical_record_key() -> None:
    """Dictionary insertion order cannot alter a server-owned record identity."""
    left = normalize_semantic_record_key(
        family_id="option.derivative",
        family_contract_version="market-data-family-v1",
        dimensions={"strike": "100", "right": "call"},
    )
    right = normalize_semantic_record_key(
        family_id="option.derivative",
        family_contract_version="market-data-family-v1",
        dimensions={"right": "call", "strike": "100"},
    )

    assert left.canonical_json == right.canonical_json
    assert left.sha256 == right.sha256
    assert left.canonical_json == (
        '{"dimensions":{"right":"call","strike":"100"},'
        '"family_contract_version":"market-data-family-v1",'
        '"family_id":"option.derivative",'
        f'"record_identity_contract_version":"{RECORD_IDENTITY_CONTRACT_VERSION}"}}'
    )
    assert left.dimensions == {"right": "call", "strike": "100"}
    assert left.is_singleton is False


def test_nested_json_safe_dimensions_are_copied_and_canonicalized() -> None:
    """Nested maps and ordered arrays are frozen before their digest is issued."""
    dimensions: dict[str, object] = {
        "contract": {"expiry": "2026-10-30", "underlying": "IF"},
        "legs": ["front", "back"],
    }

    key = normalize_semantic_record_key(
        family_id="option.derivative",
        family_contract_version="market-data-family-v1",
        dimensions=dimensions,
    )
    dimensions["contract"] = {"expiry": "mutated"}
    dimensions["legs"] = ["mutated"]

    assert key.dimensions == {
        "contract": {"expiry": "2026-10-30", "underlying": "IF"},
        "legs": ("front", "back"),
    }
    assert key.canonical_json == (
        '{"dimensions":{"contract":{"expiry":"2026-10-30","underlying":"IF"},'
        '"legs":["front","back"]},'
        '"family_contract_version":"market-data-family-v1",'
        '"family_id":"option.derivative",'
        f'"record_identity_contract_version":"{RECORD_IDENTITY_CONTRACT_VERSION}"}}'
    )


def test_singleton_record_key_is_fixed_and_has_no_caller_input() -> None:
    """All legacy single-record rows use exactly one server-owned identity."""
    left = single_record_semantic_key()
    right = single_record_semantic_key()

    assert left == right
    assert left.is_singleton is True
    assert left.dimensions == {}
    assert left.canonical_json == SINGLE_RECORD_SEMANTIC_KEY_CANONICAL_JSON
    assert left.sha256 == SINGLE_RECORD_SEMANTIC_KEY_SHA256
    assert left.canonical_json == (
        '{"record_identity_contract_version":"market-data-semantic-record-key-v1",'
        '"scope":"singleton"}'
    )
    assert left.sha256 == "98220d1065fb50740a858df25f884573e8c6aea554b05a3268ed4d1fd621d08e"


@pytest.mark.parametrize(
    ("dimensions", "match"),
    [
        ({}, "dimensions"),
        ({"strike": "   "}, "empty"),
        ({"strike": float("nan")}, "finite"),
        ({"strike": float("inf")}, "finite"),
        ({"strike": {"100", "105"}}, "unsupported"),
        ({"strike": datetime(2026, 9, 11, tzinfo=timezone.utc)}, "unsupported"),
        ({"": "100"}, "non-empty"),
        ({1: "100"}, "string"),
    ],
)
def test_non_singleton_key_rejects_empty_nonfinite_or_unstable_dimensions(
    dimensions: dict[object, object],
    match: str,
) -> None:
    """Only a bounded deterministic JSON value can become a record identity."""
    with pytest.raises((TypeError, ValueError), match=match):
        normalize_semantic_record_key(
            family_id="option.derivative",
            family_contract_version="market-data-family-v1",
            dimensions=dimensions,
        )


@pytest.mark.parametrize(
    ("family_id", "family_contract_version"),
    [
        ("", "market-data-family-v1"),
        ("option.derivative", ""),
        ("  ", "market-data-family-v1"),
        ("option.derivative", "   "),
    ],
)
def test_non_singleton_key_requires_exact_nonempty_family_contract(
    family_id: str,
    family_contract_version: str,
) -> None:
    """A row key cannot exist outside a reviewed family contract version."""
    with pytest.raises(ValueError, match="non-empty"):
        normalize_semantic_record_key(
            family_id=family_id,
            family_contract_version=family_contract_version,
            dimensions={"strike": "100"},
        )


def test_family_contract_and_dimension_changes_produce_distinct_keys() -> None:
    """Nearby products and dimensions cannot overwrite each other's record rows."""
    base = normalize_semantic_record_key(
        family_id="option.derivative",
        family_contract_version="market-data-family-v1",
        dimensions={"contract": "IF2610C100", "strike": "100", "right": "call"},
    )
    changed_dimension = normalize_semantic_record_key(
        family_id="option.derivative",
        family_contract_version="market-data-family-v1",
        dimensions={"contract": "IF2610P100", "strike": "100", "right": "put"},
    )
    changed_contract = normalize_semantic_record_key(
        family_id="option.derivative",
        family_contract_version="market-data-family-v2",
        dimensions={"contract": "IF2610C100", "strike": "100", "right": "call"},
    )

    assert base.sha256 != changed_dimension.sha256
    assert base.sha256 != changed_contract.sha256


def test_semantic_record_key_rejects_a_hash_valid_payload_with_mismatched_dimensions() -> None:
    """Callers cannot forge a key by pairing arbitrary canonical text and dimensions."""
    canonical_json = (
        '{"dimensions":{"contract":"IF2610C105","right":"call"},'
        '"family_contract_version":"market-data-family-v1",'
        '"family_id":"option.derivative",'
        f'"record_identity_contract_version":"{RECORD_IDENTITY_CONTRACT_VERSION}"}}'
    )

    with pytest.raises(ValueError, match="dimensions"):
        SemanticRecordKey(
            canonical_json=canonical_json,
            sha256=hashlib.sha256(canonical_json.encode("utf-8")).hexdigest(),
            dimensions={"contract": "IF2610C100", "right": "call"},
            is_singleton=False,
        )


@pytest.mark.parametrize(
    ("canonical_dimension", "supplied_dimension"),
    [
        (True, 1),
        (1, 1.0),
        (-0.0, 0.0),
        ({"nested": (True, -0.0)}, {"nested": (1, 0.0)}),
    ],
)
def test_semantic_record_key_rejects_hash_valid_dimensions_with_different_json_types_or_bytes(
    canonical_dimension: object,
    supplied_dimension: object,
) -> None:
    """Key canonicalization never inherits Python's bool/number equality rules."""
    canonical = normalize_semantic_record_key(
        family_id="option.derivative",
        family_contract_version="market-data-family-v1",
        dimensions={"coordinate": canonical_dimension},
    )

    with pytest.raises(ValueError, match="dimensions"):
        SemanticRecordKey(
            canonical_json=canonical.canonical_json,
            sha256=canonical.sha256,
            dimensions={"coordinate": supplied_dimension},
            is_singleton=False,
        )
