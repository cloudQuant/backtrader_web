"""Fail-closed completeness contracts for Iteration 197 B2 local records."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.market_data.multi_record import (
    B2ReportSelector,
    B2SliceSelector,
    CompletenessStatus,
    ReportCompletenessPlanner,
    SliceCompletenessPlanner,
    ZeroRecordCertificate,
    normalize_semantic_record_key,
)

_EVIDENCE_SHA256 = "f" * 64


def _event(hour: int) -> datetime:
    return datetime(2026, 9, 11, hour, tzinfo=timezone.utc)


def _key(contract: str) -> str:
    return normalize_semantic_record_key(
        family_id="option.derivative",
        family_contract_version="market-data-family-v1",
        dimensions={
            "underlying": "IF",
            "expiry": "2026-10-30",
            "contract": contract,
            "right": "call",
        },
    ).sha256


def _report_key(warehouse: str) -> str:
    return normalize_semantic_record_key(
        family_id="futures.inventory",
        family_contract_version="market-data-family-v1",
        dimensions={"report_date": "2026-09-11", "commodity": "IF", "warehouse": warehouse},
    ).sha256


def _slice_selector(*, expected: object) -> B2SliceSelector:
    return B2SliceSelector(
        family_id="option.derivative",
        family_contract_version="market-data-family-v1",
        selector_dimensions={"underlying": "IF", "expiry": "2026-10-30"},
        expected_record_key_sha256s=expected,
    )


def _report_selector(*, expected: object) -> B2ReportSelector:
    return B2ReportSelector(
        family_id="futures.inventory",
        family_contract_version="market-data-family-v1",
        selector_dimensions={"report_date": "2026-09-11", "commodity": "IF"},
        expected_record_key_sha256s=expected,
    )


def test_slice_completeness_requires_the_exact_declared_record_set() -> None:
    """A complete option slice has every expected key exactly once."""
    front = _key("IF2610C100")
    back = _key("IF2610C105")
    selector = _slice_selector(expected=frozenset({front, back}))

    result = SliceCompletenessPlanner().plan(
        selector=selector,
        observed_record_key_sha256s=(back, front),
    )

    assert result.status is CompletenessStatus.COMPLETE
    assert result.is_complete is True
    assert result.reason_codes == ()
    assert result.missing_record_key_sha256s == frozenset()
    assert result.duplicate_record_key_sha256s == frozenset()
    assert result.unexpected_record_key_sha256s == frozenset()


def test_slice_completeness_fails_closed_for_missing_duplicate_and_out_of_slice_rows() -> None:
    """One same-time row never proves an option slice is complete."""
    front = _key("IF2610C100")
    back = _key("IF2610C105")
    outsider = _key("IF2610C110")
    selector = _slice_selector(expected=frozenset({front, back}))

    result = SliceCompletenessPlanner().plan(
        selector=selector,
        observed_record_key_sha256s=(front, front, outsider),
    )

    assert result.status is CompletenessStatus.INCOMPLETE
    assert result.is_complete is False
    assert result.missing_record_key_sha256s == frozenset({back})
    assert result.duplicate_record_key_sha256s == frozenset({front})
    assert result.unexpected_record_key_sha256s == frozenset({outsider})
    assert set(result.reason_codes) == {
        "DUPLICATE_RECORD_KEY",
        "MISSING_RECORD_KEY",
        "UNEXPECTED_RECORD_KEY",
    }


def test_slice_completeness_rejects_undeclared_expected_or_empty_record_sets() -> None:
    """Neither an absent manifest nor a bare empty response is coverage proof."""
    undeclared = _slice_selector(expected=None)
    declared_empty = _slice_selector(expected=frozenset())
    planner = SliceCompletenessPlanner()

    no_manifest = planner.plan(selector=undeclared, observed_record_key_sha256s=())
    bare_empty = planner.plan(selector=declared_empty, observed_record_key_sha256s=())

    assert no_manifest.status is CompletenessStatus.INCOMPLETE
    assert no_manifest.reason_codes == ("EXPECTED_RECORD_SET_UNDECLARED",)
    assert bare_empty.status is CompletenessStatus.INCOMPLETE
    assert bare_empty.reason_codes == ("EMPTY_RESULT_UNDECLARED",)


def test_slice_empty_response_requires_a_matching_explicit_certificate() -> None:
    """A zero-record provider result must be bound to the exact requested slice."""
    selector = _slice_selector(expected=frozenset())
    matching = ZeroRecordCertificate(
        selector_digest=selector.selector_digest,
        event_at=_event(10),
        evidence_sha256=_EVIDENCE_SHA256,
    )
    mismatched = ZeroRecordCertificate(
        selector_digest="0" * 64,
        event_at=_event(10),
        evidence_sha256=_EVIDENCE_SHA256,
    )
    planner = SliceCompletenessPlanner()

    complete = planner.plan(
        selector=selector,
        observed_record_key_sha256s=(),
        zero_record_certificate=matching,
        event_at=_event(10),
    )
    incomplete = planner.plan(
        selector=selector,
        observed_record_key_sha256s=(),
        zero_record_certificate=mismatched,
        event_at=_event(10),
    )

    assert complete.status is CompletenessStatus.COMPLETE
    assert complete.zero_record_certificate_used is True
    assert incomplete.status is CompletenessStatus.INCOMPLETE
    assert incomplete.reason_codes == ("ZERO_RECORD_CERTIFICATE_SELECTOR_MISMATCH",)


def test_zero_record_certificate_cannot_be_reused_for_another_event_or_without_event_binding() -> (
    None
):
    """A zero result is a statement about one snapshot/report instant only."""
    selector = _slice_selector(expected=frozenset())
    certificate = ZeroRecordCertificate(
        selector_digest=selector.selector_digest,
        event_at=_event(10),
        evidence_sha256=_EVIDENCE_SHA256,
    )
    planner = SliceCompletenessPlanner()

    no_event = planner.plan(
        selector=selector,
        observed_record_key_sha256s=(),
        zero_record_certificate=certificate,
    )
    another_event = planner.plan(
        selector=selector,
        observed_record_key_sha256s=(),
        zero_record_certificate=certificate,
        event_at=_event(11),
    )

    assert no_event.status is CompletenessStatus.INCOMPLETE
    assert no_event.reason_codes == ("ZERO_RECORD_CERTIFICATE_EVENT_UNBOUND",)
    assert another_event.status is CompletenessStatus.INCOMPLETE
    assert another_event.reason_codes == ("ZERO_RECORD_CERTIFICATE_EVENT_MISMATCH",)


def test_report_completeness_uses_the_same_exact_set_rule_without_domain_inference() -> None:
    """Inventory/CME reports must carry their approved expected record manifest."""
    warehouse_a = _report_key("warehouse-a")
    warehouse_b = _report_key("warehouse-b")
    selector = _report_selector(expected=frozenset({warehouse_a, warehouse_b}))

    result = ReportCompletenessPlanner().plan(
        selector=selector,
        observed_record_key_sha256s=(warehouse_a,),
    )

    assert result.status is CompletenessStatus.INCOMPLETE
    assert result.missing_record_key_sha256s == frozenset({warehouse_b})
    assert result.reason_codes == ("MISSING_RECORD_KEY",)


def test_planner_rejects_wrong_selector_type_and_duplicate_manifest_entries() -> None:
    """Slice/report planners cannot be silently interchanged or deduplicated."""
    report = _report_selector(expected=frozenset({_report_key("warehouse-a")}))
    with pytest.raises(TypeError, match="B2SliceSelector"):
        SliceCompletenessPlanner().plan(selector=report, observed_record_key_sha256s=())

    key = _key("IF2610C100")
    with pytest.raises(ValueError, match="duplicate"):
        _slice_selector(expected=(key, key))


def test_selector_digest_is_canonical_and_binds_the_expected_manifest() -> None:
    """A zero certificate cannot survive a selector or expected-set change."""
    front = _key("IF2610C100")
    back = _key("IF2610C105")
    left = B2SliceSelector(
        family_id="option.derivative",
        family_contract_version="market-data-family-v1",
        selector_dimensions={"underlying": "IF", "expiry": "2026-10-30"},
        expected_record_key_sha256s=(front, back),
    )
    reordered = B2SliceSelector(
        family_id="option.derivative",
        family_contract_version="market-data-family-v1",
        selector_dimensions={"expiry": "2026-10-30", "underlying": "IF"},
        expected_record_key_sha256s=(back, front),
    )
    changed_manifest = B2SliceSelector(
        family_id="option.derivative",
        family_contract_version="market-data-family-v1",
        selector_dimensions={"underlying": "IF", "expiry": "2026-10-30"},
        expected_record_key_sha256s=(front,),
    )

    assert left.selector_digest == reordered.selector_digest
    assert left.selector_digest != changed_manifest.selector_digest


def test_selector_manifest_accepts_a_large_bounded_multi_record_slice() -> None:
    """Completeness manifests are not constrained by the small single-key size cap."""
    expected = frozenset(f"{index:064x}" for index in range(250))
    selector = _slice_selector(expected=expected)

    result = SliceCompletenessPlanner().plan(
        selector=selector,
        observed_record_key_sha256s=expected,
    )

    assert result.status is CompletenessStatus.COMPLETE


def test_selector_manifest_rejects_more_than_the_declared_provider_batch_bound() -> None:
    """The separate large-manifest allowance remains explicitly bounded."""
    with pytest.raises(ValueError, match="50000"):
        _slice_selector(expected=(f"{index:064x}" for index in range(50_001)))
