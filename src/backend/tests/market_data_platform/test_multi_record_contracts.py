"""Versioned family contracts for Iteration 197 B2 multi-record evidence."""

from __future__ import annotations

import pytest

from app.services.market_data import dataset_contracts as dataset_contracts_module
from app.services.market_data.multi_record import B2ReportSelector, B2SliceSelector
from app.services.market_data.multi_record_contracts import (
    B2FamilyContractError,
    get_b2_family_contract,
    issue_b2_selector,
)

CONTRACT_VERSION = "market-data-family-v1"


def _option_dimensions(*, strike: str = "100") -> dict[str, object]:
    return {
        "underlying_canonical_id": "instrument:futures:cn:IF",
        "contract_canonical_id": f"instrument:option:cn:IF2610C{strike}",
        "expiry": "2026-10-30",
        "strike": strike,
        "right": "call",
    }


@pytest.mark.parametrize(
    ("family_id", "expected_kind", "expected_fields"),
    [
        (
            "futures.inventory",
            "report",
            ("report_date", "location", "warehouse", "commodity"),
        ),
        (
            "option.derivative",
            "slice",
            (
                "underlying_canonical_id",
                "contract_canonical_id",
                "expiry",
                "strike",
                "right",
            ),
        ),
        (
            "option.risk_surface",
            "slice",
            ("underlying_canonical_id", "expiry", "moneyness", "model_version"),
        ),
        (
            "crypto.cme_position",
            "report",
            ("report_date", "reporting_entity", "rank", "report_type"),
        ),
    ],
)
def test_b2_family_contracts_declare_the_reviewed_record_shape(
    family_id: str,
    expected_kind: str,
    expected_fields: tuple[str, ...],
) -> None:
    """The generic normalizer cannot replace a reviewed family dictionary."""
    contract = get_b2_family_contract(family_id, CONTRACT_VERSION)

    assert contract.selector_kind == expected_kind
    assert contract.record_dimension_fields == expected_fields


def test_b2_family_contracts_match_the_unconfigured_dataset_dimension_declarations() -> None:
    """The internal dictionary and public-disabled registry cannot drift apart."""
    dataset_contracts = {
        contract.family_id: contract for contract in dataset_contracts_module._CONTRACTS
    }
    for family_id in (
        "futures.inventory",
        "option.derivative",
        "option.risk_surface",
        "crypto.cme_position",
    ):
        family_contract = get_b2_family_contract(family_id, CONTRACT_VERSION)
        dataset_contract = dataset_contracts[family_id]
        assert dataset_contract.status == "unconfigured"
        assert dataset_contract.field_profile.dimension_fields == (
            family_contract.record_dimension_fields
        )


def test_option_contract_rejects_missing_extra_and_wrong_typed_dimensions() -> None:
    """Every B2 fact must name the exact reviewed option coordinate."""
    contract = get_b2_family_contract("option.derivative", CONTRACT_VERSION)
    missing = _option_dimensions()
    del missing["right"]
    extra = {**_option_dimensions(), "alias": "IF"}
    wrong_type = _option_dimensions()
    wrong_type["strike"] = 100

    for dimensions in (missing, extra, wrong_type):
        with pytest.raises(B2FamilyContractError, match="B2_RECORD_DIMENSIONS_INVALID"):
            contract.normalize_record_dimensions(dimensions)


def test_option_contract_preserves_exact_decimal_text_without_strike_rounding() -> None:
    """Different source lexical dimensions remain distinct instead of being guessed equal."""
    first = issue_b2_selector(
        family_id="option.derivative",
        family_contract_version=CONTRACT_VERSION,
        selector_dimensions={
            "underlying_canonical_id": "instrument:futures:cn:IF",
            "expiry": "2026-10-30",
        },
        expected_record_dimensions=(_option_dimensions(strike="100"),),
    )
    second = issue_b2_selector(
        family_id="option.derivative",
        family_contract_version=CONTRACT_VERSION,
        selector_dimensions={
            "underlying_canonical_id": "instrument:futures:cn:IF",
            "expiry": "2026-10-30",
        },
        expected_record_dimensions=(_option_dimensions(strike="100.0"),),
    )

    assert isinstance(first, B2SliceSelector)
    assert isinstance(second, B2SliceSelector)
    assert first.expected_record_key_sha256s != second.expected_record_key_sha256s


def test_issuer_derives_exact_expected_keys_and_rejects_out_of_selector_dimensions() -> None:
    """A caller cannot declare a hash set unrelated to its reviewed slice."""
    selector = issue_b2_selector(
        family_id="option.derivative",
        family_contract_version=CONTRACT_VERSION,
        selector_dimensions={
            "underlying_canonical_id": "instrument:futures:cn:IF",
            "expiry": "2026-10-30",
        },
        expected_record_dimensions=(
            _option_dimensions(strike="100"),
            _option_dimensions(strike="105"),
        ),
    )

    assert isinstance(selector, B2SliceSelector)
    assert selector.expected_record_key_sha256s is not None
    assert len(selector.expected_record_key_sha256s) == 2

    mismatch = _option_dimensions()
    mismatch["expiry"] = "2026-11-27"
    with pytest.raises(B2FamilyContractError, match="B2_MANIFEST_SELECTOR_MISMATCH"):
        issue_b2_selector(
            family_id="option.derivative",
            family_contract_version=CONTRACT_VERSION,
            selector_dimensions={
                "underlying_canonical_id": "instrument:futures:cn:IF",
                "expiry": "2026-10-30",
            },
            expected_record_dimensions=(mismatch,),
        )


def test_report_contract_requires_positive_integer_rank_and_issues_a_report_selector() -> None:
    """CME report ranks cannot be a boolean, string, or zero-value alias."""
    contract = get_b2_family_contract("crypto.cme_position", CONTRACT_VERSION)
    dimensions = {
        "report_date": "2026-09-11",
        "reporting_entity": "dealer",
        "rank": 0,
        "report_type": "futures_only",
    }
    with pytest.raises(B2FamilyContractError, match="B2_RECORD_DIMENSIONS_INVALID"):
        contract.normalize_record_dimensions(dimensions)

    valid = {**dimensions, "rank": 1}
    selector = issue_b2_selector(
        family_id="crypto.cme_position",
        family_contract_version=CONTRACT_VERSION,
        selector_dimensions={"report_date": "2026-09-11", "report_type": "futures_only"},
        expected_record_dimensions=(valid,),
    )

    assert isinstance(selector, B2ReportSelector)


def test_unknown_family_or_version_and_empty_selector_fail_closed() -> None:
    """Internal contracts cannot be widened through unreviewed family inputs."""
    with pytest.raises(B2FamilyContractError, match="B2_FAMILY_CONTRACT_UNSUPPORTED"):
        get_b2_family_contract("option.derivative", "market-data-family-v2")

    with pytest.raises(B2FamilyContractError, match="B2_SELECTOR_DIMENSIONS_INVALID"):
        issue_b2_selector(
            family_id="futures.inventory",
            family_contract_version=CONTRACT_VERSION,
            selector_dimensions={},
            expected_record_dimensions=(),
        )
