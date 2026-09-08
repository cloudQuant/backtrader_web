"""Deterministic contracts for Iteration 197 coverage planning."""

from dataclasses import replace
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.services.market_data.coverage import (
    CalendarSnapshot,
    CoveragePlanner,
    CoverageStatus,
    EventKey,
    GapPosition,
    Observation,
    ObservationQuality,
    QueryIdentity,
    TimeWindow,
)

UTC = timezone.utc


def _at(hour: int, *, tz: timezone | ZoneInfo = UTC) -> datetime:
    return datetime(2026, 1, 5, hour, tzinfo=tz)


def _identity(*, canonical_id: str = "stock:CN:600000") -> QueryIdentity:
    return QueryIdentity(
        dataset_code="market.stock_daily",
        canonical_id=canonical_id,
        asset_type="stock",
        instrument_metadata_version="instrument-v1",
        data_kind="bars",
        market="CN",
        frequency="1d",
        source_policy_id="market-default-v1",
        adjustment="qfq",
        price_basis="close",
        currency="CNY",
        unit="share",
    )


def _observation(
    event_at: datetime,
    *,
    identity: QueryIdentity | None = None,
    fields: dict[str, object] | None = None,
    quality: ObservationQuality = ObservationQuality.PASS,
    available_at: datetime | None = None,
) -> Observation:
    return Observation(
        identity=identity or _identity(),
        event_key=EventKey(event_at),
        fields={"close": 10.25} if fields is None else fields,
        quality=quality,
        available_at=available_at or _at(17),
    )


def test_planner_returns_precise_head_middle_and_tail_gaps() -> None:
    """Gap runs follow calendar adjacency, not calendar-day arithmetic."""
    query = _identity()
    window = TimeWindow(start_at=_at(9), end_at=_at(16))
    calendar = CalendarSnapshot(
        calendar_id="XSHG",
        calendar_version="2026.01",
        timezone_name="Asia/Shanghai",
        coverage_window=window,
        event_keys=tuple(EventKey(_at(hour)) for hour in range(9, 16)),
        status="known",
    )

    plan = CoveragePlanner().plan(
        query=query,
        window=window,
        calendar=calendar,
        observations=(_observation(_at(10)), _observation(_at(11)), _observation(_at(14))),
        required_fields=frozenset({"close"}),
        as_of=_at(23),
    )

    assert plan.status is CoverageStatus.INCOMPLETE
    assert [gap.position for gap in plan.gaps] == [
        GapPosition.HEAD,
        GapPosition.MIDDLE,
        GapPosition.TAIL,
    ]
    assert [[key.event_at.hour for key in gap.event_keys] for gap in plan.gaps] == [
        [9],
        [12, 13],
        [15],
    ]
    assert [
        (gap.fetch_window.start_at.hour, gap.fetch_window.end_at.hour) for gap in plan.gaps
    ] == [(9, 10), (12, 14), (15, 16)]
    assert [key.event_at.hour for key in plan.accepted_event_keys] == [10, 11, 14]


def test_planner_accepts_only_identity_fields_quality_and_pit_eligible_observations() -> None:
    """A row cannot make coverage complete unless every eligibility rule passes."""
    query = _identity()
    window = TimeWindow(start_at=_at(9), end_at=_at(14))
    calendar = CalendarSnapshot(
        calendar_id="XSHG",
        calendar_version="2026.01",
        timezone_name="Asia/Shanghai",
        coverage_window=window,
        event_keys=tuple(EventKey(_at(hour)) for hour in range(9, 14)),
        status="known",
    )

    plan = CoveragePlanner().plan(
        query=query,
        window=window,
        calendar=calendar,
        observations=(
            _observation(_at(9), identity=_identity(canonical_id="stock:CN:000001")),
            _observation(_at(10), fields={"open": 10.0}),
            _observation(_at(11), quality=ObservationQuality.FAILED),
            _observation(_at(12), available_at=_at(23)),
            _observation(_at(13), available_at=_at(17)),
        ),
        required_fields=frozenset({"close"}),
        as_of=_at(18),
    )

    assert plan.status is CoverageStatus.INCOMPLETE
    assert [key.event_at.hour for key in plan.accepted_event_keys] == [13]
    assert [key.event_at.hour for key in plan.missing_event_keys] == [9, 10, 11, 12]
    assert plan.rejection_counts == {
        "identity_mismatch": 1,
        "missing_required_fields": 1,
        "quality_ineligible": 1,
        "not_available_at_cutoff": 1,
    }


