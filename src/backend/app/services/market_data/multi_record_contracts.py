"""Reviewed internal dimension contracts for B2 multi-record evidence.

The generic semantic-record normalizer deliberately has no product knowledge.
This module supplies the narrow, versioned dictionary required before one of
the four unconfigured B2 families can write a non-singleton observation or
issue an expected-record manifest.  It is an internal evidence boundary, not
a public product capability, provider adapter, or selector API.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Literal

from app.services.market_data.multi_record import (
    B2ReportSelector,
    B2SliceSelector,
    SemanticRecordKey,
    normalize_record_dimensions,
    normalize_semantic_record_key,
)

_FAMILY_CONTRACT_VERSION = "market-data-family-v1"
_MAX_EXPECTED_RECORDS = 50_000
_MAX_IDENTIFIER_LENGTH = 512
_DECIMAL_TEXT = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_DimensionKind = Literal["date", "decimal_text", "identifier", "positive_int", "right", "text"]


class B2FamilyContractError(ValueError):
    """Stable rejection for an unreviewed B2 family coordinate."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class B2FamilyContract:
    """Exact dimension and selector rules for one internal B2 family version."""

    family_id: str
    family_contract_version: str
    selector_kind: Literal["slice", "report"]
    record_dimension_fields: tuple[str, ...]
    selector_dimension_fields: frozenset[str]
    _field_kinds: Mapping[str, _DimensionKind]

    def normalize_record_dimensions(self, value: Mapping[str, object]) -> Mapping[str, object]:
        """Return one exact, type-preserving record coordinate or reject it."""
        normalized = _normalize_mapping(value, code="B2_RECORD_DIMENSIONS_INVALID")
        if set(normalized) != set(self.record_dimension_fields):
            raise B2FamilyContractError("B2_RECORD_DIMENSIONS_INVALID")
        self._validate_dimension_values(normalized, code="B2_RECORD_DIMENSIONS_INVALID")
        return normalized

    def normalize_selector_dimensions(self, value: Mapping[str, object]) -> Mapping[str, object]:
        """Return a reviewed nonempty selector dimension subset or reject it."""
        normalized = _normalize_mapping(value, code="B2_SELECTOR_DIMENSIONS_INVALID")
        if not normalized or not set(normalized) <= self.selector_dimension_fields:
            raise B2FamilyContractError("B2_SELECTOR_DIMENSIONS_INVALID")
        self._validate_dimension_values(normalized, code="B2_SELECTOR_DIMENSIONS_INVALID")
        return normalized

    def semantic_record_key(self, value: Mapping[str, object]) -> SemanticRecordKey:
        """Issue a server-owned non-singleton identity for an exact coordinate."""
        return normalize_semantic_record_key(
            family_id=self.family_id,
            family_contract_version=self.family_contract_version,
            dimensions=self.normalize_record_dimensions(value),
        )

    def _validate_dimension_values(
        self,
        value: Mapping[str, object],
        *,
        code: str,
    ) -> None:
        for field_name, dimension_value in value.items():
            kind = self._field_kinds.get(field_name)
            if kind is None or not _value_matches_kind(dimension_value, kind):
                raise B2FamilyContractError(code)


def get_b2_family_contract(
    family_id: str,
    family_contract_version: str,
) -> B2FamilyContract:
    """Return one reviewed contract; no fallback or version guessing exists."""
    if not isinstance(family_id, str) or not isinstance(family_contract_version, str):
        raise B2FamilyContractError("B2_FAMILY_CONTRACT_UNSUPPORTED")
    contract = _FAMILY_CONTRACTS.get((family_id, family_contract_version))
    if contract is None:
        raise B2FamilyContractError("B2_FAMILY_CONTRACT_UNSUPPORTED")
    return contract


def normalize_b2_record_dimensions(
    *,
    family_id: str,
    family_contract_version: str,
    dimensions: Mapping[str, object],
) -> Mapping[str, object]:
    """Normalize exact B2 record dimensions through their reviewed contract."""
    return get_b2_family_contract(
        family_id,
        family_contract_version,
    ).normalize_record_dimensions(dimensions)


def normalize_b2_selector_dimensions(
    *,
    family_id: str,
    family_contract_version: str,
    dimensions: Mapping[str, object],
) -> Mapping[str, object]:
    """Normalize a reviewed B2 selector subset without inferring omitted fields."""
    return get_b2_family_contract(
        family_id,
        family_contract_version,
    ).normalize_selector_dimensions(dimensions)


