"""Pure coverage contracts for locally persisted quote snapshots."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.market_data.coverage import (
    EventKey,
    Observation,
    ObservationQuality,
    QueryIdentity,
    SnapshotCoveragePlanner,
    TimeWindow,
)

UTC = timezone.utc


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 9, 8, hour, minute, tzinfo=UTC)


def _identity(*, canonical_id: str = "instrument:stock:CN-SSE:600000") -> QueryIdentity:
    return QueryIdentity(
        dataset_code="market.quote_snapshot",
        canonical_id=canonical_id,
        asset_type="stock",
        instrument_metadata_version="stock-v1",
        data_kind="quote_snapshot",
        market="CN-SSE",
        frequency="snapshot",
        source_policy_id="market-default-v1",
        adjustment=None,
        price_basis=None,
        currency="CNY",
        unit="share",
    )


def _observation(
    *,
    event_at: datetime,
    identity: QueryIdentity | None = None,
    fields: dict[str, object] | None = None,
    available_at: datetime | None = None,
) -> Observation:
    return Observation(
        identity=identity or _identity(),
        event_key=EventKey(event_at),
        available_at=available_at or event_at,
        quality=ObservationQuality.PASS,
        fields=fields or {"price": 10.5},
    )


def test_snapshot_coverage_accepts_a_recent_exact_local_observation() -> None:
    """A quote needs an exact usable local row, not a fabricated calendar grid."""
    window = TimeWindow(start_at=_at(11), end_at=_at(12, 1))

    plan = SnapshotCoveragePlanner().plan(
        query=_identity(),
        window=window,
        observations=(_observation(event_at=_at(12)),),
        required_fields=frozenset({"price"}),
        as_of=_at(12, 1),
        max_age=timedelta(minutes=15),
    )

    assert plan.status.value == "complete"
    assert plan.coverage_ratio == 1.0
    assert plan.missing_event_keys == ()
    assert plan.gaps == ()


def test_snapshot_coverage_returns_one_full_window_gap_for_a_stale_quote() -> None:
    """A stale local quote must request a bounded refresh instead of claiming coverage."""
    window = TimeWindow(start_at=_at(11), end_at=_at(12, 1))

    plan = SnapshotCoveragePlanner().plan(
        query=_identity(),
        window=window,
        observations=(_observation(event_at=_at(11)),),
        required_fields=frozenset({"price"}),
        as_of=_at(12, 1),
        max_age=timedelta(minutes=15),
    )

    assert plan.status.value == "incomplete"
    assert plan.coverage_ratio == 0.0
    assert [(gap.fetch_window.start_at, gap.fetch_window.end_at) for gap in plan.gaps] == [
        (_at(11), _at(12, 1))
    ]
    assert dict(plan.rejection_counts) == {"stale": 1}


def test_snapshot_coverage_rejects_nearby_identity_even_when_it_is_fresh() -> None:
    """A fresh quote for another instrument cannot satisfy an exact request."""
    window = TimeWindow(start_at=_at(11), end_at=_at(12, 1))

    plan = SnapshotCoveragePlanner().plan(
        query=_identity(),
        window=window,
        observations=(
            _observation(
                event_at=_at(12),
                identity=_identity(canonical_id="instrument:stock:CN-SSE:600519"),
            ),
        ),
        required_fields=frozenset({"price"}),
        as_of=_at(12, 1),
        max_age=timedelta(minutes=15),
    )

    assert plan.status.value == "incomplete"
    assert dict(plan.rejection_counts) == {"identity_mismatch": 1}
