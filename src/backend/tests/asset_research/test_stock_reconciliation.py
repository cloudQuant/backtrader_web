"""Structured stock signal reconciliation contracts."""

from app.services.asset_research.stock_reconciliation import reconcile_batch, reconcile_pair


def test_reconcile_pair_flags_identity_and_action_defects() -> None:
    identity_defect = reconcile_pair(
        mapping_version="stock-legacy-map-v1",
        legacy_reference="legacy-1",
        legacy={"canonical_id": "stock:A:CNY", "recommendation": "BUY"},
        generic={"canonical_id": "stock:B:CNY", "recommendation": "BUY"},
    )
    action_defect = reconcile_pair(
        mapping_version="stock-legacy-map-v1",
        legacy_reference="legacy-2",
        legacy={"canonical_id": "stock:A:CNY", "recommendation": "BUY"},
        generic={"canonical_id": "stock:A:CNY", "recommendation": "SELL"},
    )

    assert identity_defect.classification == "DEFECT"
    assert action_defect.classification == "DEFECT"


def test_reconcile_pair_allows_narrative_differences() -> None:
    row = reconcile_pair(
        mapping_version="stock-legacy-map-v1",
        legacy_reference="legacy-3",
        legacy={
            "canonical_id": "stock:A:CNY",
            "recommendation": "BUY",
            "narrative": "legacy wording",
        },
        generic={
            "canonical_id": "stock:A:CNY",
            "recommendation": "BUY",
            "narrative": "new wording",
        },
    )

    assert row.classification == "NONDETERMINISTIC_PRESENTATION"


def test_reconcile_batch_reports_defect_count() -> None:
    summary = reconcile_batch(
        mapping_version="stock-legacy-map-v1",
        pairs=[
            (
                {"reference": "r1", "canonical_id": "stock:A:CNY", "recommendation": "BUY"},
                {"canonical_id": "stock:A:CNY", "recommendation": "BUY"},
            ),
            (
                {"reference": "r2", "canonical_id": "stock:A:CNY", "recommendation": "BUY"},
                {"canonical_id": "stock:A:CNY", "recommendation": "SELL"},
            ),
        ],
    )

    assert summary.defect_count == 1
    assert summary.has_unsupported_defect is True