def issue_b2_selector(
    *,
    family_id: str,
    family_contract_version: str,
    selector_dimensions: Mapping[str, object],
    expected_record_dimensions: Iterable[Mapping[str, object]],
) -> B2SliceSelector | B2ReportSelector:
    """Derive one exact selector and expected-key manifest from B2 dimensions.

    Raw semantic-key hashes are deliberately not accepted here.  Every
    expected digest is derived from an exact family coordinate after verifying
    that it belongs to the declared selector.
    """
    contract = get_b2_family_contract(family_id, family_contract_version)
    selector = contract.normalize_selector_dimensions(selector_dimensions)
    if isinstance(expected_record_dimensions, (str, bytes)) or not isinstance(
        expected_record_dimensions,
        Iterable,
    ):
        raise B2FamilyContractError("B2_EXPECTED_RECORDS_INVALID")

    expected_keys: list[str] = []
    seen: set[str] = set()
    for index, record_dimensions in enumerate(expected_record_dimensions):
        if index >= _MAX_EXPECTED_RECORDS or not isinstance(record_dimensions, Mapping):
            raise B2FamilyContractError("B2_EXPECTED_RECORDS_INVALID")
        record = contract.normalize_record_dimensions(record_dimensions)
        if any(
            not _exact_value_equal(record[field_name], selector_value)
            for field_name, selector_value in selector.items()
        ):
            raise B2FamilyContractError("B2_MANIFEST_SELECTOR_MISMATCH")
        semantic_key = contract.semantic_record_key(record)
        if semantic_key.sha256 in seen:
            raise B2FamilyContractError("B2_EXPECTED_RECORD_DUPLICATE")
        seen.add(semantic_key.sha256)
        expected_keys.append(semantic_key.sha256)

    selector_kwargs = {
        "family_id": contract.family_id,
        "family_contract_version": contract.family_contract_version,
        "selector_dimensions": selector,
        "expected_record_key_sha256s": tuple(expected_keys),
    }
    if contract.selector_kind == "slice":
        return B2SliceSelector(**selector_kwargs)
    return B2ReportSelector(**selector_kwargs)


def _normalize_mapping(value: Mapping[str, object], *, code: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise B2FamilyContractError(code)
    try:
        return normalize_record_dimensions(value)
    except (TypeError, ValueError) as exc:
        raise B2FamilyContractError(code) from exc


def _value_matches_kind(value: object, kind: _DimensionKind) -> bool:
    if kind in {"identifier", "text"}:
        return (
            isinstance(value, str)
            and bool(value)
            and value == value.strip()
            and len(value) <= _MAX_IDENTIFIER_LENGTH
        )
    if kind == "date":
        if not isinstance(value, str) or value != value.strip():
            return False
        try:
            return date.fromisoformat(value).isoformat() == value
        except ValueError:
            return False
    if kind == "decimal_text":
        return isinstance(value, str) and bool(_DECIMAL_TEXT.fullmatch(value))
    if kind == "positive_int":
        return isinstance(value, int) and not isinstance(value, bool) and value >= 1
    return isinstance(value, str) and value in {"call", "put"}


def _exact_value_equal(left: object, right: object) -> bool:
    return type(left) is type(right) and left == right


def _contract(
    family_id: str,
    selector_kind: Literal["slice", "report"],
    field_kinds: Mapping[str, _DimensionKind],
) -> B2FamilyContract:
    record_fields = tuple(field_kinds)
    return B2FamilyContract(
        family_id=family_id,
        family_contract_version=_FAMILY_CONTRACT_VERSION,
        selector_kind=selector_kind,
        record_dimension_fields=record_fields,
        selector_dimension_fields=frozenset(record_fields),
        _field_kinds=dict(field_kinds),
    )


_FAMILY_CONTRACTS = {
    ("futures.inventory", _FAMILY_CONTRACT_VERSION): _contract(
        "futures.inventory",
        "report",
        {
            "report_date": "date",
            "location": "identifier",
            "warehouse": "identifier",
            "commodity": "identifier",
        },
    ),
    ("option.derivative", _FAMILY_CONTRACT_VERSION): _contract(
        "option.derivative",
        "slice",
        {
            "underlying_canonical_id": "identifier",
            "contract_canonical_id": "identifier",
            "expiry": "date",
            "strike": "decimal_text",
            "right": "right",
        },
    ),
    ("option.risk_surface", _FAMILY_CONTRACT_VERSION): _contract(
        "option.risk_surface",
        "slice",
        {
            "underlying_canonical_id": "identifier",
            "expiry": "date",
            "moneyness": "decimal_text",
            "model_version": "text",
        },
    ),
    ("crypto.cme_position", _FAMILY_CONTRACT_VERSION): _contract(
        "crypto.cme_position",
        "report",
        {
            "report_date": "date",
            "reporting_entity": "identifier",
            "rank": "positive_int",
            "report_type": "text",
        },
    ),
}


__all__ = [
    "B2FamilyContract",
    "B2FamilyContractError",
    "get_b2_family_contract",
    "issue_b2_selector",
    "normalize_b2_record_dimensions",
    "normalize_b2_selector_dimensions",
]
