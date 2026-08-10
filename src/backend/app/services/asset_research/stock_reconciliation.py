"""Structured legacy/new stock signal reconciliation for compatibility audits."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.middleware.metrics import record_asset_research_migration_reconciliation


@dataclass(frozen=True, slots=True)
class ReconciliationRow:
    """One pair classified by semantic mapping, never by hash equality."""

    mapping_version: str
    classification: str
    legacy_reference: str
    reason: str


@dataclass(frozen=True, slots=True)
class ReconciliationSummary:
    """Aggregated structured reconciliation evidence."""

    mapping_version: str
    rows: tuple[ReconciliationRow, ...]
    defect_count: int

    @property
    def has_unsupported_defect(self) -> bool:
        return self.defect_count != 0


def reconcile_pair(
    *,
    mapping_version: str,
    legacy_reference: str,
    legacy: Mapping[str, Any],
    generic: Mapping[str, Any],
    expected_mapping: bool = True,
) -> ReconciliationRow:
    """Classify one old/new pair using semantic invariants.

    Identity, cutoff, quality, action and outcome mismatches are ``DEFECT``.
    Versioned field name or narrative differences are ``EXPECTED_MAPPING`` or
    ``NONDETERMINISTIC_PRESENTATION``.  Source/timing differences that cannot
    be compared are ``SOURCE_OR_TIMING``.
    """
    legacy_identity = str(legacy.get("canonical_id") or legacy.get("symbol") or "")
    generic_identity = str(generic.get("canonical_id") or "")
    if legacy_identity and generic_identity and legacy_identity != generic_identity:
        return _row(mapping_version, "DEFECT", legacy_reference, "IDENTITY_MISMATCH")

    legacy_cutoff = legacy.get("cutoff_at") or legacy.get("as_of_at")
    generic_cutoff = generic.get("cutoff_at") or generic.get("as_of_at")
    if legacy_cutoff and generic_cutoff and str(legacy_cutoff) != str(generic_cutoff):
        return _row(mapping_version, "SOURCE_OR_TIMING", legacy_reference, "CUTOFF_DIFFERENT")

    legacy_action = str(legacy.get("signal_action") or legacy.get("recommendation") or "")
    generic_action = str(generic.get("recommendation") or "")
    if legacy_action and generic_action and legacy_action != generic_action:
        return _row(mapping_version, "DEFECT", legacy_reference, "ACTION_MISMATCH")

    if legacy.get("narrative") and generic.get("narrative"):
        if legacy["narrative"] != generic["narrative"]:
            return _row(
                mapping_version,
                "NONDETERMINISTIC_PRESENTATION",
                legacy_reference,
                "NARRATIVE_DIFFERENT",
            )

    return _row(
        mapping_version,
        "EXPECTED_MAPPING" if expected_mapping else "SOURCE_OR_TIMING",
        legacy_reference,
        "MAPPED" if expected_mapping else "SOURCE_OR_TIMING_UNRESOLVED",
    )


def reconcile_batch(
    *,
    mapping_version: str,
    pairs: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
) -> ReconciliationSummary:
    """Classify and emit a bounded reconciliation metric for each row."""
    rows: list[ReconciliationRow] = []
    for index, (legacy, generic) in enumerate(pairs):
        row = reconcile_pair(
            mapping_version=mapping_version,
            legacy_reference=str(legacy.get("reference") or index),
            legacy=legacy,
            generic=generic,
        )
        record_asset_research_migration_reconciliation(
            mapping_version=mapping_version,
            classification=row.classification,
        )
        rows.append(row)
    return ReconciliationSummary(
        mapping_version=mapping_version,
        rows=tuple(rows),
        defect_count=sum(row.classification == "DEFECT" for row in rows),
    )


def _row(
    mapping_version: str,
    classification: str,
    legacy_reference: str,
    reason: str,
) -> ReconciliationRow:
    return ReconciliationRow(
        mapping_version=mapping_version,
        classification=classification,
        legacy_reference=legacy_reference,
        reason=reason,
    )