def test_unknown_calendar_returns_a_typed_unknown_status_instead_of_complete() -> None:
    """A lack of calendar evidence cannot be reported as empty complete coverage."""
    plan = CoveragePlanner().plan(
        query=_identity(),
        window=TimeWindow(start_at=_at(9), end_at=_at(10)),
        calendar=CalendarSnapshot.unknown(
            calendar_id="XSHG",
            calendar_version="2026.01",
            timezone_name="Asia/Shanghai",
            reason="calendar_source_not_loaded",
        ),
        observations=(),
        required_fields=frozenset({"close"}),
        as_of=_at(23),
    )

    assert plan.status is CoverageStatus.UNKNOWN_CALENDAR
    assert plan.expected_event_keys == ()
    assert plan.accepted_event_keys == ()
    assert plan.gaps == ()
    assert plan.calendar_reason == "calendar_source_not_loaded"


def test_empty_default_calendar_cannot_prove_complete_coverage() -> None:
    """An unpopulated calendar declaration is unknown, not an empty trading session."""
    window = TimeWindow(start_at=_at(9), end_at=_at(10))
    calendar = CalendarSnapshot(
        calendar_id="XSHG",
        calendar_version="2026.01",
        timezone_name="Asia/Shanghai",
    )

    plan = CoveragePlanner().plan(
        query=_identity(),
        window=window,
        calendar=calendar,
        observations=(),
        required_fields=frozenset({"close"}),
        as_of=_at(23),
    )

    assert plan.status is CoverageStatus.UNKNOWN_CALENDAR


def test_known_calendar_outside_its_evidence_window_is_unknown() -> None:
    """A partial calendar fetch cannot assert completeness for a wider request."""
    narrow_window = TimeWindow(start_at=_at(9), end_at=_at(10))
    requested_window = TimeWindow(start_at=_at(9), end_at=_at(11))
    calendar = CalendarSnapshot(
        calendar_id="XSHG",
        calendar_version="2026.01",
        timezone_name="Asia/Shanghai",
        coverage_window=narrow_window,
        event_keys=(EventKey(_at(9)),),
        status="known",
    )

    plan = CoveragePlanner().plan(
        query=_identity(),
        window=requested_window,
        calendar=calendar,
        observations=(),
        required_fields=frozenset({"close"}),
        as_of=_at(23),
    )

    assert plan.status is CoverageStatus.UNKNOWN_CALENDAR
    assert plan.calendar_reason == "calendar_window_not_covered"


def test_calendar_expected_events_use_a_half_open_utc_window() -> None:
    """Timezone-aware timestamps are normalized, with end_at excluded."""
    new_york = ZoneInfo("America/New_York")
    window = TimeWindow(start_at=_at(14), end_at=_at(16))
    calendar = CalendarSnapshot(
        calendar_id="NYSE",
        calendar_version="2026.01",
        timezone_name="America/New_York",
        coverage_window=window,
        event_keys=(
            EventKey(_at(8, tz=new_york)),  # 13:00 UTC: before the window
            EventKey(_at(9, tz=new_york)),  # 14:00 UTC: inclusive start
            EventKey(_at(10, tz=new_york)),  # 15:00 UTC
            EventKey(_at(11, tz=new_york)),  # 16:00 UTC: exclusive end
        ),
        status="known",
    )

    plan = CoveragePlanner().plan(
        query=_identity(),
        window=window,
        calendar=calendar,
        observations=(_observation(_at(14)), _observation(_at(15))),
        required_fields=frozenset({"close"}),
        as_of=_at(23),
    )

    assert plan.status is CoverageStatus.COMPLETE
    assert [key.event_at.hour for key in plan.expected_event_keys] == [14, 15]
    assert all(key.event_at.tzinfo is UTC for key in plan.expected_event_keys)


def test_naive_time_is_rejected_at_the_coverage_boundary() -> None:
    """The planner never silently treats a naive timestamp as UTC."""
    with pytest.raises(ValueError, match="timezone-aware"):
        TimeWindow(
            start_at=datetime(2026, 1, 5, 9),
            end_at=datetime(2026, 1, 5, 10, tzinfo=UTC),
        )


def test_planner_rejects_observations_collected_under_a_different_source_policy() -> None:
    """A source-policy change cannot reuse records as policy-equivalent coverage."""
    query = _identity()
    window = TimeWindow(start_at=_at(9), end_at=_at(10))
    calendar = CalendarSnapshot(
        calendar_id="XSHG",
        calendar_version="2026.01",
        timezone_name="Asia/Shanghai",
        coverage_window=window,
        event_keys=(EventKey(_at(9)),),
        status="known",
    )
    foreign_policy = replace(query, source_policy_id="market-premium-v2")

    plan = CoveragePlanner().plan(
        query=query,
        window=window,
        calendar=calendar,
        observations=(_observation(_at(9), identity=foreign_policy),),
        required_fields=frozenset({"close"}),
        as_of=_at(23),
    )

    assert plan.status is CoverageStatus.INCOMPLETE
    assert plan.rejection_counts == {"identity_mismatch": 1}
